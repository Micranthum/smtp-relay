# SMTP Relay - Contpaq a Microsoft 365

Servidor SMTP relay seguro que actúa como puente entre Contpaq (que solo soporta autenticación básica) y Microsoft 365 (que requiere OAuth2).

## 🎯 Características

- ✅ **Autenticación híbrida**: Acepta Basic Auth de Contpaq y se autentica con OAuth2 en Microsoft 365
- ✅ **Microsoft Graph API**: Usa Graph API para envío confiable (compatible con buzones compartidos)
- ✅ **Seguro**: Contenedor Docker con usuario no-root, TLS/SSL, y variables de entorno separadas
- ✅ **Listo para producción**: Logging robusto, health checks, rate limiting
- ✅ **Caché de tokens**: Almacenamiento persistente de tokens OAuth2 para mejor rendimiento
- ✅ **Rate limiting**: Protección contra abuso (configurable)
- ✅ **Logs estructurados**: Logging con colores para desarrollo y archivos para producción
- ✅ **Soporte de adjuntos**: Envío de PDFs, XMLs y otros archivos adjuntos

## 📋 Requisitos Previos

### 1. Docker y Docker Compose
```bash
docker --version
docker-compose --version
```

### 2. Aplicación Azure AD (Microsoft 365)

Necesitas crear una aplicación en Azure AD para obtener las credenciales OAuth2:

