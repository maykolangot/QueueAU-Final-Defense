from celery import Celery
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'QueueAU.settings')

app = Celery('QueueAU')

# Load Celery config from Django settings
app.config_from_object('django.conf:settings', namespace='CELERY')

# Auto-discover tasks from all registered apps
app.autodiscover_tasks()
