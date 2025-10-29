#!/usr/bin/env python3
"""
Auto-start script for Mininet SDN Lab
Automatically starts topology and traffic simulation
"""

import sys
import time
import signal
from mininet.net import Mininet
from mininet.node import RemoteController
from mininet.cli import CLI
from mininet.log import setLogLevel, info
from mininet.link import TCLink

# Import custom topology
sys.path.insert(0, '/app')
from spine_leaf import SpineLeafTopo

# Global variable for cleanup
net = None

def signal_handler(sig, frame):
    """Handle Ctrl+C gracefully"""
    info('\n*** Shutting down network...\n')
    if net:
        net.stop()
    sys.exit(0)

def start_network():
    """Start Mininet network with spine-leaf topology"""
    global net
    
    info('*** Creating Spine-Leaf Network\n')
    
    # Create topology
    topo = SpineLeafTopo(num_spines=2, num_leaves=3, hosts_per_leaf=3)
    
    # Create network with remote controller
    net = Mininet(
        topo=topo,
        controller=None,
        link=TCLink,
        autoSetMacs=True,
        autoStaticArp=False
    )
    
    # Add remote controller (Ryu)
    info('*** Adding remote controller\n')
    net.addController(
        'c0',
        controller=RemoteController,
        ip='ryu',
        port=6653
    )
    
    # Start network
    info('*** Starting network\n')
    net.start()
    
    # Wait for controller connection
    info('*** Waiting for controller connection...\n')
    time.sleep(3)
    
    # Test connectivity
    info('*** Testing connectivity\n')
    net.pingAll()
    
    return net

def start_traffic_simulation(net, mode='continuous'):
    """
    Start traffic simulation
    
    Args:
        net: Mininet network instance
        mode: 'continuous', 'demo', or 'mixed'
    """
    info('\n*** Starting traffic simulation\n')
    
    # Make network accessible to traffic script
    import builtins
    builtins.net = net
    
    # Load traffic simulation script
    try:
        with open('/app/simulate_traffic.py', 'r') as f:
            exec(f.read(), globals())
        
        info('*** Traffic simulation script loaded\n')
        
        # Start traffic based on mode
        if mode == 'continuous':
            info('*** Running continuous mixed traffic (60s cycles)\n')
            continuous_traffic(interval=60)
        elif mode == 'demo':
            info('*** Running demo traffic pattern\n')
            demo()
        elif mode == 'mixed':
            info('*** Running mixed traffic for 120 seconds\n')
            mixed_traffic(duration=120)
        else:
            info('*** Traffic mode not recognized, running mixed traffic\n')
            mixed_traffic(duration=60)
            
    except Exception as e:
        info(f'*** Error loading traffic simulation: {e}\n')

def interactive_mode(net):
    """Enter interactive CLI mode"""
    info('\n*** Entering interactive mode\n')
    info('*** Use traffic simulation commands:\n')
    info('    mininet> py mixed_traffic(60)\n')
    info('    mininet> py demo()\n')
    info('    mininet> py continuous_traffic()\n')
    info('    mininet> py stop_all_traffic()\n')
    info('    mininet> py show_help()\n')
    info('\n')
    
    CLI(net)

def main():
    """Main function"""
    # Set log level
    setLogLevel('info')
    
    # Register signal handler for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Parse command line arguments
    import argparse
    parser = argparse.ArgumentParser(description='Auto-start Mininet SDN Lab')
    parser.add_argument(
        '--mode',
        choices=['interactive', 'continuous', 'demo', 'mixed'],
        default='interactive',
        help='Operation mode (default: interactive)'
    )
    parser.add_argument(
        '--no-traffic',
        action='store_true',
        help='Start network without traffic simulation'
    )
    args = parser.parse_args()
    
    info('\n')
    info('='*70 + '\n')
    info('  Mininet SDN Lab - Auto Start\n')
    info('  Spine-Leaf Topology with Traffic Simulation\n')
    info('='*70 + '\n')
    info('\n')
    
    try:
        # Start network
        net = start_network()
        
        # Make network globally accessible
        import builtins
        builtins.net = net
        
        # Load traffic simulation functions
        if not args.no_traffic:
            try:
                with open('/app/simulate_traffic.py', 'r') as f:
                    exec(f.read(), globals())
                info('*** Traffic simulation functions loaded\n')
            except Exception as e:
                info(f'*** Warning: Could not load traffic simulation: {e}\n')
        
        # Execute based on mode
        if args.mode == 'interactive':
            # Interactive mode with CLI
            interactive_mode(net)
        elif args.mode == 'continuous':
            # Continuous traffic - runs indefinitely
            info('*** Starting continuous traffic simulation\n')
            info('*** Press Ctrl+C to stop\n\n')
            start_traffic_simulation(net, mode='continuous')
            # Keep running
            while True:
                time.sleep(1)
        elif args.mode == 'demo':
            # Run demo then enter CLI
            start_traffic_simulation(net, mode='demo')
            info('\n*** Demo complete, entering interactive mode\n')
            interactive_mode(net)
        elif args.mode == 'mixed':
            # Run mixed traffic then enter CLI
            start_traffic_simulation(net, mode='mixed')
            info('\n*** Mixed traffic complete, entering interactive mode\n')
            interactive_mode(net)
        
    except Exception as e:
        info(f'\n*** Error: {e}\n')
        import traceback
        traceback.print_exc()
    finally:
        # Cleanup
        if net:
            info('\n*** Stopping network\n')
            net.stop()

if __name__ == '__main__':
    main()

