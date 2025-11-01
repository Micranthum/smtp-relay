#!/usr/bin/env python3
"""
Script de Prueba de Envío Masivo de Emails
Envía emails reales a direcciones temporales de Mailinator
y mide el rendimiento del relay
"""

import smtplib
import time
import threading
import sys
import os
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from datetime import datetime
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import random
import string
import requests
import json

# Agregar path al módulo
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Configuración
SMTP_SERVER = "smtp.aguafria.mx"
SMTP_PORT_SSL = 465
SMTP_PORT_STARTTLS = 587
USERNAME = "contpaq.nominas@aguafria.mx"
PASSWORD = "Ksh456Ljd953e1gg5r6yyu1"  # Cambiar según tu configuración
FROM_EMAIL = "contpaq.nominas@aguafria.mx"

# Colores para terminal
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

# Estadísticas globales
stats = {
    'total': 0,
    'success': 0,
    'failed': 0,
    'rate_limited': 0,
    'connection_errors': 0,
    'auth_errors': 0,
    'timeout_errors': 0,
    'smtp_errors': defaultdict(int),
    'start_time': None,
    'end_time': None,
    'response_times': [],
    'verified_delivered': 0,  # Emails verificados como entregados
    'verified_failed': 0,     # Emails que no llegaron
    'verification_errors': 0, # Errores al verificar
}
stats_lock = threading.Lock()

# Lista de emails enviados para verificación
sent_emails = []
sent_emails_lock = threading.Lock()


def check_mailinator_inbox(unique_id, max_retries=3, retry_delay=2):
    """
    Verifica si un email llegó a Mailinator
    
    Args:
        unique_id: ID único del inbox de Mailinator
        max_retries: Número de reintentos
        retry_delay: Segundos entre reintentos
    
    Returns:
        dict con resultado de la verificación
    """
    result = {
        'found': False,
        'messages_count': 0,
        'error': None
    }
    
    # API pública de Mailinator
    # Nota: Mailinator tiene una API pública simple sin autenticación
    url = f"https://www.mailinator.com/api/webinbox?to={unique_id}&token=public"
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Verificar si hay mensajes
                if 'messages' in data and len(data['messages']) > 0:
                    result['found'] = True
                    result['messages_count'] = len(data['messages'])
                    return result
                else:
                    # No hay mensajes aún, esperar y reintentar
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                    continue
            else:
                result['error'] = f"HTTP {response.status_code}"
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                continue
                
        except requests.exceptions.Timeout:
            result['error'] = "Timeout al verificar"
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            continue
        except Exception as e:
            result['error'] = f"Error: {type(e).__name__}: {str(e)}"
            if attempt < max_retries - 1:
                time.sleep(retry_delay)
            continue
    
    return result


def verify_deliveries(emails_to_verify, show_progress=True):
    """
    Verifica la entrega de múltiples emails
    
    Args:
        emails_to_verify: Lista de emails a verificar
        show_progress: Mostrar progreso en pantalla
    
    Returns:
        dict con estadísticas de verificación
    """
    verification_results = {
        'total': len(emails_to_verify),
        'delivered': 0,
        'not_delivered': 0,
        'errors': 0,
        'details': []
    }
    
    if show_progress:
        print(f"\n{Colors.CYAN}Verificando entrega de emails...{Colors.RESET}")
        print(f"Esperando unos segundos para que lleguen los emails...\n")
        time.sleep(5)  # Dar tiempo a que lleguen los emails
    
    for i, email_info in enumerate(emails_to_verify, 1):
        unique_id = email_info['unique_id']
        
        if show_progress:
            sys.stdout.write(f'\r{Colors.CYAN}Verificando: {i}/{verification_results["total"]} '
                           f'| ✅ {verification_results["delivered"]} '
                           f'❌ {verification_results["not_delivered"]} '
                           f'⚠️  {verification_results["errors"]}{Colors.RESET}')
            sys.stdout.flush()
        
        check_result = check_mailinator_inbox(unique_id)
        
        detail = {
            'email_number': email_info['number'],
            'to': email_info['to'],
            'unique_id': unique_id,
            'delivered': check_result['found'],
            'messages_count': check_result['messages_count'],
            'error': check_result['error']
        }
        
        if check_result['found']:
            verification_results['delivered'] += 1
            with stats_lock:
                stats['verified_delivered'] += 1
        elif check_result['error']:
            verification_results['errors'] += 1
            with stats_lock:
                stats['verification_errors'] += 1
        else:
            verification_results['not_delivered'] += 1
            with stats_lock:
                stats['verified_failed'] += 1
        
        verification_results['details'].append(detail)
        
        # Pequeño delay para no saturar la API de Mailinator
        time.sleep(0.5)
    
    if show_progress:
        print()  # Nueva línea después del progreso
    
    return verification_results


