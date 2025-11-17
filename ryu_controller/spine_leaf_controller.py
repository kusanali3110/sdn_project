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

# Protocol Names
ETHERNET = ethernet.ethernet.__name__
# VLAN = vlan.vlan.__name__
IPV4 = ipv4.ipv4.__name__
ARP = arp.arp.__name__
ICMP = icmp.icmp.__name__
TCP = tcp.tcp.__name__
UDP = udp.udp.__name__

# Constants
ENTRY_TABLE = 0
LOCAL_TABLE = 0
REMOTE_TABLE = 1

MIN_PRIORITY = 0
LOW_PRIORITY = 100
MID_PRIORITY = 300

# Set idle_time=0 to make flow entries permenant
LONG_IDLE_TIME = 60
MID_IDLE_TIME = 40
IDLE_TIME = 30


class SpineLeaf3(BaseSwitch):
    """
    A spine-leaf implementation with two tables using static network description.
    """

    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Create central MAC table
        self.mac_table = {}
        
        # Track flow entries count per switch and table
        self.flow_entries_count = {}
        
        # Initialize Prometheus metrics exporter
        metrics_port = int(os.environ.get("METRICS_PORT", 8000))
        self.metrics = SDNMetricsExporter(port=metrics_port)
        self.metrics.start_server()
        
        # Initialize topology metrics
        self.metrics.update_switch_count('spine', len(net.spines))
        self.metrics.update_switch_count('leaf', len(net.leaves))
        
        # Start periodic flow stats collection thread
        self.flow_stats_interval = 10  # Request flow stats every 10 seconds
        self.monitor_thread = hub.spawn(self._monitor_flow_stats)
        
        self.logger.info(f"Metrics exporter started on port {metrics_port}")

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, event):
        """
        This method is called after the controller configures a switch.
        """

        datapath = event.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Update switch status metrics
        switch_type = 'leaf' if datapath.id in net.leaves else 'spine'
        self.metrics.update_switch_status(datapath.id, switch_type, 1)

        # Create a message to delete all exiting flows
        msgs = [self.del_flow(datapath)]
        self.metrics.increment_flow_mod(datapath.id, 'delete')

        # Set Match to ANY
        match = parser.OFPMatch()

        if datapath.id in net.leaves:  # For all leaf switches
            # Add a table-miss entry for LOCAL_TABLE:
            # Matched packets are sent to the next table
            inst = [parser.OFPInstructionGotoTable(REMOTE_TABLE)]
            msgs += [self.add_flow(datapath, LOCAL_TABLE, MIN_PRIORITY, match, inst)]
            self.metrics.increment_flow_mod(datapath.id, 'add')

            # Add a table-miss entry for REMOTE_TABLE:
            # Matched packets are flooded and sent to the controller
            actions = [
                parser.OFPActionOutput(ofproto.OFPP_ALL),
                parser.OFPActionOutput(
                    ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER
                ),
            ]
            inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
            msgs += [self.add_flow(datapath, REMOTE_TABLE, MIN_PRIORITY, match, inst)]
            self.metrics.increment_flow_mod(datapath.id, 'add')

        else:  # For all spine switches
            # Add a table-miss entry for ENTRY_TABLE to drop packets
            msgs += [self.add_flow(datapath, ENTRY_TABLE, MIN_PRIORITY, match, [])]
            self.metrics.increment_flow_mod(datapath.id, 'add')

        # Send all messages to the switch
        self.send_messages(datapath, msgs)
        
        # Request flow statistics to update metrics
        self.request_flow_stats(datapath)

    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, event):
        """Handle flow statistics reply from switches"""
        datapath = event.msg.datapath
        dpid = datapath.id
        
        # Count flows per table
        table_flows = {}
        for stat in event.msg.body:
            table_id = stat.table_id
            if table_id not in table_flows:
                table_flows[table_id] = 0
            table_flows[table_id] += 1
        
        # Update metrics for each table
        for table_id, count in table_flows.items():
            self.metrics.update_flow_entries(dpid, table_id, count)
            # Update local tracking
            self.flow_entries_count[(dpid, table_id)] = count
        
        # Also update tables with 0 entries
        if dpid in net.leaves:
            for table_id in [LOCAL_TABLE, REMOTE_TABLE]:
                if table_id not in table_flows:
                    self.metrics.update_flow_entries(dpid, table_id, 0)
                    self.flow_entries_count[(dpid, table_id)] = 0
        else:  # spine switch
            if ENTRY_TABLE not in table_flows:
                self.metrics.update_flow_entries(dpid, ENTRY_TABLE, 0)
                self.flow_entries_count[(dpid, ENTRY_TABLE)] = 0

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, event):
        """Handle packet_in message.

        This method is called when a PacketIn message is received. The message
        is sent by the switch to request processing of the packet by the
        controller such as when a table miss occurs.
        """
        
        # Start timing for performance metrics
        start_time = time.time()

        # Get the originating switch from the event
        datapath = event.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        # Get the packet's ingress port from the event
        in_port = event.msg.match["in_port"]

        # Get the packet from the event
        pkt = packet.Packet(event.msg.data)

        # Extract head information from the packet and return as dictionary
        header_list = dict(
            (p.protocol_name, p)
            for p in pkt.protocols
            if isinstance(p, packet_base.PacketBase)
        )

        # Get the packet's source and destination MAC addresses
        eth = header_list[ETHERNET]
        dst = eth.dst
        src = eth.src
        
        # Record packet size for bandwidth metrics
        packet_size = len(event.msg.data)
        self.metrics.add_bytes_transmitted(datapath.id, 'in', packet_size)

        # Update the MAC table and record metrics
        self.update_mac_table(src, in_port, datapath.id)

        # Remote switches are all leaf switches except the originating switch
        remote_switches = list(set(net.leaves) - set([datapath.id]))
        
        # Increment PacketIn counter
        self.metrics.increment_packet_in(datapath.id, 'table_miss')

        if ARP in header_list:
            # Record ARP packet
            arp_pkt = header_list[ARP]
            arp_type = 'request' if arp_pkt.opcode == arp.ARP_REQUEST else 'reply'
            self.metrics.increment_arp_packets(datapath.id, arp_type)
            self.metrics.increment_protocol_packet('ARP', datapath.id)
            
            # Send the packet to all remote switches to be flooded
            for leaf in remote_switches:
                # Get the datapath object
                dpath = get_datapath(self, leaf)
                msgs = self.forward_packet(
                    dpath, event.msg.data, ofproto.OFPP_CONTROLLER, ofproto.OFPP_ALL
                )
                self.send_messages(dpath, msgs)
                self.metrics.increment_packets_flooded(dpath.id)

        elif IPV4 in header_list:
            # Record IPv4 packet
            self.metrics.increment_protocol_packet('IPv4', datapath.id)
            # In the originating switch:

            # Add a flow entry in LOCAL_TABLE to forward packets to the given
            # output port if their destination MAC address matches this source
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

            # Get the packet higher layer information if available
            packet_info = self.get_ipv4_packet_info(pkt, header_list)
            self.logger.info(
                f"Packet Info: {packet_info[0]}, {packet_info[1]} {packet_info[2]}, {packet_info[3]}, {packet_info[4]}"
            )

            packet_type = packet_info[0]
            protocol_name, src_ip, dst_ip, src_port, dst_port = packet_info
            
            # Record protocol-specific metrics
            self.metrics.increment_protocol_packet(protocol_name, datapath.id)
            self.metrics.record_traffic_flow(src_ip, dst_ip, protocol_name)
            
            # Record TCP/UDP connection metrics
            if protocol_name == TCP:
                self.metrics.increment_tcp_connection(src_ip, dst_ip, dst_port)
            elif protocol_name == UDP:
                self.metrics.increment_udp_flow(src_ip, dst_ip, dst_port)
            
            dst_host = self.mac_table.get(dst)

            if dst_host:
                # If the destination is in the MAC Table

                # If it is connected to a remote switch
                if dst_host["dpid"] in remote_switches:
                    # Select a spine switch based on packet info
                    # The selected spine must be the same in each direction
                    spine_id = net.spines[
                        self.select_spine_from_packet_info(packet_info, len(net.spines))
                    ]
                    
                    # Record spine selection
                    self.metrics.increment_spine_selection(spine_id)

                    # In the originating switch,
                    # add an entry to the REMOTE_TABLE to forward packets
                    # from the source to the destination towards the spine switch

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

                    # In the spine switch,
                    # add two entries to forward packets between the source and
                    # destination in both directions

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

                    # In the remote switch,
                    # Send the received packet to the destination switch
                    # to forward it.
                    remote_port = dst_host["port"]
                    msgs = self.forward_packet(
                        dst_datapath,
                        event.msg.data,
                        ofproto.OFPP_CONTROLLER,
                        remote_port,
                    )
                    self.send_messages(dst_datapath, msgs)
                    
                    # Record remote forwarding metrics
                    self.metrics.record_remote_forwarding(datapath.id, dst_host["dpid"], spine_id)
                    self.metrics.increment_packets_forwarded(dst_datapath.id, remote_port)

            else:
                # If the destination is not in the MAC Table
                # Send the packet to all remote switches to be flooded
                for leaf in remote_switches:
                    # Get the datapath object
                    dpath = get_datapath(self, leaf)
                    msgs = self.forward_packet(
                        dpath, event.msg.data, ofproto.OFPP_CONTROLLER, ofproto.OFPP_ALL
                    )

                    self.send_messages(dpath, msgs)
                    self.metrics.increment_packets_flooded(dpath.id)
        
        # Record packet processing time
        processing_time = time.time() - start_time
        self.metrics.packet_in_processing_time.labels(dpid=datapath.id).observe(processing_time)

    def update_mac_table(self, src, port, dpid):
        """
        Set/Update the node information in the MAC table
        the MAC table includes the input port and input switch
        """

        src_host = self.mac_table.get(src, {})
        
        # Check if this is a new MAC address
        if not src_host:
            self.metrics.record_mac_learned(dpid)
        
        src_host["port"] = port
        src_host["dpid"] = dpid
        self.mac_table[src] = src_host
        
        # Update MAC table size metric
        self.metrics.update_mac_table_size(len(self.mac_table))
        
        return src_host

    def create_match_entry_at_leaf(
        self, datapath, table, priority, idle_time, packet_info, out_port
    ):
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        protocol, src_ip, dst_ip, src_port, dst_port = packet_info

        if protocol == TCP:
            match = parser.OFPMatch(
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip,
                ip_proto=in_proto.IPPROTO_TCP,
                tcp_src=src_port,
                tcp_dst=dst_port,
            )
        elif protocol == UDP:
            match = parser.OFPMatch(
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip,
                ip_proto=in_proto.IPPROTO_UDP,
                udp_src=src_port,
                udp_dst=dst_port,
            )
        else:
            match = parser.OFPMatch(
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip,
            )
        actions = [parser.OFPActionOutput(out_port)]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        msg = [
            self.add_flow(
                datapath,
                table,
                priority,
                match,
                inst,
                i_time=idle_time,
            )
        ]

        return msg

    def create_match_entry_at_spine(
        self,
        datapath,
        table,
        priority,
        packet_info,
        in_port,
        out_port,
        i_time,
    ):
        """
        Returns MOD messages to add two flow entries allowing packets between
        two nodes
        """

        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser

        protocol, src_ip, dst_ip, src_port, dst_port = packet_info

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
        else:
            match = parser.OFPMatch(
                in_port=in_port,
                eth_type=ether_types.ETH_TYPE_IP,
                ipv4_src=src_ip,
                ipv4_dst=dst_ip,
            )
        actions = [parser.OFPActionOutput(out_port)]
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        msgs = [self.add_flow(datapath, table, priority, match, inst, i_time=i_time)]

        return msgs

    def get_ipv4_packet_info(self, pkt, header_list):
        """Get IPv4 packet header information"""

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
        """Select spine switch based source and destination IP addresses
        and TCP/UDP port numbers"""

        _, src_ip, dst_ip, src_port, dst_port = packet_info
        srcip_as_num = sum(map(int, src_ip.split(".")))
        dstip_as_num = sum(map(int, dst_ip.split(".")))

        return (srcip_as_num + dstip_as_num + src_port + dst_port) % num_spines

    def request_flow_stats(self, datapath):
        """Request flow statistics from a switch"""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        
        # Request all flow stats from all tables
        req = parser.OFPFlowStatsRequest(datapath)
        datapath.send_msg(req)

    def _monitor_flow_stats(self):
        """Background thread to periodically request flow statistics from all switches"""
        while True:
            # Wait for the specified interval
            hub.sleep(self.flow_stats_interval)
            
            # Request flow stats from all switches
            all_switches = net.spines + net.leaves
            for dpid in all_switches:
                datapath = get_datapath(self, dpid)
                if datapath is not None:
                    self.request_flow_stats(datapath)


config_file = os.environ.get("NETWORK_CONFIG_FILE", "network_config.yaml")
net = Network(config_file)