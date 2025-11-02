"""
Mass Email Sending Test Script
Sends real emails to temporary Mailinator addresses
and measures relay performance
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

# Add path to module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

# Configuration
SMTP_SERVER = "localhost"
SMTP_PORT_SSL = 465
SMTP_PORT_STARTTLS = 587
USERNAME = "yourusername"
PASSWORD = "yourpassword"
FROM_EMAIL = "sender@example.com"

# Terminal colors
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    MAGENTA = '\033[95m'
    RESET = '\033[0m'
    BOLD = '\033[1m'

# Global statistics
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
    'verified_delivered': 0,  # Verified as delivered emails
    'verified_failed': 0,     # Emails that didn't arrive
    'verification_errors': 0, # Errors during verification
}
stats_lock = threading.Lock()

# List of sent emails for verification
sent_emails = []
sent_emails_lock = threading.Lock()


def check_mailinator_inbox(unique_id, max_retries=3, retry_delay=2):
    """
    Check if an email arrived at Mailinator
    
    Args:
        unique_id: Unique Mailinator inbox ID
        max_retries: Number of retries
        retry_delay: Seconds between retries
    
    Returns:
        dict with verification result
    """
    result = {
        'found': False,
        'messages_count': 0,
        'error': None
    }
    
    # Mailinator public API
    # Note: Mailinator has a simple public API without authentication
    url = f"https://www.mailinator.com/api/webinbox?to={unique_id}&token=public"
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                
                # Check if there are messages
                if 'messages' in data and len(data['messages']) > 0:
                    result['found'] = True
                    result['messages_count'] = len(data['messages'])
                    return result
                else:
                    # No messages yet, wait and retry
                    if attempt < max_retries - 1:
                        time.sleep(retry_delay)
                    continue
            else:
                result['error'] = f"HTTP {response.status_code}"
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                continue
                
        except requests.exceptions.Timeout:
            result['error'] = "Timeout during verification"
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
    Verify the delivery of multiple emails
    
    Args:
        emails_to_verify: List of emails to verify
        show_progress: Show progress on screen
    
    Returns:
        dict with verification statistics
    """
    verification_results = {
        'total': len(emails_to_verify),
        'delivered': 0,
        'not_delivered': 0,
        'errors': 0,
        'details': []
    }
    
    if show_progress:
        print(f"\n{Colors.CYAN}Verifying email delivery...{Colors.RESET}")
        print(f"Waiting a few seconds for emails to arrive...\n")
        time.sleep(5)  # Give time for emails to arrive
    
    for i, email_info in enumerate(emails_to_verify, 1):
        unique_id = email_info['unique_id']
        
        if show_progress:
            sys.stdout.write(f'\r{Colors.CYAN}Verifying: {i}/{verification_results["total"]} '
                           f'| OK {verification_results["delivered"]} '
                           f'FAIL {verification_results["not_delivered"]} '
                           f'ERR {verification_results["errors"]}{Colors.RESET}')
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
        
        # Small delay to avoid saturating Mailinator API
        time.sleep(0.5)
    
    if show_progress:
        print()  # New line after progress
    
    return verification_results


def generate_test_email(index):
    """
    Generate a unique test email using Mailinator
    Mailinator allows viewing emails at https://www.mailinator.com/v4/public/inboxes.jsp?to=NAME
    """
    # Generate unique ID
    unique_id = f"test{index:05d}-{int(time.time())}"
    
    # Use mailinator.com - any email @mailinator.com is valid
    # Also supports other domains like @guerrillamail.com
    test_email = f"{unique_id}@mailinator.com"
    
    return test_email, unique_id


