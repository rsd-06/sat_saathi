"""Hashing, verifying and generating the secrets an account needs.

Argon2id, at the library's current defaults, which track what the Password
Hashing Competition and OWASP recommend. Parameters are not pinned here: a
hash records the parameters it was made with, so raising them later rehashes
on next sign-in rather than invalidating everyone's password.
"""

from __future__ import annotations

import hashlib
import secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_hasher = PasswordHasher()

#: Long enough that guessing is not a strategy; opaque so it carries no claims.
SESSION_TOKEN_BYTES = 32


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    """True when the password matches. Never raises for a wrong password."""
    try:
        return _hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError, ValueError):
        return False


def needs_rehash(password_hash: str) -> bool:
    """Whether this hash was made with weaker parameters than we use now."""
    try:
        return _hasher.check_needs_rehash(password_hash)
    except (InvalidHashError, ValueError):
        return False


def new_session_token() -> str:
    return secrets.token_urlsafe(SESSION_TOKEN_BYTES)


def hash_session_token(token: str) -> str:
    """Store this, never the token.

    A plain SHA-256 rather than Argon2: the token is already 256 bits of
    randomness, so there is nothing to slow an attacker down about, and this
    runs on every authenticated request.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
