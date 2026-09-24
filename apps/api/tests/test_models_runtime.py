"""Health, model status and the GPU runtime, as the API reports them.

No Redis, database or GPU is needed: the heartbeat and readiness probes are
replaced at the seams the routers call.
"""

from __future__ import annotations

import subprocess
import sys
import uuid

import pytest
from fastapi.testclient import TestClient

from satsaathi_api import deps
from satsaathi_api.main import app
from satsaathi_api.routers import health as health_router
from satsaathi_api.routers import models as models_router
from satsaathi_models import ModelCatalog
from satsaathi_models.testing import install_fake

BEAT = {
    "worker_id": "gpu-box:1234",
    "base_loaded": True,
    "adapters_loaded": ["vqa-optical", "vqa-sar"],
    "vram_allocated_mb": 2610.5,
    "vram_reserved_mb": 2900.0,
    "gpu_name": "NVIDIA GeForce GTX 1650 Ti",
    "torch": "2.14.0+cu126",
    "transformers": "4.57.6",
    "peft": "0.21.0",
    "bitsandbytes": "0.50.2",
    "load_seconds": 41.2,
    "last_inference_ms": 1830,
    "inferences_total": 7,
    "last_error_key": None,
}


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.clear()


def _beat(value):
    async def fake(_url):
        return value

    return fake


class TestLiveAndReady:
    def test_live_needs_nothing(self, client):
        response = client.get("/api/v1/health/live")

        assert response.status_code == 200
        assert response.json() == {"status": "live"}

    def _ready(self, monkeypatch, alive):
        async def ok(_s):
            return health_router.ReadyCheck(ok=True)

        async def consumers(_url, queues):
            return {q: alive.get(q, False) for q in queues}

        monkeypatch.setattr(health_router, "ready_database", ok)
        monkeypatch.setattr(health_router, "ready_redis", ok)
        monkeypatch.setattr(health_router, "required_queues", lambda _s: ["cpu", "gpu"])
        monkeypatch.setattr("satsaathi_api.heartbeat.queue_consumers", consumers)

    def test_ready_is_503_while_the_gpu_worker_is_down(self, client, monkeypatch):
        self._ready(monkeypatch, {"cpu": True, "gpu": False})

        response = client.get("/api/v1/health/ready")

        assert response.status_code == 503
        body = response.json()
        assert body["status"] == "not_ready"
        assert body["failing"] == ["health.gpu_worker_missing"]

    def test_ready_is_200_when_every_queue_has_a_consumer(self, client, monkeypatch):
        self._ready(monkeypatch, {"cpu": True, "gpu": True})

        response = client.get("/api/v1/health/ready")

        assert response.status_code == 200
        assert response.json()["failing"] == []

    def test_the_gpu_queue_is_required_only_when_a_gpu_model_is_usable(self, tmp_path):
        from satsaathi_core.settings import Settings

        settings = Settings(job_dispatch="celery", models_dir=tmp_path)
        assert health_router.required_queues(settings) == ["cpu"]

        install_fake(tmp_path, "vqa-sar")
        assert health_router.required_queues(settings) == ["cpu", "gpu"]

    def test_inline_dispatch_needs_no_worker(self, tmp_path):
        from satsaathi_core.settings import Settings

        settings = Settings(job_dispatch="inline", models_dir=tmp_path)

        assert health_router.required_queues(settings) == []


class TestRuntime:
    def test_no_heartbeat_means_no_gpu_worker(self, client, monkeypatch):
        monkeypatch.setattr(models_router, "gpu_heartbeat", _beat(None))

        response = client.get("/api/v1/models/runtime")

        assert response.status_code == 200
        assert response.json() == {"status": "no_gpu_worker", "adapters_loaded": []}

    def test_the_heartbeat_is_returned(self, client, monkeypatch):
        monkeypatch.setattr(models_router, "gpu_heartbeat", _beat(BEAT))

        body = client.get("/api/v1/models/runtime").json()

        assert body["status"] == "up"
        assert body["adapters_loaded"] == ["vqa-optical", "vqa-sar"]
        assert body["vram_allocated_mb"] == 2610.5
        assert body["gpu_name"] == "NVIDIA GeForce GTX 1650 Ti"