def generate_test_email(index):
    """
    Genera un email de prueba único usando Mailinator
    Mailinator permite ver los emails en https://www.mailinator.com/v4/public/inboxes.jsp?to=NOMBRE
    """
    # Generar ID único
    unique_id = f"test{index:05d}-{int(time.time())}"
    
    # Usar mailinator.com - cualquier email @mailinator.com es válido
    # También soporta otros dominios como @guerrillamail.com
    test_email = f"{unique_id}@mailinator.com"
    
    return test_email, unique_id


def send_single_email(email_number, use_ssl=True, timeout=30):
    """
    Envía un email individual
    
    Returns:
        dict con resultado del envío
    """
    start_time = time.time()
    to_email, unique_id = generate_test_email(email_number)
    
    result = {
        'number': email_number,
        'success': False,
        'to': to_email,
        'unique_id': unique_id,
        'response_time': 0,
        'error': None,
        'timestamp': datetime.now().isoformat()
    }
    
    try:
        # Crear mensaje
        msg = MIMEMultipart('alternative')
        msg['From'] = FROM_EMAIL
        msg['To'] = to_email
        msg['Subject'] = f"Test #{email_number:05d} - Prueba de Carga SMTP Relay"
        
        # Cuerpo HTML
        html_body = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                .header {{ background-color: #4CAF50; color: white; padding: 20px; text-align: center; }}
                .content {{ padding: 20px; border: 1px solid #ddd; margin-top: 10px; }}
                .info {{ background-color: #f0f0f0; padding: 10px; margin: 10px 0; }}
                .success {{ color: #4CAF50; font-weight: bold; }}
            </style>
        </head>
        <body>
            <div class="header">
                <h1>✅ Email de Prueba Recibido</h1>
            </div>
            <div class="content">
                <h2>Información del Email</h2>
                <div class="info">
                    <p><strong>Número de Email:</strong> #{email_number:05d}</p>
                    <p><strong>ID Único:</strong> {unique_id}</p>
                    <p><strong>Timestamp Envío:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p><strong>Destinatario:</strong> {to_email}</p>
                    <p><strong>Remitente:</strong> {FROM_EMAIL}</p>
                </div>
                
                <h2>Estado del Envío</h2>
                <p class="success">✅ Si estás leyendo esto, el email llegó correctamente</p>
                
                <h2>Verificación</h2>
                <p>Puedes verificar este email en:</p>
                <p><a href="https://www.mailinator.com/v4/public/inboxes.jsp?to={unique_id}">
                   https://www.mailinator.com/v4/public/inboxes.jsp?to={unique_id}
                </a></p>
                
                <hr>
                <p style="color: #666; font-size: 12px;">
                    Este es un email de prueba generado automáticamente por el sistema de pruebas
                    de carga del SMTP Relay. Este mensaje se autodestruirá en unas horas.
                </p>
            </div>
        </body>
        </html>
        """
        
        # Cuerpo texto plano (fallback)
        text_body = f"""
        EMAIL DE PRUEBA #{email_number:05d}
        =====================================
        
        ID Único: {unique_id}
        Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        Destinatario: {to_email}
        Remitente: {FROM_EMAIL}
        
        ✅ Si estás leyendo esto, el email llegó correctamente
        
        Verificar en: https://www.mailinator.com/v4/public/inboxes.jsp?to={unique_id}
        
        ---
        Este es un email de prueba del sistema SMTP Relay
        """
        
        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))
        
        # Conectar y enviar
        port = SMTP_PORT_SSL if use_ssl else SMTP_PORT_STARTTLS
        
        if use_ssl:
            smtp = smtplib.SMTP_SSL(SMTP_SERVER, port, timeout=timeout)
        else:
            smtp = smtplib.SMTP(SMTP_SERVER, port, timeout=timeout)
            smtp.starttls()
        
        smtp.login(USERNAME, PASSWORD)
        smtp.send_message(msg)
        smtp.quit()
        
        # Éxito
        result['success'] = True
        result['response_time'] = time.time() - start_time
        
        with stats_lock:
            stats['success'] += 1
            stats['response_times'].append(result['response_time'])
        
        with sent_emails_lock:
            sent_emails.append({
                'number': email_number,
                'to': to_email,
                'unique_id': unique_id,
                'timestamp': result['timestamp']
            })
        
        return result
        
    except smtplib.SMTPAuthenticationError as e:
        result['error'] = f"Error de autenticación: {str(e)}"
        with stats_lock:
            stats['auth_errors'] += 1
            stats['failed'] += 1
            stats['smtp_errors']['auth'] += 1
    
    except smtplib.SMTPServerDisconnected as e:
        result['error'] = f"Servidor desconectado: {str(e)}"
        with stats_lock:
            stats['connection_errors'] += 1
            stats['failed'] += 1
            stats['smtp_errors']['disconnected'] += 1
    
    except TimeoutError as e:
        result['error'] = f"Timeout: {str(e)}"
        with stats_lock:
            stats['timeout_errors'] += 1
            stats['failed'] += 1
            stats['smtp_errors']['timeout'] += 1
    
    except smtplib.SMTPException as e:
        error_msg = str(e).lower()
        if any(word in error_msg for word in ['rate', 'limit', 'too many', 'throttl']):
            result['error'] = f"Rate limit alcanzado: {str(e)}"
            with stats_lock:
                stats['rate_limited'] += 1
                stats['failed'] += 1
                stats['smtp_errors']['rate_limit'] += 1
        else:
            result['error'] = f"Error SMTP: {str(e)}"
            with stats_lock:
                stats['failed'] += 1
                stats['smtp_errors']['smtp_general'] += 1
    
    except Exception as e:
        result['error'] = f"Error desconocido: {type(e).__name__}: {str(e)}"
        with stats_lock:
            stats['failed'] += 1
            stats['smtp_errors']['unknown'] += 1
    
    result['response_time'] = time.time() - start_time
    return result


def print_progress_bar(current, total, start_time, bar_length=50):
    """Imprime barra de progreso"""
    percent = (current / total) * 100
    elapsed = time.time() - start_time
    rate = current / elapsed if elapsed > 0 else 0
    eta = (total - current) / rate if rate > 0 else 0
    
    filled = int(bar_length * current / total)
    bar = '█' * filled + '░' * (bar_length - filled)
    
    sys.stdout.write(f'\r{Colors.CYAN}[{bar}] {percent:5.1f}% '
                     f'({current}/{total}) | '
                     f'✅ {stats["success"]} ❌ {stats["failed"]} | '
                     f'⚡ {rate:.1f}/s | '
                     f'ETA: {eta:.0f}s{Colors.RESET}')
    sys.stdout.flush()


def print_summary():
    """Imprime resumen de resultados"""
    total_time = stats['end_time'] - stats['start_time']
    
    print("\n\n" + "=" * 80)
    print(f"{Colors.BOLD}{Colors.CYAN}📊 RESUMEN DE PRUEBA DE CARGA{Colors.RESET}")
    print("=" * 80)
    
    # Resultados generales
    print(f"\n{Colors.BOLD}Emails:{Colors.RESET}")
    print(f"  Total enviados: {stats['total']}")
    print(f"  {Colors.GREEN}✅ Exitosos: {stats['success']} ({stats['success']/stats['total']*100:.1f}%){Colors.RESET}")
    print(f"  {Colors.RED}❌ Fallidos: {stats['failed']} ({stats['failed']/stats['total']*100:.1f}%){Colors.RESET}")
    
    # Desglose de errores
    if stats['failed'] > 0:
        print(f"\n{Colors.BOLD}Errores:{Colors.RESET}")
        if stats['auth_errors'] > 0:
            print(f"  🔐 Autenticación: {stats['auth_errors']}")
        if stats['connection_errors'] > 0:
            print(f"  🔌 Conexión: {stats['connection_errors']}")
        if stats['timeout_errors'] > 0:
            print(f"  ⏱️  Timeout: {stats['timeout_errors']}")
        if stats['rate_limited'] > 0:
            print(f"  {Colors.RED}🚦 Rate Limit: {stats['rate_limited']}{Colors.RESET}")
        
        if stats['smtp_errors']:
            print(f"\n{Colors.BOLD}  Desglose detallado:{Colors.RESET}")
            for error_type, count in sorted(stats['smtp_errors'].items(), key=lambda x: x[1], reverse=True):
                print(f"    • {error_type}: {count}")
    
    # Rendimiento
    print(f"\n{Colors.BOLD}Rendimiento:{Colors.RESET}")
    print(f"  ⏱️  Tiempo total: {total_time:.2f} segundos")
    print(f"  ⚡ Tasa promedio: {stats['total']/total_time:.2f} emails/seg")
    
    if stats['response_times']:
        avg_time = sum(stats['response_times']) / len(stats['response_times'])
        min_time = min(stats['response_times'])
        max_time = max(stats['response_times'])
        print(f"  📊 Tiempo de respuesta:")
        print(f"     - Promedio: {avg_time:.3f}s")
        print(f"     - Mínimo: {min_time:.3f}s")
        print(f"     - Máximo: {max_time:.3f}s")
    
    # Proyecciones
    if stats['success'] > 0:
        rate_per_minute = (stats['success'] / total_time) * 60
        print(f"\n{Colors.BOLD}Proyecciones:{Colors.RESET}")
        print(f"  📧 Capacidad real: ~{rate_per_minute:.0f} emails/minuto")
        print(f"  📊 Para 100 emails: ~{100/rate_per_minute:.1f} minutos")
        print(f"  📊 Para 500 emails: ~{500/rate_per_minute:.1f} minutos")
        print(f"  📊 Para 1000 emails: ~{1000/rate_per_minute:.1f} minutos")
    
    # Verificación de emails
    if sent_emails:
        print(f"\n{Colors.BOLD}📬 Verificación Automática de Entregas:{Colors.RESET}")
        
        # Realizar verificación automática
        verification_results = verify_deliveries(sent_emails, show_progress=True)
        
        delivered = verification_results['delivered']
        not_delivered = verification_results['not_delivered']
        errors = verification_results['errors']
        total_verified = verification_results['total']
        
        print(f"  Total verificados: {total_verified}")
        print(f"  {Colors.GREEN}✅ Entregados: {delivered} ({delivered/total_verified*100:.1f}%){Colors.RESET}")
        print(f"  {Colors.RED}❌ No entregados: {not_delivered} ({not_delivered/total_verified*100:.1f}%){Colors.RESET}")
        print(f"  {Colors.YELLOW}⚠️  Errores de verificación: {errors} ({errors/total_verified*100:.1f}%){Colors.RESET}")
        
        # Tasa de entrega real vs aceptación SMTP
        if stats['success'] > 0:
            delivery_rate = delivered / stats['success'] * 100
            print(f"\n  {Colors.CYAN}📊 Tasa de entrega real: {delivery_rate:.1f}% (de emails aceptados por SMTP){Colors.RESET}")
        
        # Mostrar algunos ejemplos de verificación manual
        print(f"\n  {Colors.YELLOW}Verificación manual (primeros 3):{Colors.RESET}")
        for i, email in enumerate(sent_emails[:3], 1):
            url = f"https://www.mailinator.com/v4/public/inboxes.jsp?to={email['unique_id']}"
            print(f"    {i}. {email['to']}")
            print(f"       {Colors.CYAN}{url}{Colors.RESET}")

    
    # Recomendaciones
    print(f"\n{Colors.BOLD}{Colors.YELLOW}💡 RECOMENDACIONES:{Colors.RESET}")
    
    success_rate = (stats['success'] / stats['total']) * 100
    
    # Verificar tasa de entrega real si hay datos
    if stats['verified_delivered'] > 0 and stats['success'] > 0:
        actual_delivery_rate = (stats['verified_delivered'] / stats['success']) * 100
        
        if actual_delivery_rate < 90:
            print(f"  {Colors.RED}⚠️  BAJA TASA DE ENTREGA REAL ({actual_delivery_rate:.1f}%){Colors.RESET}")
            print(f"     • Los emails se aceptan por SMTP pero no llegan al destino")
            print(f"     • Verifica configuración de Microsoft Graph API")
            print(f"     • Revisa logs del servidor para errores de relay")
    
    if stats['rate_limited'] > 0:
        print(f"  {Colors.RED}⚠️  RATE LIMITING DETECTADO{Colors.RESET}")
        print(f"     • Aumenta RATE_LIMIT_PER_MINUTE en .env")
        print(f"     • Considera implementar sistema de colas")
        print(f"     • Reduce concurrencia o agrega delays")
    
    if stats['timeout_errors'] > total_time * 0.1:
        print(f"  ⚠️  Muchos timeouts detectados")
        print(f"     • Reduce el número de conexiones concurrentes")
        print(f"     • Verifica recursos del servidor")
    
    if success_rate < 95:
        print(f"  {Colors.RED}⚠️  Tasa de éxito baja ({success_rate:.1f}%){Colors.RESET}")
        print(f"     • Revisa logs del servidor: docker-compose logs")
        print(f"     • Verifica configuración de Microsoft Graph API")
    elif success_rate >= 99:
        print(f"  {Colors.GREEN}✅ Excelente tasa de éxito ({success_rate:.1f}%){Colors.RESET}")

    
    print("\n" + "=" * 80 + "\n")


def main():
    """Función principal"""
    parser = argparse.ArgumentParser(
        description='Prueba de carga para SMTP Relay con emails reales',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Ejemplos de uso:
  %(prog)s --emails 100 --threads 5          # 100 emails, 5 concurrentes
  %(prog)s --emails 1000 --threads 10        # 1000 emails, 10 concurrentes
  %(prog)s --emails 50 --mode starttls       # Usar STARTTLS en vez de SSL
        """
    )
    
    parser.add_argument('--emails', type=int, default=100,
                        help='Número de emails a enviar (default: 100)')
    parser.add_argument('--threads', type=int, default=5,
                        help='Conexiones concurrentes (default: 5)')
    parser.add_argument('--mode', choices=['ssl', 'starttls'], default='ssl',
                        help='Modo de conexión (default: ssl)')
    parser.add_argument('--timeout', type=int, default=30,
                        help='Timeout de conexión en segundos (default: 30)')
    
    args = parser.parse_args()
    
    # Configurar estadísticas
    stats['total'] = args.emails
    use_ssl = (args.mode == 'ssl')
    port = SMTP_PORT_SSL if use_ssl else SMTP_PORT_STARTTLS
    
    # Imprimir encabezado
    print("\n" + "=" * 80)
    print(f"{Colors.BOLD}{Colors.CYAN}📧 PRUEBA DE CARGA SMTP RELAY{Colors.RESET}")
    print("=" * 80)
    print(f"\n{Colors.BOLD}Configuración:{Colors.RESET}")
    print(f"  Servidor: {SMTP_SERVER}:{port}")
    print(f"  Modo: {args.mode.upper()}")
    print(f"  Emails a enviar: {args.emails}")
    print(f"  Conexiones concurrentes: {args.threads}")
    print(f"  Usuario: {USERNAME}")
    print(f"  Remitente: {FROM_EMAIL}")
    print(f"\n{Colors.YELLOW}Los emails se enviarán a direcciones @mailinator.com")
    print(f"Puedes verificar su recepción en https://www.mailinator.com{Colors.RESET}\n")
    
    input(f"{Colors.BOLD}Presiona ENTER para comenzar...{Colors.RESET} ")
    
    # Iniciar prueba
    print(f"\n{Colors.CYAN}Iniciando envío de emails...{Colors.RESET}\n")
    stats['start_time'] = time.time()
    
    # Enviar emails con ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=args.threads) as executor:
        futures = {
            executor.submit(send_single_email, i, use_ssl, args.timeout): i 
            for i in range(1, args.emails + 1)
        }
        
        completed = 0
        for future in as_completed(futures):
            completed += 1
            try:
                result = future.result()
                if not result['success'] and result['error']:
                    # Log errores en tiempo real (opcional)
                    pass
            except Exception as e:
                print(f"\n{Colors.RED}Error procesando email: {e}{Colors.RESET}")
            
            print_progress_bar(completed, args.emails, stats['start_time'])
    
    stats['end_time'] = time.time()
    
    # Imprimir resumen
    print_summary()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Prueba interrumpida por el usuario{Colors.RESET}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n{Colors.RED}Error fatal: {e}{Colors.RESET}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
