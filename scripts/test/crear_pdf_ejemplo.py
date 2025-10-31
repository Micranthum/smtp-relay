#!/usr/bin/env python3
"""
Script para crear un PDF de ejemplo para pruebas
"""
from datetime import datetime

# Crear un PDF simple sin dependencias externas
def crear_pdf_simple():
    """Crea un PDF mínimo válido"""
    
    # PDF básico con texto
    pdf_content = f"""%PDF-1.4
1 0 obj
<<
/Type /Catalog
/Pages 2 0 R
>>
endobj

2 0 obj
<<
/Type /Pages
/Kids [3 0 R]
/Count 1
>>
endobj

3 0 obj
<<
/Type /Page
/Parent 2 0 R
/Resources <<
/Font <<
/F1 <<
/Type /Font
/Subtype /Type1
/BaseFont /Helvetica
>>
>>
>>
/MediaBox [0 0 612 792]
/Contents 4 0 R
>>
endobj

4 0 obj
<<
/Length 200
>>
stream
BT
/F1 24 Tf
50 750 Td
(Recibo de Nomina - Ejemplo) Tj
0 -40 Td
/F1 12 Tf
(Fecha: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}) Tj
0 -30 Td
(Empleado: Juan Perez) Tj
0 -20 Td
(Salario Neto: $12,500.00 MXN) Tj
0 -30 Td
(Este es un documento de prueba) Tj
0 -20 Td
(para el SMTP Relay - Contpaq to MS365) Tj
ET
endstream
endobj

xref
0 5
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000317 00000 n
trailer
<<
/Size 5
/Root 1 0 R
>>
startxref
568
%%EOF
"""
    
    with open('recibo_ejemplo.pdf', 'wb') as f:
        f.write(pdf_content.encode('latin-1'))
    
    print("✅ PDF de ejemplo creado: recibo_ejemplo.pdf")

if __name__ == '__main__':
    crear_pdf_simple()
