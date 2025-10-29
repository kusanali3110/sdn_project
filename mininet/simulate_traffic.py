#!/usr/bin/env python3
"""
Traffic Simulation Script for Spine-Leaf Topology
Usage in Mininet CLI: py exec(open('/app/simulate_traffic.py').read())
"""

import time
import random
from threading import Thread

# Global list to track background processes
background_procs = []


def get_all_hosts():
    """Get all hosts from the network topology"""
    hosts = []
    for l in range(1, 4):  # 3 leaves
        for h in range(1, 4):  # 3 hosts per leaf
            host_name = 'h{}{}'.format(l, h)
            hosts.append(net.get(host_name))
    return hosts


def get_host_pairs(exclude_same_leaf=False):
    """Generate all possible host pairs for traffic simulation"""
    hosts = get_all_hosts()
    pairs = []
    for i, src in enumerate(hosts):
        for dst in hosts[i+1:]:
            if exclude_same_leaf:
                # Extract leaf number from host name (h11 -> leaf 1)
                src_leaf = src.name[1]
                dst_leaf = dst.name[1]
                if src_leaf == dst_leaf:
                    continue
            pairs.append((src, dst))
    return pairs


def stop_all_traffic():
    """Stop all background traffic and clear iperf/ping processes"""
    print("Stopping all traffic...")
    hosts = get_all_hosts()
    
    # Kill all iperf and ping processes on all hosts
    for h in hosts:
        h.cmd('killall -9 iperf ping 2>/dev/null')
        h.cmd('killall -9 python python3 2>/dev/null')
    
    # Clear background processes list
    global background_procs
    background_procs = []
    
    print("All traffic stopped.")


def ping_test(duration=10, count=None):
    """
    Simple ping test between random host pairs
    
    Args:
        duration: How long to run (seconds)
        count: Number of pings per pair (overrides duration)
    """
    print("Starting ping test...")
    pairs = get_host_pairs()
    
    for src, dst in random.sample(pairs, min(5, len(pairs))):
        if count:
            cmd = 'ping -c {} {} &'.format(count, dst.IP())
        else:
            cmd = 'ping -i 0.5 -w {} {} &'.format(duration, dst.IP())
        
        print("  {} -> {}: {}".format(src.name, dst.name, dst.IP()))
        src.cmd(cmd)


def tcp_traffic(duration=30, port=5001):
    """
    Generate TCP traffic using iperf between multiple host pairs
    
    Args:
        duration: How long to run iperf (seconds)
        port: Starting port number (incremented for each pair)
    """
    print("Starting TCP traffic (iperf)...")
    pairs = get_host_pairs(exclude_same_leaf=False)
    
    # Select random pairs
    selected_pairs = random.sample(pairs, min(4, len(pairs)))
    
    for i, (src, dst) in enumerate(selected_pairs):
        current_port = port + i
        
        # Start iperf server on destination
        dst.cmd('iperf -s -p {} > /tmp/iperf_server_{}.log 2>&1 &'.format(
            current_port, dst.name))
        
        # Small delay to ensure server is ready
        time.sleep(0.2)
        
        # Start iperf client on source
        cmd = 'iperf -c {} -p {} -t {} -i 1 > /tmp/iperf_client_{}_{}.log 2>&1 &'.format(
            dst.IP(), current_port, duration, src.name, dst.name)
        
        print("  {} -> {} (port {})".format(src.name, dst.name, current_port))
        src.cmd(cmd)
    
    print("TCP traffic running for {} seconds...".format(duration))


def udp_traffic(duration=30, bandwidth='1M', port=5101):
    """
    Generate UDP traffic using iperf between multiple host pairs
    
    Args:
        duration: How long to run iperf (seconds)
        bandwidth: Bandwidth to use (e.g., '1M', '500K')
        port: Starting port number
    """
    print("Starting UDP traffic (iperf)...")
    pairs = get_host_pairs(exclude_same_leaf=False)
    
    # Select random pairs
    selected_pairs = random.sample(pairs, min(4, len(pairs)))
    
    for i, (src, dst) in enumerate(selected_pairs):
        current_port = port + i
        
        # Start iperf server in UDP mode on destination
        dst.cmd('iperf -s -u -p {} > /tmp/iperf_udp_server_{}.log 2>&1 &'.format(
            current_port, dst.name))
        
        time.sleep(0.2)
        
        # Start iperf client in UDP mode on source
        cmd = 'iperf -c {} -u -p {} -b {} -t {} -i 1 > /tmp/iperf_udp_client_{}_{}.log 2>&1 &'.format(
            dst.IP(), current_port, bandwidth, duration, src.name, dst.name)
        
        print("  {} -> {} (port {}, bandwidth: {})".format(
            src.name, dst.name, current_port, bandwidth))
        src.cmd(cmd)
    
    print("UDP traffic running for {} seconds...".format(duration))


