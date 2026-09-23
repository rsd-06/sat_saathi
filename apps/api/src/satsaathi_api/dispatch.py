"""Deciding where a job actually runs.

Two deployments, one behaviour. `inline` runs the job in this process on a
FastAPI background task, which is what a developer with nothing but `uv run`
gets. `celery` hands it to a worker over Redis, which is what the compose
stack and anything resembling production do. Neither changes the trace.

The choice is a setting rather than a guess: probing the broker at request
time would make a misconfigured deployment look like a working one.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import BackgroundTasks

from satsaathi_core.settings import Settings
from satsaathi_jobs.runner import run_job

logger = logging.getLogger(__name__)

#: The queue the CPU-bound pipeline belongs on. The worker also listens on
#: `gpu` and `lang`, which the model-backed steps will use once they are real.
CPU_QUEUE = "cpu"
TASK_NAME = "satsaathi.run_job"


def send_to_celery(job_id: uuid.UUID, settings: Settings) -> None:
    """Enqueue the job by name, without importing the worker package.

    The API knows the task's name and queue and nothing else about it, so the
    worker stays free to change how it runs one.
    """
    from celery import Celery

    producer = Celery(broker=settings.redis_url)
    producer.send_task(TASK_NAME, args=[str(job_id)], queue=CPU_QUEUE)


def dispatch_job(
    job_id: uuid.UUID, settings: Settings, background: BackgroundTasks
) -> None:
    if settings.job_dispatch == "celery":
        try:
            send_to_celery(job_id, settings)
            return
        except Exception:  # noqa: BLE001
            # An unreachable broker would otherwise leave the job queued for
            # ever with nothing to explain it. Running it here is slower and
            # does not scale, but it answers the question, and the log says
            # the deployment is not doing what it was configured to do.
            logger.exception("celery dispatch failed for job %s; running inline", job_id)

    background.add_task(run_job, job_id)
