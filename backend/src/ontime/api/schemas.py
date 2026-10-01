from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class HealthResponse(BaseModel):
    status: str


class IngestStatus(BaseModel):
    last_success_at: datetime | None
    lag_s: int | None


class ReadyResponse(BaseModel):
    status: str
    db: str
    ingest: IngestStatus | None = None
