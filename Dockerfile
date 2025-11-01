FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ ./src/
COPY scripts/start.sh ./
COPY scripts/entrypoint.sh ./

# Make scripts executable
RUN chmod +x start.sh entrypoint.sh

# Create directories (will be mounted from host)
RUN mkdir -p /app/logs /app/token_cache /app/certs

# Expose SMTP port
EXPOSE 587

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(5); s.connect(('localhost', 587)); s.close()"

# Run the application via entrypoint
ENTRYPOINT ["./entrypoint.sh"]
