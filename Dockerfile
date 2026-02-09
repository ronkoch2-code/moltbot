FROM python:3.12-slim

LABEL maintainer="Ron"
LABEL description="Moltbook MCP Server — sandboxed agent interaction with moltbook.com"

# Non-root user for security
RUN groupadd -r moltbot && useradd -r -g moltbot -d /app -s /sbin/nologin moltbot

WORKDIR /app

# Install dependencies first (cache-friendly layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY server.py .
COPY content_filter.py .
COPY download_model.py .

# Pre-download the DeBERTa prompt injection model during build.
# This caches ~400MB of model weights inside the image so the
# container never needs outbound access to HuggingFace at runtime.
# The cache lives in /app/.cache so it's accessible to moltbot user.
ENV HF_HOME=/app/.cache/huggingface
RUN python download_model.py && rm download_model.py

# Create config mount point and fix ownership
RUN mkdir -p /app/config && chown -R moltbot:moltbot /app

USER moltbot

# Streamable HTTP transport
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD PYTHONDONTWRITEBYTECODE=1 python -c "from urllib.request import urlopen; urlopen('http://localhost:8080/health', timeout=5).read()" || exit 1

ENTRYPOINT ["python", "server.py"]
CMD ["--transport", "streamable_http", "--port", "8080"]
