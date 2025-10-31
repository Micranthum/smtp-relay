#!/usr/bin/env python3
"""
Script de prueba para el SMTP Relay
Envía un email de prueba a través del relay con adjuntos (PDF y XML)
"""

import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from pathlib import Path

# Configuración - AJUSTAR SEGÚN TU ENTORNO
SMTP_SERVER = "localhost"  # o la IP/dominio de tu servidor
SMTP_PORT = 587
SMTP_USERNAME = "contpaq.nominas"  # El valor de SMTP_RELAY_USERNAME
SMTP_PASSWORD = "nominas2025"  # El valor de SMTP_RELAY_PASSWORD

# Email de prueba
FROM_EMAIL = "recibos.contpaqi@aguafria.mx"
TO_EMAIL = "ramonvillanueva@aguafria.mx"
SUBJECT = f"Test SMTP Relay con Adjuntos - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

# Archivos adjuntos de prueba
SCRIPT_DIR = Path(__file__).parent
TEST_DIR = SCRIPT_DIR / "test"
ATTACHMENTS = [
    TEST_DIR / "recibo_ejemplo.pdf",
    TEST_DIR / "factura_ejemplo.xml"
]

def send_test_email():
    """Envía un email de prueba con adjuntos"""
    
    try:
        # Crear mensaje
        msg = MIMEMultipart('mixed')
        msg['Subject'] = SUBJECT
        msg['From'] = FROM_EMAIL
        msg['To'] = TO_EMAIL
        
        # Crear el cuerpo del mensaje (parte alternativa para texto/html)
        body = MIMEMultipart('alternative')
        
        # Contenido del email
        text = """
        Este es un email de prueba del SMTP Relay con archivos adjuntos.
        
        Si recibes este mensaje con los adjuntos (PDF y XML), significa que el relay
        está funcionando correctamente y puede enviar recibos de nómina.
        
        Adjuntos incluidos:
        - recibo_ejemplo.pdf (Recibo de nómina de ejemplo)
        - factura_ejemplo.xml (Factura electrónica CFDI)
        
        Sistema: SMTP Relay - Contpaq to Microsoft 365
        Hora: {time}
        """.format(time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        html = """
        <html>
          <body>
            <h2>📧 Email de Prueba - SMTP Relay</h2>
            <p>Este es un email de prueba del <strong>SMTP Relay</strong> con archivos adjuntos.</p>
            <p>Si recibes este mensaje con los adjuntos, significa que el relay está funcionando correctamente.</p>
            
            <h3>📎 Archivos Adjuntos:</h3>
            <ul>
              <li><strong>recibo_ejemplo.pdf</strong> - Recibo de nómina de ejemplo</li>
              <li><strong>factura_ejemplo.xml</strong> - Factura electrónica CFDI</li>
            </ul>
            
            <hr>
            <p><small>
              <strong>Sistema:</strong> SMTP Relay - Contpaq to Microsoft 365<br>
              <strong>Hora:</strong> {time}<br>
              <strong>Método:</strong> Microsoft Graph API
            </small></p>
          </body>
        </html>
        """.format(time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        # Adjuntar partes del mensaje
        part1 = MIMEText(text, 'plain', 'utf-8')
        part2 = MIMEText(html, 'html', 'utf-8')
        body.attach(part1)
        body.attach(part2)
        
        # Adjuntar el cuerpo al mensaje principal
        msg.attach(body)
        
        # Adjuntar archivos
        attachments_found = []
        for attachment_path in ATTACHMENTS:
            if attachment_path.exists():
                print(f"📎 Adjuntando: {attachment_path.name} ({attachment_path.stat().st_size} bytes)")
                
                with open(attachment_path, 'rb') as f:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(f.read())
                
                encoders.encode_base64(part)
                part.add_header(
                    'Content-Disposition',
                    f'attachment; filename={attachment_path.name}'
                )
                msg.attach(part)
                attachments_found.append(attachment_path.name)
            else:
                print(f"⚠️  Archivo no encontrado: {attachment_path}")
        
        if not attachments_found:
            print("\n⚠️  No se encontraron archivos adjuntos. Creando archivos de ejemplo...")
            # Ejecutar el script de crear PDF si no existen los archivos
            create_script = TEST_DIR / "crear_pdf_ejemplo.py"
            if create_script.exists():
                import subprocess
                subprocess.run(['python3', str(create_script)], cwd=str(TEST_DIR))
                print("   Ejecuta el script nuevamente para incluir los adjuntos.")
                return
        
        # Conectar y enviar
        print(f"\n🔌 Conectando a {SMTP_SERVER}:{SMTP_PORT}...")
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.set_debuglevel(1)  # Ver debug info
        
        # Para relay local, no usar STARTTLS
        # Si necesitas TLS, descomenta la siguiente línea:
        # print("Iniciando STARTTLS...")
        # server.starttls()
        
        print(f"🔐 Autenticando como {SMTP_USERNAME}...")
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        
        print(f"📨 Enviando email de {FROM_EMAIL} a {TO_EMAIL}...")
        server.send_message(msg)
        
        server.quit()
        
        print("\n✅ Email enviado exitosamente!")
        print(f"   De: {FROM_EMAIL}")
        print(f"   Para: {TO_EMAIL}")
        print(f"   Asunto: {SUBJECT}")
        print(f"   Adjuntos: {len(attachments_found)} archivo(s)")
        for att in attachments_found:
            print(f"      - {att}")
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"\n❌ Error de autenticación: {e}")
        print("   Verifica SMTP_USERNAME y SMTP_PASSWORD")
        
    except smtplib.SMTPException as e:
        print(f"\n❌ Error SMTP: {e}")
        
    except ConnectionRefusedError:
        print(f"\n❌ Conexión rechazada a {SMTP_SERVER}:{SMTP_PORT}")
        print("   Verifica que el servidor esté corriendo")
        
    except Exception as e:
        print(f"\n❌ Error inesperado: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("=" * 60)
    print("Script de Prueba - SMTP Relay")
    print("=" * 60)
    print()
    send_test_email()