def http_traffic(duration=20, interval=1):
    """
    Simulate HTTP traffic using wget/curl
    
    Args:
        duration: How long to generate traffic (seconds)
        interval: Time between requests (seconds)
    """
    print("Starting HTTP-like traffic...")
    pairs = get_host_pairs()
    selected_pairs = random.sample(pairs, min(3, len(pairs)))
    
    for src, dst in selected_pairs:
        # Start a simple HTTP server on destination (port 8000)
        dst.cmd('python3 -m http.server 8000 > /dev/null 2>&1 &')
        
        time.sleep(0.5)
        
        # Generate HTTP requests from source
        num_requests = int(duration / interval)
        cmd = '''
for i in $(seq 1 {}); do
    wget -q -O /dev/null http://{}:8000/ 2>&1 | head -1
    sleep {}
done &
'''.format(num_requests, dst.IP(), interval)
        
        print("  {} -> {} (HTTP requests every {}s)".format(
            src.name, dst.name, interval))
        src.cmd(cmd)
    
    print("HTTP traffic running for ~{} seconds...".format(duration))


def mixed_traffic(duration=60):
    """
    Generate mixed traffic patterns (TCP, UDP, ICMP) simultaneously
    
    Args:
        duration: How long to run the mixed traffic (seconds)
    """
    print("\n" + "="*60)
    print("Starting MIXED TRAFFIC simulation for {} seconds".format(duration))
    print("="*60)
    
    # Stop any existing traffic first
    stop_all_traffic()
    time.sleep(1)
    
    # Start different types of traffic
    tcp_traffic(duration=duration, port=5001)
    time.sleep(1)
    
    udp_traffic(duration=duration, bandwidth='500K', port=5101)
    time.sleep(1)
    
    ping_test(duration=duration)
    time.sleep(1)
    
    http_traffic(duration=duration, interval=2)
    
    print("\nAll traffic types started. Running for {} seconds...".format(duration))
    print("Use stop_all_traffic() to stop all traffic immediately.")


def elephant_mouse_traffic(duration=30):
    """
    Simulate elephant flows (large, long-lived) and mouse flows (small, short-lived)
    
    Args:
        duration: How long to run the simulation (seconds)
    """
    print("\n" + "="*60)
    print("Starting ELEPHANT-MOUSE TRAFFIC simulation")
    print("="*60)
    
    stop_all_traffic()
    time.sleep(1)
    
    pairs = get_host_pairs()
    
    # Elephant flows: Large TCP transfers
    print("\nStarting ELEPHANT FLOWS (large TCP transfers)...")
    elephant_pairs = random.sample(pairs, min(2, len(pairs)))
    for i, (src, dst) in enumerate(elephant_pairs):
        port = 5201 + i
        dst.cmd('iperf -s -p {} > /dev/null 2>&1 &'.format(port))
        time.sleep(0.2)
        # High bandwidth, long duration
        src.cmd('iperf -c {} -p {} -t {} -i 2 > /tmp/elephant_{}_{}.log 2>&1 &'.format(
            dst.IP(), port, duration, src.name, dst.name))
        print("  ELEPHANT: {} -> {} (port {})".format(src.name, dst.name, port))
    
    # Mouse flows: Small, frequent TCP connections
    print("\nStarting MOUSE FLOWS (small, frequent transfers)...")
    mouse_pairs = random.sample(pairs, min(4, len(pairs)))
    for i, (src, dst) in enumerate(mouse_pairs):
        port = 5301 + i
        dst.cmd('iperf -s -p {} > /dev/null 2>&1 &'.format(port))
        time.sleep(0.2)
        
        # Short bursts every few seconds
        cmd = '''
for i in $(seq 1 {}); do
    iperf -c {} -p {} -t 1 -i 1 >> /tmp/mouse_{}_{}.log 2>&1
    sleep 3
done &
'''.format(int(duration/4), dst.IP(), port, src.name, dst.name)
        
        src.cmd(cmd)
        print("  MOUSE: {} -> {} (port {})".format(src.name, dst.name, port))
    
    print("\nElephant-Mouse traffic running for {} seconds...".format(duration))


def incast_traffic(target_host='h11', duration=15):
    """
    Simulate incast traffic: multiple sources sending to one destination
    
    Args:
        target_host: Destination host name (default: 'h11')
        duration: How long to run (seconds)
    """
    print("\n" + "="*60)
    print("Starting INCAST TRAFFIC to {}".format(target_host))
    print("="*60)
    
    stop_all_traffic()
    time.sleep(1)
    
    dst = net.get(target_host)
    all_hosts = get_all_hosts()
    
    # All other hosts send to target
    sources = [h for h in all_hosts if h.name != target_host]
    
    # Start iperf servers on target host (multiple ports)
    for i in range(len(sources)):
        port = 5401 + i
        dst.cmd('iperf -s -p {} > /dev/null 2>&1 &'.format(port))
    
    time.sleep(0.5)
    
    # All sources send to target simultaneously
    print("\nSources sending to {}:".format(target_host))
    for i, src in enumerate(sources):
        port = 5401 + i
        src.cmd('iperf -c {} -p {} -t {} -i 1 > /tmp/incast_{}_{}.log 2>&1 &'.format(
            dst.IP(), port, duration, src.name, dst.name))
        print("  {} -> {}".format(src.name, target_host))
    
    print("\nIncast traffic running for {} seconds...".format(duration))


