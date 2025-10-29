# Mininet SDN Lab

Thư mục này chứa các script và cấu hình để mô phỏng mạng SDN sử dụng Mininet với topology spine-leaf.

## 📁 Cấu trúc thư mục

```
mininet/
├── README.md                    # Tài liệu này
├── Dockerfile                   # Container image cho Mininet
├── .dockerignore               # Files bị loại trừ khi build Docker
├── start_wrapper.sh            # Script khởi động chính
├── auto_start.py              # Script tự động khởi tạo mạng
├── spine_leaf.py              # Định nghĩa topology spine-leaf
└── simulate_traffic.py        # Script mô phỏng traffic
```

## 🚀 Khởi động

### Sử dụng Docker Compose (Khuyến nghị)
```bash
# Khởi động toàn bộ stack SDN
docker-compose up -d

# Vào container Mininet
docker-compose exec mininet bash

# Hoặc chạy trực tiếp với các mode khác nhau
docker-compose run --rm mininet /app/start_wrapper.sh --mode interactive
```

### Các chế độ chạy

#### 1. Interactive Mode (Mặc định)
```bash
/app/start_wrapper.sh --mode interactive
```
- Khởi tạo mạng spine-leaf
- Vào Mininet CLI để tương tác thủ công
- Phù hợp cho học tập và thử nghiệm

#### 2. Continuous Mode
```bash
/app/start_wrapper.sh --mode continuous
```
- Tự động chạy traffic liên tục
- Không vào CLI, chạy background
- Phù hợp cho testing và monitoring

#### 3. Demo Mode
```bash
/app/start_wrapper.sh --mode demo
```
- Chạy demo traffic ngắn rồi vào CLI
- Phù hợp cho presentation

#### 4. Mixed Mode
```bash
/app/start_wrapper.sh --mode mixed
```
- Chạy mixed traffic trong 120 giây
- Sau đó vào CLI để phân tích

## 🏗️ Topology Spine-Leaf

### Cấu trúc mạng
![Topology](topo.png)

### Thông số kỹ thuật
- **2 Spine switches** (S1, S2)
- **3 Leaf switches** (L1, L2, L3)
- **3 hosts per leaf** (H11-H13, H21-H23, H31-H33)
- **Bandwidth:**
  - Host-Leaf: 1 Mbps
  - Leaf-Spine: 10 Mbps
- **Delay:** 1ms trên fabric links
- **Protocol:** OpenFlow 1.3

### Địa chỉ IP
- **Subnet:** 10.0.0.0/24
- **Host IPs:** 10.0.0.11-33
- **L2 connectivity** across toàn bộ fabric

## 📜 Scripts chính

### 1. `start_wrapper.sh`
Script khởi động chính với các chức năng:
- Khởi động Open vSwitch
- Cài đặt Mininet cho Python 3
- Chạy `auto_start.py` với mode được chỉ định

### 2. `auto_start.py`
Script tự động khởi tạo mạng:
- Tạo topology spine-leaf
- Kết nối với Ryu controller
- Hỗ trợ nhiều chế độ chạy
- Xử lý signal để shutdown graceful

### 3. `spine_leaf.py`
Định nghĩa topology Mininet:
- Class `SpineLeafTopo` kế thừa từ `Topo`
- Cấu hình switches với DPID cố định
- Thiết lập links với bandwidth và delay
- Hỗ trợ tham số tùy chỉnh

### 4. `simulate_traffic.py`
Script mô phỏng traffic phong phú:
- **Ping tests:** Kiểm tra kết nối cơ bản
- **Iperf tests:** Đo bandwidth
- **Mixed traffic:** Kết hợp nhiều loại traffic
- **Background processes:** Chạy traffic liên tục
- **ECMP testing:** Kiểm tra load balancing

## 🎯 Các loại traffic simulation

### Ping Tests
```python
# Ping giữa các hosts
ping_test(src_host, dst_host, count=5)
ping_all_hosts()  # Ping tất cả hosts
ping_cross_leaf()  # Ping giữa các leaf khác nhau
```

### Iperf Tests
```python
# Đo bandwidth
iperf_test(src_host, dst_host, duration=10)
iperf_all_pairs()  # Test tất cả cặp hosts
iperf_cross_leaf()  # Test giữa các leaf
```

### Mixed Traffic
```python
# Chạy nhiều loại traffic đồng thời
mixed_traffic_test(duration=60)
continuous_traffic()  # Traffic liên tục
```

## 🔧 Tùy chỉnh

### Thay đổi topology
Chỉnh sửa `spine_leaf.py`:
```python
# Thay đổi số lượng spines, leaves, hosts
topo = SpineLeafTopo(num_spines=3, num_leaves=4, hosts_per_leaf=2)
```

### Thêm traffic patterns
Chỉnh sửa `simulate_traffic.py`:
```python
def custom_traffic_test():
    # Thêm logic traffic tùy chỉnh
    pass
```

### Cấu hình bandwidth/delay
```python
# Trong spine_leaf.py
self.addLink(leaf, host, cls=TCLink, bw=5, delay='2ms')
self.addLink(leaf, spine, cls=TCLink, bw=20, delay='0.5ms')
```

## 🐛 Troubleshooting

### Mininet không khởi động
```bash
# Kiểm tra logs
docker-compose logs mininet

# Kiểm tra Open vSwitch
docker-compose exec mininet ovs-vsctl show
```

### Controller không kết nối
```bash
# Kiểm tra Ryu controller
docker-compose logs ryu

# Test kết nối từ Mininet
docker-compose exec mininet ping ryu
```

### Traffic không chạy
```bash
# Kiểm tra flow rules
docker-compose exec mininet ovs-ofctl dump-flows s1

# Kiểm tra kết nối hosts
docker-compose exec mininet pingall
```

### Reset mạng
```bash
# Dừng và xóa containers
docker-compose down

# Xóa Open vSwitch state
docker-compose exec mininet ovs-vsctl del-br s1 2>/dev/null || true
```

## 📊 Monitoring

### Xem traffic real-time
```bash
# Trong Mininet CLI
mininet> iperf h11 h21
mininet> ping h11 h31
```

### Kiểm tra flow statistics
```bash
# Xem flow rules trên switch
docker-compose exec mininet ovs-ofctl dump-flows s1
docker-compose exec mininet ovs-ofctl dump-flows l1
```

### Monitor bandwidth
```bash
# Sử dụng iperf server/client
mininet> h11 iperf -s &
mininet> h21 iperf -c 10.0.0.11
```

## 🔗 Tích hợp với hệ thống

### Kết nối với Ryu Controller
- **Controller IP:** ryu (Docker network)
- **Port:** 6653 (OpenFlow)
- **Protocol:** OpenFlow 1.3

### Metrics cho Prometheus
- Traffic statistics được thu thập bởi Ryu controller
- Metrics được expose qua port 9090
- Prometheus scrape metrics từ controller

### Grafana Dashboards
- **Network Overview:** Hiển thị topology và trạng thái
- **Traffic Analysis:** Phân tích lưu lượng
- **Performance Metrics:** Hiệu suất mạng

## 📚 Tài liệu tham khảo

- [Mininet Documentation](http://mininet.org/)
- [Open vSwitch](https://www.openvswitch.org/)
- [Ryu Controller](https://ryu.readthedocs.io/)
- [Docker Mininet](https://github.com/iwaseyusuke/docker-mininet)

## 🔗 Liên kết hữu ích

- **Mininet CLI:** `docker-compose exec mininet bash`
- **Ryu Controller:** http://localhost:8080
- **Prometheus:** http://localhost:9091
- **Grafana:** http://localhost:3000
