# 🚀 SDN Lab - Quick Start Guide

Hệ thống SDN Lab với Spine-Leaf topology, Ryu controller, và monitoring stack (Prometheus + Grafana).

## 📦 Yêu cầu hệ thống

- Docker & Docker Compose
- RAM: 4GB+ khuyến nghị
- CPU: 2 cores+
- Disk: 5GB free space

## ⚡ Khởi động nhanh (3 bước)

### 1. Clone và khởi động

```bash
# Di chuyển vào thư mục project
cd sdn_lab

# Khởi động toàn bộ hệ thống
docker-compose up -d
```

### 2. Kiểm tra services

```bash
# Kiểm tra containers đang chạy
docker ps

# Bạn sẽ thấy 4 containers:
# - ryu_controller (port 6653, 8080, 9090)
# - mininet (auto-start với topology)
# - prometheus (port 9091)
# - grafana (port 3000)
```

### 3. Truy cập Dashboards

- **Flow manager:** http://localhost:8080/home/index.html

- **Metrics:** http://localhost:9090/metrics 

- **Grafana:** http://localhost:3000
  - Username: `admin`
  - Password: `admin` (đổi khi đăng nhập lần đầu)
  - Dashboards → SDN Monitoring folder

- **Prometheus:** http://localhost:9091
  - Xem metrics và queries

## 🎮 Sử dụng Mininet

### Mode mặc định: Interactive

Container Mininet tự động khởi động với topology và vào CLI mode:

```bash
# Attach vào Mininet CLI
docker attach mininet

# Bạn sẽ thấy:
# mininet>
```

### Chạy traffic simulation

```bash
# Trong Mininet CLI:
mininet> py show_help()              # Xem tất cả commands
mininet> py mixed_traffic(60)        # Mixed traffic 60 giây
mininet> py demo()                   # Chạy demo
mininet> pingall                     # Test connectivity
```

### Thoát CLI mà không dừng container

Nhấn: `Ctrl+P` sau đó `Ctrl+Q`

## 🔄 Các chế độ tự động khác

Edit file `docker-compose.yaml` để thay đổi mode:

### Continuous Traffic (Tự động liên tục)

```yaml
# Trong docker-compose.yaml, section mininet:
command: /app/start_wrapper.sh --mode continuous
```

```bash
# Restart container
docker-compose restart mininet

# Traffic sẽ tự động chạy liên tục
# Mở Grafana để xem real-time metrics
```

### Demo Mode

```yaml
command: /app/start_wrapper.sh --mode demo
```

Chạy demo các loại traffic rồi vào CLI.

### Mixed Traffic Mode

```yaml
command: /app/start_wrapper.sh --mode mixed
```

Chạy mixed traffic 120s rồi vào CLI.

## 📊 Xem Metrics trên Grafana

1. Mở browser: http://localhost:3000
2. Login (admin/admin)
3. Vào: Dashboards → SDN Monitoring
4. Chọn dashboard:
   - **SDN Executive Summary** - Overview
   - **SDN Network Overview** - Topology details
   - **SDN Traffic & ECMP** - Traffic analysis
   - **SDN Controller Performance** - Controller metrics

## 🛠️ Commands hữu ích

### Xem logs

```bash
# Mininet logs
docker logs mininet -f

# Ryu controller logs
docker logs ryu_controller -f

# Prometheus logs
docker logs prometheus -f

# Grafana logs
docker logs grafana -f
```

### Restart services

```bash
# Restart một service
docker-compose restart mininet
docker-compose restart ryu

# Restart tất cả
docker-compose restart
```

### Dừng hệ thống

```bash
# Dừng containers (giữ data)
docker-compose stop

# Dừng và xóa containers
docker-compose down

# Dừng và xóa cả volumes (xóa data)
docker-compose down -v
```

### Rebuild containers

```bash
# Rebuild Ryu controller
docker-compose build ryu
docker-compose up -d ryu

# Force recreate containers
docker-compose up -d --force-recreate
```

## 🎯 Use Cases phổ biến

### 1. Development & Testing

```bash
# Mode: Interactive (mặc định)
docker-compose up -d
docker attach mininet

# Trong CLI:
mininet> py mixed_traffic(60)
mininet> py elephant_mouse_traffic(30)
```

### 2. Monitoring liên tục

```yaml
# docker-compose.yaml
command: python3 /app/auto_start.py --mode continuous
```

```bash
docker-compose up -d
# Mở Grafana → Watch dashboards update real-time
```

### 3. Demo presentation

```yaml
command: python3 /app/auto_start.py --mode demo
```

```bash
docker-compose up -d
docker logs mininet -f  # Xem demo
```

## 🏗️ Kiến trúc hệ thống

```
┌─────────────────────────────────────────────────────┐
│                Monitoring Stack                     │
│  ┌──────────────┐            ┌──────────────┐       │
│  │   Grafana    │◄───────────│  Prometheus  │       │
│  │  (port 3000) │            │  (port 9091) │       │
│  └──────────────┘            └───────┬──────┘       │
│                                      │              │
│                              Scrape metrics (5s)    │
└──────────────────────────────────────┼──────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────┐
│                  SDN Controller                     │
│    ┌──────────────────────────────────────────┐     │
│    │         Ryu Controller + Metrics         │     │
│    │     (OpenFlow: 6653, Metrics: 9090)      │     │
│    └──────────────┬───────────────────────────┘     │
└───────────────────┼─────────────────────────────────┘
                    │ OpenFlow Protocol
                    ▼
┌─────────────────────────────────────────────────────┐
│                 Mininet                             |
│    ┌──────────────────────────────────────────┐     │
│    │    Spine-leaf Topo + Simulate traffic    │     │
│    └──────────────────────────────────────────┘     │
└─────────────────────────────────────────────────────┘
```

## 📋 Topology Details

![Topology](./mininet/topo.png)

- **2 Spine switches** (S1, S2) - DPID 1-2
- **3 Leaf switches** (L1, L2, L3) - DPID 3-5
- **9 Hosts** (h11-h13, h21-h23, h31-h33)
- **IP range:** 10.0.0.0/24
- **Links:** 
  - Spine-Leaf: 10 Mbps, 1ms delay
  - Leaf-Host: 1 Mbps
- **ECMP:** Load balancing across spine switches

## 🔍 Troubleshooting

### Container không start

```bash
# Xem logs
docker logs mininet
docker logs ryu_controller

# Check network
docker network ls
docker network inspect sdn_lab_sdn_net
```

### Không kết nối được Grafana

```bash
# Kiểm tra port
netstat -an | grep 3000

# Restart Grafana
docker-compose restart grafana

# Check logs
docker logs grafana
```

### Metrics không hiển thị

```bash
# Kiểm tra Prometheus targets
# Mở: http://localhost:9091/targets
# Ryu endpoint (ryu:9090) phải UP

# Test metrics endpoint trực tiếp
docker exec -it ryu_controller curl http://localhost:9090/metrics
```

### Reset toàn bộ hệ thống

```bash
# Dừng và xóa tất cả
docker-compose down -v

# Xóa data directories (optional)
sudo rm -rf grafana/data/* prometheus/data/*

# Khởi động lại
docker-compose up -d
```

## 📚 Tài liệu chi tiết

- [**Mininet**](./mininet/README.md)
- [**Ryu controller**](./ryu_controller/README.md) 
- [**Prometheus**](./prometheus/README.md)
- [**Grafana**](./grafana/README.md)

