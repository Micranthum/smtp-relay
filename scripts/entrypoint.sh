#!/bin/bash
# Docker entrypoint script to set permissions

# Set permissions for mounted volumes
chown -R root:root /app/logs /app/token_cache /app/certs 2>/dev/null || true

# Set secure permissions: owner read/write only
chmod 700 /app/token_cache 2>/dev/null || true
chmod 600 /app/token_cache/*.json 2>/dev/null || true

# Logs
chmod 755 /app/logs 2>/dev/null || true

# Prometheus multiprocess directory (shared between relay and worker)
chmod 777 /tmp/prometheus_multiproc 2>/dev/null || true

# Execute the main command
exec "$@"
