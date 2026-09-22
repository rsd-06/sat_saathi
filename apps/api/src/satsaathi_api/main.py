from fastapi import FastAPI

from satsaathi_api.routers.health import router as health_router

app = FastAPI(title="SatSaathi API")
app.include_router(health_router, prefix="/api/v1", tags=["health"])
