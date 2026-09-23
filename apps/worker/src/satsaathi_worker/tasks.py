"""The tasks a worker actually consumes.

Only one so far, and deliberately thin: the worker owns *where* a job runs,
never *what* running one means. That lives in `satsaathi_jobs.runner`, which
the API calls too, so a trace is the same document whichever process built it.

Retries are off. A job that failed has a persisted trace saying which step
failed and why, and that trace is the product — silently running it again
would replace an honest failure with a second opinion nobody asked for.
"""

from __future__ import annotations

from celery.signals import worker_shutdown

from satsaathi_jobs.runner import close_worker_loop, run_job_blocking

from .celery_app import celery_app


@celery_app.task(name="satsaathi.run_job", queue="cpu", acks_late=True)
def run_job_task(job_id: str) -> str:
    """Run one job to completion and return its id for the result backend.

    `acks_late` so a worker killed mid-job leaves the message on the queue
    rather than losing it: the pipeline is idempotent per job, since every
    step is rewritten from the trace rather than appended to.
    """
    run_job_blocking(job_id)
    return job_id


@worker_shutdown.connect
def _close_loop(**_kwargs) -> None:
    """Return the database connections rather than dropping the sockets."""
    close_worker_loop()
