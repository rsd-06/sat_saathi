"""The process-level invariants a worker depends on."""

from __future__ import annotations

import asyncio

from satsaathi_jobs import runner


def test_every_job_in_a_process_shares_one_loop():
    """Regression: the second job on a worker died inside the driver.

    The engine is cached per process and its connections belong to the loop
    that opened them, so a loop created and closed per task leaves the pool
    pointing at a dead one. The symptom was `'NoneType' object has no
    attribute 'send'` from asyncpg on job two, with job one succeeding.
    """
    runner.close_worker_loop()

    first = runner.worker_loop()
    first.run_until_complete(asyncio.sleep(0))
    second = runner.worker_loop()

    assert second is first
    assert not second.is_closed()

    # And the loop is still usable after a job has run on it.
    second.run_until_complete(asyncio.sleep(0))

    runner.close_worker_loop()


def test_closing_is_safe_to_repeat():
    # Celery can fire worker_shutdown more than once, and a worker that never
    # ran a job has no loop to close at all.
    runner.close_worker_loop()
    runner.close_worker_loop()

    assert runner.worker_loop() is runner.worker_loop()
    runner.close_worker_loop()
