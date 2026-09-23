"""Accounts and sign-in.

The API issues an opaque session token and never sets a browser cookie: the
Next.js app owns the cookie, on its own origin, and forwards the token as a
bearer credential. That keeps the two servers free to live on different hosts
without SameSite rules deciding whether sign-in works.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from satsaathi_core.models import User, UserSession
from satsaathi_core.passwords import (
    hash_password,
    hash_session_token,
    needs_rehash,
    new_session_token,
    verify_password,
)

#: Long enough to work through a day's imagery without re-authenticating.
SESSION_LIFETIME = timedelta(days=14)

_DUMMY_HASH: str | None = None


def _timing_hash() -> str:
    """A real hash of a value nobody knows, built once and reused."""
    global _DUMMY_HASH
    if _DUMMY_HASH is None:
        _DUMMY_HASH = hash_password(new_session_token())
    return _DUMMY_HASH


class EmailTaken(Exception):
    """Raised rather than returned, so a caller cannot ignore it."""


def normalise_email(email: str) -> str:
    return email.strip().lower()


async def get_by_email(session: AsyncSession, email: str) -> User | None:
    result = await session.scalars(
        select(User).where(User.email == normalise_email(email))
    )
    return result.first()


async def register(
    session: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str,
    department: str | None = None,
    district: str | None = None,
    preferred_locale: str = "en",
) -> User:
    email = normalise_email(email)
    if await get_by_email(session, email) is not None:
        raise EmailTaken(email)

    user = User(
        email=email,
        password_hash=hash_password(password),
        full_name=full_name.strip(),
        department=(department or None),
        district=(district or None),
        preferred_locale=preferred_locale,
    )
    session.add(user)
    await session.flush()
    return user


async def authenticate(
    session: AsyncSession, *, email: str, password: str
) -> User | None:
    """Return the user when the password is right, otherwise None.

    Both "no such account" and "wrong password" return None, and the caller
    reports one message for both: telling them apart tells an attacker which
    email addresses are registered.
    """
    user = await get_by_email(session, email)
    if user is None:
        # Spend the time anyway. Returning instantly for an unknown address
        # and slowly for a known one is the same disclosure by other means,
        # and it has to be a real hash: verifying against a malformed one
        # fails immediately and equalises nothing.
        verify_password(_timing_hash(), password)
        return None

    if not verify_password(user.password_hash, password):
        return None

    if needs_rehash(user.password_hash):
        user.password_hash = hash_password(password)

    user.last_seen_at = datetime.now(UTC)
    return user


async def start_session(session: AsyncSession, user: User) -> str:
    """Open a session and return the token. It is never recoverable later."""
    token = new_session_token()
    session.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_session_token(token),
            expires_at=datetime.now(UTC) + SESSION_LIFETIME,
        )
    )
    await session.flush()
    return token


async def resolve_session(session: AsyncSession, token: str) -> User | None:
    """The signed-in user for a token, or None if it is not usable."""
    if not token:
        return None

    result = await session.scalars(
        select(UserSession).where(UserSession.token_hash == hash_session_token(token))
    )
    record = result.first()
    if record is None or record.revoked_at is not None:
        return None

    expires_at = record.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if expires_at <= datetime.now(UTC):
        return None

    return await session.get(User, record.user_id)


async def end_session(session: AsyncSession, token: str) -> None:
    """Revoke one session. Signing out twice is not an error."""
    result = await session.scalars(
        select(UserSession).where(UserSession.token_hash == hash_session_token(token))
    )
    record = result.first()
    if record is not None and record.revoked_at is None:
        record.revoked_at = datetime.now(UTC)


async def end_all_sessions(session: AsyncSession, user_id: uuid.UUID) -> int:
    """Revoke every live session for an account. Returns how many."""
    result = await session.scalars(
        select(UserSession).where(
            UserSession.user_id == user_id, UserSession.revoked_at.is_(None)
        )
    )
    now = datetime.now(UTC)
    count = 0
    for record in result:
        record.revoked_at = now
        count += 1
    return count