def cross_leaf_traffic(duration=30):
    """
    Generate traffic only between hosts on different leaves
    
    Args:
        duration: How long to run (seconds)
    """
    print("\n" + "="*60)
    print("Starting CROSS-LEAF TRAFFIC (inter-leaf only)")
    print("="*60)
    
    stop_all_traffic()
    time.sleep(1)
    
    # Get pairs from different leaves only
    pairs = get_host_pairs(exclude_same_leaf=True)
    selected_pairs = random.sample(pairs, min(6, len(pairs)))
    
    for i, (src, dst) in enumerate(selected_pairs):
        port = 5501 + i
        dst.cmd('iperf -s -p {} > /dev/null 2>&1 &'.format(port))
        time.sleep(0.2)
        
        src.cmd('iperf -c {} -p {} -t {} -i 1 > /tmp/cross_leaf_{}_{}.log 2>&1 &'.format(
            dst.IP(), port, duration, src.name, dst.name))
        
        print("  {} (leaf {}) -> {} (leaf {})".format(
            src.name, src.name[1], dst.name, dst.name[1]))
    
    print("\nCross-leaf traffic running for {} seconds...".format(duration))


def continuous_traffic(interval=60):
    """
    Start continuous mixed traffic that runs indefinitely
    Call stop_all_traffic() to stop
    
    Args:
        interval: Duration of each traffic cycle (seconds)
    """
    print("\n" + "="*60)
    print("Starting CONTINUOUS TRAFFIC (runs indefinitely)")
    print("Call stop_all_traffic() to stop")
    print("="*60)
    
    def traffic_loop():
        cycle = 1
        while True:
            try:
                print("\n--- Traffic Cycle {} ---".format(cycle))
                mixed_traffic(duration=interval)
                time.sleep(interval + 5)  # Wait for traffic to finish
                cycle += 1
            except Exception as e:
                print("Traffic loop error: {}".format(e))
                break
    
    thread = Thread(target=traffic_loop, daemon=True)
    thread.start()
    print("Continuous traffic started in background thread.")


# Convenience functions
def demo():
    """Run a quick demo of different traffic patterns"""
    print("\n" + "="*70)
    print(" TRAFFIC SIMULATION DEMO")
    print("="*70)
    
    print("\n1. Testing basic connectivity with ping...")
    ping_test(count=3)
    time.sleep(5)
    
    print("\n2. Running TCP traffic for 15 seconds...")
    tcp_traffic(duration=15)
    time.sleep(17)
    
    print("\n3. Running UDP traffic for 15 seconds...")
    udp_traffic(duration=15, bandwidth='800K')
    time.sleep(17)
    
    print("\n4. Running HTTP-like traffic for 10 seconds...")
    http_traffic(duration=10, interval=1)
    time.sleep(12)
    
    print("\n5. Cleaning up...")
    stop_all_traffic()
    
    print("\n" + "="*70)
    print(" DEMO COMPLETE")
    print("="*70)


def show_help():
    """Display available functions and usage"""
    help_text = """
╔══════════════════════════════════════════════════════════════════╗
║          TRAFFIC SIMULATION FUNCTIONS - HELP                     ║
╚══════════════════════════════════════════════════════════════════╝

Available Functions:
────────────────────────────────────────────────────────────────────

📊 BASIC TRAFFIC:
  ping_test(duration=10, count=None)
    - Simple ICMP ping test between random hosts
  
  tcp_traffic(duration=30, port=5001)
    - Generate TCP traffic using iperf
  
  udp_traffic(duration=30, bandwidth='1M', port=5101)
    - Generate UDP traffic using iperf

  http_traffic(duration=20, interval=1)
    - Simulate HTTP traffic using wget

🔀 ADVANCED PATTERNS:
  mixed_traffic(duration=60)
    - Run TCP, UDP, ICMP, and HTTP traffic simultaneously
  
  elephant_mouse_traffic(duration=30)
    - Simulate large long-lived flows and small short-lived flows
  
  incast_traffic(target_host='h11', duration=15)
    - Multiple sources send to one destination
  
  cross_leaf_traffic(duration=30)
    - Traffic only between different leaf switches
  
  continuous_traffic(interval=60)
    - Run continuous traffic indefinitely (runs in background)

🛠️  UTILITY:
  stop_all_traffic()
    - Stop all running traffic and clean up processes
  
  demo()
    - Run a quick demonstration of different traffic types
  
  show_help()
    - Display this help message

────────────────────────────────────────────────────────────────────
USAGE EXAMPLES:

  mininet> py exec(open('/app/simulate_traffic.py').read())
  mininet> py mixed_traffic(duration=60)
  mininet> py stop_all_traffic()
  mininet> py incast_traffic(target_host='h23', duration=20)

────────────────────────────────────────────────────────────────────
"""
    print(help_text)


# Auto-display help on load
print("\n✓ Traffic simulation script loaded successfully!")
print("  Type: py show_help() for available functions")
print("  Quick start: py demo()")
print("  Mixed traffic: py mixed_traffic(60)")
print()

