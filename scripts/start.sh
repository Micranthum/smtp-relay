#!/bin/bash

# Script de inicio para verificar configuración antes de ejecutar

echo "=========================================="
echo "SMTP Relay - Contpaq to Microsoft 365"
echo "Environment: ${ENVIRONMENT:-development}"
echo "=========================================="
echo ""

# Verificar variables de entorno requeridas
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
    echo "ERROR: Variables de entorno faltantes:"
    for var in "${MISSING_VARS[@]}"; do
        echo "  - $var"
    done
    echo ""
    echo "Por favor, configura estas variables en tu archivo .env"
    exit 1
fi

echo "Todas las variables de entorno están configuradas"
echo ""

echo "Starting SMTP Relay server..."
echo ""

# Ejecutar la aplicación como módulo
exec python -u -m src.main
