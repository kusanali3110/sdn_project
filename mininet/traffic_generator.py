from mininet.net import Mininet
from mininet.log import setLogLevel, info
import time
import random
import signal
import sys

setLogLevel("info")

# Signal handler for graceful shutdown
def signal_handler(sig, frame):
    info("\n*** Stopping traffic generator...\n")
    # Kill all running iperf processes
    for h in hosts:
        h.cmd("pkill -f iperf")
    info("*** Traffic generator stopped\n")
    sys.exit(0)

signal.signal(signal.SIGINT, signal_handler)

# Get hosts
host_names = ["h1", "h2", "h3", "h4", "h5", "h6"]
hosts = []
for h in host_names:
    hosts.append(net.get(h))

# Traffic protocols and parameters
protocols = ['tcp', 'udp', 'ping']
tcp_streams_options = [1, 2, 4, 8]
bandwidth_options = [50, 100, 200, 500, 1000]  # Kbps
ping_count_options = [5, 10, 20]

info("*** Starting continuous traffic generator (Ctrl+C to stop)\n")

# Start iperf server on all hosts for TCP/UDP traffic
for h in hosts:
    h.cmd("iperf -s -D")  # -D runs in daemon mode

# Main traffic generation loop
while True:
    # Randomly select protocol
    protocol = random.choice(protocols)

    # Randomly select source and destination (ensure they're different)
    src_host = random.choice(hosts)
    dst_host = random.choice(hosts)
    while dst_host == src_host:
        dst_host = random.choice(hosts)

    if protocol in ['tcp', 'udp']:
        # Generate iperf traffic
        duration = random.randint(5, 30)  # Random duration 5-30 seconds
        streams = random.choice(tcp_streams_options)
        bandwidth = random.choice(bandwidth_options)

        protocol_flag = "-u" if protocol == 'udp' else ""
        bandwidth_str = f"{bandwidth}K"

        info(f"*** Starting {protocol.upper()} traffic: {src_host.name} -> {dst_host.name} "
             f"(duration: {duration}s, streams: {streams}, bandwidth: {bandwidth}K)\n")

        src_host.cmd(
            f"iperf -c {dst_host.IP()} -t {duration} {protocol_flag} -P {streams} -b {bandwidth_str} "
            f"-M 1400 > /dev/null 2>&1 &"
        )

    elif protocol == 'ping':
        # Generate ping traffic
        count = random.choice(ping_count_options)
        interval = random.uniform(0.1, 1.0)  # Random interval between pings

        info(f"*** Starting PING traffic: {src_host.name} -> {dst_host.name} "
             f"(count: {count}, interval: {interval:.1f}s)\n")

        src_host.cmd(
            f"ping -c {count} -i {interval} {dst_host.IP()} > /dev/null 2>&1 &"
        )

    # Wait for random cycle time (1-5 seconds)
    cycle_time = random.uniform(1, 5)
    info(f"*** Waiting {cycle_time:.1f} seconds before next traffic...\n")
    time.sleep(cycle_time)