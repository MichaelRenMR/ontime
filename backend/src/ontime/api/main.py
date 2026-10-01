from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ontime.api.routes import health
from ontime.config import get_settings
from ontime.logging import setup_logging


def create_app() -> FastAPI:
    setup_logging()
    settings = get_settings()
    app = FastAPI(title="OnTime API")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",") if o.strip()],
        allow_methods=["GET"],
        allow_headers=["*"],
    )
    app.include_router(health.router)
    # Feature routes (airports, boards, flights, ask) will mount under /v1/.
    return app


app = create_app()
