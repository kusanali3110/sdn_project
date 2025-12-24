import os
import time
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.ofproto import ofproto_v1_3
from ryu.lib.packet import packet
from ryu.lib.packet import packet_base
from ryu.lib.packet import ethernet
from ryu.lib.packet import ether_types
from ryu.lib.packet import ipv4
from ryu.lib.packet import arp
from ryu.lib.packet import icmp
from ryu.lib.packet import tcp
from ryu.lib.packet import udp
from ryu.lib.packet import in_proto
from ryu.app.ofctl.api import get_datapath
from ryu.lib import hub
from base_switch import BaseSwitch
from utils import Network
from metrics_exporter import SDNMetricsExporter

# Tên các giao thức
ETHERNET = ethernet.ethernet.__name__
# VLAN = vlan.vlan.__name__
IPV4 = ipv4.ipv4.__name__
ARP = arp.arp.__name__
ICMP = icmp.icmp.__name__
TCP = tcp.tcp.__name__
UDP = udp.udp.__name__

# Các hằng số
ENTRY_TABLE = 0
LOCAL_TABLE = 0
REMOTE_TABLE = 1

MIN_PRIORITY = 0
LOW_PRIORITY = 100
MID_PRIORITY = 300

# Đặt idle_time=0 để flow entries không bị xóa
LONG_IDLE_TIME = 60
MID_IDLE_TIME = 40
IDLE_TIME = 30


