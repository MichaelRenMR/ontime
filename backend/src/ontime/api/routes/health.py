from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Response
from sqlalchemy import func, select, text

from ontime.api.schemas import HealthResponse, IngestStatus, ReadyResponse
from ontime.db import session_scope
from ontime.models import IngestLog

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness: the process is up. Deliberately does not touch the database, so a DB blip
    can't make a container platform restart healthy API containers."""
    return HealthResponse(status="ok")


@router.get("/health/ready", response_model=ReadyResponse)
def ready(response: Response) -> ReadyResponse:
    """Readiness: the database is reachable. Ingest lag is informational and never fails the check."""
    try:
        with session_scope() as s:
            s.execute(text("SELECT 1"))
            last = s.scalar(
                select(func.max(IngestLog.fetched_at)).where(IngestLog.status.in_(("ok", "unchanged")))
            )
    except Exception:
        response.status_code = 503
        return ReadyResponse(status="unavailable", db="down")
    lag = int((datetime.now(UTC) - last).total_seconds()) if last else None
    return ReadyResponse(status="ok", db="ok", ingest=IngestStatus(last_success_at=last, lag_s=lag))