1. Ir a [Azure Portal](https://portal.azure.com)
2. Navegar a **Azure Active Directory** → **App registrations** → **New registration**
3. Configurar la aplicación:
   - **Name**: `SMTP Relay Contpaq`
   - **Supported account types**: Accounts in this organizational directory only
   - **Redirect URI**: No necesario para esta aplicación
4. Después de crear, copiar:
   - **Application (client) ID**
   - **Directory (tenant) ID**
5. Crear un **Client Secret**:
   - Ir a **Certificates & secrets** → **New client secret**
   - Descripción: `SMTP Relay Secret`
   - Expiration: 24 months (o según política de tu organización)
   - **Copiar el valor del secret** (solo se muestra una vez)
6. Configurar permisos API:
   - Ir a **API permissions** → **Add a permission**
   - Seleccionar **Microsoft Graph** → **Application permissions**
   - Agregar: `Mail.Send`
   - Hacer clic en **Grant admin consent** para tu organización

## 🚀 Instalación

### 1. Clonar o copiar el proyecto

```bash
cd smtp-relay
```

### 2. Configurar variables de entorno

```bash
cp .env.example .env
```

Editar `.env` con tus credenciales:

```bash
nano .env
```

**Configuración mínima requerida:**

```env
# Credenciales para Contpaq (crear nuevas, no usar las de Microsoft 365)
SMTP_RELAY_USERNAME=contpaq_smtp
SMTP_RELAY_PASSWORD=TuPasswordSeguro123!

# Credenciales de Azure AD (obtenidas en el paso anterior)
MS365_TENANT_ID=tu-tenant-id-aqui
MS365_CLIENT_ID=tu-client-id-aqui
MS365_CLIENT_SECRET=tu-client-secret-aqui
MS365_EMAIL_ADDRESS=noreply@tudominio.com
```

**Configuración adicional (opcional):**

```env
# Restringir remitentes permitidos (por seguridad)
ALLOWED_SENDERS=nominas@tudominio.com,rh@tudominio.com

# Rate limiting (emails por minuto)
RATE_LIMIT_PER_MINUTE=60

# Nivel de logs
LOG_LEVEL=INFO
```

### 3. Construir y ejecutar

```bash
# Construir la imagen
docker-compose build

# Iniciar el servicio
docker-compose up -d

# Ver logs
docker-compose logs -f
```

## 🔧 Configuración de Contpaq

Configurar Contpaq para usar el SMTP relay:

1. **Servidor SMTP**: `tu-servidor.com` o `localhost` (si está en la misma máquina)
2. **Puerto**: `587`
3. **Seguridad/TLS**: Activado (STARTTLS)
4. **Autenticación**: Básica/Simple
5. **Usuario**: El valor de `SMTP_RELAY_USERNAME` (ej: `contpaq_smtp`)
6. **Contraseña**: El valor de `SMTP_RELAY_PASSWORD`

## 📊 Monitoreo

### Ver logs en tiempo real
```bash
docker-compose logs -f smtp-relay
```

### Ver estado del servicio
```bash
docker-compose ps
```

### Health check
```bash
docker inspect smtp-relay-contpaq | grep -A 5 Health
```

### Archivos de log
Los logs también se guardan en `./logs/smtp_relay.log` con rotación automática.

## 🔒 Seguridad

### Mejores prácticas implementadas:

1. **Usuario no-root en contenedor**: El servicio se ejecuta con UID 1000
2. **Variables de entorno**: Credenciales nunca en código
3. **TLS/SSL**: Conexiones cifradas con Microsoft 365
4. **Rate limiting**: Protección contra abuso
5. **Validación de remitentes**: Lista blanca opcional
6. **Logs de auditoría**: Todos los intentos de autenticación se registran

### Recomendaciones adicionales:

1. **Firewall**: Limitar acceso al puerto 587 solo desde la IP de Contpaq
   ```bash
   # Ejemplo con ufw
   ufw allow from 192.168.1.100 to any port 587
   ```

2. **Reverse proxy**: Considerar usar nginx/traefik para SSL termination

3. **Rotación de secrets**: Cambiar `SMTP_RELAY_PASSWORD` periódicamente

4. **Monitoreo**: Configurar alertas para intentos de autenticación fallidos

## 🐛 Solución de Problemas

### El servidor no inicia

```bash
# Ver logs detallados
docker-compose logs smtp-relay

# Verificar configuración
docker-compose config
```

**Errores comunes:**
- `Configuration error`: Verificar que todas las variables requeridas estén en `.env`
- `OAuth2 authentication failed`: Verificar credenciales de Azure AD y permisos

### Contpaq no puede conectar

1. Verificar que el puerto 587 esté accesible:
   ```bash
   telnet tu-servidor.com 587
   ```

2. Verificar logs del relay:
   ```bash
   docker-compose logs -f | grep -i auth
   ```

3. Probar conexión manual con openssl:
   ```bash
   openssl s_client -starttls smtp -connect tu-servidor.com:587
   ```

### Emails no se envían

1. Verificar logs de Microsoft 365:
   ```bash
   docker-compose logs -f | grep -i "microsoft\|oauth"
   ```

2. Verificar permisos en Azure AD (Mail.Send debe estar granted)

3. Verificar que la dirección de correo en `MS365_EMAIL_ADDRESS` existe y tiene buzón activo

### Rate limiting activo

Si ves errores de rate limit, ajustar en `.env`:
```env
RATE_LIMIT_PER_MINUTE=120
```

Y reiniciar:
```bash
docker-compose restart
```

## 🔄 Actualización

```bash
# Detener servicio
docker-compose down

# Actualizar código (si hay cambios)
git pull  # o copiar nuevos archivos

# Reconstruir
docker-compose build

# Reiniciar
docker-compose up -d
```

## 📁 Estructura del Proyecto

```
smtp-relay/
├── src/
│   ├── __init__.py          # Paquete Python
│   ├── main.py              # Punto de entrada
│   ├── config.py            # Configuración
│   ├── logger.py            # Sistema de logging
│   ├── oauth.py             # Autenticación OAuth2
│   └── relay.py             # Servidor SMTP relay
├── logs/                    # Logs (creado automáticamente)
├── token_cache/             # Caché de tokens OAuth2
├── Dockerfile               # Imagen Docker
├── docker-compose.yml       # Orquestación
├── requirements.txt         # Dependencias Python
├── .env.example             # Plantilla de configuración
├── .env                     # Tu configuración (no en git)
├── .gitignore              # Archivos ignorados
└── README.md               # Esta documentación
```

## 🧪 Pruebas

### Test manual con Python

```python
import smtplib
from email.mime.text import MIMEText

# Configuración
smtp_server = "tu-servidor.com"
smtp_port = 587
username = "contpaq_smtp"  # SMTP_RELAY_USERNAME
password = "TuPasswordSeguro123!"  # SMTP_RELAY_PASSWORD

# Crear mensaje
msg = MIMEText("Este es un email de prueba desde el SMTP relay")
msg['Subject'] = 'Test SMTP Relay'
msg['From'] = 'nominas@tudominio.com'
msg['To'] = 'destino@ejemplo.com'

# Enviar
try:
    server = smtplib.SMTP(smtp_server, smtp_port)
    server.starttls()
    server.login(username, password)
    server.send_message(msg)
    server.quit()
    print("Email enviado exitosamente!")
except Exception as e:
    print(f"Error: {e}")
```

### Test con telnet

```bash
telnet tu-servidor.com 587
# Debería responder: 220 ... ESMTP

EHLO test
# Debería mostrar capacidades incluyendo STARTTLS y AUTH
```

## 📝 Mantenimiento

### Backup de configuración

```bash
# Backup de .env
cp .env .env.backup.$(date +%Y%m%d)

# Backup de logs
tar -czf logs-backup-$(date +%Y%m%d).tar.gz logs/
```

### Limpieza de logs antiguos

```bash
# Mantener solo últimos 7 días
find logs/ -name "*.log" -mtime +7 -delete
```

### Renovación de Client Secret

Cuando el client secret de Azure AD esté por expirar:

1. Crear nuevo secret en Azure Portal
2. Actualizar `MS365_CLIENT_SECRET` en `.env`
3. Reiniciar servicio: `docker-compose restart`
4. Verificar logs: `docker-compose logs -f`

## 🤝 Soporte

Para problemas o preguntas:

1. Revisar los logs: `docker-compose logs -f`
2. Verificar configuración: `cat .env` (sin compartir secrets)
3. Consultar documentación de Microsoft 365: [Authenticate an IMAP, POP or SMTP connection using OAuth](https://learn.microsoft.com/en-us/exchange/client-developer/legacy-protocols/how-to-authenticate-an-imap-pop-smtp-application-by-using-oauth)

## 📜 Licencia

Este proyecto es de código abierto y está disponible bajo la licencia MIT.

## ⚠️ Aviso Legal

Este software se proporciona "tal cual", sin garantías de ningún tipo. Úsalo bajo tu propia responsabilidad y asegúrate de cumplir con las políticas de seguridad de tu organización.
