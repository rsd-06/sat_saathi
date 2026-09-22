from __future__ import annotations

from celery import Celery
from kombu import Queue

from satsaathi_core.settings import get_settings


def create_celery_app() -> Celery:
    settings = get_settings()
    app = Celery("satsaathi", broker=settings.redis_url, backend=settings.redis_url)
    app.conf.task_queues = (Queue("cpu"), Queue("gpu"), Queue("lang"))
    app.conf.task_default_queue = "cpu"
    return app


celery_app = create_celery_app()
