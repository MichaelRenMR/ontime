"""Aircraft types, provider aliases, and airframes (tails)."""
from __future__ import annotations

import re
from collections.abc import Iterable

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ontime.models import Aircraft, AircraftType, AircraftTypeAlias

_CHUNK = 1000


def normalize_alias(s: str) -> str:
    """Matching key for provider type strings: casing, whitespace and non-breaking spaces don't matter.
    SQL twin: normalize_alias() in migration 0005; tests check they agree."""
    return re.sub(r"\s+", " ", s.replace(" ", " ")).strip().lower()


def upsert_aircraft_types(session: Session, rows: list[dict]) -> int:
    for i in range(0, len(rows), _CHUNK):
        stmt = pg_insert(AircraftType).values(rows[i : i + _CHUNK])
        update = {c: getattr(stmt.excluded, c) for c in ("manufacturer", "name", "family", "category")}
        session.execute(stmt.on_conflict_do_update(index_elements=["designator"], set_=update))
    return len(rows)


def sync_aliases(session: Session, source: str, rows: list[dict]) -> int:
    """Make the aliases for `source` exactly match `rows` (upsert, then drop aliases no longer listed)."""
    rows = [{**r, "source": source, "alias_key": normalize_alias(r["alias"])} for r in rows]
    keys = [r["alias_key"] for r in rows]
    if len(set(keys)) != len(keys):
        raise ValueError("two aliases normalize to the same key")
    for i in range(0, len(rows), _CHUNK):
        stmt = pg_insert(AircraftTypeAlias).values(rows[i : i + _CHUNK])
        update = {c: getattr(stmt.excluded, c) for c in ("alias", "designator", "family", "note")}
        session.execute(stmt.on_conflict_do_update(index_elements=["source", "alias_key"], set_=update))
    session.execute(delete(AircraftTypeAlias).where(
        AircraftTypeAlias.source == source, AircraftTypeAlias.alias_key.not_in(keys)))
    return len(rows)


def upsert_aircraft(session: Session, rows: Iterable[dict]) -> int:
    """Upsert airframes keyed on icao24, in chunks; duplicates within a chunk keep the last row."""
    n, chunk = 0, {}
    for row in rows:
        chunk[row["icao24"]] = row
        if len(chunk) >= _CHUNK:
            n += _flush(session, chunk)
            chunk = {}
    return n + (_flush(session, chunk) if chunk else 0)


def _flush(session: Session, chunk: dict[str, dict]) -> int:
    stmt = pg_insert(Aircraft).values(list(chunk.values()))
    update = {c: getattr(stmt.excluded, c) for c in next(iter(chunk.values())) if c != "icao24"}
    session.execute(stmt.on_conflict_do_update(index_elements=["icao24"], set_=update))
    return len(chunk)


def snapshot_loaded(session: Session, snapshot: str) -> bool:
    return session.scalar(select(Aircraft.icao24).where(Aircraft.source_snapshot == snapshot).limit(1)) is not None


def resolution_coverage(session: Session) -> list[tuple[str, int, float]]:
    """How flights resolve to an aircraft type: (resolution, flights, percent)."""
    rows = session.execute(text("""
        SELECT coalesce(resolution, 'unresolved') AS r, count(*) AS n FROM movement_aircraft GROUP BY 1 ORDER BY 2 DESC
    """)).all()
    total = sum(n for _, n in rows) or 1
    return [(r, n, round(100 * n / total, 1)) for r, n in rows]
