from __future__ import annotations

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from ontime.models.base import Base


class Airport(Base):
    __tablename__ = "airport"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    iata: Mapped[str | None] = mapped_column(unique=True)
    icao: Mapped[str | None] = mapped_column(unique=True)
    name: Mapped[str]
    city: Mapped[str | None]
    country: Mapped[str | None]
    lat: Mapped[float | None] = mapped_column(Float)
    lon: Mapped[float | None] = mapped_column(Float)
    tz: Mapped[str]  # IANA, e.g. 'Asia/Tokyo'
    ourairports_id: Mapped[int | None] = mapped_column(BigInteger, unique=True)


class Runway(Base):
    __tablename__ = "runway"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    airport_id: Mapped[int] = mapped_column(ForeignKey("airport.id", ondelete="CASCADE"), index=True)
    le_ident: Mapped[str | None]
    he_ident: Mapped[str | None]
    le_heading: Mapped[float | None] = mapped_column(Float)
    he_heading: Mapped[float | None] = mapped_column(Float)
    length_ft: Mapped[int | None] = mapped_column(Integer)
    surface: Mapped[str | None]
    closed: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class Airline(Base):
    __tablename__ = "airline"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    iata: Mapped[str | None] = mapped_column(index=True)  # not unique: IATA codes get reused
    icao: Mapped[str | None] = mapped_column(index=True)
    name: Mapped[str]
    country: Mapped[str | None]
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="true")
