from __future__ import annotations

from celery import Celery
from kombu import Queue

from satsaathi_core.settings import get_settings

#: Imported by the worker at startup rather than at module import time, so
#: `create_celery_app` stays cheap enough for tests to call repeatedly.
TASK_MODULES = ["satsaathi_worker.tasks"]


def create_celery_app() -> Celery:
    settings = get_settings()
    app = Celery(
        "satsaathi",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=TASK_MODULES,
    )
    app.conf.task_queues = (Queue("cpu"), Queue("gpu"), Queue("lang"))
    app.conf.task_default_queue = "cpu"
    # A raster job takes seconds to minutes; the default of prefetching four
    # at a time would leave three queued behind one slow scene.
    app.conf.worker_prefetch_multiplier = 1
    app.conf.task_acks_late = True
    return app


celery_app = create_celery_app()
