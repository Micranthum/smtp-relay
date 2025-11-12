"""
Celery tasks for email processing
Handles email sending with retry logic and rate limiting
"""
import base64
import requests
from email.parser import BytesParser
from email.policy import default
from email.utils import parseaddr
from celery import Task
from celery.exceptions import Reject, Retry
from .celery_app import celery_app
from .config import Config
from .logger import logger
from .oauth import MS365OAuth


class EmailSendTask(Task):
    """
    Base task class for email sending with dependency injection
    """
    _oauth_client = None
    
    @property
    def oauth_client(self):
        """
        Lazy initialization of OAuth client (singleton per worker)
        """
        if self._oauth_client is None:
            self._oauth_client = MS365OAuth()
        return self._oauth_client


@celery_app.task(
    bind=True,
    base=EmailSendTask,
    name='src.tasks.send_email_via_graph',
    max_retries=Config.CELERY_MAX_RETRIES,
    default_retry_delay=Config.CELERY_RETRY_DELAY,
    autoretry_for=(requests.exceptions.RequestException,),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
)
def send_email_via_graph(self, envelope_data: dict):
    """
    Send email via Microsoft Graph API with retry logic
    
    Args:
        envelope_data: Dictionary containing email envelope information
            - mail_from: Sender email address
            - rcpt_tos: List of recipient email addresses
            - content: Email content as bytes (base64 encoded)
            - client_ip: Client IP address for logging
    
    Returns:
        dict: Response information from Graph API
    
    Raises:
        Retry: When a retryable error occurs
        Reject: When a permanent error occurs
    """
    try:
        mail_from = envelope_data['mail_from']
        rcpt_tos = envelope_data['rcpt_tos']
        content_b64 = envelope_data['content']
        client_ip = envelope_data.get('client_ip', 'unknown')
        
        logger.info(
            f"Processing email task from {mail_from} to {rcpt_tos} "
            f"(client: {client_ip}, attempt: {self.request.retries + 1})"
        )
        
        # Decode email content
        content = base64.b64decode(content_b64)
        
        # Parse email message
        msg = BytesParser(policy=default).parsebytes(content)
        
        # Build Graph API message
        graph_message = _build_graph_message(msg, rcpt_tos)
        
        # Get OAuth2 token
        logger.debug("Acquiring OAuth2 token for Graph API")
        token = self.oauth_client.get_access_token()
        
        # Send via Graph API
        logger.debug(f"Sending email via Graph API from {Config.MS365_EMAIL_ADDRESS}")
        
        graph_url = (
            f"{self.oauth_client.graph_endpoint}/users/"
            f"{Config.MS365_EMAIL_ADDRESS}/sendMail"
        )
        
        headers = {
            'Authorization': f'Bearer {token}',
            'Content-Type': 'application/json'
        }
        
        payload = {
            'message': graph_message,
            'saveToSentItems': 'true'
        }
        
        response = requests.post(
            graph_url,
            headers=headers,
            json=payload,
            timeout=30
        )
        
        # Handle response
        if response.status_code == 202:
            logger.info(
                f"Email sent successfully via Graph API to {rcpt_tos} "
                f"(attempt: {self.request.retries + 1})"
            )
            return {
                'status': 'success',
                'recipients': rcpt_tos,
                'attempts': self.request.retries + 1
            }
        
        # Handle rate limiting (429 Too Many Requests)
        elif response.status_code == 429:
            retry_after = int(response.headers.get('Retry-After', 60))
            logger.warning(
                f"Rate limit exceeded for Graph API. "
                f"Retrying after {retry_after} seconds"
            )
            raise self.retry(countdown=retry_after)
        
        # Handle throttling (503 Service Unavailable)
        elif response.status_code == 503:
            logger.warning("Graph API service unavailable. Retrying with backoff")
            raise self.retry()
        
        # Handle authentication errors (401 Unauthorized)
        elif response.status_code == 401:
            logger.error("OAuth token invalid or expired. Clearing cache and retrying")
            self.oauth_client._cached_token = None
            self.oauth_client._token_expiry = None
            raise self.retry()
        
        # Handle bad request (400) - permanent error, do not retry
        elif response.status_code == 400:
            error_msg = f"Bad request to Graph API: {response.text}"
            logger.error(error_msg)
            raise Reject(error_msg, requeue=False)
        
        # Handle forbidden (403) - permanent error, do not retry
        elif response.status_code == 403:
            error_msg = f"Forbidden - check permissions: {response.text}"
            logger.error(error_msg)
            raise Reject(error_msg, requeue=False)
        
        # Handle other errors with retry
        else:
            error_msg = f"Graph API error: {response.status_code} - {response.text}"
            logger.error(error_msg)
            
            if self.request.retries >= self.max_retries:
                raise Reject(error_msg, requeue=False)
            else:
                raise self.retry()
    
    except (Retry, Reject):
        raise
    
    except Exception as e:
        logger.error(
            f"Unexpected error sending email: {e}",
            exc_info=True
        )
        
        if self.request.retries >= self.max_retries:
            raise Reject(str(e), requeue=False)
        else:
            raise self.retry()


def _build_graph_message(msg, rcpt_tos: list) -> dict:
    """
    Build Graph API message format from email message
    
    Args:
        msg: Parsed email message
        rcpt_tos: List of recipient email addresses
    
    Returns:
        dict: Graph API message payload
    """
    subject = msg.get('Subject', 'No Subject')
    
    # Build recipient list
    to_recipients = []
    for recipient in rcpt_tos:
        name, email = parseaddr(recipient)
        to_recipients.append({
            'emailAddress': {
                'address': email if email else recipient
            }
        })
    
    # Build message structure
    graph_msg = {
        'subject': subject,
        'from': {
            'emailAddress': {
                'address': Config.MS365_EMAIL_ADDRESS
            }
        },
        'toRecipients': to_recipients
    }
    
    # Handle multipart or simple messages
    if msg.is_multipart():
        html_body = None
        text_body = None
        attachments = []
        
        for part in msg.walk():
            content_type = part.get_content_type()
            content_disposition = str(part.get('Content-Disposition', ''))
            
            if content_type == 'text/plain' and 'attachment' not in content_disposition:
                text_body = part.get_content()
            elif content_type == 'text/html' and 'attachment' not in content_disposition:
                html_body = part.get_content()
            elif 'attachment' in content_disposition or part.get_filename():
                filename = part.get_filename() or 'attachment'
                content = part.get_payload(decode=True)
                if content:
                    attachments.append({
                        '@odata.type': '#microsoft.graph.fileAttachment',
                        'name': filename,
                        'contentType': content_type,
                        'contentBytes': base64.b64encode(content).decode('utf-8')
                    })
        
        # Set body (prefer HTML, fallback to text)
        if html_body:
            graph_msg['body'] = {
                'contentType': 'HTML',
                'content': html_body
            }
        elif text_body:
            graph_msg['body'] = {
                'contentType': 'Text',
                'content': text_body
            }
        
        # Add attachments
        if attachments:
            graph_msg['attachments'] = attachments
            logger.debug(f"Including {len(attachments)} attachment(s)")
    else:
        # Simple message
        body = msg.get_content()
        content_type = msg.get_content_type()
        
        if content_type == 'text/html':
            graph_msg['body'] = {
                'contentType': 'HTML',
                'content': body
            }
        else:
            graph_msg['body'] = {
                'contentType': 'Text',
                'content': body
            }
    
    return graph_msg
