from ryu.base import app_manager
from ryu.controller import ofp_event
from ryu.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, DEAD_DISPATCHER
from ryu.controller.handler import set_ev_cls
from ryu.lib.packet import packet
from ryu.lib.packet import ethernet, arp, ipv4
from ryu.ofproto import ofproto_v1_3
from ryu.topology import event as topo_event
from ryu.topology.api import get_all_switch, get_all_link
from ryu.lib import mac
from ryu.lib import hub
import time
from metrics_exporter import PrometheusMetricsExporter


class SpineLeafController(app_manager.RyuApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.datapaths = {}
        # Table to determine cross-leaf MAC
        self.mac_to_dpid = {}
        # host_mac -> (dpid, port)
        self.host_locations = {}
        # ip -> mac (learned via ARP)
        self.ip_to_mac = {}
        # switch_dpid -> set(uplink ports)
        self.uplink_ports = {}
        # switch_dpid -> set(host ports)
        self.host_ports = {}
        # switch_dpid -> neighbor switch ports: dpid -> port_no
        self.switch_neighbors = {}
        
        
        # Initialize Prometheus metrics exporter
        self.metrics = PrometheusMetricsExporter(self, port=9090, host='0.0.0.0')
        try:
            self.metrics.start()
        except Exception as e:
            self.logger.error("Failed to start metrics exporter: %s", e)
        
        # periodic maintenance
        self._monitor_thread = hub.spawn(self._monitor)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        datapath = ev.msg.datapath
        ofp = datapath.ofproto
        parser = datapath.ofproto_parser

        # Install a table-miss flow to send unknown to controller
        match = parser.OFPMatch()
        actions = [parser.OFPActionOutput(ofp.OFPP_CONTROLLER, ofp.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, priority=0, match=match, actions=actions)

        # Enable ARP to controller
        match_arp = parser.OFPMatch(eth_type=0x0806)
        self.add_flow(datapath, priority=5, match=match_arp, actions=actions)

        # Track datapath
        self.datapaths[datapath.id] = datapath
        self.logger.info("Switch connected: dpid=%s", datapath.id)

    def add_flow(self, datapath, priority, match, actions=None, buffer_id=None, table_id=0, inst=None):
        start_time = time.time()
        ofp = datapath.ofproto
        parser = datapath.ofproto_parser
        if inst is None:
            if actions is None:
                actions = []
            inst = [parser.OFPInstructionActions(ofp.OFPIT_APPLY_ACTIONS, actions)]
        if buffer_id:
            mod = parser.OFPFlowMod(datapath=datapath, table_id=table_id, priority=priority,
                                    buffer_id=buffer_id, match=match, instructions=inst)
        else:
            mod = parser.OFPFlowMod(datapath=datapath, table_id=table_id, priority=priority,
                                    match=match, instructions=inst)
        datapath.send_msg(mod)
        
        # Record flow installation timing
        duration = time.time() - start_time
        if hasattr(self, 'metrics'):
            self.metrics.record_flow_install(datapath.id, duration)

    @set_ev_cls(ofp_event.EventOFPPortStatus, MAIN_DISPATCHER)
    def port_status_handler(self, ev):
        msg = ev.msg
        reason = msg.reason
        port = msg.desc
        port_state = msg.desc.state
        dpid = msg.datapath.id
        if reason == msg.datapath.ofproto.OFPPR_ADD:
            self.logger.info("Port added %s on dpid=%s", port.port_no, dpid)
        elif reason == msg.datapath.ofproto.OFPPR_DELETE:
            self.logger.info("Port deleted %s on dpid=%s", port.port_no, dpid)
        else:
            self.logger.info("Port modified %s on dpid=%s", port.port_no, dpid)
        if port_state == 0: # PORT UP
            self.metrics.port_status.labels(dpid=dpid, port_no=port.port_no, port_state='up').set(1)
        else: # PORT DOWN/BLOCKED
            self.metrics.port_status.labels(dpid=dpid, port_no=port.port_no, port_state=port_state).set(0)
        # Recompute groups on this switch
        self.recompute_groups_for_switch(dpid)

    @set_ev_cls(topo_event.EventSwitchEnter)
    def handler_switch_enter(self, ev):
        self.logger.info("Switch discovered: %s", ev.switch.dp.id)
        self.rebuild_topology()

    @set_ev_cls(topo_event.EventLinkAdd)
    def handler_link_add(self, ev):
        self.logger.info("Link added: %s -> %s", ev.link.src, ev.link.dst)
        self.rebuild_topology()

    @set_ev_cls(topo_event.EventLinkDelete)
    def handler_link_del(self, ev):
        self.logger.info("Link deleted: %s -> %s", ev.link.src, ev.link.dst)
        self.rebuild_topology()

    def rebuild_topology(self):
        # Build neighbor maps and infer uplinks vs host ports
        start_time = time.time()
        switches = get_all_switch(self)
        links = get_all_link(self)

        neighbor_ports = {sw.dp.id: {} for sw in switches}
        uplinks = {sw.dp.id: set() for sw in switches}

        for link in links:
            src_dpid = link.src.dpid
            dst_dpid = link.dst.dpid
            neighbor_ports[src_dpid][dst_dpid] = link.src.port_no
            neighbor_ports[dst_dpid][src_dpid] = link.dst.port_no
            uplinks[src_dpid].add(link.src.port_no)
            uplinks[dst_dpid].add(link.dst.port_no)

        self.switch_neighbors = neighbor_ports
        self.uplink_ports = uplinks

        # Host ports are those not in uplinks and not local OFPP_LOCAL
        for sw in switches:
            dp = sw.dp
            ofp = dp.ofproto
            host_ports = set()
            for p in sw.ports:
                if p.port_no == ofp.OFPP_LOCAL:
                    continue
                if p.port_no not in self.uplink_ports.get(dp.id, set()):
                    host_ports.add(p.port_no)
            self.host_ports[dp.id] = host_ports

        # Create/update ECMP groups on leaves (switches that have host_ports)
        for dpid, ports in self.host_ports.items():
            if ports:
                self.install_ecmp_group_on_leaf(dpid)

        self.logger.info("Topology rebuilt. Neighbors: %s, uplinks: %s, host_ports: %s",
                         self.switch_neighbors, self.uplink_ports, self.host_ports)
        
        # Record topology rebuild duration
        duration = time.time() - start_time
        if hasattr(self, 'metrics'):
            self.metrics.record_topology_rebuild(duration)

    def install_ecmp_group_on_leaf(self, dpid):
        dp = self.datapaths.get(dpid)
        if dp is None:
            return
        parser = dp.ofproto_parser
        ofp = dp.ofproto

        uplinks = sorted(self.uplink_ports.get(dpid, []))
        if not uplinks:
            return

        group_id = 100  # fixed group id for leaf uplink ECMP

        buckets = []
        for port in uplinks:
            actions = [parser.OFPActionOutput(port)]
            buckets.append(parser.OFPBucket(actions=actions))

        req = parser.OFPGroupMod(datapath=dp,
                                 command=ofp.OFPGC_DELETE,
                                 type_=ofp.OFPGT_SELECT,
                                 group_id=group_id)
        dp.send_msg(req)

        req = parser.OFPGroupMod(datapath=dp,
                                 command=ofp.OFPGC_ADD,
                                 type_=ofp.OFPGT_SELECT,
                                 group_id=group_id,
                                 buckets=buckets)
        dp.send_msg(req)
        self.logger.info("Installed ECMP group on leaf dpid=%s uplinks=%s", dpid, uplinks)

    def recompute_groups_for_switch(self, dpid):
        # Re-evaluate links and update ECMP
        self.rebuild_topology()
        if self.host_ports.get(dpid):
            self.install_ecmp_group_on_leaf(dpid)

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        msg = ev.msg
        datapath = msg.datapath
        dpid = datapath.id
        parser = datapath.ofproto_parser
        ofp = datapath.ofproto
        in_port = msg.match['in_port']

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None:
            return
        dst = eth.dst
        src = eth.src

        # Learn source location
        self.mac_to_dpid[src] = dpid

        if dst in self.mac_to_dpid:
            src_dpid = self.mac_to_dpid[src]
            dst_dpid = self.mac_to_dpid[dst]
            if src_dpid != dst_dpid:
                # Cross-leaf traffic
                self.metrics.cross_leaf_traffic_bytes.labels(src_dpid=src_dpid, dst_dpid=dst_dpid).inc(len(msg.data))
                return

        # Ignore LLDP
        if eth.ethertype == 0x88cc:
            return

        # Track packet-in event
        reason_str = 'table_miss' if msg.reason == ofp.OFPR_NO_MATCH else 'action'
        if hasattr(self, 'metrics'):
            self.metrics.handle_packet_in(dpid, reason_str)

        # Learn host location on access ports
        if in_port in self.host_ports.get(dpid, set()):
            self.host_locations[src] = (dpid, in_port)

        # ARP handling
        arp_pkt = pkt.get_protocol(arp.arp)
        if arp_pkt:
            # Track ARP packet
            if hasattr(self, 'metrics'):
                self.metrics.handle_arp_packet(dpid, arp_pkt.opcode)
            self.handle_arp(datapath, in_port, eth, arp_pkt, msg)
            return

        # IP handling (ECMP across fabric)
        ip4 = pkt.get_protocol(ipv4.ipv4)
        if ip4:
            self.forward_unicast(datapath, in_port, src, dst, msg)
            return

        # Default behavior: treat as L2 unicast
        self.forward_unicast(datapath, in_port, src, dst, msg)

        # Try forwarding packet to another switch port
        try:
            actions = [parser.OFPActionOutput(ofp.OFPP_FLOOD)]
            out = parser.OFPPacketOut(datapath=datapath, buffer_id=ofproto_v1_3.OFP_NO_BUFFER, in_port=in_port, actions=actions, data=msg.data)
            datapath.send_msg(out)
        except Exception:
            self.metrics.packet_out_errors.labels(dpid=dpid).inc()

    def handle_arp(self, datapath, in_port, eth, arp_pkt, msg):
        parser = datapath.ofproto_parser
        ofp = datapath.ofproto
        dpid = datapath.id

        # Learn IP -> MAC mapping
        if arp_pkt.src_ip and eth.src:
            self.ip_to_mac[arp_pkt.src_ip] = eth.src
            # Learn source location if on a host port
            if in_port in self.host_ports.get(dpid, set()):
                self.host_locations[eth.src] = (dpid, in_port)

        # If request and we know the answer, reply
        if arp_pkt.opcode == arp.ARP_REQUEST:
            target_mac = self.ip_to_mac.get(arp_pkt.dst_ip)
            if target_mac:
                self.send_arp_reply(datapath, in_port, src_mac=target_mac,
                                    dst_mac=eth.src, src_ip=arp_pkt.dst_ip, dst_ip=arp_pkt.src_ip)
                return

        actions = []
        host_ports = self.host_ports.get(dpid, set())

        if host_ports:
            # Leaf: flood to host ports (except in_port). If came from host, also send up to spines.
            for p in host_ports:
                if p != in_port:
                    actions.append(parser.OFPActionOutput(p))
            if in_port in host_ports:
                # also send into fabric for discovery via ECMP
                actions.append(parser.OFPActionGroup(100))
        else:
            # Spine: forward ARP down to all neighbors except incoming port
            neighbor_map = self.switch_neighbors.get(dpid, {})
            for _, port_no in neighbor_map.items():
                if port_no != in_port:
                    actions.append(parser.OFPActionOutput(port_no))

        if actions:
            out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                      in_port=in_port, actions=actions,
                                      data=None if msg.buffer_id != ofp.OFP_NO_BUFFER else msg.data)
            datapath.send_msg(out)

    def send_arp_reply(self, datapath, out_port, src_mac, dst_mac, src_ip, dst_ip):
        parser = datapath.ofproto_parser
        ofp = datapath.ofproto

        e = ethernet.ethernet(dst=dst_mac, src=src_mac, ethertype=0x0806)
        a = arp.arp_ip(arp.ARP_REPLY, src_mac, src_ip, dst_mac, dst_ip)
        p = packet.Packet()
        p.add_protocol(e)
        p.add_protocol(a)
        p.serialize()

        actions = [parser.OFPActionOutput(out_port)]
        out = parser.OFPPacketOut(datapath=datapath,
                                  buffer_id=ofp.OFP_NO_BUFFER,
                                  in_port=ofp.OFPP_CONTROLLER,
                                  actions=actions,
                                  data=p.data)
        datapath.send_msg(out)

    def forward_unicast(self, datapath, in_port, src_mac, dst_mac, msg):
        parser = datapath.ofproto_parser
        ofp = datapath.ofproto
        dpid = datapath.id

        # If destination is broadcast/multicast, limit flooding to host ports
        if dst_mac == mac.BROADCAST or dst_mac.startswith('01:'):
            out_ports = [p for p in self.host_ports.get(dpid, set()) if p != in_port]
            actions = [parser.OFPActionOutput(p) for p in out_ports]
            out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                      in_port=in_port, actions=actions,
                                      data=None if msg.buffer_id != ofp.OFP_NO_BUFFER else msg.data)
            datapath.send_msg(out)
            return

        # If we know destination host location
        dst_loc = self.host_locations.get(dst_mac)
        if dst_loc:
            dst_dpid, dst_port = dst_loc
            if dst_dpid == dpid:
                # Same switch: install flow to local port
                match = parser.OFPMatch(eth_dst=dst_mac)
                actions = [parser.OFPActionOutput(dst_port)]
                self.add_flow(datapath, priority=20, match=match, actions=actions)
                self.packetout(datapath, msg, actions)
                return
            else:
                # Different leaf: on source leaf, send to ECMP group; on spines, send down to leaf
                if in_port in self.host_ports.get(dpid, set()):
                    # source leaf
                    group_id = 100
                    actions = [parser.OFPActionGroup(group_id)]
                    match = parser.OFPMatch(eth_dst=dst_mac)
                    self.add_flow(datapath, priority=15, match=match, actions=actions)
                    self.packetout(datapath, msg, actions)
                    return
                else:
                    # transit/spine: forward to port that leads to dst leaf
                    out_port = self.get_port_towards(dpid, dst_dpid)
                    if out_port:
                        actions = [parser.OFPActionOutput(out_port)]
                        match = parser.OFPMatch(eth_dst=dst_mac)
                        self.add_flow(datapath, priority=15, match=match, actions=actions)
                        self.packetout(datapath, msg, actions)
                        return

        # Unknown destination: limit flood to host ports; on leaves also send to ECMP for discovery
        out_actions = []
        for p in self.host_ports.get(dpid, set()):
            if p != in_port:
                out_actions.append(parser.OFPActionOutput(p))
        if in_port in self.host_ports.get(dpid, set()):
            # also send up into fabric for discovery
            out_actions.append(parser.OFPActionGroup(100))
        if out_actions:
            self.packetout(datapath, msg, out_actions)

    def get_port_towards(self, src_dpid, dst_dpid):
        # One hop towards destination leaf: if src is spine, choose neighbor port towards dst leaf.
        neighbors = self.switch_neighbors.get(src_dpid, {})
        if dst_dpid in neighbors:
            return neighbors[dst_dpid]
        # If src is a leaf and dst is different leaf, choose any uplink (first)
        upl = sorted(self.uplink_ports.get(src_dpid, []))
        return upl[0] if upl else None

    def packetout(self, datapath, msg, actions):
        parser = datapath.ofproto_parser
        ofp = datapath.ofproto
        out = parser.OFPPacketOut(datapath=datapath, buffer_id=msg.buffer_id,
                                  in_port=msg.match['in_port'], actions=actions,
                                  data=None if msg.buffer_id != ofp.OFP_NO_BUFFER else msg.data)
        datapath.send_msg(out)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        """Handle port statistics reply"""
        if hasattr(self, 'metrics'):
            self.metrics.handle_port_stats_reply(ev)
    
    @set_ev_cls(ofp_event.EventOFPFlowStatsReply, MAIN_DISPATCHER)
    def flow_stats_reply_handler(self, ev):
        """Handle flow statistics reply"""
        if hasattr(self, 'metrics'):
            self.metrics.handle_flow_stats_reply(ev)
    
    @set_ev_cls(ofp_event.EventOFPGroupStatsReply, MAIN_DISPATCHER)
    def group_stats_reply_handler(self, ev):
        """Handle group statistics reply"""
        if hasattr(self, 'metrics'):
            self.metrics.handle_group_stats_reply(ev)

    @set_ev_cls(ofp_event.EventOFPErrorMsg, MAIN_DISPATCHER)
    def error_msg_handler(self, ev):
        """Handle error messages"""
        if hasattr(self, 'metrics'):
            self.metrics.handle_error_msg(ev)

    def _monitor(self):
        while True:
            # Periodically refresh topology and ECMP groups to react to link changes
            try:
                self.rebuild_topology()
            except Exception as e:
                self.logger.exception("Error in monitor: %s", e)
            hub.sleep(5)
