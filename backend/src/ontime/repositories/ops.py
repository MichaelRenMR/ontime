"""Operational tables: ingest log, poll state, API usage ledger."""
from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import select, update
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


def enabled_airports_in_tier(session: Session, tier: int) -> list[str]:
    return list(session.scalars(
        select(AirportPoll.airport_iata)
        .where(AirportPoll.tier == tier, AirportPoll.enabled.is_(True))
        .order_by(AirportPoll.airport_iata)
    ))
