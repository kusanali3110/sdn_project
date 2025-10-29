
# Ryu Controller cho SDN Lab

Thư mục này chứa Ryu SDN Controller tùy biến cho topology spine-leaf, tích hợp FlowManager và exporter Prometheus.

## Nội dung
- `spine_leaf_controller.py`: Logic điều khiển (OpenFlow 1.3), học host, quản lý uplink/host ports, xử lý ARP/IPv4, cài đặt flows và theo dõi topology.
- `metrics_exporter.py`: HTTP `/metrics` (Prometheus) cung cấp số liệu về switch, ports, flows, traffic, topology, ECMP, hiệu năng controller.
- `Dockerfile`: Image cài đặt Ryu từ source, thêm FlowManager, copy controller và exporter, expose ports.
- `requirements.txt`: Phụ thuộc Python (Prometheus client).

## Cổng dịch vụ
- 6653: OpenFlow (controller)
- 8080: FlowManager UI/API (`/home/index.html`)
- 9090: Prometheus metrics exporter (`/metrics`)

## Cách chạy (qua Docker Compose)
Controller được khởi chạy bởi `docker-compose.yaml` ở thư mục gốc dự án:
```bash
docker-compose up -d ryu
docker-compose logs -f ryu
```

## Tích hợp
- Mininet kết nối controller trên `ryu:6653` (Docker network).
- Prometheus scrape metrics tại `ryu:9090` (job `sdn_controller`).
- Grafana dùng Prometheus làm data source để hiển thị dashboards SDN.

## Kiểm tra nhanh
1) Kiểm tra controller lắng nghe cổng OF: `nc -zv localhost 6653`
2) Mở FlowManager: `http://localhost:8080`
3) Kiểm tra metrics: `curl http://localhost:9090/metrics`


