"""The tasks a worker actually consumes.

Deliberately thin: the worker owns *where* a job runs,
never *what* running one means. That lives in `satsaathi_jobs.runner`, which
the API calls too, so a trace is the same document whichever process built it.

Retries are off. A job that failed has a persisted trace saying which step
failed and why, and that trace is the product — silently running it again
would replace an honest failure with a second opinion nobody asked for.
"""

from __future__ import annotations

from typing import Any

from celery.signals import worker_ready, worker_shutdown

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


@celery_app.task(name="satsaathi.model_selftest", queue="gpu", acks_late=False)
def model_selftest_task(name: str) -> dict[str, Any]:
    """Run one model's golden fixtures on this GPU worker.

    Returns {passed, checks, latency_ms, vram_peak_mb, output_excerpt}. An
    unavailable model is a failed self-test with a reason, not an exception:
    the caller asked whether it works, and "no" is an answer.
    """
    from satsaathi_core.settings import get_settings

    from . import gpu

    settings = get_settings()
    try:
        from satsaathi_inference import golden
    except ImportError:
        return _failed_selftest(name, "model.not_loadable", "satsaathi-inference not installed")

    gpu.register_runtime(settings)
    runtime = gpu.ensure_runtime(settings)
    status = runtime.catalog.status(name)
    if status is None or not status.available:
        reason = status.reason_key if status else "model.unknown"
        return _failed_selftest(name, reason or "model.unavailable", "")
    samples = golden.discover(name)
    if not samples:
        return _failed_selftest(name, "selftest.no_fixtures", str(golden.DEFAULT_ROOT / name))

    runtime.reset_peak()
    try:
        results = [golden.run_sample(runtime, s) for s in samples]
    except Exception as exc:  # noqa: BLE001 - the self-test reports, it does not crash
        key = runtime.stats.last_error_key or "model.not_loadable"
        return _failed_selftest(name, key, f"{type(exc).__name__}: {exc}")
    checks = [
        {"sample": r.sample, "check": c.check, "passed": c.passed, "detail": c.detail}
        for r in results
        for c in r.checks
    ]
    return {
        "model": name,
        "passed": all(r.passed for r in results),
        "checks": checks,
        "latency_ms": sum(r.latency_ms for r in results),
        "vram_peak_mb": runtime.snapshot().get("vram_peak_mb"),
        "output_excerpt": results[0].output_excerpt if results else "",
    }


def _failed_selftest(name: str, key: str, detail: str) -> dict[str, Any]:
    return {
        "model": name,
        "passed": False,
        "checks": [{"sample": None, "check": key, "passed": False, "detail": detail}],
        "latency_ms": None,
        "vram_peak_mb": None,
        "output_excerpt": "",
    }


def consumed_queues(sender: Any) -> list[str]:
    try:
        return sorted(sender.app.amqp.queues.consume_from.keys())
    except Exception:  # noqa: BLE001 - fall back to everything declared
        return ["cpu", "gpu", "lang"]


@worker_ready.connect
def _on_ready(sender=None, **_kwargs) -> None:
    """Register the model runtime on a GPU worker and start heartbeats."""
    from satsaathi_core.settings import get_settings

    from . import gpu

    gpu.on_worker_ready(get_settings(), consumed_queues(sender))


@worker_shutdown.connect
def _close_loop(**_kwargs) -> None:
    """Return the database connections rather than dropping the sockets."""
    from . import gpu

    gpu.stop()
    close_worker_loop()
