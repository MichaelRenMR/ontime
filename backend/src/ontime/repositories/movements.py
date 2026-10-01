from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from ontime.ingest.base import Movement
from ontime.models import Movement as MovementRow

# Columns a later response may refresh, but only with a non-null value: a sparse response
# must never erase a terminal, gate or actual time we already know.
_KEEP_IF_NULL = (
    "other_iata", "flight_number_raw", "estimated_utc", "actual_utc", "terminal", "gate",
    "runway", "status", "aircraft_type",
)
_CHUNK = 1000  # 17 columns x 1000 rows stays well under Postgres' 65535 bind-parameter limit


def upsert_movements(session: Session, movements: Iterable[Movement]) -> int:
    """Idempotent upsert keyed on the movement identity. Returns the number of distinct rows sent."""
    unique = {
        (m.source, m.airport_iata, m.side, m.airline_iata, m.flight_number, m.sched_date_local): asdict(m)
        for m in movements  # later duplicates in one batch win; ON CONFLICT can't touch a row twice
    }
    rows = list(unique.values())
    for i in range(0, len(rows), _CHUNK):
        stmt = insert(MovementRow).values(rows[i : i + _CHUNK])
        ex = stmt.excluded
        update = {c: func.coalesce(getattr(ex, c), getattr(MovementRow, c)) for c in _KEEP_IF_NULL}
        update.update(sched_utc=ex.sched_utc, is_codeshare=ex.is_codeshare, updated_at=func.now())
        session.execute(stmt.on_conflict_do_update(constraint="uq_movement_identity", set_=update))
    return len(rows)
