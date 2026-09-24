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
    assert settings.database_url == "postgresql+asyncpg://u:p@db:5432/x"


def test_offline_mode_ignores_a_hosted_database(monkeypatch):
    """Offline means no network, and a hosted database is the network.

    Configuring one and then asking for offline is not a contradiction to
    resolve in the host's favour: the local Postgres is the only database
    offline mode will speak to, whatever else is set.
    """
    monkeypatch.setenv("SATSAATHI_MODE", "offline")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.supabase.co:5432/postgres")

    settings = Settings()

    assert settings.effective_database_url == settings.local_database_url
    assert settings.database_is_remote is False


def test_an_online_host_is_used_and_gets_tls(monkeypatch):
    monkeypatch.setenv("SATSAATHI_MODE", "online")
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@db.supabase.co:5432/postgres")

    settings = Settings()

    assert settings.database_is_remote is True
    # A hosted database must never be spoken to in the clear.
    assert settings.asyncpg_connect_args()["ssl"] == "require"
    assert settings.psycopg_connect_args()["sslmode"] == "require"


def test_a_provider_url_is_given_our_driver(monkeypatch):
    """Supabase and most hosts print `postgresql://`, which SQLAlchemy would
    read as psycopg. The app runs on asyncpg."""
    monkeypatch.setenv("DATABASE_URL", "postgres://u:p@db.supabase.co:5432/postgres")

    settings = Settings()

    assert settings.effective_database_url.startswith("postgresql+asyncpg://")
    assert settings.sync_database_url.startswith("postgresql+psycopg://")


def test_the_transaction_pooler_turns_off_prepared_statements(monkeypatch):
    """Port 6543 is Supabase's transaction pooler. It hands each statement to
    whichever backend is free, so a prepared statement made on one connection
    is not there on the next."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@aws.pooler.supabase.com:6543/postgres")

    settings = Settings()

    assert settings.asyncpg_connect_args()["statement_cache_size"] == 0
    assert settings.psycopg_connect_args()["prepare_threshold"] is None


def test_a_session_pooler_keeps_prepared_statements(monkeypatch):
    # Port 5432 is session mode: one backend for the whole connection, so
    # prepared statements are safe and worth keeping.
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@aws.pooler.supabase.com:5432/postgres")

    settings = Settings()

    assert "statement_cache_size" not in settings.asyncpg_connect_args()


def test_get_settings_is_cached(monkeypatch):
    get_settings.cache_clear()
    monkeypatch.setenv("SATSAATHI_MODE", "online")

    first = get_settings()
    second = get_settings()

    assert first is second
