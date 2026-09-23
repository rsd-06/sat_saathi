from satsaathi_core.settings import get_settings
from satsaathi_worker.celery_app import create_celery_app


def test_run_job_is_registered_under_the_name_the_api_sends(monkeypatch):
    # The API enqueues by name and never imports this package, so the name
    # and the queue are the whole contract between them.
    get_settings.cache_clear()
    monkeypatch.setenv("REDIS_URL", "redis://example:6379/2")

    app = create_celery_app()
    app.loader.import_default_modules()

    task = app.tasks["satsaathi.run_job"]
    assert task.queue == "cpu"


def test_a_killed_worker_leaves_the_job_on_the_queue(monkeypatch):
    # Acknowledging late is what makes a crashed worker recoverable; a job
    # acknowledged on receipt would vanish with the process that took it.
    get_settings.cache_clear()
    monkeypatch.setenv("REDIS_URL", "redis://example:6379/2")

    app = create_celery_app()

    assert app.conf.task_acks_late is True
    # One slow scene must not strand three others behind it.
    assert app.conf.worker_prefetch_multiplier == 1
