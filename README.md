# SDN Monitoring System

A comprehensive Software-Defined Networking (SDN) laboratory environment featuring automated traffic generation, real-time monitoring, and advanced visualization capabilities. Built with Mininet, Ryu SDN controller, Prometheus metrics collection, and Grafana dashboards.

## ✨ Features

- **🏗️ Complete SDN Lab Environment**: Pre-configured Mininet topology with spine-leaf architecture
- **🎛️ Ryu SDN Controller**: Custom controller with advanced routing and monitoring capabilities
- **📊 Real-time Monitoring**: Prometheus metrics collection from SDN switches
- **📈 Advanced Visualization**: Grafana dashboards for network performance analysis
- **🚀 Automated Traffic Generation**: Random traffic patterns with multiple protocols (TCP, UDP, ICMP)
- **🔄 Flow Management**: Web-based interface for flow rule management
- **🐳 Containerized**: Fully dockerized environment for easy deployment
- **📈 Performance Metrics**: Comprehensive network statistics and analytics

### Network Topology

The lab implements a spine-leaf data center topology with:
- **2 Spine Switches**: Core layer for inter-rack connectivity
- **4 Leaf Switches**: Edge layer connecting to servers
- **6 Hosts**: Simulating end devices (h1-h6)

![Network Topology](./mininet/topo.png)

## 📋 Prerequisites

- **Docker**: Version 20.10 or later
- **Docker Compose**: Version 2.0 or later
- **Git**: For cloning the repository
- **Web Browser**: For accessing web interfaces
- **Minimum System Requirements**:
  - CPU: 2 cores
  - RAM: 4GB
  - Disk: 2GB free space

### Installing Prerequisites

**Ubuntu/Debian:**
```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

**Windows:**
```powershell
# Install Docker Desktop from https://www.docker.com/products/docker-desktop
# Docker Compose is included with Docker Desktop
```

## 📖 Get started

### Step 1: Environment Setup

```bash
# Clone repository
git clone https://github.com/kusanali3110/sdn_project
cd sdn_project

# Start all services
docker-compose up -d

# Verify all containers are running
docker ps -a
```

### Step 2: Network Topology Setup

```bash
# Access Mininet container
docker exec -it mininet bash

# Create network topology with Ryu controller
mn --custom /app/spine_leaf.py --topo spineleaf --controller remote,ip=ryu,port=6653 --switch ovsk,protocols=OpenFlow13
```

### Step 3: Traffic Generation

Once inside the Mininet CLI after setting up network tpopology (`mininet>` prompt):

```bash
# Start automated traffic generation
mininet> py exec(open('/app/traffic_generator.py').read())
```

The traffic generator will:
- Generate random TCP/UDP/Ping traffic
- Use random source/destination pairs
- Apply random bandwidth and timing parameters
- Run continuously until stopped (Ctrl+C)

## 🌐 Services & Endpoints

After getting through above instructions, there are endpoints which will be available:

| Service | URL | Description | Credentials |
|---------|-----|-------------|-------------|
| **Grafana** | http://localhost:3000 | Visualization & Dashboards | admin/admin |
| **Flow Manager** | http://localhost:8080/home/index.html | SDN Flow Management | - |
| **Prometheus** | http://localhost:9091 | Metrics Collection | - |
| **Metrics** | http://localhost:9090/metrics | Raw Metrics Endpoint | - |

### Default Ports Mapping

- **Ryu Controller**: Container port 6653 → Host port 6653
- **Flow Manager**: Container port 8080 → Host port 8080
- **Prometheus**: Container port 9090 → Host port 9091
- **Grafana**: Container port 3000 → Host port 3000
- **Metrics Exporter**: Container port 8000 → Host port 9090

## 📊 Monitoring & Visualization

### Flow Management

Access the Flow Manager web interface at http://localhost:8080/home/index.html to:
- View current flow rules
- Add/modify flow entries
- Monitor switch statistics
- Manage SDN policies

### Grafana Dashboards

The system will run at http://localhost:3000 which includes three pre-configured dashboards:

1. **Network Monitoring**: Real-time network topology and status
2. **Performance Analysis**: Detailed performance metrics and trends
3. **Traffic Analysis**: Traffic patterns and protocol analysis

### Key Metrics Monitored

- **Switch Statistics**: Port counters, flow table utilization
- **Traffic Metrics**: Bandwidth usage, packet rates, protocol distribution
- **Network Performance**: Latency, jitter, packet loss
- **Flow Rules**: Active flows, rule hit counts, aging statistics

### Prometheus Metrics

Raw metrics are available at http://localhost:9090/metrics including:
- OpenFlow port statistics
- Flow table information
- Switch capabilities
- Traffic counters

---
