from satsaathi_core.settings import get_settings
from satsaathi_worker.celery_app import create_celery_app


def test_broker_and_backend_come_from_settings(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("REDIS_URL", "redis://example:6379/2")

    app = create_celery_app()

    assert app.conf.broker_url == "redis://example:6379/2"
    assert app.conf.result_backend == "redis://example:6379/2"


def test_declares_cpu_gpu_lang_queues(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("REDIS_URL", "redis://example:6379/2")

    app = create_celery_app()

    queue_names = {queue.name for queue in app.conf.task_queues}
    assert queue_names == {"cpu", "gpu", "lang"}
    assert app.conf.task_default_queue == "cpu"
