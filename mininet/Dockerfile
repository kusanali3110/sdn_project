# Dockerfile cho Mininet với Python 3 support (https://github.com/iwaseyusuke/docker-mininet)
FROM iwaseyusuke/mininet:ubuntu-20.04

# Cập nhật danh sách package và cài đặt Python 3 dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-setuptools \
    wget \
    netcat \
    && rm -rf /var/lib/apt/lists/*

# Cài đặt Mininet cho Python 3
RUN pip3 install mininet PyYAML || \
    (ln -s /usr/lib/python2.7/dist-packages/mininet /usr/local/lib/python3.8/dist-packages/mininet 2>/dev/null || true)

# Kiểm tra Mininet có khả dụng cho Python 3
RUN python3 -c "import mininet; print('Mininet imported successfully')" || \
    echo "Warning: Mininet not available for Python 3 yet, will be handled by startup script"

# Thiết lập working directory
WORKDIR /app

# Sao chép file start.sh vào container
COPY start.sh /start.sh
# Cấp quyền thực thi cho file start.sh
RUN chmod +x /start.sh

ENTRYPOINT ["/start.sh"]
