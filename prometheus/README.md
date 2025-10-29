# Prometheus cho SDN Lab

Thư mục này chứa cấu hình Prometheus để thu thập metrics từ Ryu SDN Controller và lưu trữ dữ liệu phục vụ giám sát (Grafana).

## Nội dung
- `prometheus.yaml`: Cấu hình Prometheus
- `data/`: Thư mục dữ liệu (TSDB) được mount để lưu trữ

## Cấu hình chính
- Job: `sdn_controller`
- Target: `ryu:9090`
- Global scrape: 15s; Job scrape: 5s; Timeout: 4s

## Cách chạy nhanh
```bash
docker-compose up -d           # Khởi động toàn bộ stack
docker-compose logs -f prometheus
```

## Truy cập
- UI Prometheus: http://localhost:9091
- Grafana dùng Prometheus tại `http://prometheus:9090`

## Kiểm tra nhanh
1) Vào tab Targets, đảm bảo `sdn_controller` UP
2) Thử query: `up`, `process_cpu_seconds_total`, các metrics từ controller

## Sự cố thường gặp
- Target DOWN: kiểm tra container `ryu` và endpoint `ryu:9090`
- Không có dữ liệu: kiểm tra mounts và logs của Prometheus
