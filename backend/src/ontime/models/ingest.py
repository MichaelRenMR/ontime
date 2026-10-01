from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, CheckConstraint, Date, Index, Integer, UniqueConstraint, func, text
from sqlalchemy.orm import Mapped, mapped_column

from ontime.models.base import Base


class Movement(Base):
    """One departure or arrival event at an airport, as reported by one source.

    Codes are plain text (no FKs) so ingestion never drops rows over missing reference data.
    Identity is the flight on a local calendar day; sched_utc is a mutable attribute, so an
    airline retime updates the row instead of creating a duplicate.
    """

    __tablename__ = "movement"
    __table_args__ = (
        UniqueConstraint(
            "source", "airport_iata", "side", "airline_iata", "flight_number", "sched_date_local",
            name="uq_movement_identity",
        ),
        CheckConstraint("side IN ('dep', 'arr')", name="side"),
        Index("ix_movement_board", "airport_iata", "side", "sched_utc"),
        Index("ix_movement_flight", "flight_number", "sched_date_local"),
        Index("ix_movement_open", "sched_utc", postgresql_where=text("actual_utc IS NULL")),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str]
    airport_iata: Mapped[str]
    side: Mapped[str]
    other_iata: Mapped[str | None]
    airline_iata: Mapped[str]
    flight_number: Mapped[str]       # normalized number only, e.g. '888' (airline_iata holds 'UA')
    flight_number_raw: Mapped[str | None]
    sched_date_local: Mapped[date] = mapped_column(Date)  # at airport_iata
    sched_utc: Mapped[datetime]
    estimated_utc: Mapped[datetime | None]
    actual_utc: Mapped[datetime | None]
    terminal: Mapped[str | None]
    gate: Mapped[str | None]
    runway: Mapped[str | None]
    status: Mapped[str | None]
    aircraft_type: Mapped[str | None]
    is_codeshare: Mapped[bool] = mapped_column(default=False, server_default="false")
    first_seen_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now())


class IngestLog(Base):
    """One row per provider fetch. The raw payload itself lives in object storage (raw_key)."""

    __tablename__ = "ingest_log"
    __table_args__ = (Index("ix_ingest_log_recent", "source", "airport_iata", text("fetched_at DESC")),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    source: Mapped[str]
    airport_iata: Mapped[str]
    window_start: Mapped[datetime | None]
    window_end: Mapped[datetime | None]
    fetched_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # ok | unchanged | parse_error | http_error | skipped_budget
    status: Mapped[str]
    raw_key: Mapped[str | None]
    payload_sha256: Mapped[str | None]
    error: Mapped[str | None]
    movements_upserted: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    flow_run_id: Mapped[str | None]
