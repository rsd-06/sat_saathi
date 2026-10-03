"""Only TIFF gets in, decided before anything is stored.

Needs no database: both refusals happen before the handler touches the session
or storage, so those dependencies are replaced with ones that fail loudly if
anything reaches for them. (A real GeoTIFF going through is covered by the
database-backed flow tests and the browser e2e.)
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from satsaathi_api.deps import storage_dep
from satsaathi_api.main import app
from satsaathi_api.routers.auth import current_user
from satsaathi_core.db import get_session

JPEG = bytes.fromhex("ffd8ffe0") + bytes(64)
PNG = bytes.fromhex("89504e470d0a1a0a") + bytes(64)


class _Tripwire:
    """Resolving a dependency is harmless; *using* it is the failure.

    FastAPI resolves every parameter a handler declares before the handler
    runs, so a stand-in that raised on resolution would fire whatever the
    handler does. This only raises when something reaches into it.
    """

    def __init__(self, what: str):
        self._what = what

    def __getattr__(self, name: str):
        raise AssertionError(f"a refused upload must not reach {self._what} ({name})")


async def _tripwire_session():
    yield _Tripwire("the database")


@pytest.fixture
def client():
    app.dependency_overrides[current_user] = lambda: SimpleNamespace(id=uuid.uuid4())
    app.dependency_overrides[storage_dep] = lambda: _Tripwire("storage")
    app.dependency_overrides[get_session] = _tripwire_session
    yield TestClient(app)
    app.dependency_overrides.clear()


def _post(client: TestClient, name: str, body: bytes):
    return client.post(
        "/api/v1/assets", files={"file": (name, body, "application/octet-stream")}
    )


@pytest.mark.parametrize(
    "name,body",
    [
        ("scene.png", PNG),
        ("scene.jpg", JPEG),
        ("scene.jpeg", JPEG),
        ("scene.webp", b"RIFF"),
        ("notes.txt", b"hi"),
    ],
)
def test_a_wrong_extension_is_refused(client, name, body):
    response = _post(client, name, body)

    assert response.status_code == 415
    assert response.json()["error"]["key"] == "upload.error.unsupportedType"


@pytest.mark.parametrize("name", ["scene.tif", "scene.tiff", "SCENE.TIF"])
def test_a_jpeg_renamed_to_tif_is_refused_on_its_bytes(client, name):
    """The extension is a claim; the leading bytes are the evidence."""
    response = _post(client, name, JPEG)

    assert response.status_code == 415
    assert response.json()["error"]["key"] == "upload.error.notTiff"


def test_an_empty_tif_is_refused(client):
    response = _post(client, "scene.tif", b"")

    assert response.status_code == 415
    assert response.json()["error"]["key"] == "upload.error.notTiff"
