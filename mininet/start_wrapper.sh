#!/bin/bash
# Wrapper script to start OVS and run auto_start.py
# This bypasses the Mininet ENTRYPOINT.sh issue

set -e

echo "=================================="
echo "  Mininet SDN Lab - Starting..."
echo "=================================="

# Start Open vSwitch if not already running
echo "* Starting Open vSwitch..."
service openvswitch-switch start
ovs-vsctl set-manager ptcp:6640

# Wait a moment for OVS to fully start
sleep 1

echo "* Open vSwitch started successfully"
echo ""

# Parse command line arguments
MODE="interactive"

while [[ $# -gt 0 ]]; do
    case $1 in
        --mode)
            MODE="$2"
            shift 2
            ;;
        *)
            echo "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Check if Mininet is available for Python 3
echo "* Checking Mininet availability..."
if ! python3 -c "import mininet" 2>/dev/null; then
    echo "  - Mininet not found for Python 3, installing..."
    
    # Try multiple installation methods
    if pip3 install mininet 2>/dev/null; then
        echo "  - Installed via pip3"
    elif [ -d "/usr/lib/python2.7/dist-packages/mininet" ]; then
        echo "  - Creating symlink from Python 2 installation..."
        # Find Python 3 site-packages directory
        PY3_SITE=$(python3 -c "import site; print(site.getsitepackages()[0])" 2>/dev/null)
        if [ -n "$PY3_SITE" ]; then
            ln -sf /usr/lib/python2.7/dist-packages/mininet "$PY3_SITE/mininet"
            echo "  - Symlink created at $PY3_SITE/mininet"
        fi
    else
        echo "  - Warning: Could not install Mininet, script may fail"
    fi
else
    echo "  - Mininet is available"
fi

# Run the auto_start.py script
echo ""
echo "* Running auto_start.py with mode: $MODE"
echo ""

exec python3 /app/auto_start.py --mode "$MODE"

