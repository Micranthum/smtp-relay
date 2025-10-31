#!/bin/bash

# Script para verificar el estado del SMTP Relay

echo "=========================================="
echo "SMTP Relay - Estado del Sistema"
echo "=========================================="
echo ""

# Verificar si el contenedor está corriendo
echo "📦 Estado del contenedor:"
docker ps --filter name=smtp-relay-contpaq --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
echo ""

# Verificar health check
echo "🏥 Health check:"
docker inspect smtp-relay-contpaq 2>/dev/null | grep -A 5 '"Health"' || echo "Contenedor no encontrado"
echo ""

# Verificar logs recientes
echo "📋 Últimos 10 logs:"
docker logs --tail 10 smtp-relay-contpaq 2>/dev/null || echo "No se pueden obtener logs"
echo ""

# Verificar conectividad al puerto
echo "🔌 Prueba de conectividad al puerto 587:"
if command -v nc &> /dev/null; then
    timeout 2 nc -zv localhost 587 2>&1 || echo "Puerto no accesible"
elif command -v telnet &> /dev/null; then
    timeout 2 telnet localhost 587 2>&1 || echo "Puerto no accesible"
else
    echo "Instalar netcat o telnet para probar conectividad"
fi
echo ""

# Verificar uso de recursos
echo "💻 Uso de recursos:"
docker stats smtp-relay-contpaq --no-stream 2>/dev/null || echo "Contenedor no corriendo"
echo ""

echo "=========================================="
echo "Comandos útiles:"
echo "  - Ver logs en tiempo real: docker-compose logs -f"
echo "  - Reiniciar servicio: docker-compose restart"
echo "  - Ver configuración: docker-compose config"
echo "=========================================="
