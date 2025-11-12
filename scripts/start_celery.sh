#!/bin/bash
set -e

echo "Starting Celery worker for SMTP Relay"
echo "Configuration:"
echo "  Broker: ${CELERY_BROKER_URL:-redis://redis:6379/0}"
echo "  Backend: ${CELERY_RESULT_BACKEND:-redis://redis:6379/0}"
echo "  Rate Limit: ${GRAPH_API_RATE_LIMIT_PER_MINUTE:-30} emails/minute"
echo "  Max Retries: ${CELERY_MAX_RETRIES:-3}"
echo "  Retry Delay: ${CELERY_RETRY_DELAY:-60} seconds"
echo ""

# Wait for Redis to be ready
echo "Waiting for Redis..."
until redis-cli -h redis ping > /dev/null 2>&1; do
  echo "Redis is unavailable - sleeping"
  sleep 1
done
echo "Redis is up and running"

# Start Celery worker with single concurrency for Graph API rate limiting
exec celery -A src.celery_app worker \
  --loglevel=INFO \
  --concurrency=1 \
  --max-tasks-per-child=1000 \
  --task-events \
  --without-gossip \
  --without-mingle \
  --without-heartbeat
