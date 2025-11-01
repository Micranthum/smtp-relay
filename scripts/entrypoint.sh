#!/bin/bash
set -e

# Set permissions for mounted volumes
echo "Setting permissions for mounted volumes..."
chown -R root:root /app/logs /app/token_cache 2>/dev/null || true
chmod -R 777 /app/logs /app/token_cache 2>/dev/null || true

# Execute the start script
exec ./start.sh
