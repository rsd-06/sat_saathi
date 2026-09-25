"""Keep the test suite off real databases.

These tests register accounts, create jobs and upload rasters by the dozen.
Since the app now reads a hosted database from .env.local by default, a test
run without an explicit DATABASE_URL — or with one pasted from the wrong
terminal — would fill production with test rows. This refuses before any test
runs, unless someone has said in so many words that they mean it.
"""

from __future__ import annotations

import os
from urllib.parse import urlsplit

import pytest

_LOCAL = {"localhost", "127.0.0.1", "::1", "postgres"}


def pytest_configure(config: pytest.Config) -> None:
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        # Database tests skip themselves when no URL is set; nothing to guard.
        return
    host = urlsplit(url.replace("+asyncpg", "")).hostname or ""
    if host in _LOCAL:
        return
    if os.environ.get("SATSAATHI_ALLOW_REMOTE_TESTS") == "1":
        return
    pytest.exit(
        f"DATABASE_URL points at {host}, which is not a local database. "
        "The test suite creates and deletes rows freely. Point it at the "
        "Docker Postgres, or set SATSAATHI_ALLOW_REMOTE_TESTS=1 if you "
        "really mean to run it against that host.",
        returncode=2,
    )
