"""End-to-end API flow against a real database.

Uses Postgres+PostGIS when DATABASE_URL points at one (the compose `core`
profile), because geometry columns and the PostGIS types cannot be faked. The
whole suite skips cleanly when no database is reachable, so the unit tests
still run on a laptop with nothing up.
"""

from __future__ import annotations

import asyncio
import io
import os
import uuid
from pathlib import Path

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from rasterio.transform import from_origin

DATABASE_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; integration test needs Postgres"
)


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    storage_dir = tmp_path_factory.mktemp("storage")
    os.environ["STORAGE_DIR"] = str(storage_dir)
    os.environ.setdefault("SATSAATHI_MODE", "online")

    from satsaathi_core.settings import get_settings

    get_settings.cache_clear()

    from satsaathi_api.main import app

    with TestClient(app) as test_client:
        # Every data endpoint needs an account now; sign one in for the module.
        registered = test_client.post(
            "/api/v1/auth/register",
            json={
                "email": f"flow-{uuid.uuid4().hex[:10]}@example.gov.in",
                "password": "a-long-enough-passphrase",
                "full_name": "Flow Test",
            },
        )
        test_client.headers["Authorization"] = f"Bearer {registered.json()['token']}"
        yield test_client


def make_geotiff() -> bytes:
    """A 4x4 optical scene with a known NDVI of 2/3 everywhere."""
    path = Path(os.environ["STORAGE_DIR"]) / "fixture.tif"
    with rasterio.open(
        path, "w", driver="GTiff", height=4, width=4, count=4, dtype="float32",
        crs="EPSG:32645", transform=from_origin(500000, 2700000, 10, 10),
    ) as dst:
        for i, v in enumerate((0.05, 0.12, 0.10, 0.50), start=1):
            dst.write(np.full((4, 4), v, dtype="float32"), i)
    return path.read_bytes()


