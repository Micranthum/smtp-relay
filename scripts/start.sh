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

# Crear directorios necesarios y asignar permisos correctos
echo "Creating directories with proper permissions..."
mkdir -p /app/logs /app/token_cache

# Asignar permisos de escritura (funciona incluso con volúmenes montados)
chmod 755 /app/logs /app/token_cache 2>/dev/null || true

# Intentar crear un archivo de prueba para verificar permisos
if ! touch /app/logs/.test 2>/dev/null; then
    echo "WARNING: Cannot write to /app/logs - attempting to fix permissions..."
    # Si no podemos escribir, intentar con permisos más amplios
    chmod 777 /app/logs 2>/dev/null || true
fi
rm -f /app/logs/.test 2>/dev/null || true

if ! touch /app/token_cache/.test 2>/dev/null; then
    echo "WARNING: Cannot write to /app/token_cache - attempting to fix permissions..."
    chmod 777 /app/token_cache 2>/dev/null || true
fi
rm -f /app/token_cache/.test 2>/dev/null || true

echo "Directories ready"
echo ""
echo "Starting SMTP Relay server..."
echo ""

# Ejecutar la aplicación como módulo
exec python -u -m src.main
