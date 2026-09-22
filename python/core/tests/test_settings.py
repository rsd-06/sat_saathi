from satsaathi_core.settings import Settings, get_settings


def test_defaults_when_no_env(monkeypatch):
    for key in ("SATSAATHI_MODE", "DATABASE_URL", "REDIS_URL", "STORAGE_DIR", "TILER_URL"):
        monkeypatch.delenv(key, raising=False)

    settings = Settings()

    assert settings.mode == "online"
    assert settings.redis_url == "redis://localhost:6379/0"
    assert settings.tiler_url == "http://localhost:8001"


def test_reads_from_env(monkeypatch):
    monkeypatch.setenv("SATSAATHI_MODE", "offline")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://u:p@db:5432/x")

    settings = Settings()

    assert settings.mode == "offline"
    assert settings.database_url_asyncpg_dsn == "postgresql://u:p@db:5432/x"


def test_get_settings_is_cached(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("SATSAATHI_MODE", "online")

    first = get_settings()
    second = get_settings()

    assert first is second
