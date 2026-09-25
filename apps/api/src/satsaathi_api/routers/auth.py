"""Registering, signing in, and knowing who is asking.

No cookies are set here. The token goes back in the response body and the
Next.js app stores it in an httpOnly cookie on its own origin, which keeps
sign-in working whether the two servers share a host or not.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, status

from satsaathi_core.models import User

from .. import auth_service, google_identity
from ..deps import Session, SettingsDep, api_error
from ..schemas import (
    GoogleTokenIn,
    LoginIn,
    ProfileIn,
    RegisterIn,
    SessionOut,
    UserOut,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        return ""
    return authorization[7:].strip()


async def current_user(
    session: Session, authorization: Annotated[str | None, Header()] = None
) -> User:
    """The signed-in user, or a 401 that says nothing about why."""
    user = await auth_service.resolve_session(session, _bearer(authorization))
    if user is None:
        raise api_error(status.HTTP_401_UNAUTHORIZED, "auth.error.notSignedIn")
    return user


CurrentUser = Annotated[User, Depends(current_user)]


async def optional_user(
    session: Session, authorization: Annotated[str | None, Header()] = None
) -> User | None:
    return await auth_service.resolve_session(session, _bearer(authorization))


OptionalUser = Annotated[User | None, Depends(optional_user)]


def _session_out(token: str, user: User, created: bool = False) -> SessionOut:
    return SessionOut(
        token=token,
        expires_at=datetime.now(UTC) + auth_service.SESSION_LIFETIME,
        user=UserOut.model_validate(user, from_attributes=True),
        created=created,
    )


@router.post(
    "/register", response_model=SessionOut, status_code=status.HTTP_201_CREATED
)
async def register(session: Session, body: RegisterIn) -> SessionOut:
    try:
        user = await auth_service.register(
            session,
            email=body.email,
            password=body.password,
            full_name=body.full_name,
            department=body.department,
            district=body.district,
            preferred_locale=body.preferred_locale,
        )
    except auth_service.EmailTaken:
        raise api_error(
            status.HTTP_409_CONFLICT, "auth.error.emailTaken"
        ) from None

    user.state = body.state
    user.designation = body.designation
    token = await auth_service.start_session(session, user)
    await session.commit()
    return _session_out(token, user)


@router.post("/login", response_model=SessionOut)
async def login(session: Session, body: LoginIn) -> SessionOut:
    user = await auth_service.authenticate(
        session, email=body.email, password=body.password
    )
    if user is None:
        # One message for both a wrong password and an unknown address.
        # Telling them apart tells an attacker which addresses are registered.
        raise api_error(status.HTTP_401_UNAUTHORIZED, "auth.error.badCredentials")

    token = await auth_service.start_session(session, user)
    await session.commit()
    return _session_out(token, user)


@router.post("/google", response_model=SessionOut)
async def sign_in_with_google(
    session: Session, settings: SettingsDep, body: GoogleTokenIn
) -> SessionOut:
    """Sign in with a Google ID token, verified here.

    The caller has already exchanged an authorization code for this token, but
    that is not evidence of anything on its own: a token can be minted for a
    different application, or replayed after expiry. Every claim that matters
    is checked against Google's own keys before an account is touched.
    """
    if not settings.google_sign_in_enabled:
        raise api_error(status.HTTP_503_SERVICE_UNAVAILABLE, "auth.error.googleDisabled")

    try:
        identity = google_identity.verify(
            body.id_token, client_id=settings.google_client_id
        )
    except google_identity.InvalidGoogleToken:
        # The reason is deliberately not reported. A caller with a bad token
        # learns that it was bad, and nothing about why.
        raise api_error(
            status.HTTP_401_UNAUTHORIZED, "auth.error.googleRejected"
        ) from None

    try:
        user, created = await auth_service.sign_in_with_provider(
            session,
            provider="google",
            subject=identity.subject,
            email=identity.email,
            email_verified=identity.email_verified,
            full_name=identity.name,
            preferred_locale=body.preferred_locale,
        )
    except auth_service.UnverifiedProviderEmail:
        raise api_error(
            status.HTTP_409_CONFLICT, "auth.error.googleUnverifiedEmail"
        ) from None

    token = await auth_service.start_session(session, user)
    await session.commit()
    return _session_out(token, user, created)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    session: Session, authorization: Annotated[str | None, Header()] = None
) -> None:
    """Signing out with no session, or twice, is not an error."""
    await auth_service.end_session(session, _bearer(authorization))
    await session.commit()


@router.patch("/me", response_model=UserOut)
async def update_me(session: Session, user: CurrentUser, body: ProfileIn) -> UserOut:
    """Edit one's own profile. Email and password are not changed here."""
    for field, value in body.model_dump(exclude_unset=True).items():
        if field == "full_name" and not value:
            continue
        setattr(user, field, (value.strip() or None) if isinstance(value, str) else value)
    await session.commit()
    return UserOut.model_validate(user, from_attributes=True)


@router.get("/me", response_model=UserOut)
async def me(session: Session, user: CurrentUser) -> UserOut:
    """Who is signed in. Asked on nearly every page, so kept to one query.

    `last_seen_at` is refreshed at most every few minutes rather than on each
    call: a write per page load is a commit per page load.
    """
    if auth_service.needs_last_seen_update(user):
        user.last_seen_at = datetime.now(UTC)
        await session.commit()
    return UserOut.model_validate(user, from_attributes=True)
