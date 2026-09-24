"""Signing in through Google, and the account takeover it must refuse.

Google's signature is not faked here — the verifier is replaced, and what is
tested is everything this codebase decides *after* Google has been believed.
The verifier itself is tested separately against tokens it should reject.
"""

from __future__ import annotations

import os
import uuid

import pytest

from satsaathi_api import google_identity

DATABASE_URL = os.environ.get("DATABASE_URL")
pytestmark = pytest.mark.skipif(
    not DATABASE_URL, reason="DATABASE_URL not set; these tests need Postgres"
)

PASSWORD = "a-long-enough-passphrase"
CLIENT_ID = "test-client.apps.googleusercontent.com"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    os.environ["STORAGE_DIR"] = str(tmp_path_factory.mktemp("storage"))
    os.environ["GOOGLE_CLIENT_ID"] = CLIENT_ID
    from satsaathi_core.settings import get_settings

    get_settings.cache_clear()
    from fastapi.testclient import TestClient

    from satsaathi_api.main import app

    with TestClient(app) as test_client:
        yield test_client
    os.environ.pop("GOOGLE_CLIENT_ID", None)
    get_settings.cache_clear()


def unique_email(tag: str) -> str:
    return f"{tag}-{uuid.uuid4().hex[:10]}@example.gov.in"


@pytest.fixture
def google(monkeypatch):
    """Stand in for Google, so a test can say exactly what it asserted."""

    def say(
        subject: str,
        email: str,
        *,
        email_verified: bool = True,
        name: str | None = "G. User",
    ):
        def fake_verify(_token, *, client_id, leeway=30):
            assert client_id == CLIENT_ID, "the audience must still be checked"
            return google_identity.GoogleIdentity(
                subject=subject,
                email=email,
                email_verified=email_verified,
                name=name,
                picture=None,
            )

        monkeypatch.setattr(
            "satsaathi_api.routers.auth.google_identity.verify", fake_verify
        )

    return say


def sign_in(client, token: str = "any-token"):
    return client.post("/api/v1/auth/google", json={"id_token": token})


def register(client, email: str, password: str = PASSWORD):
    return client.post(
        "/api/v1/auth/register",
        json={"email": email, "password": password, "full_name": "Local User"},
    )


class TestFirstTime:
    def test_a_new_google_user_gets_an_account(self, client, google):
        email = unique_email("new-google")
        google("google-sub-1" + uuid.uuid4().hex, email)

        response = sign_in(client)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["created"] is True
        assert body["user"]["email"] == email
        assert body["token"]

    def test_the_new_account_has_no_password_to_guess(self, client, google):
        email = unique_email("no-pw")
        google("sub-" + uuid.uuid4().hex, email)
        sign_in(client)

        # There is no password, so password sign-in must not succeed with
        # anything at all — including an empty string.
        for attempt in ("", PASSWORD, "password"):
            response = client.post(
                "/api/v1/auth/login", json={"email": email, "password": attempt or "x"}
            )
            assert response.status_code == 401


class TestReturning:
    def test_the_same_google_account_returns_to_the_same_user(self, client, google):
        subject = "sub-" + uuid.uuid4().hex
        email = unique_email("returning")
        google(subject, email)
        first = sign_in(client).json()

        google(subject, email)
        second = sign_in(client).json()

        assert second["created"] is False
        assert second["user"]["id"] == first["user"]["id"]

    def test_a_changed_google_address_still_finds_the_same_user(self, client, google):
        """The subject is the identity; the address is only a label.

        A person who changes their address at Google must not become a second
        account here.
        """
        subject = "sub-" + uuid.uuid4().hex
        google(subject, unique_email("before"))
        first = sign_in(client).json()

        google(subject, unique_email("after"))
        second = sign_in(client).json()

        assert second["user"]["id"] == first["user"]["id"]
        assert second["created"] is False


class TestLinking:
    def test_a_verified_address_links_to_the_existing_account(self, client, google):
        email = unique_email("linkable")
        local = register(client, email).json()

        google("sub-" + uuid.uuid4().hex, email, email_verified=True)
        response = sign_in(client)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["created"] is False
        # Same account, reached two ways — not a duplicate.
        assert body["user"]["id"] == local["user"]["id"]

    def test_an_unverified_address_cannot_take_over_an_account(self, client, google):
        """The attack this exists to stop.

        Someone registers a Google account claiming a victim's address. If
        Google has not verified it and this linked anyway, they would be
        signed in as the victim.
        """
        email = unique_email("victim")
        register(client, email)

        google("attacker-sub-" + uuid.uuid4().hex, email, email_verified=False)
        response = sign_in(client)

        assert response.status_code == 409
        assert response.json()["error"]["key"] == "auth.error.googleUnverifiedEmail"

    def test_a_refused_link_creates_no_account_at_all(self, client, google):
        """Falling back to a second account on the same address would be its
        own confusion, and would still hand the attacker a foothold."""
        email = unique_email("victim2")
        register(client, email)
        google("attacker-" + uuid.uuid4().hex, email, email_verified=False)
        sign_in(client)

        # The victim's own password still works, and is still the only way in.
        response = client.post(
            "/api/v1/auth/login", json={"email": email, "password": PASSWORD}
        )
        assert response.status_code == 200

    def test_an_unverified_address_is_fine_when_nobody_owns_it(self, client, google):
        """There is nothing to take over, so this is just a new account."""
        google("sub-" + uuid.uuid4().hex, unique_email("fresh"), email_verified=False)

        response = sign_in(client)

        assert response.status_code == 200
        assert response.json()["created"] is True


class TestRefusals:
    def test_a_rejected_token_says_nothing_about_why(self, client, monkeypatch):
        def boom(_token, *, client_id, leeway=30):
            raise google_identity.InvalidGoogleToken("audience mismatch: acme.com")

        monkeypatch.setattr(
            "satsaathi_api.routers.auth.google_identity.verify", boom
        )

        response = sign_in(client)

        assert response.status_code == 401
        assert response.json()["error"]["key"] == "auth.error.googleRejected"
        # The reason must not leak into the response.
        assert "acme.com" not in response.text
        assert "audience" not in response.text

    def test_google_sign_in_is_refused_when_it_is_not_configured(
        self, client, monkeypatch
    ):
        from satsaathi_core.settings import Settings, get_settings

        get_settings.cache_clear()
        monkeypatch.delenv("GOOGLE_CLIENT_ID", raising=False)
        monkeypatch.setattr(
            "satsaathi_api.deps.get_settings", lambda: Settings(google_client_id="")
        )

        response = sign_in(client)

        assert response.status_code == 503
        assert response.json()["error"]["key"] == "auth.error.googleDisabled"


class TestTokenVerifier:
    """The verifier itself, on inputs that must never be believed."""

    @pytest.mark.parametrize("token", ["", "   ", "not.a.jwt", "a.b.c"])
    def test_garbage_is_refused(self, token):
        with pytest.raises(google_identity.InvalidGoogleToken):
            google_identity.verify(token, client_id=CLIENT_ID)

    def test_a_token_is_refused_when_no_client_id_is_configured(self):
        """Skipping the audience check would accept tokens minted for any
        other application, so a missing client id refuses rather than
        relaxes."""
        with pytest.raises(google_identity.InvalidGoogleToken, match="client id"):
            google_identity.verify("some.jwt.value", client_id="")
