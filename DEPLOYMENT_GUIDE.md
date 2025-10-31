# 🚀 Guía de Despliegue a Producción

## 📋 Pre-requisitos

- [ ] Servidor Linux con Docker y Docker Compose instalados
- [ ] IP fija del servidor de Contpaq
- [ ] Certificados SSL/TLS (opcional pero recomendado)
- [ ] Credenciales de Azure AD configuradas
- [ ] Acceso administrativo al servidor

## 🔧 Pasos de Configuración

### 1. Preparar el Servidor

```bash
# Instalar Docker y Docker Compose si no están instalados
sudo apt update
sudo apt install -y docker.io docker-compose

# Agregar usuario al grupo docker
sudo usermod -aG docker $USER
# Cerrar sesión y volver a entrar para que tome efecto

# Crear directorio del proyecto
mkdir -p /opt/smtp-relay
cd /opt/smtp-relay
```

### 2. Copiar Archivos del Proyecto

```bash
# Copiar todos los archivos del proyecto al servidor
# (usando scp, rsync, git clone, etc.)

# Ejemplo con scp desde tu máquina local:
# scp -r smtp-relay/* usuario@servidor:/opt/smtp-relay/

# O clonar desde git:
# git clone <tu-repo> /opt/smtp-relay
```

### 3. Configurar Variables de Entorno

```bash
# Copiar el ejemplo de producción
cp .env.production.example .env

# Editar el archivo .env con tus valores
nano .env
```

**Configuración mínima requerida para producción:**

```properties
# CRÍTICO: Cambiar a production
ENVIRONMENT=production

# IP del servidor de Contpaq (OBLIGATORIO)
ALLOWED_IPS=192.168.1.50

# Email permitido (RECOMENDADO)
ALLOWED_SENDERS=recibos.contpaqi@aguafria.mx

# Credenciales seguras
SMTP_RELAY_USERNAME=contpaq.nominas
SMTP_RELAY_PASSWORD=<contraseña-segura-aquí>

# Azure AD
MS365_TENANT_ID=<tu-tenant-id>
MS365_CLIENT_ID=<tu-client-id>
MS365_CLIENT_SECRET=<tu-client-secret>
MS365_EMAIL_ADDRESS=recibos.contpaqi@aguafria.mx
```

### 4. Configurar Certificados SSL/TLS (Opcional pero Recomendado)

#### Opción A: Usar Certificados Existentes

```bash
# Copiar tus certificados al directorio certs/
cp /ruta/a/tu/certificado.crt certs/smtp_relay.crt
cp /ruta/a/tu/llave.key certs/smtp_relay.key

# Configurar permisos
chmod 600 certs/smtp_relay.key
chmod 644 certs/smtp_relay.crt

# Actualizar .env
nano .env
```

```properties
SMTP_RELAY_USE_TLS=true
TLS_CERT_FILE=/app/certs/smtp_relay.crt
TLS_KEY_FILE=/app/certs/smtp_relay.key
```

#### Opción B: Generar Certificados Auto-firmados (Solo para Testing Interno)

```bash
# Generar certificado auto-firmado
openssl req -x509 -newkey rsa:4096 -keyout certs/smtp_relay.key -out certs/smtp_relay.crt -days 365 -nodes \
  -subj "/C=MX/ST=Estado/L=Ciudad/O=Tu Empresa/CN=smtp.tudominio.com"

# Actualizar .env
SMTP_RELAY_USE_TLS=true
TLS_CERT_FILE=/app/certs/smtp_relay.crt
TLS_KEY_FILE=/app/certs/smtp_relay.key
```

**Nota:** Los certificados auto-firmados generarán advertencias. Para producción, usa certificados válidos de Let's Encrypt o CA comercial.

#### Opción C: Sin TLS (Solo si Contpaq está en red privada segura)

```properties
SMTP_RELAY_USE_TLS=false
TLS_CERT_FILE=
TLS_KEY_FILE=
```

### 5. Configurar Permisos y Seguridad

```bash
# Crear directorios necesarios
mkdir -p logs token_cache certs

# Configurar permisos
chmod 755 logs token_cache
chmod 700 certs  # Certificados deben ser privados

# Proteger el archivo .env
chmod 600 .env

# Verificar que .env no esté en git
echo ".env" >> .gitignore
echo "certs/*.key" >> .gitignore
echo "certs/*.crt" >> .gitignore
```

### 6. Validar Configuración

```bash
# Verificar que todas las variables estén configuradas
cat .env | grep -v '^#' | grep -v '^$'

# Verificar sintaxis del docker-compose
docker-compose config
```

### 7. Iniciar el Servicio