def send_single_email(email_number, use_ssl=True, timeout=30):
    """
    Send a single email
    
    Returns:
        dict with sending result
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
        # Create message
        msg = MIMEMultipart('alternative')
        msg['From'] = FROM_EMAIL
        msg['To'] = to_email
        msg['Subject'] = f"Test #{email_number:05d} - SMTP Relay Load Test"
        
        # HTML body
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
                <h1>Test Email Received</h1>
            </div>
            <div class="content">
                <h2>Email Information</h2>
                <div class="info">
                    <p><strong>Email Number:</strong> #{email_number:05d}</p>
                    <p><strong>Unique ID:</strong> {unique_id}</p>
                    <p><strong>Send Timestamp:</strong> {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
                    <p><strong>Recipient:</strong> {to_email}</p>
                    <p><strong>Sender:</strong> {FROM_EMAIL}</p>
                </div>
                
                <h2>Delivery Status</h2>
                <p class="success">If you are reading this, the email arrived successfully</p>
                
                <h2>Verification</h2>
                <p>You can verify this email at:</p>
                <p><a href="https://www.mailinator.com/v4/public/inboxes.jsp?to={unique_id}">
                   https://www.mailinator.com/v4/public/inboxes.jsp?to={unique_id}
                </a></p>
                
                <hr>
                <p style="color: #666; font-size: 12px;">
                    This is a test email automatically generated by the SMTP Relay load testing system.
                    This message will self-destruct in a few hours.
                </p>
            </div>
        </body>
        </html>
        """
        
        # Plain text body (fallback)
        text_body = f"""
        TEST EMAIL #{email_number:05d}
        =====================================
        
        Unique ID: {unique_id}
        Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        Recipient: {to_email}
        Sender: {FROM_EMAIL}
        
        If you are reading this, the email arrived successfully
        
        Verify at: https://www.mailinator.com/v4/public/inboxes.jsp?to={unique_id}
        
        ---
        This is a test email from the SMTP Relay system
        """
        
        msg.attach(MIMEText(text_body, 'plain'))
        msg.attach(MIMEText(html_body, 'html'))
        
        # Connect and send
        port = SMTP_PORT_SSL if use_ssl else SMTP_PORT_STARTTLS
        
        if use_ssl:
            smtp = smtplib.SMTP_SSL(SMTP_SERVER, port, timeout=timeout)
        else:
            smtp = smtplib.SMTP(SMTP_SERVER, port, timeout=timeout)
            smtp.starttls()
        
        smtp.login(USERNAME, PASSWORD)
        smtp.send_message(msg)
        smtp.quit()
        
        # Success
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
        result['error'] = f"Authentication error: {str(e)}"
        with stats_lock:
            stats['auth_errors'] += 1
            stats['failed'] += 1
            stats['smtp_errors']['auth'] += 1
    
    except smtplib.SMTPServerDisconnected as e:
        result['error'] = f"Server disconnected: {str(e)}"
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
            result['error'] = f"Rate limit reached: {str(e)}"
            with stats_lock:
                stats['rate_limited'] += 1
                stats['failed'] += 1
                stats['smtp_errors']['rate_limit'] += 1
        else:
            result['error'] = f"SMTP error: {str(e)}"
            with stats_lock:
                stats['failed'] += 1
                stats['smtp_errors']['smtp_general'] += 1
    
    except Exception as e:
        result['error'] = f"Unknown error: {type(e).__name__}: {str(e)}"
        with stats_lock:
            stats['failed'] += 1
            stats['smtp_errors']['unknown'] += 1
    
    result['response_time'] = time.time() - start_time
    return result


def print_progress_bar(current, total, start_time, bar_length=50):
    """Print progress bar"""
    percent = (current / total) * 100
    elapsed = time.time() - start_time
    rate = current / elapsed if elapsed > 0 else 0
    eta = (total - current) / rate if rate > 0 else 0
    
    filled = int(bar_length * current / total)
    bar = '█' * filled + '░' * (bar_length - filled)
    
    sys.stdout.write(f'\r{Colors.CYAN}[{bar}] {percent:5.1f}% '
                     f'({current}/{total}) | '
                     f'OK {stats["success"]} FAIL {stats["failed"]} | '
                     f'{rate:.1f}/s | '
                     f'ETA: {eta:.0f}s{Colors.RESET}')
    sys.stdout.flush()


