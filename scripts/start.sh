#!/bin/bash

echo "=========================================="
echo "SMTP Relay - Basic Auth to OAuth2 Microsoft Graph"
echo "Environment: ${ENVIRONMENT:-development}"
echo "=========================================="
echo ""


REQUIRED_VARS=(
    "SMTP_RELAY_USERNAME"
    "SMTP_RELAY_PASSWORD"
    "GRAPH_API_TENANT_ID"
    "GRAPH_API_CLIENT_ID"
    "GRAPH_API_CLIENT_SECRET"
    "MS365_EMAIL_ADDRESS"
)

MISSING_VARS=()

for var in "${REQUIRED_VARS[@]}"; do
    if [ -z "${!var}" ]; then
        MISSING_VARS+=("$var")
    fi
done

if [ ${#MISSING_VARS[@]} -ne 0 ]; then
    echo "ERROR: Missing environment variables:"
    for var in "${MISSING_VARS[@]}"; do
        echo "  - $var"
    done
    echo ""
    echo "Please configure these variables in your .env file"
    exit 1
fi

echo "All required environment variables are set"
echo ""

echo "Starting SMTP Relay server..."
echo ""

exec python -u -m src.main
