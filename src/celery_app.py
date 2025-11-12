"""
Celery application configuration for SMTP Relay
Handles task queue management with rate limiting for Microsoft Graph API
"""
from celery import Celery
from kombu import Queue, Exchange
from .config import Config

def create_celery_app():
    """
    Factory function to create and configure Celery application
    """
    app = Celery('smtp_relay')
    
    # Broker and backend configuration
    app.conf.broker_url = Config.CELERY_BROKER_URL
    app.conf.result_backend = Config.CELERY_RESULT_BACKEND
    
    # Serialization
    app.conf.task_serializer = 'json'
    app.conf.result_serializer = 'json'
    app.conf.accept_content = ['json']
    app.conf.timezone = 'America/Mexico_City'
    app.conf.enable_utc = True
    
    # Task execution settings
    app.conf.task_acks_late = True
    app.conf.task_reject_on_worker_lost = True
    app.conf.worker_prefetch_multiplier = 1
    
    # Result backend settings
    app.conf.result_expires = 3600
    app.conf.result_persistent = True
    
    # Queue configuration
    default_exchange = Exchange('smtp_relay', type='direct', durable=True)
    
    app.conf.task_queues = (
        Queue(
            'email_outbound',
            exchange=default_exchange,
            routing_key='email.outbound',
            queue_arguments={'x-max-priority': 10}
        ),
    )
    
    app.conf.task_default_queue = 'email_outbound'
    app.conf.task_default_exchange = 'smtp_relay'
    app.conf.task_default_routing_key = 'email.outbound'
    
    # Rate limiting for Graph API
    # Microsoft Graph API supports up to 4 concurrent requests
    # Exchange Online has a limit of 30 emails per minute
    app.conf.worker_concurrency = 1
    app.conf.worker_max_tasks_per_child = 1000
    
    # Task routing
    app.conf.task_routes = {
        'src.tasks.send_email_via_graph': {
            'queue': 'email_outbound',
            'routing_key': 'email.outbound',
        },
    }
    
    # Retry configuration
    app.conf.task_annotations = {
        'src.tasks.send_email_via_graph': {
            'rate_limit': f'{Config.GRAPH_API_RATE_LIMIT_PER_MINUTE}/m',
        }
    }
    
    # Import tasks
    app.autodiscover_tasks(['src'])
    
    return app


celery_app = create_celery_app()