def print_summary():
    """Print results summary"""
    total_time = stats['end_time'] - stats['start_time']
    
    print("\n\n" + "=" * 80)
    print(f"{Colors.BOLD}{Colors.CYAN}LOAD TEST SUMMARY{Colors.RESET}")
    print("=" * 80)
    
    # General results
    print(f"\n{Colors.BOLD}Emails:{Colors.RESET}")
    print(f"  Total sent: {stats['total']}")
    print(f"  {Colors.GREEN}Successful: {stats['success']} ({stats['success']/stats['total']*100:.1f}%){Colors.RESET}")
    print(f"  {Colors.RED}Failed: {stats['failed']} ({stats['failed']/stats['total']*100:.1f}%){Colors.RESET}")
    
    # Error breakdown
    if stats['failed'] > 0:
        print(f"\n{Colors.BOLD}Errors:{Colors.RESET}")
        if stats['auth_errors'] > 0:
            print(f"  Authentication: {stats['auth_errors']}")
        if stats['connection_errors'] > 0:
            print(f"  Connection: {stats['connection_errors']}")
        if stats['timeout_errors'] > 0:
            print(f"  Timeout: {stats['timeout_errors']}")
        if stats['rate_limited'] > 0:
            print(f"  {Colors.RED}Rate Limit: {stats['rate_limited']}{Colors.RESET}")
        
        if stats['smtp_errors']:
            print(f"\n{Colors.BOLD}  Detailed breakdown:{Colors.RESET}")
            for error_type, count in sorted(stats['smtp_errors'].items(), key=lambda x: x[1], reverse=True):
                print(f"    - {error_type}: {count}")
    
    # Performance
    print(f"\n{Colors.BOLD}Performance:{Colors.RESET}")
    print(f"  Total time: {total_time:.2f} seconds")
    print(f"  Average rate: {stats['total']/total_time:.2f} emails/sec")
    
    if stats['response_times']:
        avg_time = sum(stats['response_times']) / len(stats['response_times'])
        min_time = min(stats['response_times'])
        max_time = max(stats['response_times'])
        print(f"  Response time:")
        print(f"     - Average: {avg_time:.3f}s")
        print(f"     - Minimum: {min_time:.3f}s")
        print(f"     - Maximum: {max_time:.3f}s")
    
    # Projections
    if stats['success'] > 0:
        rate_per_minute = (stats['success'] / total_time) * 60
        print(f"\n{Colors.BOLD}Projections:{Colors.RESET}")
        print(f"  Real capacity: ~{rate_per_minute:.0f} emails/minute")
        print(f"  For 100 emails: ~{100/rate_per_minute:.1f} minutes")
        print(f"  For 500 emails: ~{500/rate_per_minute:.1f} minutes")
        print(f"  For 1000 emails: ~{1000/rate_per_minute:.1f} minutes")
    
    # Email verification
    if sent_emails:
        print(f"\n{Colors.BOLD}Automatic Delivery Verification:{Colors.RESET}")
        
        # Perform automatic verification
        verification_results = verify_deliveries(sent_emails, show_progress=True)
        
        delivered = verification_results['delivered']
        not_delivered = verification_results['not_delivered']
        errors = verification_results['errors']
        total_verified = verification_results['total']
        
        print(f"  Total verified: {total_verified}")
        print(f"  {Colors.GREEN}Delivered: {delivered} ({delivered/total_verified*100:.1f}%){Colors.RESET}")
        print(f"  {Colors.RED}Not delivered: {not_delivered} ({not_delivered/total_verified*100:.1f}%){Colors.RESET}")
        print(f"  {Colors.YELLOW}Verification errors: {errors} ({errors/total_verified*100:.1f}%){Colors.RESET}")
        
        # Real delivery rate vs SMTP acceptance
        if stats['success'] > 0:
            delivery_rate = delivered / stats['success'] * 100
            print(f"\n  {Colors.CYAN}Real delivery rate: {delivery_rate:.1f}% (of emails accepted by SMTP){Colors.RESET}")
        
        # Show some manual verification examples
        print(f"\n  {Colors.YELLOW}Manual verification (first 3):{Colors.RESET}")
        for i, email in enumerate(sent_emails[:3], 1):
            url = f"https://www.mailinator.com/v4/public/inboxes.jsp?to={email['unique_id']}"
            print(f"    {i}. {email['to']}")
            print(f"       {Colors.CYAN}{url}{Colors.RESET}")

    
    # Recommendations
    print(f"\n{Colors.BOLD}{Colors.YELLOW}RECOMMENDATIONS:{Colors.RESET}")
    
    success_rate = (stats['success'] / stats['total']) * 100
    
    # Check real delivery rate if data available
    if stats['verified_delivered'] > 0 and stats['success'] > 0:
        actual_delivery_rate = (stats['verified_delivered'] / stats['success']) * 100
        
        if actual_delivery_rate < 90:
            print(f"  {Colors.RED}LOW REAL DELIVERY RATE ({actual_delivery_rate:.1f}%){Colors.RESET}")
            print(f"     - Emails are accepted by SMTP but don't reach destination")
            print(f"     - Check Microsoft Graph API configuration")
            print(f"     - Review server logs for relay errors")
    
    if stats['rate_limited'] > 0:
        print(f"  {Colors.RED}RATE LIMITING DETECTED{Colors.RESET}")
        print(f"     - Increase RATE_LIMIT_PER_MINUTE in .env")
        print(f"     - Consider implementing queue system")
        print(f"     - Reduce concurrency or add delays")
    
    if stats['timeout_errors'] > total_time * 0.1:
        print(f"  Many timeouts detected")
        print(f"     - Reduce number of concurrent connections")
        print(f"     - Check server resources")
    
    if success_rate < 95:
        print(f"  {Colors.RED}Low success rate ({success_rate:.1f}%){Colors.RESET}")
        print(f"     - Review server logs: docker-compose logs")
        print(f"     - Check Microsoft Graph API configuration")
    elif success_rate >= 99:
        print(f"  {Colors.GREEN}Excellent success rate ({success_rate:.1f}%){Colors.RESET}")

    
    print("\n" + "=" * 80 + "\n")


