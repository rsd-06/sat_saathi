import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager

import asyncpg
import sqlalchemy.exc
from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from satsaathi_core.db import dispose_engine
from satsaathi_core.settings import get_settings

from .routers.assets import router as assets_router
from .routers.auth import router as auth_router
from .routers.health import router as health_router
from .routers.input_sets import router as input_sets_router
from .routers.jobs import router as jobs_router
from .routers.models import router as models_router
from .routers.review import router as review_router
from .routers.tools import router as tools_router

logger = logging.getLogger("satsaathi_api")


async def _warm_pool(connections: int) -> None:
    """Open connections up front, so no request pays to establish one.

    Reaching a hosted database is TCP, then TLS, then SCRAM — measured at
    around five seconds to Supabase from here, against 146ms for a query once
    the connection exists. A job that does a handful of round trips therefore
    spends almost all of its time connecting rather than working: 23 seconds
    of wall clock for 391ms of actual steps, the first time through.

    Opening them in the background rather than during startup, because a
    process that refuses to accept requests for half a minute while it warms
    up is worse than one that is briefly slow.
    """
    from sqlalchemy import text

    from satsaathi_core.db import get_engine

    engine = get_engine()
    try:
        # Held together so the pool keeps all of them, rather than handing the
        # same connection back for each turn of the loop.
        async with contextlib.AsyncExitStack() as stack:
            for _ in range(connections):
                conn = await stack.enter_async_context(engine.connect())
                await conn.execute(text("SELECT 1"))
    except Exception as exc:  # noqa: BLE001
        # A database that is down is the health check's story to tell, not a
        # reason to fail startup.
        logger.warning("could not warm the connection pool: %s", exc)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Warm the pool on the way in, hand it back on the way out.

    The engine is cached per process and its connections belong to the event
    loop that opened them. Leaving the pool open at shutdown strands sockets
    on a loop that is about to close, which the driver reports much later as
    `'NoneType' object has no attribute 'send'` — the same failure the Celery
    worker hit for the same reason.
    """
    settings = get_settings()
    warming = (
        asyncio.create_task(_warm_pool(3)) if settings.database_is_remote else None
    )
    try:
        yield
    finally:
        if warming is not None:
            warming.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await warming
        await dispose_engine()


app = FastAPI(title="SatSaathi API", version="0.1.0", lifespan=lifespan)

settings = get_settings()

# The browser app is served from a different origin in development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3100",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(HTTPException)
async def message_key_errors(request: Request, exc: HTTPException) -> JSONResponse:
    """Errors leave as {"error": {"key", "params"}} so the frontend localises.

    Handlers that raise with an already-shaped detail pass through untouched;
    anything else (including FastAPI's own 404s) is wrapped rather than
    leaking an English sentence into the interface.
    """
    detail = exc.detail
    if isinstance(detail, dict) and "error" in detail:
        return JSONResponse(detail, status_code=exc.status_code)
    return JSONResponse(
        {"error": {"key": "http.error", "params": {"status": exc.status_code}}},
        status_code=exc.status_code,
    )


# Only failures to *reach* the database are caught here: the resolver and
# socket (OSError, including getaddrinfo), timeouts, and the driver's own
# connection errors. A genuine bug in a query must still surface as a 500,
# not be disguised as an outage.
@app.exception_handler(asyncpg.exceptions.CannotConnectNowError)
@app.exception_handler(asyncpg.exceptions.TooManyConnectionsError)
@app.exception_handler(asyncpg.exceptions.ConnectionDoesNotExistError)
@app.exception_handler(sqlalchemy.exc.OperationalError)
@app.exception_handler(sqlalchemy.exc.InterfaceError)
@app.exception_handler(OSError)
@app.exception_handler(TimeoutError)
async def database_unreachable(request: Request, exc: Exception) -> JSONResponse:
    """The database could not be reached: say so, as a key, with a 503.

    Left to itself this surfaced as a bare 500 after a long wait, which the
    sign-in form could only call "something went wrong". A 503 with a key
    lets the interface say the service is unreachable, and tells a caller
    that trying again later is reasonable.
    """
    logger.warning("database unreachable on %s: %s", request.url.path, exc)
    return JSONResponse(
        {"error": {"key": "service.databaseUnavailable", "params": {}}},
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


@app.exception_handler(RequestValidationError)
async def validation_errors(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    """A rejected field leaves as a key too, not as FastAPI's English.

    Pydantic writes messages like "value is not a valid email address", which
    is exactly the user-facing English this API promises never to send. The
    fields it names still travel, so the interface can mark the right inputs;
    the wording is the frontend's to choose.
    """
    fields = sorted(
        {
            str(part)
            for error in exc.errors()
            for part in error.get("loc", ())
            if part != "body"
        }
    )
    return JSONResponse(
        {"error": {"key": "request.invalid", "params": {"fields": fields}}},
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


for router in (
    health_router,
    auth_router,
    assets_router,
    input_sets_router,
    jobs_router,
    models_router,
    review_router,
    tools_router,
):
    app.include_router(router, prefix="/api/v1")
