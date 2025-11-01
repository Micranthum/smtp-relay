# Configuración de Cifrado SMTP

## Resumen de Cambios

Este documento describe las nuevas opciones de configuración disponibles para el SMTP relay.

### 1. Eliminación de Restricción de ALLOWED_IPS

**Antes:** El sistema no permitía usar `ALLOWED_IPS=*` en modo producción.

**Ahora:** Puedes usar `ALLOWED_IPS=*` incluso en producción si lo necesitas. El sistema ya no bloquea esta configuración, aunque se recomienda usar listas específicas de IPs por seguridad.

### 2. Modos de Cifrado Flexibles

Se ha añadido la variable de entorno `SMTP_ENCRYPTION_MODE` para soportar diferentes métodos de cifrado.

## Variable SMTP_ENCRYPTION_MODE

Esta variable controla cómo el servidor SMTP maneja el cifrado de las conexiones.

### Valores Permitidos

| Modo | Puerto Típico | Descripción | Uso Recomendado |
|------|---------------|-------------|-----------------|
| `STARTTLS` | 587 | Conexión inicia sin cifrar, se actualiza a TLS con comando STARTTLS | **Por defecto** - Clientes modernos |
| `SSL` | 465 | Conexión cifrada desde el inicio (TLS implícito) | Programas antiguos que solo soportan SSL/TLS directo |
| `NONE` | 25/custom | Sin cifrado | **Solo para desarrollo/testing** |

## Ejemplos de Configuración

### Configuración por Defecto (STARTTLS)

```env
SMTP_ENCRYPTION_MODE=STARTTLS
SMTP_RELAY_PORT=587
SMTP_RELAY_USE_TLS=true
TLS_CERT_FILE=/path/to/cert.pem
TLS_KEY_FILE=/path/to/key.pem
```

### Configuración para Programas Antiguos (SSL)

Para programas como Contpaq antiguos o sistemas legacy que solo soportan SSL/TLS directo:

```env
SMTP_ENCRYPTION_MODE=SSL
SMTP_RELAY_PORT=465
TLS_CERT_FILE=/path/to/cert.pem
TLS_KEY_FILE=/path/to/key.pem
```

**Notas:**
- En modo SSL, el servidor usa TLS implícito desde el inicio de la conexión
- No se usa el comando STARTTLS
- Compatible con clientes SMTP antiguos

### Configuración Sin Cifrado (Solo Desarrollo)

```env
SMTP_ENCRYPTION_MODE=NONE
SMTP_RELAY_PORT=25
```

**⚠️ ADVERTENCIA:** No usar en producción. Todas las comunicaciones serán en texto plano.

### Configuración con IPs Permitidas Flexibles

```env
# Permitir todas las IPs (incluso en producción si es necesario)
ALLOWED_IPS=*
ENVIRONMENT=production

# O especificar IPs concretas
ALLOWED_IPS=192.168.1.100,10.0.0.50,172.16.0.10
```

## Configuración Completa de Ejemplo

### Para Contpaq Antiguo con SSL

```env
# Entorno
ENVIRONMENT=production

# Servidor SMTP Relay
SMTP_RELAY_HOST=0.0.0.0
SMTP_RELAY_PORT=465
SMTP_ENCRYPTION_MODE=SSL

# Certificados TLS (requeridos para SSL y STARTTLS con TLS)
TLS_CERT_FILE=/app/certs/cert.pem
TLS_KEY_FILE=/app/certs/key.pem

# Autenticación básica (para el cliente)
SMTP_RELAY_USERNAME=contpaq
SMTP_RELAY_PASSWORD=tu_password_seguro

# Microsoft 365 OAuth
MS365_TENANT_ID=tu-tenant-id
MS365_CLIENT_ID=tu-client-id
MS365_CLIENT_SECRET=tu-client-secret
MS365_EMAIL_ADDRESS=tu-email@empresa.com

# Seguridad
ALLOWED_IPS=192.168.1.100
ALLOWED_SENDERS=*

# Logs
LOG_LEVEL=INFO
RATE_LIMIT_PER_MINUTE=60
```

### Para Cliente Moderno con STARTTLS

```env
# Entorno
ENVIRONMENT=production

# Servidor SMTP Relay
SMTP_RELAY_HOST=0.0.0.0
SMTP_RELAY_PORT=587
SMTP_ENCRYPTION_MODE=STARTTLS
SMTP_RELAY_USE_TLS=true

# Certificados TLS
TLS_CERT_FILE=/app/certs/cert.pem
TLS_KEY_FILE=/app/certs/key.pem

# ... resto de configuración igual ...
```

## Diagnóstico de Problemas

### Problema: Cliente antiguo no puede conectar con STARTTLS

**Síntoma:** Errores de timeout o "connection refused" con puerto 587

**Solución:** Cambiar a modo SSL:
```env
SMTP_ENCRYPTION_MODE=SSL
SMTP_RELAY_PORT=465
```

### Problema: "TLS certificate required" en modo SSL

**Solución:** Asegurarse de que los certificados están configurados:
```env
TLS_CERT_FILE=/ruta/completa/al/cert.pem
TLS_KEY_FILE=/ruta/completa/al/key.pem
```

### Problema: Necesito permitir todas las IPs temporalmente

**Solución:** Ahora es posible incluso en producción:
```env
ALLOWED_IPS=*
```

## Validaciones del Sistema

El sistema valida automáticamente:

1. ✅ `SMTP_ENCRYPTION_MODE` debe ser uno de: STARTTLS, SSL, NONE
2. ✅ Si modo es SSL: certificados TLS son obligatorios
3. ✅ Si modo es STARTTLS y `SMTP_RELAY_USE_TLS=true`: certificados TLS son obligatorios
4. ✅ Si modo es NONE: no requiere certificados (muestra advertencia)

## Logs del Sistema

Al iniciar, el servidor mostrará:

```
Environment: production
Encryption Mode: SSL
TLS Enabled: true
✅ SSL mode: TLS context created (implicit TLS)
Starting SMTP Relay Server on 0.0.0.0:465
```

O con STARTTLS:

```
Environment: production
Encryption Mode: STARTTLS
TLS Enabled: true
✅ STARTTLS mode: TLS context created (optional upgrade)
Starting SMTP Relay Server on 0.0.0.0:587
```

## Migración desde Configuración Antigua

Si ya tenías:
```env
SMTP_RELAY_USE_TLS=true
SMTP_RELAY_PORT=587
```

Sigue funcionando igual (modo STARTTLS por defecto). No necesitas cambiar nada.

Para soportar clientes antiguos, solo añade:
```env
SMTP_ENCRYPTION_MODE=SSL
SMTP_RELAY_PORT=465
```