def upload(client) -> dict:
    response = client.post(
        "/api/v1/assets",
        files={"file": ("scene.tif", io.BytesIO(make_geotiff()), "image/tiff")},
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestAssets:
    def test_upload_reads_real_metadata(self, client):
        asset = upload(client)

        assert asset["width"] == 4 and asset["height"] == 4
        assert asset["band_count"] == 4
        assert "32645" in asset["crs"]
        assert asset["pixel_size"] == pytest.approx(10.0)
        assert asset["sensor_type"] == "optical"

    def test_indices_are_unavailable_until_bands_are_mapped(self, client):
        asset = upload(client)

        # Roles decide what is computable and are never inferred from order.
        assert asset["available_indices"] == []
        assert "nir" in asset["unavailable_indices"]["ndvi"]

    def test_applying_a_preset_unlocks_the_indices_it_supports(self, client):
        asset = upload(client)
        response = client.patch(
            f"/api/v1/assets/{asset['id']}/bands",
            json={"preset": "cartosat-2s-mx"},
        )
        assert response.status_code == 200, response.text
        updated = response.json()

        assert updated["sensor_preset"] == "cartosat-2s-mx"
        assert set(updated["available_indices"]) == {"ndvi", "ndwi"}
        # No SWIR band in this preset, so LSWI stays unavailable with a reason.
        assert updated["unavailable_indices"]["lswi"] == ["swir1"]

    def test_rejects_an_unsupported_file_type(self, client):
        response = client.post(
            "/api/v1/assets",
            files={"file": ("notes.txt", io.BytesIO(b"hello"), "text/plain")},
        )

        assert response.status_code == 415
        assert response.json()["error"]["key"] == "upload.error.unsupportedType"

    def test_rejects_a_band_number_outside_the_raster(self, client):
        asset = upload(client)
        response = client.patch(
            f"/api/v1/assets/{asset['id']}/bands",
            json={"band_map": {"red": 3, "nir": 99}},
        )

        assert response.status_code == 400
        assert response.json()["error"]["key"] == "bands.error.outOfRange"

    def test_unknown_asset_is_a_message_key_not_a_sentence(self, client):
        response = client.get(f"/api/v1/assets/{uuid.uuid4()}")

        assert response.status_code == 404
        body = response.json()
        assert body["error"]["key"] == "asset.not_found"
        assert " " not in body["error"]["key"]


class TestInputSets:
    def test_single_image_set_passes_its_check(self, client):
        asset = upload(client)
        response = client.post(
            "/api/v1/input-sets",
            json={"mode": "single", "assets": {"single": asset["id"]}},
        )

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["blocked"] is False
        assert body["checks"][0]["status"] == "pass"

    def test_rejects_roles_that_do_not_match_the_mode(self, client):
        asset = upload(client)
        response = client.post(
            "/api/v1/input-sets",
            json={"mode": "fusion", "assets": {"single": asset["id"]}},
        )

        assert response.status_code == 400
        assert response.json()["error"]["key"] == "inputSet.error.wrongRoles"


class TestJobs:
    def _ready_input_set(self, client) -> str:
        asset = upload(client)
        client.patch(
            f"/api/v1/assets/{asset['id']}/bands",
            json={"preset": "cartosat-2s-mx"},
        )
        response = client.post(
            "/api/v1/input-sets",
            json={"mode": "single", "assets": {"single": asset["id"]}},
        )
        return response.json()["id"]

    def test_creating_a_job_seeds_all_eight_steps_immediately(self, client):
        response = client.post(
            "/api/v1/jobs",
            json={
                "input_set_id": self._ready_input_set(client),
                "query_text": "how much vegetation is there",
                "query_lang": "en",
                "ui_lang": "en",
            },
        )

        assert response.status_code == 201, response.text
        job = response.json()
        assert len(job["steps"]) == 8
        assert [s["ordinal"] for s in job["steps"]] == list(range(8))

    def test_a_job_runs_to_completion_and_measures_the_raster(self, client):
        created = client.post(
            "/api/v1/jobs",
            json={
                "input_set_id": self._ready_input_set(client),
                "query_text": "how much vegetation is there",
                "query_lang": "en",
                "ui_lang": "en",
            },
        ).json()

        job = client.get(f"/api/v1/jobs/{created['id']}").json()
        assert job["status"] in {"succeeded", "needs_review"}

        compute = next(s for s in job["steps"] if s["step_key"] == "compute")
        assert compute["status"] == "succeeded"
        assert compute["is_stub"] is False
        # NIR 0.50 / Red 0.10 -> NDVI 0.6667 across all 16 pixels.
        assert compute["output_summary"]["mean"] == pytest.approx(0.6667, abs=1e-3)
        assert compute["output_summary"]["area_ha"] == pytest.approx(0.16)

    def test_the_stream_finishes_even_when_the_broker_says_nothing(
        self, client, monkeypatch
    ):
        """Regression: a job that finished before the browser subscribed.

        Redis pub/sub has no replay. Once the worker ran jobs in another
        process they routinely completed before the subscription existed, and
        every frame went into an empty channel — the page then sat on
        "running" for ever. A silent broker must not be able to hang the
        stream, so this replaces it with one that never yields anything.
        """
        created = client.post(
            "/api/v1/jobs",
            json={
                "input_set_id": self._ready_input_set(client),
                "query_text": "how much vegetation is there",
                "query_lang": "en",
                "ui_lang": "en",
            },
        ).json()

        class SilentBus:
            async def publish(self, job_id, payload):
                pass

            async def subscribe(self, job_id):
                while True:
                    await asyncio.sleep(3600)
                    yield {}

        from satsaathi_api.routers import jobs as jobs_router

        monkeypatch.setattr(
            jobs_router, "event_bus", lambda _settings: (SilentBus(), True)
        )
        # Poll fast enough that the test does not wait on the real interval.
        monkeypatch.setattr(jobs_router, "POLL_SECONDS", 0.1)

        with client.stream("GET", f"/api/v1/jobs/{created['id']}/events") as response:
            assert response.status_code == 200
            events = []
            for line in response.iter_lines():
                if line.startswith("event: "):
                    events.append(line[7:])
                if events and events[-1] == "done":
                    break

        assert events[-1] == "done"
        assert "snapshot" in events


    def test_the_trace_export_is_a_complete_versioned_document(self, client):
        created = client.post(
            "/api/v1/jobs",
            json={
                "input_set_id": self._ready_input_set(client),
                "query_text": "describe the land cover",
                "query_lang": "en",
                "ui_lang": "en",
            },
        ).json()

        response = client.get(f"/api/v1/jobs/{created['id']}/trace")
        assert response.status_code == 200
        assert "attachment" in response.headers["content-disposition"]

        trace = response.json()
        assert trace["trace_version"] == 1
        assert len(trace["steps"]) == 8
        assert trace["query"]["text"] == "describe the land cover"
        # Which steps measured and which were fixture is on the record.
        by_key = {s["step_key"]: s for s in trace["steps"]}
        assert by_key["compute"]["is_stub"] is False
        assert by_key["vision_language"]["is_stub"] is True

    def test_geojson_export_carries_the_real_footprint(self, client):
        created = client.post(
            "/api/v1/jobs",
            json={
                "input_set_id": self._ready_input_set(client),
                "query_text": "describe the land cover",
                "query_lang": "en",
                "ui_lang": "en",
            },
        ).json()

        collection = client.get(f"/api/v1/jobs/{created['id']}/result.geojson").json()

        assert collection["type"] == "FeatureCollection"
        assert len(collection["features"]) == 1
        feature = collection["features"][0]
        assert feature["geometry"]["type"] == "Polygon"
        lons = [c[0] for c in feature["geometry"]["coordinates"][0]]
        assert all(86 < lon < 88 for lon in lons)

    def test_history_lists_the_job(self, client):
        page = client.get("/api/v1/jobs?limit=5").json()

        assert page["total"] >= 1
        assert page["items"][0]["mode"] == "single"


class TestToolsAndVoice:
    def test_tools_endpoint_exposes_stub_flags_and_param_schemas(self, client):
        tools = {t["name"]: t for t in client.get("/api/v1/tools").json()}

        assert tools["indices.compute"]["is_stub"] is False
        assert tools["vlm.vqa"]["is_stub"] is True
        assert set(
            tools["indices.compute"]["params_schema"]["properties"]
        ) == {"index", "threshold"}

    def test_voice_is_honestly_unavailable(self, client):
        response = client.post("/api/v1/voice/transcribe")

        assert response.status_code == 501
        assert response.json()["error"]["key"] == "voice.not_available"

    def test_sensor_presets_are_served_without_english_labels(self, client):
        presets = client.get("/api/v1/sensor-presets").json()

        assert "sentinel-2-l2a" in presets
        assert presets["sentinel-1-grd"] == {"vv": 1, "vh": 2}


def test_one_account_cannot_see_anothers_work(client):
    asset = upload(client)
    theirs = client.post(
        "/api/v1/auth/register",
        json={
            "email": f"other-{uuid.uuid4().hex[:10]}@example.gov.in",
            "password": "a-long-enough-passphrase",
            "full_name": "Someone Else",
        },
    ).json()["token"]
    other = {"Authorization": f"Bearer {theirs}"}

    # Reported exactly like a missing asset, so ids cannot be probed.
    assert client.get(f"/api/v1/assets/{asset['id']}", headers=other).status_code == 404
    assert client.get("/api/v1/jobs", headers=other).json()["total"] == 0
    assert client.get("/api/v1/jobs", headers={"Authorization": ""}).status_code == 401
