#!/usr/bin/env python3
"""
Quick test script to verify Celery configuration
Run this after starting the services to ensure everything is connected
"""
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from src.celery_app import celery_app
from src.config import Config

def test_celery_connection():
    """Test Celery broker connection"""
    print("Testing Celery Configuration")
    print("=" * 60)
    
    print(f"Broker URL: {Config.CELERY_BROKER_URL}")
    print(f"Result Backend: {Config.CELERY_RESULT_BACKEND}")
    print(f"Graph API Rate Limit: {Config.GRAPH_API_RATE_LIMIT_PER_MINUTE}/min")
    print(f"Incoming Rate Limit: {Config.INCOMING_RATE_LIMIT_PER_MINUTE}/min")
    print(f"Max Retries: {Config.CELERY_MAX_RETRIES}")
    print(f"Retry Delay: {Config.CELERY_RETRY_DELAY}s")
    print("")
    
    print("Checking broker connection...")
    try:
        # Inspect registered tasks
        inspect = celery_app.control.inspect()
        
        # Check if workers are available
        stats = inspect.stats()
        if stats:
            print(f"Active workers: {len(stats)}")
            for worker_name, worker_stats in stats.items():
                print(f"  - {worker_name}")
        else:
            print("WARNING: No active workers found")
            print("Make sure celery-worker container is running:")
            print("  docker compose ps celery-worker")
            return False
        
        # Check registered tasks
        registered = inspect.registered()
        if registered:
            print("\nRegistered tasks:")
            for worker_name, tasks in registered.items():
                for task in tasks:
                    if 'src.tasks' in task:
                        print(f"  - {task}")
        
        print("\nConnection successful")
        return True
        
    except Exception as e:
        print(f"ERROR: Failed to connect to broker: {e}")
        print("\nMake sure Redis is running:")
        print("  docker compose ps redis")
        return False

if __name__ == '__main__':
    success = test_celery_connection()
    sys.exit(0 if success else 1)
