"""Checking that a Google ID token is genuine, current, and meant for us.

This is the only evidence the API accepts that somebody is who they say they
are through Google, so every part of it is verified rather than read:

  * the signature, against Google's published keys, fetched over TLS,
  * the issuer, so a token minted elsewhere is refused,
  * the audience, so a valid token issued to a *different* application cannot
    be replayed against this one,
  * the expiry, so an old token cannot be reused.

`jwt.decode` does all of this when told to. What it cannot do is decide
whether an address is trustworthy, and that judgement lives in `verify`.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any

import httpx
import jwt
from jwt import PyJWKClient

ISSUERS = {"https://accounts.google.com", "accounts.google.com"}
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
TOKEN_URL = "https://oauth2.googleapis.com/token"

#: Google rotates signing keys; the client caches them and refetches on a miss.
_jwk_client: PyJWKClient | None = None
_lock = threading.Lock()


class InvalidGoogleToken(Exception):
    """The token is missing, malformed, expired, or not addressed to us."""


@dataclass(frozen=True)
class GoogleIdentity:
    """What Google asserts about a person, after the token checked out."""

    subject: str
    email: str
    email_verified: bool
    name: str | None
    picture: str | None


def _client() -> PyJWKClient:
    global _jwk_client
    if _jwk_client is None:
        with _lock:
            if _jwk_client is None:
                _jwk_client = PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600)
    return _jwk_client


def verify(token: str, *, client_id: str, leeway: int = 30) -> GoogleIdentity:
    """Return what Google asserts, or raise.

    `leeway` forgives a little clock skew between this machine and Google's,
    which is otherwise a source of spurious sign-in failures on a laptop whose
    clock has drifted.
    """
    if not token:
        raise InvalidGoogleToken("no token")
    if not client_id:
        # Refusing here rather than skipping the audience check: a deployment
        # with no client id configured must not accept tokens meant for some
        # other application.
        raise InvalidGoogleToken("no client id configured")

    try:
        signing_key = _client().get_signing_key_from_jwt(token)
        claims: dict[str, Any] = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=client_id,
            leeway=leeway,
            options={"require": ["exp", "iat", "aud", "iss", "sub"]},
        )
    except Exception as exc:  # noqa: BLE001 - every failure means the same thing
        raise InvalidGoogleToken(str(exc)) from exc

    if claims.get("iss") not in ISSUERS:
        raise InvalidGoogleToken(f"unexpected issuer {claims.get('iss')!r}")

    email = (claims.get("email") or "").strip().lower()
    if not email:
        raise InvalidGoogleToken("token carries no email")

    return GoogleIdentity(
        subject=str(claims["sub"]),
        email=email,
        # Google sends this as a bool, but has historically sent the string
        # "true" as well. Anything else is treated as unverified, because the
        # safe reading of an ambiguous claim is the restrictive one.
        email_verified=claims.get("email_verified") in (True, "true"),
        name=claims.get("name"),
        picture=claims.get("picture"),
    )


async def exchange_code(
    *,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    code_verifier: str,
) -> str:
    """Trade an authorization code for an ID token. Returns the raw token.

    The verifier is what makes an intercepted code useless: without the
    original random value, the code cannot be redeemed.
    """
    async with httpx.AsyncClient(timeout=15) as client:
        response = await client.post(
            TOKEN_URL,
            data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
                "code_verifier": code_verifier,
            },
        )
    if response.status_code != 200:
        raise InvalidGoogleToken(f"code exchange failed: {response.status_code}")

    payload = response.json()
    id_token = payload.get("id_token")
    if not id_token:
        raise InvalidGoogleToken("no id_token in the exchange response")
    return str(id_token)