class TestModels:
    def _catalog(self, tmp_path):
        install_fake(tmp_path, "vqa-sar", eval_doc={"finetuned": {"ground_acc@0.5": 0.2}})
        install_fake(tmp_path, "vqa-optical", base_repo="Some/OtherBase")
        catalog = ModelCatalog(tmp_path)
        app.dependency_overrides[deps.catalog_dep] = lambda: catalog
        from satsaathi_tools.builtin import build_default_registry

        app.dependency_overrides[deps.registry_dep] = lambda: build_default_registry(catalog)

    def test_each_model_reports_kind_files_base_eval_and_residency(
        self, client, monkeypatch, tmp_path
    ):
        self._catalog(tmp_path)
        monkeypatch.setattr(models_router, "gpu_heartbeat", _beat(BEAT))

        body = client.get("/api/v1/models").json()
        rows = {m["name"]: m for m in body["models"]}

        sar = rows["vqa-sar"]
        assert sar["kind"] == "lora_adapter"
        assert sar["installed"] is True and sar["available"] is True
        assert sar["base"] == "qwen3-vl-2b-instruct"
        assert sar["compatible"] is True
        assert sar["eval"]["finetuned"]["ground_acc@0.5"] == 0.2
        assert sar["loaded"] is True
        assert sar["is_stub"] is False

        optical = rows["vqa-optical"]
        assert optical["available"] is False
        assert optical["compatible"] is False
        assert optical["reason"]["key"] == "model.base_mismatch"

        ndvi = rows["index-ndvi"]
        assert ndvi["installed"] is False
        assert ndvi["missing_files"] == [
            "adapter_config.json", "adapter_model.safetensors", "satquery_index_meta.json"
        ]

        stub = rows["translate-indic"]
        assert stub["kind"] == "stub" and stub["is_stub"] is True
        assert stub["reason"]["key"] == "model.stub"
        assert body["gpu_worker"] is True

    def test_without_a_gpu_worker_residency_is_unknown(self, client, monkeypatch, tmp_path):
        self._catalog(tmp_path)
        monkeypatch.setattr(models_router, "gpu_heartbeat", _beat(None))

        body = client.get("/api/v1/models").json()

        assert all(m["loaded"] is None for m in body["models"])
        assert body["gpu_worker"] is False


class TestSelftest:
    def _signed_in(self):
        from satsaathi_api.routers.auth import current_user

        app.dependency_overrides[current_user] = lambda: object()

    def test_it_is_off_unless_debug(self, client, monkeypatch):
        self._signed_in()
        monkeypatch.setenv("SATSAATHI_DEBUG", "0")
        from satsaathi_core.settings import get_settings

        get_settings.cache_clear()

        response = client.post("/api/v1/models/vqa-sar/selftest")

        assert response.status_code == 404
        assert response.json()["error"]["key"] == "selftest.disabled"
        get_settings.cache_clear()

    def test_it_enqueues_on_the_gpu_queue(self, client, monkeypatch):
        self._signed_in()
        monkeypatch.setenv("SATSAATHI_DEBUG", "1")
        from satsaathi_core.settings import get_settings

        get_settings.cache_clear()
        sent = {}

        class FakeCelery:
            def send_task(self, name, args, queue):
                sent.update(name=name, args=args, queue=queue)
                return type("R", (), {"id": "task-123"})()

        monkeypatch.setattr(models_router, "_celery", lambda _s: FakeCelery())

        response = client.post("/api/v1/models/vqa-sar/selftest")

        assert response.status_code == 202
        assert response.json() == {"task_id": "task-123", "model": "vqa-sar"}
        assert sent == {"name": "satsaathi.model_selftest", "args": ["vqa-sar"], "queue": "gpu"}
        get_settings.cache_clear()

    def test_it_requires_a_signed_in_user(self, client):
        response = client.post("/api/v1/models/vqa-sar/selftest")

        assert response.status_code == 401


def test_a_gpu_job_with_no_gpu_worker_runs_as_fixtures_on_cpu(monkeypatch):
    from fastapi import BackgroundTasks

    from satsaathi_api import dispatch
    from satsaathi_core.settings import Settings

    sent = []
    monkeypatch.setattr(dispatch, "send_to_celery", lambda jid, s, q: sent.append(q))
    monkeypatch.setattr("satsaathi_api.heartbeat.gpu_worker_alive_sync", lambda _u: False)

    dispatch.dispatch_job(
        uuid.uuid4(), Settings(job_dispatch="celery"), BackgroundTasks(), queue="gpu"
    )

    assert sent == ["cpu"]


def test_the_api_never_imports_torch():
    code = (
        "import sys; import satsaathi_api.main;"
        "print(','.join(m for m in ('torch','transformers','peft','bitsandbytes')"
        " if m in sys.modules))"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)

    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == ""
