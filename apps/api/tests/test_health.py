from fastapi.testclient import TestClient

from satsaathi_api.main import app
from satsaathi_api.routers import health as health_router


def test_health_ok_when_all_checks_pass(monkeypatch):
    async def ok(_settings):
        return health_router.CheckResult(status="ok")

    monkeypatch.setattr(health_router, "check_database", ok)
    monkeypatch.setattr(health_router, "check_redis", ok)
    monkeypatch.setattr(health_router, "check_storage", ok)
    monkeypatch.setattr(health_router, "check_tiler", ok)

    client = TestClient(app)
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["checks"]["database"]["status"] == "ok"
    assert body["checks"]["redis"]["status"] == "ok"
    assert body["checks"]["storage"]["status"] == "ok"
    assert body["checks"]["tiler"]["status"] == "ok"


def test_health_degraded_when_one_check_fails(monkeypatch):
    async def ok(_settings):
        return health_router.CheckResult(status="ok")

    async def failing(_settings):
        return health_router.CheckResult(status="error", detail="boom")

    monkeypatch.setattr(health_router, "check_database", failing)
    monkeypatch.setattr(health_router, "check_redis", ok)
    monkeypatch.setattr(health_router, "check_storage", ok)
    monkeypatch.setattr(health_router, "check_tiler", ok)

    client = TestClient(app)
    response = client.get("/api/v1/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "degraded"
    assert body["checks"]["database"]["status"] == "error"
    assert body["checks"]["database"]["detail"] == "boom"
