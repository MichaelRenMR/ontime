"""Operational tables: ingest log, poll state, API usage ledger."""
from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import func, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from ontime.models import ApiUsage, AirportPoll, IngestLog


def add_ingest_log(session: Session, **fields) -> IngestLog:
    row = IngestLog(**fields)
    session.add(row)
    session.flush()
    return row


def last_ok_hash(session: Session, source: str, airport_iata: str) -> str | None:
    """Payload hash of the most recent successful fetch (ordered by id: fetched_at is the
    transaction start time and can tie)."""
    return session.scalar(
        select(IngestLog.payload_sha256)
        .where(IngestLog.source == source, IngestLog.airport_iata == airport_iata,
               IngestLog.status.in_(("ok", "unchanged")), IngestLog.payload_sha256.is_not(None))
        .order_by(IngestLog.id.desc())
        .limit(1)
    )


def usage_today(session: Session, provider: str, day: date | None = None) -> int:
    day = day or datetime.now(UTC).date()
    return session.scalar(select(ApiUsage.units).where(ApiUsage.provider == provider, ApiUsage.day == day)) or 0


def usage_month(session: Session, provider: str, day: date | None = None) -> tuple[int, int]:
    """(units, requests) recorded so far in the calendar month (UTC) containing `day`."""
    day = day or datetime.now(UTC).date()
    units, calls = session.execute(
        select(func.coalesce(func.sum(ApiUsage.units), 0), func.coalesce(func.sum(ApiUsage.calls), 0))
        .where(ApiUsage.provider == provider, ApiUsage.day >= day.replace(day=1), ApiUsage.day <= day)
    ).one()
    return int(units), int(calls)


def charge_usage(session: Session, provider: str, units: int, calls: int = 1, day: date | None = None) -> None:
    day = day or datetime.now(UTC).date()
    stmt = pg_insert(ApiUsage).values(provider=provider, day=day, calls=calls, units=units)
    session.execute(stmt.on_conflict_do_update(
        index_elements=["provider", "day"],
        set_={"calls": ApiUsage.calls + calls, "units": ApiUsage.units + units},
    ))


def record_poll_result(session: Session, airport_iata: str, status: str, *, failed: bool) -> None:
    """Update poll state for airports in airport_poll (airports polled ad hoc have no row)."""
    session.execute(
        update(AirportPoll)
        .where(AirportPoll.airport_iata == airport_iata)
        .values(
            last_polled_at=datetime.now(UTC),
            last_status=status,
            consecutive_failures=AirportPoll.consecutive_failures + 1 if failed else 0,
        )
    )


def all_enabled_airports(session: Session) -> list[str]:
    return list(session.scalars(
        select(AirportPoll.airport_iata).where(AirportPoll.enabled.is_(True)).order_by(AirportPoll.airport_iata)
    ))


def pause_failing_airports(session: Session, threshold: int) -> tuple[list[str], bool]:
    """Disable airports whose consecutive failures reached `threshold`.

    If more than half of the enabled airports are failing, that is almost certainly a provider
    outage or a bad key rather than many broken airports, so nothing is paused. Returns
    (paused airports, suspected_outage).
    """
    enabled = len(all_enabled_airports(session))
    failing = list(session.scalars(
        select(AirportPoll.airport_iata)
        .where(AirportPoll.enabled.is_(True), AirportPoll.consecutive_failures >= threshold)
        .order_by(AirportPoll.airport_iata)
    ))
    if not failing:
        return [], False
    if len(failing) * 2 > enabled:
        return [], True
    session.execute(update(AirportPoll).where(AirportPoll.airport_iata.in_(failing)).values(enabled=False))
    return failing, False


def unmatched_codes(session: Session, limit: int = 50) -> dict[str, list[str]]:
    """Codes seen in movement data that the reference tables don't know (for a periodic report)."""
    airports = session.execute(text("""
        SELECT code FROM (
            SELECT airport_iata AS code FROM movement UNION SELECT other_iata FROM movement
        ) c
        WHERE code IS NOT NULL AND code NOT IN (SELECT iata FROM airport WHERE iata IS NOT NULL)
        ORDER BY code LIMIT :n
    """), {"n": limit}).scalars().all()
    airlines = session.execute(text("""
        SELECT DISTINCT airline_iata FROM movement
        WHERE airline_iata NOT IN (SELECT iata FROM airline WHERE iata IS NOT NULL)
        ORDER BY airline_iata LIMIT :n
    """), {"n": limit}).scalars().all()
    aircraft_types = session.execute(text("""
        SELECT m.aircraft_type FROM movement m
        WHERE m.aircraft_type IS NOT NULL AND NOT EXISTS (
            SELECT 1 FROM aircraft_type_alias a WHERE a.source = m.source AND a.alias_key = normalize_alias(m.aircraft_type))
        GROUP BY 1 ORDER BY count(*) DESC LIMIT :n
    """), {"n": limit}).scalars().all()
    return {"airports": list(airports), "airlines": list(airlines), "aircraft_types": list(aircraft_types)}


def enabled_airports_in_tier(session: Session, tier: int) -> list[str]:
    return list(session.scalars(
        select(AirportPoll.airport_iata)
        .where(AirportPoll.tier == tier, AirportPoll.enabled.is_(True))
        .order_by(AirportPoll.airport_iata)
    ))
