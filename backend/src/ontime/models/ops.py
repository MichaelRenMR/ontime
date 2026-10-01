from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import BigInteger, Boolean, Date, Integer, SmallInteger
from sqlalchemy.orm import Mapped, mapped_column

from ontime.models.base import Base


class AirportPoll(Base):
    """Which airports are polled and in which tier. Cadence per tier lives in config.TIERS."""

    __tablename__ = "airport_poll"

    airport_iata: Mapped[str] = mapped_column(primary_key=True)
    tier: Mapped[int] = mapped_column(SmallInteger)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
    last_polled_at: Mapped[datetime | None]
    last_status: Mapped[str | None]
    consecutive_failures: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class ApiUsage(Base):
    """Per-provider daily ledger used for the budget cap."""

    __tablename__ = "api_usage"

    provider: Mapped[str] = mapped_column(primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    calls: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
    units: Mapped[int] = mapped_column(BigInteger, default=0, server_default="0")
