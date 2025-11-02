"""
Test script for SMTP Relay
Sends a test email through the relay with attachments (PDF and XML)
"""

import smtplib
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from datetime import datetime
from pathlib import Path

# Configuration - ADJUST ACCORDING TO YOUR ENVIRONMENT
SMTP_SERVER = "localhost"  # or the IP/domain of your server
SMTP_PORT = 465 # Use 587 for development without TLS, 465 for production with SSL
USE_TLS = True # Set to True if TLS is enabled on the server
SMTP_USERNAME = "yourusername"  # SMTP_RELAY_USERNAME value
SMTP_PASSWORD = "yourpassword"  # SMTP_RELAY_PASSWORD value

# Test email
FROM_EMAIL = "sender@example.com"
TO_EMAIL = "nadeen37@2200freefonts.com"
SUBJECT = f"Test SMTP Relay with Attachment - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"

# Test attachment files
SCRIPT_DIR = Path(__file__).parent
ATTACHMENTS = [
    SCRIPT_DIR / "example.pdf",
]

def send_test_email():
    """Send a test email with attachments"""
    
    try:
        # Create message
        msg = MIMEMultipart('mixed')
        msg['Subject'] = SUBJECT
        msg['From'] = FROM_EMAIL
        msg['To'] = TO_EMAIL
        
        # Create message body (alternative part for text/html)
        body = MIMEMultipart('alternative')
        
        # Email content
        text = """
        This is a test email from the SMTP Relay with attachment.
        
        If you receive this message with the attachment (PDF), it means the relay
        is working correctly and can send payroll receipts.
        
        Included attachment:
        - recibo_ejemplo.pdf (Sample payroll receipt)
        
        System: SMTP Relay - Contpaq to Microsoft 365
        Time: {time}
        """.format(time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        html = """
        <html>
          <body>
            <h2>Test Email - SMTP Relay</h2>
            <p>This is a test email from the <strong>SMTP Relay</strong> with attachment.</p>
            <p>If you receive this message with the attachment, it means the relay is working correctly.</p>
            
            <h3>Attachment:</h3>
            <ul>
              <li><strong>recibo_ejemplo.pdf</strong> - Sample payroll receipt</li>
            </ul>
            
            <hr>
            <p><small>
              <strong>System:</strong> SMTP Relay - Contpaq to Microsoft 365<br>
              <strong>Time:</strong> {time}<br>
              <strong>Method:</strong> Microsoft Graph API
            </small></p>
          </body>
        </html>
        """.format(time=datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
        
        # Attach message parts
        part1 = MIMEText(text, 'plain', 'utf-8')
        part2 = MIMEText(html, 'html', 'utf-8')
        body.attach(part1)
        body.attach(part2)
        
        # Attach body to main message
        msg.attach(body)
        
        # Attach files
        attachments_found = []
        for attachment_path in ATTACHMENTS:
            if attachment_path.exists():
                print(f"Attaching: {attachment_path.name} ({attachment_path.stat().st_size} bytes)")

                
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
                print(f"File not found: {attachment_path}")
        
        if not attachments_found:
            print("\nNo attachment files found. Creating sample files...")
            # Execute the PDF creation script if files don't exist
            create_script = SCRIPT_DIR / "crear_pdf_ejemplo.py"
            if create_script.exists():
                import subprocess
                subprocess.run(['python3', str(create_script)], cwd=str(SCRIPT_DIR))
                print("   Run the script again to include attachments.")
                return
        
        # Connect and send
        print(f"\nConnecting to {SMTP_SERVER}:{SMTP_PORT}...")
        
        if USE_TLS and SMTP_PORT == 465:
            # Use SMTP_SSL for port 465 with TLS enabled (implicit SSL)
            print("Using implicit SSL/TLS (port 465)...")
            server = smtplib.SMTP_SSL(SMTP_SERVER, SMTP_PORT)
            server.set_debuglevel(1)
        elif USE_TLS and SMTP_PORT == 587:
            # Use SMTP with STARTTLS for port 587 with TLS enabled
            print("Using STARTTLS (port 587)...")
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.set_debuglevel(1)
            server.starttls()
        else:
            # Plain SMTP without TLS (development mode)
            print("Using plain SMTP (no encryption - development only)...")
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.set_debuglevel(1)
        
        print(f"Authenticating as {SMTP_USERNAME}...")
        server.login(SMTP_USERNAME, SMTP_PASSWORD)
        
        print(f"Sending email from {FROM_EMAIL} to {TO_EMAIL}...")
        server.send_message(msg)
        
        server.quit()
        
        print("\nEmail sent successfully!")
        print(f"   From: {FROM_EMAIL}")
        print(f"   To: {TO_EMAIL}")
        print(f"   Subject: {SUBJECT}")
        print(f"   Attachments: {len(attachments_found)} file(s)")
        for att in attachments_found:
            print(f"      - {att}")
        
    except smtplib.SMTPAuthenticationError as e:
        print(f"\nAuthentication error: {e}")
        print("   Check SMTP_USERNAME and SMTP_PASSWORD")
        
    except smtplib.SMTPException as e:
        print(f"\nSMTP error: {e}")
        
    except ConnectionRefusedError:
        print(f"\nConnection refused to {SMTP_SERVER}:{SMTP_PORT}")
        print("   Check that the server is running")
        
    except Exception as e:
        print(f"\nUnexpected error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    print("=" * 60)
    print("Test Script - SMTP Relay")
    print("=" * 60)
    print()
    send_test_email()
