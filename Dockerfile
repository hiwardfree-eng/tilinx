FROM python:3.11-slim

WORKDIR /opt/tilinx

RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY config.py logger.py database.py cache.py utils.py ./
COPY tilinx_proxy.py .
COPY ips.json keys.json ./
COPY data/ ./data/

RUN mkdir -p logs certs

EXPOSE 8884

ENV TilinX_BASE_DIR=/opt/tilinx \
    TilinX_DB_PATH=/opt/tilinx/ips.json \
    TilinX_LOG_DIR=/opt/tilinx/logs \
    TilinX_DATA_DIR=/opt/tilinx/data/TilinX \
    TilinX_PROXY_PORT=8884 \
    TilinX_RATE_LIMIT=30

CMD mitmdump -p "$TilinX_PROXY_PORT" \
    --set block_global=false \
    --ssl-insecure \
    -s /opt/tilinx/tilinx_proxy.py
