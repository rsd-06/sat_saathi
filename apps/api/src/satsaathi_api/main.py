from contextlib import asynccontextmanager

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


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Hand the database its connections back on the way out.

    The engine is cached per process and its connections belong to the event
    loop that opened them. Leaving the pool open at shutdown strands sockets
    on a loop that is about to close, which the driver reports much later as
    `'NoneType' object has no attribute 'send'` — the same failure the Celery
    worker hit for the same reason.
    """
    yield
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
