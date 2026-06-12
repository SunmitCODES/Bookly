"""Celery application + Beat schedule for background reminders."""
from celery import Celery

from app.config import settings

celery_app = Celery(
    "bookly",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    beat_schedule={
        "sweep-reminders-every-15-min": {
            "task": "app.tasks.reminder_tasks.sweep_reminders",
            "schedule": 15 * 60,  # seconds
        },
    },
)

# Ensure the task module is imported so the task registers.
import app.tasks.reminder_tasks  # noqa: E402,F401
