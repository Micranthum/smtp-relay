# 📧 Script de Prueba de Envío Masivo

## ✨ Características

- ✅ **Envía emails REALES** a direcciones temporales de Mailinator
- ✅ **Verifica la recepción** con URLs únicas para cada email
- ✅ **Mide el rendimiento** real del servidor SMTP relay
- ✅ **Prueba concurrencia** con múltiples threads
- ✅ **Detecta rate limiting** y otros errores
- ✅ **No satura tu bandeja** - usa emails temporales

## 🚀 Uso Rápido

### Prueba Básica (100 emails)
```bash
python3 scripts/test_mass_email.py --emails 100 --threads 5
```

### Prueba de Nómina (500 emails)
```bash
python3 scripts/test_mass_email.py --emails 500 --threads 10
```

### Prueba de Carga Máxima (1000 emails)
```bash
python3 scripts/test_mass_email.py --emails 1000 --threads 15
```

## 📖 Opciones

```
--emails N       Número de emails a enviar (default: 100)
--threads N      Conexiones concurrentes (default: 5)
--mode MODE      ssl o starttls (default: ssl)
--timeout N      Timeout en segundos (default: 30)
```

## 🧪 Escenarios de Prueba

### 1. Prueba de Rate Limiting
```bash
# Enviar rápido para detectar límites
python3 scripts/test_mass_email.py --emails 200 --threads 20
```

### 2. Prueba de Concurrencia
```bash
# Muchas conexiones simultáneas
python3 scripts/test_mass_email.py --emails 100 --threads 50
```

### 3. Simular Nómina Real
```bash
# 5 threads es similar a cómo envía ContPaqi
python3 scripts/test_mass_email.py --emails 300 --threads 5
```

### 4. Comparar SSL vs STARTTLS
```bash
# Puerto 465 (SSL)
python3 scripts/test_mass_email.py --emails 100 --mode ssl

# Puerto 587 (STARTTLS)
python3 scripts/test_mass_email.py --emails 100 --mode starttls
```

## 📬 Verificación de Emails

El script usa **Mailinator**, un servicio de emails temporales que permite:

- ✅ Ver si los emails llegaron
- ✅ Leer el contenido completo
- ✅ No requiere registro
- ✅ Los emails se autodestruyen en unas horas

### Cómo verificar:

1. El script mostrará URLs al final
2. Abre las URLs en tu navegador
3. Verás los emails recibidos

Ejemplo:
```
https://www.mailinator.com/v4/public/inboxes.jsp?to=test00001-1698876543
```

## 📊 Interpretación de Resultados

### Tasa de Éxito

| Porcentaje | Evaluación | Acción |
|------------|------------|--------|
| > 99% | ✅ Excelente | Todo funciona bien |
| 95-99% | ⚠️ Bueno | Revisar configuración |
| 90-95% | ⚠️ Regular | Ajustar rate limit |
| < 90% | ❌ Malo | Revisar logs del servidor |

### Errores Comunes

#### 🚦 Rate Limit Alcanzado
```
🚦 Rate Limit: 45
```
**Causa**: El servidor rechaza emails por exceder límite  
**Solución**: 
- Aumentar `RATE_LIMIT_PER_MINUTE` en `.env`
- Reducir `--threads`
- Implementar sistema de colas

#### ⏱️ Timeouts
```
⏱️ Timeout: 23
```
**Causa**: El servidor no responde a tiempo  
**Solución**:
- Reducir concurrencia (`--threads`)
- Aumentar timeout (`--timeout 60`)
- Verificar recursos del servidor (CPU/RAM)

#### 🔐 Errores de Autenticación
```
🔐 Autenticación: 5
```
**Causa**: Credenciales incorrectas en el script  
**Solución**: Verificar `USERNAME` y `PASSWORD` en el script

#### 🔌 Errores de Conexión
```
🔌 Conexión: 12
```
**Causa**: No se puede conectar al servidor  
**Solución**:
- Verificar que el servidor esté corriendo: `docker-compose ps`
- Verificar firewall: `sudo ufw status`
- Verificar puertos expuestos en docker-compose.yml

## 💡 Ejemplos de Salida

### Ejemplo Exitoso
```
================================================================================
📊 RESUMEN DE PRUEBA DE CARGA
================================================================================

Emails:
  Total enviados: 100
  ✅ Exitosos: 99 (99.0%)
  ❌ Fallidos: 1 (1.0%)

Rendimiento:
  ⏱️  Tiempo total: 45.32 segundos
  ⚡ Tasa promedio: 2.21 emails/seg
  📊 Tiempo de respuesta:
     - Promedio: 2.156s
     - Mínimo: 1.234s
     - Máximo: 4.567s

Proyecciones:
  📧 Capacidad real: ~132 emails/minuto
  📊 Para 100 emails: ~0.8 minutos
  📊 Para 500 emails: ~3.8 minutos
  📊 Para 1000 emails: ~7.6 minutos

💡 RECOMENDACIONES:
  ✅ Excelente tasa de éxito (99.0%)
```

### Ejemplo con Rate Limiting
```
Errores:
  🚦 Rate Limit: 45

💡 RECOMENDACIONES:
  ⚠️  RATE LIMITING DETECTADO
     • Aumenta RATE_LIMIT_PER_MINUTE en .env
     • Considera implementar sistema de colas
     • Reduce concurrencia o agrega delays
```

## 🔧 Antes de Ejecutar

### 1. Verifica que el servidor esté corriendo
```bash
docker-compose ps
```

### 2. Revisa los logs
```bash
docker-compose logs -f
```

### 3. Configura las credenciales en el script
Edita `scripts/test_mass_email.py`:
```python
USERNAME = "contpaq.nominas"
PASSWORD = "tu_password_aqui"
```

### 4. Verifica el firewall
```bash
sudo ufw status | grep -E '465|587'
```

## 📈 Métricas Importantes

El script mide:

- ✅ **Emails exitosos/fallidos**
- ⏱️ **Tiempo de respuesta** (min/max/promedio)
- ⚡ **Tasa de envío** (emails/segundo)
- 🚦 **Detección de rate limiting**
- 📊 **Proyecciones de capacidad**

## ⚠️ Notas Importantes

1. **Mailinator es público**: Los emails son visibles públicamente, no envíes información sensible
2. **Rate Limits de Mailinator**: Mailinator también tiene límites, no abuses
3. **Microsoft Graph API**: Tiene sus propios límites independientes del relay
4. **Emails temporales**: Se borran automáticamente después de unas horas

## 🐛 Solución de Problemas

### El script no se conecta
```bash
# Verificar conectividad
telnet smtp.aguafria.mx 465
```

### Todos los emails fallan con auth error
```bash
# Verificar credenciales en .env del servidor
cat .env | grep SMTP_RELAY_
```

### Rate limit muy bajo
```bash
# Aumentar en .env
RATE_LIMIT_PER_MINUTE=300

# Reiniciar servidor
docker-compose restart
```

## 📞 Ayuda

Si encuentras problemas:
1. Revisa los logs: `docker-compose logs --tail 100`
2. Verifica la configuración: `cat .env`
3. Prueba con menos emails primero: `--emails 10`
