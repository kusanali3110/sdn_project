from prometheus_client import Counter, Gauge, Histogram, Info, make_wsgi_app
from threading import Thread
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn
import logging


class SDNMetricsExporter:
    """
    Prometheus Metrics Exporter cho việc theo dõi mạng SDN
    Cung cấp các metrics chi tiết về topo mạng, flows, packets, và trạng thái của switches
    """

    def __init__(self, port=8000):
        """
        Khởi tạo tất cả Prometheus metrics cho việc theo dõi mạng SDN
        
        Args:
            port: Cổng số cho HTTP server (mặc định: 8000)
        """
        self.port = port
        self.logger = logging.getLogger(self.__class__.__name__)
        
        # Thông tin Controller
        self.controller_info = Info(
            'sdn_controller',
            'Information about the SDN controller'
        )
        self.controller_info.info({
            'name': 'SpineLeafController',
            'version': '3.0',
            'topology': 'spine-leaf'
        })
        
        # Metrics Topology
        self.switch_count = Gauge(
            'sdn_switches_total',
            'Total number of switches connected',
            ['switch_type']
        )
        
        self.switch_status = Gauge(
            'sdn_switch_status',
            'Switch connection status (1=connected, 0=disconnected)',
            ['dpid', 'switch_type']
        )
        
        self.port_status = Gauge(
            'sdn_port_status',
            'Port status on switches (1=up, 0=down)',
            ['dpid', 'port_no']
        )
        
        # Metrics MAC Table
        self.mac_table_size = Gauge(
            'sdn_mac_table_size',
            'Number of entries in MAC address table'
        )
        
        self.mac_learned = Counter(
            'sdn_mac_addresses_learned_total',
            'Total number of MAC addresses learned',
            ['dpid']
        )
        
        # Metrics Flow Table
        self.flow_entries_total = Gauge(
            'sdn_flow_entries_total',
            'Total number of flow entries installed',
            ['dpid', 'table_id']
        )
        
        self.flow_mod_sent = Counter(
            'sdn_flow_mod_messages_sent_total',
            'Total number of FlowMod messages sent',
            ['dpid', 'command']
        )
        
        self.flow_removed = Counter(
            'sdn_flows_removed_total',
            'Total number of flows removed',
            ['dpid', 'reason']
        )
        
        # Metrics xử lý packet
        self.packet_in_total = Counter(
            'sdn_packet_in_total',
            'Total number of PacketIn messages received',
            ['dpid', 'reason']
        )
        
        self.packets_by_protocol = Counter(
            'sdn_packets_by_protocol_total',
            'Total packets processed by protocol type',
            ['protocol', 'dpid']
        )
        
        self.packet_in_processing_time = Histogram(
            'sdn_packet_in_processing_seconds',
            'Time taken to process PacketIn messages',
            ['dpid'],
            buckets=(0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0)
        )
        
        # Metrics luồng traffic
        self.traffic_flows = Counter(
            'sdn_traffic_flows_total',
            'Total traffic flows between hosts',
            ['src_ip', 'dst_ip', 'protocol']
        )
        
        self.spine_selection = Counter(
            'sdn_spine_switch_selection_total',
            'Total times each spine switch was selected for routing',
            ['spine_id']
        )
        
        # Metrics chuyển tiếp packet
        self.packets_forwarded = Counter(
            'sdn_packets_forwarded_total',
            'Total packets forwarded by the controller',
            ['dpid', 'out_port']
        )
        
        self.packets_flooded = Counter(
            'sdn_packets_flooded_total',
            'Total packets flooded to all ports',
            ['dpid']
        )
        
        # Metrics ARP
        self.arp_packets = Counter(
            'sdn_arp_packets_total',
            'Total ARP packets processed',
            ['dpid', 'arp_type']
        )
        
        # Metrics lỗi
        self.errors_total = Counter(
            'sdn_errors_total',
            'Total errors encountered',
            ['error_type', 'dpid']
        )
        
        # Metrics kết nối
        self.tcp_connections = Counter(
            'sdn_tcp_connections_total',
            'Total TCP connections observed',
            ['src_ip', 'dst_ip', 'dst_port']
        )
        
        self.udp_flows = Counter(
            'sdn_udp_flows_total',
            'Total UDP flows observed',
            ['src_ip', 'dst_ip', 'dst_port']
        )
        
        # Metrics băng thông (ước tính từ kích thước packet)
        self.bytes_transmitted = Counter(
            'sdn_bytes_transmitted_total',
            'Total bytes transmitted through the network',
            ['dpid', 'direction']
        )
        
        # Thống kê bảng
        self.table_miss_total = Counter(
            'sdn_table_miss_total',
            'Total table miss events',
            ['dpid', 'table_id']
        )
        
        # Metrics hiệu suất
        self.flow_setup_time = Histogram(
            'sdn_flow_setup_seconds',
            'Time taken to setup a new flow',
            ['dpid'],
            buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0, 2.0)
        )
        
        # Metrics chuyển tiếp từ xa
        self.remote_forwarding = Counter(
            'sdn_remote_forwarding_total',
            'Total packets forwarded to remote switches',
            ['src_dpid', 'dst_dpid', 'via_spine']
        )
    
    def start_server(self):
        """Bắt đầu server Prometheus HTTP trong một thread riêng biệt"""
        class ThreadedWSGIServer(ThreadingMixIn, WSGIServer):
            """Server WSGI để xử lý yêu cầu đồng thời"""
            daemon_threads = True
        
        def run_server():
            try:
                app = make_wsgi_app()
                httpd = make_server('', self.port, app, server_class=ThreadedWSGIServer)
                self.logger.info(f"Prometheus metrics server started on port http://0.0.0.0:{self.port}/metrics")
                httpd.serve_forever()
            except Exception as e:
                self.logger.error(f"Failed to start metrics server: {e}")
        
        thread = Thread(target=run_server, daemon=True)
        thread.start()
        return thread
    
    # Các hàm hỗ trợ để cập nhật metrics
    
    def increment_packet_in(self, dpid, reason='table_miss'):
        """Tăng counter PacketIn"""
        self.packet_in_total.labels(dpid=dpid, reason=reason).inc()
    
    def increment_protocol_packet(self, protocol, dpid):
        """Tăng counter packet cụ thể cho protocol"""
        self.packets_by_protocol.labels(protocol=protocol, dpid=dpid).inc()
    
    def record_mac_learned(self, dpid):
        """Ghi lại địa chỉ MAC học được"""
        self.mac_learned.labels(dpid=dpid).inc()
    
    def update_mac_table_size(self, size):
        """Cập nhật kích thước bảng MAC"""
        self.mac_table_size.set(size)
    
    def increment_flow_mod(self, dpid, command='add'):
        """Tăng counter FlowMod"""
        self.flow_mod_sent.labels(dpid=dpid, command=command).inc()
    
    def increment_spine_selection(self, spine_id):
        """Tăng counter chọn spine"""
        self.spine_selection.labels(spine_id=spine_id).inc()
    
    def record_traffic_flow(self, src_ip, dst_ip, protocol):
        """Ghi lại luồng traffic"""
        self.traffic_flows.labels(src_ip=src_ip, dst_ip=dst_ip, protocol=protocol).inc()
    
    def increment_packets_forwarded(self, dpid, out_port):
        """Tăng counter packet chuyển tiếp"""
        self.packets_forwarded.labels(dpid=dpid, out_port=out_port).inc()
    
    def increment_packets_flooded(self, dpid):
        """Tăng counter packet lặp lại"""
        self.packets_flooded.labels(dpid=dpid).inc()
    
    def increment_arp_packets(self, dpid, arp_type='request'):
        """Tăng counter packet ARP"""
        self.arp_packets.labels(dpid=dpid, arp_type=arp_type).inc()
    
    def increment_tcp_connection(self, src_ip, dst_ip, dst_port):
        """Ghi lại kết nối TCP"""
        self.tcp_connections.labels(src_ip=src_ip, dst_ip=dst_ip, dst_port=dst_port).inc()
    
    def increment_udp_flow(self, src_ip, dst_ip, dst_port):
        """Ghi lại luồng UDP"""
        self.udp_flows.labels(src_ip=src_ip, dst_ip=dst_ip, dst_port=dst_port).inc()
    
    def record_remote_forwarding(self, src_dpid, dst_dpid, via_spine):
        """Ghi lại sự kiện chuyển tiếp từ xa"""
        self.remote_forwarding.labels(
            src_dpid=src_dpid, 
            dst_dpid=dst_dpid, 
            via_spine=via_spine
        ).inc()
    
    def increment_table_miss(self, dpid, table_id):
        """Tăng counter miss bảng"""
        self.table_miss_total.labels(dpid=dpid, table_id=table_id).inc()
    
    def record_error(self, error_type, dpid='unknown'):
        """Ghi lại lỗi"""
        self.errors_total.labels(error_type=error_type, dpid=dpid).inc()
    
    def update_switch_count(self, switch_type, count):
        """Cập nhật số lượng switch"""
        self.switch_count.labels(switch_type=switch_type).set(count)
    
    def update_switch_status(self, dpid, switch_type, status):
        """Cập nhật trạng thái switch (1=connected, 0=disconnected)"""
        self.switch_status.labels(dpid=dpid, switch_type=switch_type).set(status)
    
    def update_flow_entries(self, dpid, table_id, count):
        """Cập nhật số lượng flow entries"""
        self.flow_entries_total.labels(dpid=dpid, table_id=table_id).set(count)
    
    def add_bytes_transmitted(self, dpid, direction, bytes_count):
        """Thêm bytes được truyền"""
        self.bytes_transmitted.labels(dpid=dpid, direction=direction).inc(bytes_count)

