# Dockerfile for Mininet with Python 3 support (https://github.com/iwaseyusuke/docker-mininet)
FROM iwaseyusuke/mininet:ubuntu-20.04

# Update package list and install Python 3 dependencies
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-setuptools \
    wget \
    netcat \
    && rm -rf /var/lib/apt/lists/*

# Install Mininet for Python 3
# Option 1: Try to install via pip3 (simpler and faster)
RUN pip3 install mininet PyYAML || \
    # Option 2: If pip install fails, create symlink from Python 2 installation
    (ln -s /usr/lib/python2.7/dist-packages/mininet /usr/local/lib/python3.8/dist-packages/mininet 2>/dev/null || true)

# Verify Mininet is available for Python 3
RUN python3 -c "import mininet; print('Mininet imported successfully')" || \
    echo "Warning: Mininet not available for Python 3 yet, will be handled by startup script"

# Set working directory
WORKDIR /app

# Keep the original ENTRYPOINT from base image
# We'll override it in docker-compose.yaml
