from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import delete, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ontime.models import Airline, Airport, AirportPoll, Runway

_CHUNK = 1000


def _chunks(rows: list[dict]):
    for i in range(0, len(rows), _CHUNK):
        yield rows[i : i + _CHUNK]


def upsert_airports(session: Session, rows: list[dict]) -> int:
    """Upsert keyed on the stable OurAirports id, so IATA/ICAO corrections update in place."""
    for chunk in _chunks(rows):
        stmt = pg_insert(Airport).values(chunk)
        update = {c: getattr(stmt.excluded, c) for c in ("iata", "icao", "name", "city", "country", "lat", "lon", "tz")}
        session.execute(stmt.on_conflict_do_update(index_elements=["ourairports_id"], set_=update))
    return len(rows)


def replace_runways(session: Session, rows: list[dict]) -> int:
    """Reload all runways. Nothing references runway ids yet, so replace-all is the simplest idempotent load."""
    ids = dict(session.execute(select(Airport.ourairports_id, Airport.id)).all())
    mapped = [
        {**{k: v for k, v in r.items() if k != "ourairports_id"}, "airport_id": ids[r["ourairports_id"]]}
        for r in rows
        if r["ourairports_id"] in ids
    ]
    session.execute(delete(Runway))
    for chunk in _chunks(mapped):
        session.execute(insert(Runway), chunk)
    return len(mapped)


def replace_airlines(session: Session, rows: list[dict]) -> int:
    """Reload all airlines. OpenFlights rows have no stable key and nothing references them yet."""
    session.execute(delete(Airline))
    for chunk in _chunks(rows):
        session.execute(insert(Airline), chunk)
    return len(rows)


def get_airport_tz(session: Session, iata: str) -> str | None:
    return session.scalar(select(Airport.tz).where(Airport.iata == iata.upper()))


def load_poll_tiers(session: Session, tiers: Iterable[tuple[str, int]]) -> tuple[int, list[str]]:
    """Upsert airport -> tier. Only the tier is written, so `enabled` and failure state survive a re-seed.

    Returns (rows loaded, IATA codes missing from the airport table). Unknown airports are still
    loaded; they work, but each poll then has to ask the provider for the timezone.
    """
    pairs = [(iata.upper(), tier) for iata, tier in tiers]
    if pairs:
        stmt = pg_insert(AirportPoll).values([{"airport_iata": i, "tier": t} for i, t in pairs])
        session.execute(stmt.on_conflict_do_update(
            index_elements=["airport_iata"], set_={"tier": stmt.excluded.tier}
        ))
    known = set(session.scalars(select(Airport.iata).where(Airport.iata.in_([i for i, _ in pairs]))))
    return len(pairs), sorted({i for i, _ in pairs} - known)


def count_airports(session: Session) -> tuple[int, int]:
    """(total airports, airports with a timezone), a quick seed sanity check."""
    return session.execute(select(func.count(), func.count(Airport.tz)).select_from(Airport)).one()
