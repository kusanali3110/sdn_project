# Grafana Configuration cho SDN Lab

Thư mục này chứa cấu hình Grafana để giám sát và phân tích hiệu suất mạng SDN

## 📁 Cấu trúc thư mục

```
grafana/
├── README.md                    # Tài liệu này
├── data/                        # Dữ liệu Grafana (database, plugins, etc.)
│   ├── csv/                     # Dữ liệu CSV được xuất
│   ├── pdf/                     # Báo cáo PDF
│   ├── png/                     # Hình ảnh được xuất
│   └── grafana.db              # Database Grafana
├── dashboards/                  # Các dashboard JSON
│   ├── sdn_executive_summary.json
│   ├── sdn_network_overview.json
│   ├── sdn_controller_performance.json
│   └── sdn_traffic_ecmp.json
└── provisioning/               # Cấu hình tự động
    ├── dashboards/
    │   └── dashboards.yaml
    └── datasources/
        └── datasource.yaml
```

## 🚀 Khởi động

Grafana được cấu hình để chạy trong Docker container thông qua `docker-compose.yaml`:

```bash
# Khởi động toàn bộ stack SDN
docker-compose up -d

# Chỉ khởi động Grafana
docker-compose up -d grafana
```

**Truy cập Grafana:** http://localhost:3000

## 📊 Dashboards

### 1. Executive Summary (`sdn_executive_summary.json`)
- **Mục đích:** Tổng quan cao cấp về tình trạng hệ thống SDN
- **Nội dung chính:**
  - Tổng quan hiệu suất controller
  - Thống kê traffic tổng thể
  - Các chỉ số KPI quan trọng
  - Cảnh báo và thông báo

### 2. Network Overview (`sdn_network_overview.json`)
- **Mục đích:** Giám sát chi tiết cấu trúc mạng
- **Nội dung chính:**
  - Topology mạng spine-leaf
  - Trạng thái các switch và link
  - Thông tin chi tiết về các node
  - Biểu đồ kết nối

### 3. Controller Performance (`sdn_controller_performance.json`)
- **Mục đích:** Phân tích hiệu suất Ryu SDN Controller
- **Nội dung chính:**
  - CPU và Memory usage
  - Số lượng flow rules
  - Thời gian xử lý packet
  - Thống kê OpenFlow messages

### 4. Traffic & ECMP (`sdn_traffic_ecmp.json`)
- **Mục đích:** Giám sát traffic và cân bằng tải ECMP
- **Nội dung chính:**
  - Lưu lượng traffic real-time
  - Phân tích ECMP load balancing
  - Thống kê bandwidth utilization
  - Biểu đồ traffic patterns

## ⚙️ Cấu hình

### Data Sources
- **Prometheus:** Nguồn dữ liệu chính (http://prometheus:9090)
  - Thu thập metrics từ Ryu controller
  - Interval: 5 giây
  - Method: POST

### Dashboard Provisioning
- **Folder:** "SDN Monitoring"
- **Auto-loading:** Tự động load dashboards từ thư mục `/etc/grafana/dashboards`
- **Editable:** Cho phép chỉnh sửa qua UI
- **Auto-update:** Tự động cập nhật khi có thay đổi

## 🔧 Tùy chỉnh

### Thêm Dashboard mới
1. Tạo file JSON dashboard trong thư mục `dashboards/`
2. Dashboard sẽ tự động được load vào Grafana
3. Có thể chỉnh sửa qua UI hoặc file JSON

### Thêm Data Source mới
1. Chỉnh sửa `provisioning/datasources/datasource.yaml`
2. Restart Grafana container

### Xuất dữ liệu
- **CSV:** Lưu trong `data/csv/`
- **PDF:** Lưu trong `data/pdf/`
- **PNG:** Lưu trong `data/png/`

## 📈 Metrics được giám sát

### Controller Metrics
- `ryu_controller_cpu_usage`
- `ryu_controller_memory_usage`
- `ryu_controller_flow_count`
- `ryu_controller_packet_processing_time`

### Network Metrics
- `switch_port_stats`
- `link_utilization`
- `traffic_throughput`
- `ecmp_distribution`

### Traffic Metrics
- `packet_count`
- `byte_count`
- `flow_duration`
- `bandwidth_utilization`

## 🐛 Troubleshooting

### Grafana không khởi động
```bash
# Kiểm tra logs
docker-compose logs grafana

# Kiểm tra quyền thư mục
ls -la grafana/data/
```

### Dashboard không hiển thị dữ liệu
1. Kiểm tra Prometheus có chạy không: http://localhost:9091
2. Kiểm tra kết nối data source
3. Xem logs: `docker-compose logs prometheus`

### Reset Grafana
```bash
# Xóa dữ liệu và khởi động lại
docker-compose down
rm -rf grafana/data/grafana.db
docker-compose up -d
```

## 📚 Tài liệu tham khảo

- [Grafana Documentation](https://grafana.com/docs/)
- [Prometheus Documentation](https://prometheus.io/docs/)
- [Ryu Controller](https://ryu.readthedocs.io/)

## 🔗 Liên kết hữu ích

- **Grafana UI:** http://localhost:3000
- **Prometheus UI:** http://localhost:9091
- **Ryu Controller API:** http://localhost:8080
