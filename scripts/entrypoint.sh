#!/bin/bash
# Docker entrypoint script to set permissions

# Set permissions for mounted volumes
chown -R root:root /app/logs /app/certs 2>/dev/null || true

# Logs
chmod 755 /app/logs 2>/dev/null || true

# Prometheus multiprocess directory (shared between relay and worker)
chmod 777 /tmp/prometheus_multiproc 2>/dev/null || true

# Execute the main command
exec "$@"
