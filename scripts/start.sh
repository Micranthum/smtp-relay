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
    "MS365_TENANT_ID"
    "MS365_CLIENT_ID"
    "MS365_CLIENT_SECRET"
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

# Crear directorios necesarios (con permisos correctos para el usuario actual)
mkdir -p /app/logs 2>/dev/null || true
mkdir -p /app/token_cache 2>/dev/null || true

echo "✅ Directorios creados"
echo ""
echo "Iniciando servidor SMTP Relay..."
echo ""

# Ejecutar la aplicación como módulo
exec python -u -m src.main