def main():
    """Main function"""
    parser = argparse.ArgumentParser(
        description='Load test for SMTP Relay with real emails',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage examples:
  %(prog)s --emails 100 --threads 5          # 100 emails, 5 concurrent
  %(prog)s --emails 1000 --threads 10        # 1000 emails, 10 concurrent
  %(prog)s --emails 50 --mode starttls       # Use STARTTLS instead of SSL
        """
    )
    
    parser.add_argument('--emails', type=int, default=100,
                        help='Number of emails to send (default: 100)')
    parser.add_argument('--threads', type=int, default=5,
                        help='Concurrent connections (default: 5)')
    parser.add_argument('--mode', choices=['ssl', 'starttls'], default='ssl',
                        help='Connection mode (default: ssl)')
    parser.add_argument('--timeout', type=int, default=30,
                        help='Connection timeout in seconds (default: 30)')
    
    args = parser.parse_args()
    
    # Configure statistics
    stats['total'] = args.emails
    use_ssl = (args.mode == 'ssl')
    port = SMTP_PORT_SSL if use_ssl else SMTP_PORT_STARTTLS
    
    # Print header
    print("\n" + "=" * 80)
    print(f"{Colors.BOLD}{Colors.CYAN}SMTP RELAY LOAD TEST{Colors.RESET}")
    print("=" * 80)
    print(f"\n{Colors.BOLD}Configuration:{Colors.RESET}")
    print(f"  Server: {SMTP_SERVER}:{port}")
    print(f"  Mode: {args.mode.upper()}")
    print(f"  Emails to send: {args.emails}")
    print(f"  Concurrent connections: {args.threads}")
    print(f"  User: {USERNAME}")
    print(f"  Sender: {FROM_EMAIL}")
    print(f"\n{Colors.YELLOW}Emails will be sent to @mailinator.com addresses")
    print(f"You can verify receipt at https://www.mailinator.com{Colors.RESET}\n")
    
    input(f"{Colors.BOLD}Press ENTER to start...{Colors.RESET} ")
    
    # Start test
    print(f"\n{Colors.CYAN}Starting email sending...{Colors.RESET}\n")
    stats['start_time'] = time.time()
    
    # Send emails with ThreadPoolExecutor
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
                    # Log errors in real time (optional)
                    pass
            except Exception as e:
                print(f"\n{Colors.RED}Error processing email: {e}{Colors.RESET}")
            
            print_progress_bar(completed, args.emails, stats['start_time'])
    
    stats['end_time'] = time.time()
    
    # Print summary
    print_summary()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n{Colors.YELLOW}Test interrupted by user{Colors.RESET}\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n{Colors.RED}Fatal error: {e}{Colors.RESET}\n")
        import traceback
        traceback.print_exc()
        sys.exit(1)