class SpineLeaf3(BaseSwitch):
    """
    Controller cho spine-leaf topology với hai bảng sử dụng mô tả mạng tĩnh.
    """

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Tạo bảng MAC chính
        self.mac_table = {}
        
        # Theo dõi số lượng flow entries cho mỗi switch và bảng
        self.flow_entries_count = {}
        
        # Khởi tạo Prometheus metrics exporter
        metrics_port = int(os.environ.get("METRICS_PORT", 8000))
        self.metrics = SDNMetricsExporter(port=metrics_port)
        self.metrics.start_server()
        
        # Khởi tạo metrics topo
        self.metrics.update_switch_count('spine', len(net.spines))
        self.metrics.update_switch_count('leaf', len(net.leaves))
        
        # Bắt đầu thread thu thập flow stats theo chu kỳ
        self.flow_stats_interval = 10  # Request flow stats every 10 seconds
        self.monitor_thread = hub.spawn(self._monitor_flow_stats)
        
        self.logger.info(f"Metrics exporter started on port {metrics_port}")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, event):
        """
        Phương thức này được gọi sau khi controller cấu hình một switch.
        """

        datapath = event.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Cập nhật metrics trạng thái switch
        switch_type = 'leaf' if datapath.id in net.leaves else 'spine'
        self.metrics.update_switch_status(datapath.id, switch_type, 1)

        # Tạo message để xóa tất cả flow entries hiện có
        msgs = [self.del_flow(datapath)]
        self.metrics.increment_flow_mod(datapath.id, 'delete')

        # Đặt Match là ANY
        match = parser.OFPMatch()

        if datapath.id in net.leaves:  # Với tất cả switch leaf
            # Thêm entry table-miss cho LOCAL_TABLE:
            # Packet khớp được gửi đến bảng tiếp theo
            inst = [parser.OFPInstructionGotoTable(REMOTE_TABLE)]
            msgs += [self.add_flow(datapath, LOCAL_TABLE, MIN_PRIORITY, match, inst)]
            self.metrics.increment_flow_mod(datapath.id, 'add')

            # Thêm entry table-miss cho REMOTE_TABLE:
            # Packet khớp được flood và gửi đến controller
            actions = [
                parser.OFPActionOutput(ofproto.OFPP_ALL),
                parser.OFPActionOutput(
                    ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER
                ),
            ]
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
            msgs += [self.add_flow(datapath, REMOTE_TABLE, MIN_PRIORITY, match, inst)]
            self.metrics.increment_flow_mod(datapath.id, 'add')

        else:  # Với tất cả switch spine
            # Thêm entry table-miss cho ENTRY_TABLE để drop packets
            msgs += [self.add_flow(datapath, ENTRY_TABLE, MIN_PRIORITY, match, [])]
            self.metrics.increment_flow_mod(datapath.id, 'add')

        # Gửi tất cả messages đến switch
        self.send_messages(datapath, msgs)
        
        # Yêu cầu flow stats để cập nhật metrics
        self.request_flow_stats(datapath)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, event):
        """Xử lý flow stats reply từ switch"""
        datapath = event.msg.datapath
        dpid = datapath.id
        
        # Đếm flows cho mỗi bảng
        table_flows = {}
        for stat in event.msg.body:
            table_id = stat.table_id
            if table_id not in table_flows:
                table_flows[table_id] = 0
            table_flows[table_id] += 1
        
        # Cập nhật metrics cho mỗi bảng
        for table_id, count in table_flows.items():
            self.metrics.update_flow_entries(dpid, table_id, count)
            # Cập nhật tracking local
            self.flow_entries_count[(dpid, table_id)] = count
        
        # Cập nhật bảng với 0 entries
        if dpid in net.leaves:
            for table_id in [LOCAL_TABLE, REMOTE_TABLE]:
                if table_id not in table_flows:
                    self.metrics.update_flow_entries(dpid, table_id, 0)
                    self.flow_entries_count[(dpid, table_id)] = 0
        else:  # switch spine
            if ENTRY_TABLE not in table_flows:
                self.metrics.update_flow_entries(dpid, ENTRY_TABLE, 0)
                self.flow_entries_count[(dpid, ENTRY_TABLE)] = 0

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, event):
        """Xử lý message packet_in.

        Phương thức này được gọi khi nhận được message PacketIn.
        Message này được gửi bởi switch để yêu cầu xử lý packet bởi controller khi xảy ra table miss.
        """
        
        # Bắt đầu đo thời gian cho metrics hiệu suất
        start_time = time.time()

        # Lấy switch gốc từ event
        datapath = event.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Lấy port ingress từ event
        in_port = event.msg.match["in_port"]

        # Lấy packet từ event
        pkt = packet.Packet(event.msg.data)

        # Trích xuất thông tin header từ packet và trả về dưới dạng dictionary
        header_list = dict(
            (p.protocol_name, p)
            for p in pkt.protocols
            if isinstance(p, packet_base.PacketBase)
        )

        # Lấy địa chỉ MAC nguồn và đích từ packet
        eth = header_list[ETHERNET]
        dst = eth.dst
        src = eth.src
        
        # Ghi lại kích thước packet cho metrics băng thông
        packet_size = len(event.msg.data)
        self.metrics.add_bytes_transmitted(datapath.id, 'in', packet_size)

        # Cập nhật bảng MAC và ghi lại metrics
        self.update_mac_table(src, in_port, datapath.id)

        # Switch remote là tất cả switch leaf trừ switch gốc
        remote_switches = list(set(net.leaves) - set([datapath.id]))
        
        # Tăng counter PacketIn
        self.metrics.increment_packet_in(datapath.id, 'table_miss')

        if ARP in header_list:
            # Ghi lại packet ARP
            arp_pkt = header_list[ARP]
            arp_type = 'request' if arp_pkt.opcode == arp.ARP_REQUEST else 'reply'
            self.metrics.increment_arp_packets(datapath.id, arp_type)
            self.metrics.increment_protocol_packet('ARP', datapath.id)
            
            # Gửi packet đến tất cả switch remote để được flood
            for leaf in remote_switches:
                # Lấy datapath object
                dpath = get_datapath(self, leaf)
                msgs = self.forward_packet(
                    dpath, event.msg.data, ofproto.OFPP_CONTROLLER, ofproto.OFPP_ALL
                )
                self.send_messages(dpath, msgs)
                self.metrics.increment_packets_flooded(dpath.id)

        elif IPV4 in header_list:
            # Ghi lại packet IPv4
            self.metrics.increment_protocol_packet('IPv4', datapath.id)
            # Trong switch gốc:

            # Thêm entry flow trong LOCAL_TABLE để chuyển tiếp packet đến port đầu ra nếu địa chỉ MAC đích khớp với địa chỉ MAC nguồn
            match = parser.OFPMatch(eth_dst=src)
            actions = [parser.OFPActionOutput(in_port)]
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
            msgs = [
                self.add_flow(
                    datapath,
                    LOCAL_TABLE,
                    LOW_PRIORITY,
                    match,
                    inst,
                    i_time=LONG_IDLE_TIME,
                )
            ]
            self.send_messages(datapath, msgs)
            self.metrics.increment_flow_mod(datapath.id, 'add')

            # Lấy thông tin layer cao hơn từ packet nếu có
            packet_info = self.get_ipv4_packet_info(pkt, header_list)
            self.logger.info(
                f"Packet Info: {packet_info[0]}, {packet_info[1]} {packet_info[2]}, {packet_info[3]}, {packet_info[4]}"
            )

            packet_type = packet_info[0]
            protocol_name, src_ip, dst_ip, src_port, dst_port = packet_info
            
            # Ghi lại metrics cho giao thức cụ thể
            self.metrics.increment_protocol_packet(protocol_name, datapath.id)
            self.metrics.record_traffic_flow(src_ip, dst_ip, protocol_name)
            
            # Ghi lại metrics cho kết nối TCP/UDP
            if protocol_name == TCP:
                self.metrics.increment_tcp_connection(src_ip, dst_ip, dst_port)
            elif protocol_name == UDP:
                self.metrics.increment_udp_flow(src_ip, dst_ip, dst_port)
            
            dst_host = self.mac_table.get(dst)

            if dst_host:
                # Nếu địa chỉ đích nằm trong bảng MAC

                # Nếu địa chỉ đích được kết nối với một switch remote
                if dst_host["dpid"] in remote_switches:
                    # Chọn một switch spine dựa trên thông tin packet
                    # Switch spine được chọn phải giống nhau trong mỗi hướng
                    spine_id = net.spines[
                        self.select_spine_from_packet_info(packet_info, len(net.spines))
                    ]
                    
                    # Ghi lại selection spine
                    self.metrics.increment_spine_selection(spine_id)

                    # Trong switch gốc,
                    # thêm entry vào REMOTE_TABLE để chuyển tiếp packet
                    # từ nguồn đến đích về phía switch spine

                    # in_port = net.links[datapath.id, spine_id]["port"]
                    upstream_port = net.links[datapath.id, spine_id]["port"]

                    msgs = self.create_match_entry_at_leaf(
                        datapath,
                        REMOTE_TABLE,
                        MID_PRIORITY,
                        IDLE_TIME,
                        packet_info,
                        upstream_port,
                    )
                    self.send_messages(datapath, msgs)
                    self.metrics.increment_flow_mod(datapath.id, 'add')

                    # Trong switch spine,
                    # thêm hai entry để chuyển tiếp packet giữa nguồn và đích trong cả hai hướng

                    spine_datapath = get_datapath(self, spine_id)
                    dst_datapath = get_datapath(self, dst_host["dpid"])
                    spine_ingress_port = net.links[spine_id, datapath.id]["port"]
                    spine_egress_port = net.links[spine_id, dst_datapath.id]["port"]

                    msgs = self.create_match_entry_at_spine(
                        spine_datapath,
                        ENTRY_TABLE,
                        MID_PRIORITY,
                        packet_info,
                        spine_ingress_port,
                        spine_egress_port,
                        MID_IDLE_TIME,
                    )
                    self.send_messages(spine_datapath, msgs)
                    self.metrics.increment_flow_mod(spine_id, 'add')

                    # Trong switch remote,
                    # Gửi packet nhận được đến switch đích để chuyển tiếp.
                    remote_port = dst_host["port"]
                    msgs = self.forward_packet(
                        dst_datapath,
                        event.msg.data,
                        ofproto.OFPP_CONTROLLER,
                        remote_port,
                    )
                    self.send_messages(dst_datapath, msgs)
                    
                    # Ghi lại metrics chuyển tiếp từ xa
                    self.metrics.record_remote_forwarding(datapath.id, dst_host["dpid"], spine_id)
                    self.metrics.increment_packets_forwarded(dst_datapath.id, remote_port)

            else:
                # Nếu địa chỉ đích không nằm trong bảng MAC
                # Gửi packet đến tất cả switch remote để được flood
                for leaf in remote_switches:
                    # Lấy datapath object
                    dpath = get_datapath(self, leaf)
                    msgs = self.forward_packet(
                        dpath, event.msg.data, ofproto.OFPP_CONTROLLER, ofproto.OFPP_ALL
                    )

                    self.send_messages(dpath, msgs)
                    self.metrics.increment_packets_flooded(dpath.id)
        
        # Ghi lại thời gian xử lý packet
        processing_time = time.time() - start_time
        self.metrics.packet_in_processing_time.labels(dpid=datapath.id).observe(processing_time)

    def update_mac_table(self, src, port, dpid):
        """
        Thiết lập/cập nhật thông tin node trong bảng MAC
        bao gồm port ingress và switch ingress
        """

        src_host = self.mac_table.get(src, {})
        
        # Kiểm tra nếu địa chỉ MAC này là mới
        if not src_host:
            self.metrics.record_mac_learned(dpid)
        
        src_host["port"] = port
        src_host["dpid"] = dpid
        self.mac_table[src] = src_host
        
        # Cập nhật kích thước bảng MAC cho metrics
        self.metrics.update_mac_table_size(len(self.mac_table))
        
        return src_host

    def create_match_entry_at_leaf(self, datapath, table, priority, idle_time, packet_info, out_port):
        """
        Tạo entry flow trong bảng MAC cho switch leaf
        bao gồm port đầu ra và thông tin packet
        """

        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Lấy thông tin packet từ packet_info
        protocol, src_ip, dst_ip, src_port, dst_port = packet_info

        # Tạo match cho protocol TCP
        if protocol == TCP:
            match = parser.OFPMatch(
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip,
                ip_proto=in_proto.IPPROTO_TCP,
                tcp_src=src_port,
                tcp_dst=dst_port,
            )
        # Tạo match cho protocol UDP
        elif protocol == UDP:
            match = parser.OFPMatch(
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip,
                ip_proto=in_proto.IPPROTO_UDP,
                udp_src=src_port,
                udp_dst=dst_port,
            )
        # Tạo match cho protocol khác
        else:
            match = parser.OFPMatch(
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip,
            )

        # Tạo action đầu ra
        actions = [parser.OFPActionOutput(out_port)]
        # Tạo instruction actions
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        # Tạo message để thêm entry flow
        msg = [self.add_flow(datapath, table, priority, match, inst, i_time=idle_time)]

        return msg

    def create_match_entry_at_spine(self, datapath, table, priority, packet_info, in_port, out_port, i_time):
        """
        Tạo entry flow trong bảng MAC cho switch spine
        bao gồm port ingress và port egress
        """

        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        protocol, src_ip, dst_ip, src_port, dst_port = packet_info

        # Tạo match cho protocol TCP
        if protocol == TCP:
            match = parser.OFPMatch(
                in_port=in_port,
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip,
                ip_proto=in_proto.IPPROTO_TCP,
                tcp_src=src_port,
                tcp_dst=dst_port,
            )
        # Tạo match cho protocol UDP
        elif protocol == UDP:
            match = parser.OFPMatch(
                in_port=in_port,
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip,
                ip_proto=in_proto.IPPROTO_UDP,
                udp_src=src_port,
                udp_dst=dst_port,
            )
        # Tạo match cho protocol khác
        else:
            match = parser.OFPMatch(
                in_port=in_port,
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip,
            )

        # Tạo action đầu ra
        actions = [parser.OFPActionOutput(out_port)]
        # Tạo instruction actions
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        # Tạo message để thêm entry flow
        msgs = [self.add_flow(datapath, table, priority, match, inst, i_time=i_time)]

        return msgs

    def get_ipv4_packet_info(self, pkt, header_list):
        """Lấy thông tin header packet IPv4"""

        ip_pkt = header_list[IPV4]
        src_ip = ip_pkt.src
        dst_ip = ip_pkt.dst

        if TCP in header_list:
            tcp_pkt = header_list[TCP]
            return TCP, src_ip, dst_ip, tcp_pkt.src_port, tcp_pkt.dst_port

        if UDP in header_list:
            udp_pkt = header_list[UDP]
            return UDP, src_ip, dst_ip, udp_pkt.src_port, udp_pkt.dst_port

        return ICMP, src_ip, dst_ip, 0, 0

    def select_spine_from_packet_info(self, packet_info, num_spines):
        """Chọn switch spine dựa trên địa chỉ IP nguồn và đích
        và port TCP/UDP nguồn và đích (hash function)"""

        _, src_ip, dst_ip, src_port, dst_port = packet_info
        srcip_as_num = sum(map(int, src_ip.split(".")))
        dstip_as_num = sum(map(int, dst_ip.split(".")))

        return (srcip_as_num + dstip_as_num + src_port + dst_port) % num_spines

    def request_flow_stats(self, datapath):
        """Yêu cầu flow stats từ một switch"""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        # Yêu cầu tất cả flow stats từ tất cả bảng
        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)

    def _monitor_flow_stats(self):
        """Thread nền để yêu cầu flow stats từ tất cả switch theo chu kỳ"""
        while True:
            # Chờ khoảng thời gian chỉ định
            hub.sleep(self.flow_stats_interval)
            
            # Yêu cầu flow stats từ tất cả switch
            all_switches = net.spines + net.leaves
            for dpid in all_switches:
                datapath = get_datapath(self, dpid)
                if datapath is not None:
                    self.request_flow_stats(datapath)


config_file = os.environ.get("NETWORK_CONFIG_FILE", "network_config.yaml")
net = Network(config_file)