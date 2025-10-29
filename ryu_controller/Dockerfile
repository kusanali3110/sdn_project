FROM python:3.8-alpine

RUN apk add --virtual .build-dependencies \
    gcc \
    git \
    libffi-dev \
    libgcc \
    libxslt-dev \
    libxml2-dev \
    make \
    musl-dev \
    openssl-dev \
    zlib-dev

# Cài đặt Ryu
RUN git clone https://github.com/faucetsdn/ryu.git && \
    cd ryu && \
    pip install . && \
    pip install -r tools/optional-requires && \
    cd ..

# Cài đặt FlowManager
RUN git clone https://github.com/martimy/flowmanager.git

# Copy custom controller
COPY spine_leaf_controller.py /app/spine_leaf_controller.py

# Cài đặt các thư viện cần thiết
COPY requirements.txt /app/requirements.txt
RUN pip3 install -r /app/requirements.txt

# Copy metrics_exporter
COPY metrics_exporter.py /app/metrics_exporter.py

# Mở cổng OpenFlow (mặc định của Ryu là 6653)
EXPOSE 6653
# Mở cổng FlowManager
EXPOSE 8080
# Mở cổng Prometheus
EXPOSE 9100

# Chạy ứng dụng cùng flowmanager và metrics exporter
CMD ["ryu-manager", "--observe-links", "flowmanager/flowmanager.py", "/app/spine_leaf_controller.py", "/app/metrics_exporter.py"]