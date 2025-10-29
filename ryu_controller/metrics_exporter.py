#!/usr/bin/env python3
"""
Prometheus Metrics Exporter for Spine-Leaf SDN Controller

This module exports comprehensive metrics about the SDN network topology,
switches, flows, traffic, and ECMP load balancing to Prometheus.

Uses a lightweight WSGI server to avoid conflicts with Ryu's eventlet.
"""

from prometheus_client import Counter, Gauge, Histogram, Info, generate_latest, REGISTRY
from prometheus_client.core import CollectorRegistry
from wsgiref.simple_server import make_server, WSGIServer
from socketserver import ThreadingMixIn
import threading
import time
from ryu.lib import hub


class ThreadingWSGIServer(ThreadingMixIn, WSGIServer):
    """Thread per request HTTP server"""
    daemon_threads = True
    allow_reuse_address = True


class PrometheusMetricsExporter:
    """
    Exports SDN network metrics to Prometheus
    
    Metrics Categories:
    - Switch & Datapath metrics
    - Port metrics (uplinks, host ports, status)
    - Flow table metrics
    - Traffic statistics (packets, bytes, throughput)
    - Topology metrics (links, neighbors)
    - ECMP group metrics
    - Host learning metrics
    - Controller performance metrics
    """
    
    def __init__(self, controller, port=9090, host='0.0.0.0'):
        """
        Initialize metrics exporter
        
        Args:
            controller: Reference to SpineLeafController instance
            port: HTTP server port for /metrics endpoint
            host: HTTP server bind address
        """
        self.controller = controller
        self.port = port
        self.host = host
        self.httpd = None
        self._stats_thread = None
        
        # ============================================================
        # SWITCH & DATAPATH METRICS
        # ============================================================
        
        self.switch_count = Gauge(
            'sdn_switches_total',
            'Total number of OpenFlow switches connected',
            ['type']  # spine or leaf
        )
        
        self.switch_info = Info(
            'sdn_switch',
            'Information about each switch',
            ['dpid', 'type']
        )
        
        self.datapath_status = Gauge(
            'sdn_datapath_status',
            'Datapath connection status (1=up, 0=down)',
            ['dpid', 'type']
        )
        
        # ============================================================
        # PORT METRICS
        # ============================================================
        
        self.port_count = Gauge(
            'sdn_ports_total',
            'Number of ports per switch',
            ['dpid', 'port_type']  # uplink, host, or total
        )
        
        self.port_status = Gauge(
            'sdn_port_status',
            'Port status (1=up, 0=down)',
            ['dpid', 'port_no', 'port_type']
        )
        
        self.port_rx_packets = Counter(
            'sdn_port_rx_packets_total',
            'Received packets on port',
            ['dpid', 'port_no', 'port_type']
        )
        
        self.port_tx_packets = Counter(
            'sdn_port_tx_packets_total',
            'Transmitted packets on port',
            ['dpid', 'port_no', 'port_type']
        )
        
        self.port_rx_bytes = Counter(
            'sdn_port_rx_bytes_total',
            'Received bytes on port',
            ['dpid', 'port_no', 'port_type']
        )
        
        self.port_tx_bytes = Counter(
            'sdn_port_tx_bytes_total',
            'Transmitted bytes on port',
            ['dpid', 'port_no', 'port_type']
        )
        
        self.port_rx_errors = Counter(
            'sdn_port_rx_errors_total',
            'Receive errors on port',
            ['dpid', 'port_no', 'port_type']
        )
        
        self.port_tx_errors = Counter(
            'sdn_port_tx_errors_total',
            'Transmit errors on port',
            ['dpid', 'port_no', 'port_type']
        )
        
        self.port_rx_drops = Counter(
            'sdn_port_rx_drops_total',
            'Received packets dropped on port',
            ['dpid', 'port_no', 'port_type']
        )
        
        self.port_tx_drops = Counter(
            'sdn_port_tx_drops_total',
            'Transmitted packets dropped on port',
            ['dpid', 'port_no', 'port_type']
        )
        
        # ============================================================
        # FLOW TABLE METRICS
        # ============================================================
        
        self.flow_count = Gauge(
            'sdn_flow_entries_total',
            'Number of flow entries in flow table',
            ['dpid', 'table_id']
        )
        
        self.flow_packet_count = Counter(
            'sdn_flow_packets_matched_total',
            'Packets matched by flows',
            ['dpid', 'table_id', 'priority']
        )
        
        self.flow_byte_count = Counter(
            'sdn_flow_bytes_matched_total',
            'Bytes matched by flows',
            ['dpid', 'table_id', 'priority']
        )
        
        self.flow_duration = Gauge(
            'sdn_flow_duration_seconds',
            'Flow entry duration',
            ['dpid', 'table_id', 'priority']
        )
        
        self.flow_age = Histogram(
            'sdn_flow_age_seconds',
            'Age of flow entries',
            ['dpid'],
            buckets=[1, 5, 10, 30, 60, 300, 600, 1800, 3600]
        )
        
        # ============================================================
        # TOPOLOGY METRICS
        # ============================================================
        
        self.link_count = Gauge(
            'sdn_links_total',
            'Total number of inter-switch links',
            ['link_type']  # spine_to_leaf, leaf_to_spine
        )
        
        self.link_status = Gauge(
            'sdn_link_status',
            'Link status (1=up, 0=down)',
            ['src_dpid', 'dst_dpid', 'src_port']
        )
        
        self.neighbor_count = Gauge(
            'sdn_neighbors_total',
            'Number of neighbor switches',
            ['dpid']
        )
        
        # ============================================================
        # ECMP GROUP METRICS
        # ============================================================
        
        self.ecmp_group_bucket_count = Gauge(
            'sdn_ecmp_buckets_total',
            'Number of buckets in ECMP group',
            ['dpid', 'group_id']
        )
        
        self.ecmp_group_packet_count = Counter(
            'sdn_ecmp_packets_total',
            'Packets processed by ECMP group',
            ['dpid', 'group_id']
        )
        
        self.ecmp_group_byte_count = Counter(
            'sdn_ecmp_bytes_total',
            'Bytes processed by ECMP group',
            ['dpid', 'group_id']
        )
        
        self.ecmp_bucket_packet_count = Counter(
            'sdn_ecmp_bucket_packets_total',
            'Packets per ECMP bucket',
            ['dpid', 'group_id', 'bucket_id']
        )
        
        self.ecmp_bucket_byte_count = Counter(
            'sdn_ecmp_bucket_bytes_total',
            'Bytes per ECMP bucket',
            ['dpid', 'group_id', 'bucket_id']
        )
        
        # ============================================================
        # HOST LEARNING METRICS
        # ============================================================
        
        self.learned_hosts = Gauge(
            'sdn_learned_hosts_total',
            'Total number of learned host MAC addresses'
        )
        
        self.learned_ips = Gauge(
            'sdn_learned_ips_total',
            'Total number of learned IP addresses'
        )
        
        self.host_location = Gauge(
            'sdn_host_location',
            'Host location in topology (value=port)',
            ['mac', 'dpid']
        )
        
        self.hosts_per_leaf = Gauge(
            'sdn_hosts_per_leaf',
            'Number of hosts connected to each leaf',
            ['dpid']
        )
        
        # ============================================================
        # PACKET-IN METRICS
        # ============================================================
        
        self.packet_in_total = Counter(
            'sdn_packet_in_total',
            'Total packet-in messages received',
            ['dpid', 'reason']
        )
        
        self.packet_in_rate = Gauge(
            'sdn_packet_in_rate',
            'Packet-in rate per second',
            ['dpid']
        )
        
        self.arp_packets = Counter(
            'sdn_arp_packets_total',
            'ARP packets processed',
            ['dpid', 'opcode']  # request or reply
        )
        
        # ============================================================
        # TRAFFIC METRICS
        # ============================================================
        
        self.total_traffic_bytes = Counter(
            'sdn_total_traffic_bytes',
            'Total traffic in bytes',
            ['direction']  # rx or tx
        )
        
        self.total_traffic_packets = Counter(
            'sdn_total_traffic_packets',
            'Total traffic in packets',
            ['direction']  # rx or tx
        )
        
        self.throughput_bps = Gauge(
            'sdn_throughput_bits_per_second',
            'Network throughput in bits per second',
            ['dpid', 'port_no']
        )
        
        self.cross_leaf_traffic_bytes = Counter(
            'sdn_cross_leaf_traffic_bytes_total',
            'Traffic between different leaves',
            ['src_dpid', 'dst_dpid']
        )
        
        # ============================================================
        # CONTROLLER PERFORMANCE METRICS
        # ============================================================
        
        self.controller_uptime = Gauge(
            'sdn_controller_uptime_seconds',
            'Controller uptime in seconds'
        )
        
        self.topology_rebuild_count = Counter(
            'sdn_topology_rebuild_total',
            'Number of topology rebuilds'
        )
        
        self.topology_rebuild_duration = Histogram(
            'sdn_topology_rebuild_duration_seconds',
            'Time taken to rebuild topology',
            buckets=[0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1.0]
        )
        
        self.flow_install_duration = Histogram(
            'sdn_flow_install_duration_seconds',
            'Time to install flow rules',
            ['dpid'],
            buckets=[0.0001, 0.0005, 0.001, 0.005, 0.01, 0.05, 0.1]
        )
        
        # ============================================================
        # ERROR METRICS
        # ============================================================
        
        self.error_count = Counter(
            'sdn_errors_total',
            'Total errors by type',
            ['error_type', 'dpid']
        )
        
        self.packet_out_errors = Counter(
            'sdn_packet_out_errors_total',
            'Packet-out send errors',
            ['dpid']
        )
        
        # Track start time for uptime
        self._start_time = time.time()
        
        # Track packet-in for rate calculation
        self._packet_in_count = {}
        self._last_packet_in_time = {}
    
    def get_switch_type(self, dpid):
        """Determine if switch is spine or leaf based on DPID"""
        # Based on spine_leaf.py: spines are DPID 1-2, leaves are DPID 3-5
        if dpid <= 2:
            return 'spine'
        else:
            return 'leaf'
    
    def get_port_type(self, dpid, port_no):
        """Determine port type: uplink, host, or unknown"""
        if port_no in self.controller.uplink_ports.get(dpid, set()):
            return 'uplink'
        elif port_no in self.controller.host_ports.get(dpid, set()):
            return 'host'
        else:
            return 'unknown'
    
    def update_switch_metrics(self):
        """Update switch and datapath metrics"""
        spine_count = 0
        leaf_count = 0
        
        for dpid, dp in self.controller.datapaths.items():
            switch_type = self.get_switch_type(dpid)
            
            if switch_type == 'spine':
                spine_count += 1
            else:
                leaf_count += 1
            
            # Datapath status
            self.datapath_status.labels(
                dpid=dpid,
                type=switch_type
            ).set(1)  # Connected
        
        self.switch_count.labels(type='spine').set(spine_count)
        self.switch_count.labels(type='leaf').set(leaf_count)
    
    def update_port_metrics(self):
        """Update port statistics and status"""
        for dpid, dp in self.controller.datapaths.items():
            ofp = dp.ofproto
            parser = dp.ofproto_parser
            
            # Count ports by type
            uplink_count = len(self.controller.uplink_ports.get(dpid, set()))
            host_count = len(self.controller.host_ports.get(dpid, set()))
            
            self.port_count.labels(dpid=dpid, port_type='uplink').set(uplink_count)
            self.port_count.labels(dpid=dpid, port_type='host').set(host_count)
            self.port_count.labels(dpid=dpid, port_type='total').set(uplink_count + host_count)
            
            # Request port statistics
            req = parser.OFPPortStatsRequest(dp, 0, ofp.OFPP_ANY)
            dp.send_msg(req)
    
    def update_flow_metrics(self):
        """Request flow statistics from all switches"""
        for dpid, dp in self.controller.datapaths.items():
            parser = dp.ofproto_parser
            req = parser.OFPFlowStatsRequest(dp)
            dp.send_msg(req)
    
    def update_group_metrics(self):
        """Request group statistics for ECMP monitoring"""
        for dpid, dp in self.controller.datapaths.items():
            parser = dp.ofproto_parser
            ofp = dp.ofproto
            
            # Only leaves have ECMP groups
            if self.controller.host_ports.get(dpid):
                req = parser.OFPGroupStatsRequest(dp, 0, ofp.OFPG_ALL)
                dp.send_msg(req)
    
    def update_topology_metrics(self):
        """Update topology-related metrics"""
        # Link counts
        spine_to_leaf = 0
        leaf_to_spine = 0
        
        for dpid, neighbors in self.controller.switch_neighbors.items():
            self.neighbor_count.labels(dpid=dpid).set(len(neighbors))
            
            switch_type = self.get_switch_type(dpid)
            for neighbor_dpid, port_no in neighbors.items():
                neighbor_type = self.get_switch_type(neighbor_dpid)
                
                if switch_type == 'spine' and neighbor_type == 'leaf':
                    spine_to_leaf += 1
                elif switch_type == 'leaf' and neighbor_type == 'spine':
                    leaf_to_spine += 1
                
                # Link status (assume up if in neighbors)
                self.link_status.labels(
                    src_dpid=dpid,
                    dst_dpid=neighbor_dpid,
                    src_port=port_no
                ).set(1)
        
        self.link_count.labels(link_type='spine_to_leaf').set(spine_to_leaf)
        self.link_count.labels(link_type='leaf_to_spine').set(leaf_to_spine)
    
    def update_host_metrics(self):
        """Update host learning metrics"""
        self.learned_hosts.set(len(self.controller.host_locations))
        self.learned_ips.set(len(self.controller.ip_to_mac))
        
        # Hosts per leaf
        hosts_per_leaf = {}
        for mac, (dpid, port) in self.controller.host_locations.items():
            if self.get_switch_type(dpid) == 'leaf':
                hosts_per_leaf[dpid] = hosts_per_leaf.get(dpid, 0) + 1
                self.host_location.labels(mac=mac, dpid=dpid).set(port)
        
        for dpid, count in hosts_per_leaf.items():
            self.hosts_per_leaf.labels(dpid=dpid).set(count)
    
    def update_controller_metrics(self):
        """Update controller performance metrics"""
        uptime = time.time() - self._start_time
        self.controller_uptime.set(uptime)
    
    def handle_port_stats_reply(self, ev):
        """Process port statistics reply"""
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        
        for stat in body:
            port_no = stat.port_no
            port_type = self.get_port_type(dpid, port_no)
            
            # Skip local port
            if port_no >= 0xffffff00:
                continue
            
            labels = {'dpid': dpid, 'port_no': port_no, 'port_type': port_type}
            
            # Update counters (Prometheus Counter only increases)
            # We set the counter to the current value from switch
            self.port_rx_packets.labels(**labels)._value.set(stat.rx_packets)
            self.port_tx_packets.labels(**labels)._value.set(stat.tx_packets)
            self.port_rx_bytes.labels(**labels)._value.set(stat.rx_bytes)
            self.port_tx_bytes.labels(**labels)._value.set(stat.tx_bytes)
            self.port_rx_errors.labels(**labels)._value.set(stat.rx_errors)
            self.port_tx_errors.labels(**labels)._value.set(stat.tx_errors)
            self.port_rx_drops.labels(**labels)._value.set(stat.rx_dropped)
            self.port_tx_drops.labels(**labels)._value.set(stat.tx_dropped)
            
            # Calculate throughput (simplified - needs time tracking for accuracy)
            if stat.duration_sec > 0:
                throughput = (stat.tx_bytes * 8) / stat.duration_sec
                self.throughput_bps.labels(dpid=dpid, port_no=port_no).set(throughput)

            # Calculate total traffic
            if stat.port_no > ev.msg.datapath.ofproto.OFPP_MAX:
                self.total_traffic_bytes.labels(direction='tx').inc(stat.tx_bytes)
                self.total_traffic_bytes.labels(direction='rx').inc(stat.rx_bytes)
                self.total_traffic_packets.labels(direction='tx').inc(stat.tx_packets)
                self.total_traffic_packets.labels(direction='rx').inc(stat.rx_packets)
    
    def handle_flow_stats_reply(self, ev):
        """Process flow statistics reply"""
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        
        flow_counts = {}
        
        for stat in body:
            table_id = stat.table_id
            priority = stat.priority
            
            flow_counts[table_id] = flow_counts.get(table_id, 0) + 1
            
            # Flow packet and byte counters
            self.flow_packet_count.labels(
                dpid=dpid,
                table_id=table_id,
                priority=priority
            )._value.set(stat.packet_count)
            
            self.flow_byte_count.labels(
                dpid=dpid,
                table_id=table_id,
                priority=priority
            )._value.set(stat.byte_count)
            
            # Flow duration
            duration = stat.duration_sec + (stat.duration_nsec / 1e9)
            self.flow_duration.labels(
                dpid=dpid,
                table_id=table_id,
                priority=priority
            ).set(duration)
            
            # Flow age histogram
            self.flow_age.labels(dpid=dpid).observe(duration)
        
        # Update flow count per table
        for table_id, count in flow_counts.items():
            self.flow_count.labels(dpid=dpid, table_id=table_id).set(count)
    
    def handle_group_stats_reply(self, ev):
        """Process group statistics reply"""
        body = ev.msg.body
        dpid = ev.msg.datapath.id
        
        for stat in body:
            group_id = stat.group_id
            
            # Group bucket count
            self.ecmp_group_bucket_count.labels(
                dpid=dpid,
                group_id=group_id
            ).set(len(stat.bucket_stats))
            
            # Group totals
            self.ecmp_group_packet_count.labels(
                dpid=dpid,
                group_id=group_id
            )._value.set(stat.packet_count)
            
            self.ecmp_group_byte_count.labels(
                dpid=dpid,
                group_id=group_id
            )._value.set(stat.byte_count)
            
            # Per-bucket stats
            for i, bucket in enumerate(stat.bucket_stats):
                self.ecmp_bucket_packet_count.labels(
                    dpid=dpid,
                    group_id=group_id,
                    bucket_id=i
                )._value.set(bucket.packet_count)
                
                self.ecmp_bucket_byte_count.labels(
                    dpid=dpid,
                    group_id=group_id,
                    bucket_id=i
                )._value.set(bucket.byte_count)
    
    def handle_packet_in(self, dpid, reason):
        """Track packet-in events"""
        # Increment counter
        self.packet_in_total.labels(dpid=dpid, reason=reason).inc()
        
        # Calculate rate
        now = time.time()
        key = (dpid, reason)
        
        if key not in self._packet_in_count:
            self._packet_in_count[key] = 0
            self._last_packet_in_time[key] = now
        
        self._packet_in_count[key] += 1
        
        # Update rate every second
        elapsed = now - self._last_packet_in_time[key]
        if elapsed >= 1.0:
            rate = self._packet_in_count[key] / elapsed
            self.packet_in_rate.labels(dpid=dpid).set(rate)
            self._packet_in_count[key] = 0
            self._last_packet_in_time[key] = now
    
    def handle_arp_packet(self, dpid, opcode):
        """Track ARP packets"""
        opcode_name = 'request' if opcode == 1 else 'reply'
        self.arp_packets.labels(dpid=dpid, opcode=opcode_name).inc()

    def handle_error_msg(self, ev):
        """Handle error messages"""
        dpid = ev.msg.datapath.id
        error_type = ev.msg.type
        self.error_count.labels(error_type=error_type, dpid=dpid).inc()
    
    def record_topology_rebuild(self, duration):
        """Record topology rebuild event"""
        self.topology_rebuild_count.inc()
        self.topology_rebuild_duration.observe(duration)
    
    def record_flow_install(self, dpid, duration):
        """Record flow installation timing"""
        self.flow_install_duration.labels(dpid=dpid).observe(duration)
    
    def record_error(self, error_type, dpid=None):
        """Record an error event"""
        dpid_str = str(dpid) if dpid else 'unknown'
        self.error_count.labels(error_type=error_type, dpid=dpid_str).inc()
    
    def _stats_collector(self):
        """Periodic stats collection thread"""
        while True:
            try:
                self.update_switch_metrics()
                self.update_port_metrics()
                self.update_flow_metrics()
                self.update_group_metrics()
                self.update_topology_metrics()
                self.update_host_metrics()
                self.update_controller_metrics()
            except Exception as e:
                self.controller.logger.error("Error collecting metrics: %s", e)
            
            hub.sleep(5)  # Collect every 5 seconds
    
    def _metrics_app(self, environ, start_response):
        """WSGI application for /metrics endpoint"""
        path = environ.get('PATH_INFO', '/')
        
        if path == '/metrics':
            status = '200 OK'
            headers = [('Content-Type', 'text/plain; charset=utf-8')]
            start_response(status, headers)
            return [generate_latest(REGISTRY)]
        elif path == '/' or path == '/health':
            status = '200 OK'
            headers = [('Content-Type', 'text/plain')]
            start_response(status, headers)
            return [b'SDN Metrics Exporter OK\n']
        else:
            status = '404 Not Found'
            headers = [('Content-Type', 'text/plain')]
            start_response(status, headers)
            return [b'Not Found\n']
    
    def start(self):
        """Start the metrics HTTP server"""
        try:
            # Start stats collection thread
            self._stats_thread = hub.spawn(self._stats_collector)
            
            # Start HTTP server in separate thread
            self.httpd = make_server(
                self.host,
                self.port,
                self._metrics_app,
                server_class=ThreadingWSGIServer
            )
            
            server_thread = threading.Thread(
                target=self.httpd.serve_forever,
                daemon=True
            )
            server_thread.start()
            
            self.controller.logger.info(
                "Prometheus metrics server started on http://%s:%d/metrics",
                self.host, self.port
            )
        except Exception as e:
            self.controller.logger.error("Failed to start metrics server: %s", e)
            raise
    
    def stop(self):
        """Stop the metrics HTTP server"""
        if self.httpd:
            self.httpd.shutdown()
            self.controller.logger.info("Prometheus metrics server stopped")

