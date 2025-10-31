# Archivos de Prueba

Esta carpeta contiene archivos de ejemplo para probar el envío de emails con adjuntos a través del SMTP Relay.

## Archivos

### `recibo_ejemplo.pdf`
PDF de ejemplo que simula un recibo de nómina. Este archivo se crea automáticamente ejecutando `crear_pdf_ejemplo.py`.

**Contenido:**
- Título: "Recibo de Nomina - Ejemplo"
- Fecha de generación
- Información de empleado simulada
- Monto de salario neto

### `factura_ejemplo.xml`
Archivo XML de ejemplo que simula una factura electrónica (CFDI). Este archivo representa el formato típico de facturas que Contpaq genera.

**Uso:** Archivo real de factura que se usa como ejemplo para pruebas.

## Scripts

### `crear_pdf_ejemplo.py`
Script de Python que genera el archivo `recibo_ejemplo.pdf` con contenido de ejemplo.

**Uso:**
```bash
cd scripts/test
python3 crear_pdf_ejemplo.py
```

## Uso en Pruebas

El script `test_email.py` (en el directorio padre) utiliza estos archivos para probar el envío de emails con adjuntos:

```bash
cd scripts
python3 test_email.py
```

Esto enviará un email con:
- Cuerpo de texto plano
- Cuerpo HTML
- Adjuntos: `recibo_ejemplo.pdf` y `factura_ejemplo.xml`

## Notas

- Los archivos PDF y XML son de ejemplo y no contienen información real.
- El tamaño total de los adjuntos es < 10KB, ideal para pruebas rápidas.
- En producción, Contpaq enviará archivos reales de nómina y facturación.
