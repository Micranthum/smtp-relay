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

# Make start script executable
RUN chmod +x start.sh

# Create non-root user for security
RUN useradd -m -u 1000 smtprelay

# Create directories and set ownership
RUN mkdir -p /app/logs /app/token_cache && \
    chown -R smtprelay:smtprelay /app

# Switch to non-root user
USER smtprelay

# Expose SMTP port
EXPOSE 587

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import socket; s=socket.socket(); s.settimeout(5); s.connect(('localhost', 587)); s.close()"

# Run the application
CMD ["./start.sh"]
