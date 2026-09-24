"""The GPU worker's heartbeat, idle unload and self-test wiring."""

from __future__ import annotations

import json
import subprocess
import sys
from types import SimpleNamespace

from satsaathi_core.settings import get_settings
from satsaathi_worker import gpu
from satsaathi_worker.celery_app import create_celery_app


class FakeRedis:
    def __init__(self):
        self.data: dict[str, tuple[str, int | None]] = {}

    def set(self, key, value, ex=None):
        self.data[key] = (value, ex)


SETTINGS = SimpleNamespace(models_dir="/nowhere", model_idle_unload_min=20, preload_models=False)


def test_every_consumed_queue_announces_itself_with_a_short_ttl():
    client = FakeRedis()

    gpu.beat_once(client, SETTINGS, ["cpu", "lang"])

    assert set(client.data) == {"workers:cpu:heartbeat", "workers:lang:heartbeat"}
    assert all(ttl == 15 for _v, ttl in client.data.values())


def test_a_gpu_worker_publishes_the_runtime_heartbeat():
    client = FakeRedis()

    gpu.beat_once(client, SETTINGS, ["gpu"])

    value, ttl = client.data["models:gpu:heartbeat"]
    payload = json.loads(value)
    assert ttl == 15
    for key in (
        "worker_id", "base_loaded", "adapters_loaded", "vram_allocated_mb",
        "vram_reserved_mb", "gpu_name", "torch", "transformers", "peft",
        "bitsandbytes", "load_seconds", "last_inference_ms", "inferences_total",
        "last_error_key",
    ):
        assert key in payload, key
    assert payload["base_loaded"] is False
    assert payload["adapters_loaded"] == []


def test_the_heartbeat_does_not_import_torch_to_report_nothing():
    code = (
        "import sys, json; from types import SimpleNamespace;"
        "from satsaathi_worker import gpu;"
        "gpu.gpu_payload(SimpleNamespace());"
        "print('torch' in sys.modules)"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False"


def test_an_idle_model_is_unloaded(monkeypatch):
    calls = []
    fake_runtime = SimpleNamespace(
        unload_if_idle=lambda minutes: calls.append(minutes) or True,
        stats=SimpleNamespace(base_loaded=False, adapters_loaded=[], load_seconds=None,
                              last_inference_ms=None, inferences_total=0,
                              last_error_key=None),
    )
    monkeypatch.setattr(gpu, "runtime", lambda: fake_runtime)

    gpu.beat_once(FakeRedis(), SETTINGS, ["gpu"])

    assert calls == [20.0]


def test_the_selftest_runs_on_the_gpu_queue(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("REDIS_URL", "redis://example:6379/2")

    app = create_celery_app()
    app.loader.import_default_modules()

    task = app.tasks["satsaathi.model_selftest"]
    assert task.queue == "gpu"


def test_a_selftest_of_an_uninstalled_model_fails_with_a_reason(monkeypatch, tmp_path):
    get_settings.cache_clear()
    monkeypatch.setenv("MODELS_DIR", str(tmp_path))
    from satsaathi_worker.tasks import model_selftest_task

    result = model_selftest_task.run("vqa-sar")

    assert result["passed"] is False
    assert result["checks"][0]["check"] == "model.not_installed"
    get_settings.cache_clear()
