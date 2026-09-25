"""A database that cannot be reached must be reported, not crashed on.

Regression: with Supabase's IPv6-only direct host, Windows intermittently
failed to resolve the name at all. Sign-in then hung for a quarter of a
minute and failed with a bare 500 that the form could only call "something
went wrong". Needs no database — the failure is what is being simulated.
"""

from __future__ import annotations

import socket

import pytest
from fastapi.testclient import TestClient

from satsaathi_api.main import app
from satsaathi_core.db import get_session


@pytest.fixture
def client_without_database():
    async def unreachable():
        raise socket.gaierror(11001, "getaddrinfo failed")
        yield  # pragma: no cover - makes this an async generator

    app.dependency_overrides[get_session] = unreachable
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client
    finally:
        app.dependency_overrides.pop(get_session, None)


@pytest.mark.parametrize(
    ("method", "path", "body"),
    [
        ("post", "/api/v1/auth/login", {"email": "a@example.gov.in", "password": "x" * 12}),
        (
            "post",
            "/api/v1/auth/register",
            {"email": "a@example.gov.in", "password": "x" * 12, "full_name": "A"},
        ),
    ],
)
def test_an_unreachable_database_is_a_503_with_a_key(
    client_without_database, method, path, body
):
    response = getattr(client_without_database, method)(path, json=body)

    assert response.status_code == 503
    assert response.json()["error"]["key"] == "service.databaseUnavailable"
    # The resolver's own message is operator detail, not something to show.
    assert "getaddrinfo" not in response.text


def test_a_timeout_reaching_the_database_is_also_an_outage(monkeypatch):
    async def slow():
        raise TimeoutError("connect timed out")
        yield  # pragma: no cover

    app.dependency_overrides[get_session] = slow
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={"email": "a@example.gov.in", "password": "x" * 12},
            )
    finally:
        app.dependency_overrides.pop(get_session, None)

    assert response.status_code == 503
    assert response.json()["error"]["key"] == "service.databaseUnavailable"
