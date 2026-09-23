"""Sign-up, sign-in and session handling, against a real database."""

from __future__ import annotations

import os
import uuid

import pytest

DATABASE_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; auth tests need Postgres"
)

PASSWORD = "a-long-enough-passphrase"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    os.environ["STORAGE_DIR"] = str(tmp_path_factory.mktemp("storage"))
    from satsaathi_core.settings import get_settings

    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    from satsaathi_api.main import app

    with TestClient(app) as test_client:
        yield test_client


def unique_email(tag: str) -> str:
    return f"{tag}-{uuid.uuid4().hex[:10]}@example.gov.in"


def sync_engine():
    """A plain synchronous connection for poking at rows directly.

    The app's engine is async and its connections belong to the TestClient's
    event loop, so reaching for it from a test would hit the same
    different-loop error the Celery worker did.
    """
    from sqlalchemy import create_engine

    return create_engine(
        DATABASE_URL.replace("postgresql+asyncpg://", "postgresql+psycopg://", 1)
    )


def register(client, email: str, password: str = PASSWORD, **extra):
    return client.post(
        "/api/v1/auth/register",
        json={
            "email": email,
            "password": password,
            "full_name": "A. Surveyor",
            **extra,
        },
    )


class TestRegistration:
    def test_creating_an_account_signs_you_in_straight_away(self, client):
        email = unique_email("new")
        response = register(client, email)

        assert response.status_code == 201, response.text
        body = response.json()
        assert body["user"]["email"] == email
        assert body["token"]
        # The account is usable immediately; no separate sign-in round trip.
        me = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {body['token']}"},
        )
        assert me.status_code == 200
        assert me.json()["email"] == email

    def test_the_password_never_comes_back(self, client):
        response = register(client, unique_email("secret"))

        serialised = response.text.lower()
        assert PASSWORD not in serialised
        assert "password" not in serialised
        assert "argon2" not in serialised

    def test_an_address_can_only_be_registered_once(self, client):
        email = unique_email("dupe")
        assert register(client, email).status_code == 201

        again = register(client, email)

        assert again.status_code == 409
        assert again.json()["error"]["key"] == "auth.error.emailTaken"

    def test_the_address_is_matched_regardless_of_case(self, client):
        email = unique_email("Case")
        register(client, email)

        signed_in = client.post(
            "/api/v1/auth/login",
            json={"email": email.upper(), "password": PASSWORD},
        )

        assert signed_in.status_code == 200

    def test_a_short_password_is_refused_before_it_reaches_the_database(self, client):
        response = register(client, unique_email("short"), password="short")

        assert response.status_code == 422
        body = response.json()
        # Even a rejected field leaves as a key: FastAPI's own message is
        # English prose, which is exactly what this API promises not to send.
        assert body["error"]["key"] == "request.invalid"
        assert "password" in body["error"]["params"]["fields"]

    def test_a_malformed_address_names_the_field_and_not_the_reason(self, client):
        response = client.post(
            "/api/v1/auth/register",
            json={"email": "not-an-address", "password": PASSWORD, "full_name": "A"},
        )

        assert response.status_code == 422
        body = response.json()
        assert body["error"]["key"] == "request.invalid"
        assert body["error"]["params"]["fields"] == ["email"]
        assert "valid email" not in response.text


class TestSignIn:
    def test_the_right_password_opens_a_session(self, client):
        email = unique_email("signin")
        register(client, email)

        response = client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )

        assert response.status_code == 200, response.text
        assert response.json()["token"]

    def test_a_wrong_password_and_an_unknown_address_are_alike(self, client):
        """Different messages here would enumerate who has an account."""
        email = unique_email("known")
        register(client, email)

        wrong = client.post(
            "/api/v1/auth/login",
            json={"email": email, "password": "not-the-password"},
        )
        unknown = client.post(
            "/api/v1/auth/login",
            json={"email": unique_email("nobody"), "password": PASSWORD},
        )

        assert wrong.status_code == unknown.status_code == 401
        assert wrong.json() == unknown.json()
        assert wrong.json()["error"]["key"] == "auth.error.badCredentials"


class TestSessions:
    def test_signing_out_makes_the_token_useless(self, client):
        token = register(client, unique_email("out")).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}
        assert client.get("/api/v1/auth/me", headers=headers).status_code == 200

        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204

        assert client.get("/api/v1/auth/me", headers=headers).status_code == 401

    def test_signing_out_twice_is_not_an_error(self, client):
        token = register(client, unique_email("twice")).json()["token"]
        headers = {"Authorization": f"Bearer {token}"}

        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204
        assert client.post("/api/v1/auth/logout", headers=headers).status_code == 204

    def test_signing_out_of_one_session_leaves_the_others_alone(self, client):
        email = unique_email("two-devices")
        first = register(client, email).json()["token"]
        second = client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        ).json()["token"]

        client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {first}"})

        # The other device stays signed in.
        still_in = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {second}"}
        )
        assert still_in.status_code == 200

    @pytest.mark.parametrize(
        "headers",
        [
            {},
            {"Authorization": "Bearer not-a-real-token"},
            {"Authorization": "Basic abc"},
            {"Authorization": "Bearer "},
        ],
    )
    def test_nonsense_credentials_are_refused_the_same_way(self, client, headers):
        response = client.get("/api/v1/auth/me", headers=headers)

        assert response.status_code == 401
        assert response.json()["error"]["key"] == "auth.error.notSignedIn"

    def test_an_expired_session_stops_working(self, client):
        """Time is not mocked; the row is aged instead, which is what expires."""
        from datetime import UTC, datetime, timedelta

        from sqlalchemy.orm import Session as SyncSession

        from satsaathi_core.models import UserSession
        from satsaathi_core.passwords import hash_session_token

        token = register(client, unique_email("expired")).json()["token"]

        engine = sync_engine()
        with SyncSession(engine) as db:
            record = (
                db.query(UserSession)
                .filter(UserSession.token_hash == hash_session_token(token))
                .one()
            )
            record.expires_at = datetime.now(UTC) - timedelta(seconds=1)
            db.commit()
        engine.dispose()

        response = client.get(
            "/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert response.status_code == 401


class TestStoredSecrets:
    def test_the_database_stores_a_hash_of_the_token_not_the_token(self, client):
        """A dump of the sessions table must not let anyone sign in."""
        from sqlalchemy.orm import Session as SyncSession

        from satsaathi_core.models import User, UserSession

        email = unique_email("stored")
        token = register(client, email).json()["token"]

        engine = sync_engine()
        with SyncSession(engine) as db:
            hashes = [row.token_hash for row in db.query(UserSession).all()]
            password_hash = (
                db.query(User).filter(User.email == email).one().password_hash
            )
        engine.dispose()

        assert token not in hashes
        assert PASSWORD not in password_hash
        assert password_hash.startswith("$argon2id$")