```bash
# Construir e iniciar el contenedor
docker-compose up -d --build

# Verificar que esté corriendo
docker-compose ps

# Ver logs
docker-compose logs -f
```

### 8. Verificar el Servicio

```bash
# Verificar que el puerto esté abierto
netstat -tlnp | grep 587

# Probar conexión básica
telnet localhost 587

# Ver logs en tiempo real
docker-compose logs -f --tail 50
```

### 9. Prueba de Envío

```bash
# Ejecutar script de prueba desde el servidor
cd scripts
python3 test_email.py

# O desde el servidor de Contpaq
# telnet <ip-del-relay> 587
```

### 10. Configurar Contpaq

En el servidor de Contpaq, configurar el cliente de correo:

```
Servidor SMTP: <IP o hostname del servidor relay>
Puerto: 587
Seguridad: STARTTLS (si TLS está habilitado) o Ninguna
Usuario: contpaq.nominas
Contraseña: <la configurada en .env>
```

## 🔒 Checklist de Seguridad

Antes de poner en producción, verifica:

- [ ] `ENVIRONMENT=production` en .env
- [ ] `ALLOWED_IPS` configurado con IP específica (NO usar `*`)
- [ ] `ALLOWED_SENDERS` configurado con emails específicos (NO usar `*`)
- [ ] Contraseña fuerte en `SMTP_RELAY_PASSWORD` (mínimo 16 caracteres)
- [ ] Archivo `.env` con permisos 600
- [ ] Certificados TLS configurados (si se usa TLS)
- [ ] Permisos correctos en directorio `certs/` (700)
- [ ] `.env` y certificados NO están en git (.gitignore)
- [ ] Firewall configurado para permitir solo IP de Contpaq al puerto 587
- [ ] Logging configurado a nivel INFO o WARNING
- [ ] Backup de credenciales guardado en lugar seguro

## 📊 Monitoreo

### Ver Logs en Tiempo Real

```bash
# Logs completos
docker-compose logs -f

# Solo errores
docker-compose logs -f | grep ERROR

# Últimas 100 líneas
docker-compose logs --tail 100
```

### Ver Estado del Servicio

```bash
# Estado del contenedor
docker-compose ps

# Uso de recursos
docker stats smtp-relay-contpaq

# Health check
docker inspect smtp-relay-contpaq | grep -A 10 Health
```

### Archivos de Log

Los logs también se guardan en:
```
./logs/smtp_relay.log
```

## 🔄 Mantenimiento

### Actualizar el Servicio

```bash
# Detener servicio
docker-compose down

# Hacer cambios necesarios
nano .env  # o actualizar código

# Reconstruir y reiniciar
docker-compose up -d --build
```

### Backup de Configuración

```bash
# Backup de .env
cp .env .env.backup.$(date +%Y%m%d)

# Backup de tokens (opcional)
tar -czf token_cache.backup.$(date +%Y%m%d).tar.gz token_cache/

# Backup de certificados
tar -czf certs.backup.$(date +%Y%m%d).tar.gz certs/
```

### Rotar Logs

Los logs se rotan automáticamente por Docker (configurado en docker-compose.yml):
- Tamaño máximo: 10MB por archivo
- Archivos mantenidos: 3

Para limpiar logs manualmente:
```bash
docker-compose logs --tail 0 smtp-relay-contpaq
```

## 🆘 Troubleshooting

### El servicio no inicia

```bash
# Ver logs de error
docker-compose logs

# Verificar configuración
docker-compose config

# Validar .env
cat .env | grep -v '^#' | grep -v '^$'
```

### Error de validación en producción

Si ves errores de validación al iniciar:
- Verifica que `ALLOWED_IPS` no sea `*`
- Verifica que `ALLOWED_SENDERS` no sea `*`
- Verifica que `LOG_LEVEL` no sea `DEBUG`
- Si usas TLS, verifica que los certificados existan

### Emails no llegan

1. Verificar logs: `docker-compose logs -f`
2. Verificar que la IP de Contpaq esté en `ALLOWED_IPS`
3. Verificar conectividad: `telnet <ip-relay> 587`
4. Verificar permisos en Azure AD (Mail.Send con consentimiento)

### Error 403 de Graph API

- Verificar que `Mail.Send` tenga consentimiento de administrador
- Borrar cache de tokens: `rm -rf token_cache/*.json && docker-compose restart`

## 📞 Soporte Post-Despliegue

Después del despliegue, monitorear durante las primeras 24-48 horas:

1. Revisar logs regularmente
2. Verificar que todos los emails lleguen correctamente
3. Monitorear uso de recursos (CPU, memoria, red)
4. Verificar que no haya intentos de acceso no autorizados

---

**Última actualización:** 31 de Octubre, 2025  
**Versión:** 1.0.0
