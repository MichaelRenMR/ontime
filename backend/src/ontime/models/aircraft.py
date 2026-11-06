from __future__ import annotations

from datetime import date

from sqlalchemy import Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ontime.models.base import Base, TimestampMixin
from ontime.models.enums import AircraftCategory, text_enum


class AircraftType(TimestampMixin, Base):
    """One row per ICAO type designator (A21N = every A321neo), curated in data/aircraft_types.csv."""

    __tablename__ = "aircraft_type"

    designator: Mapped[str] = mapped_column(primary_key=True)  # ICAO Doc 8643, e.g. 'B738'
    manufacturer: Mapped[str]
    name: Mapped[str]                                          # e.g. '737-800'
    family: Mapped[str] = mapped_column(index=True)            # e.g. '737', 'A320'
    category: Mapped[AircraftCategory] = mapped_column(text_enum(AircraftCategory, "category"))


class AircraftTypeAlias(TimestampMixin, Base):
    """A provider's spelling of an aircraft type -> the type it means (data/aircraft_type_aliases.csv).

    Matched on alias_key = normalize_alias(text), the same function in Python and SQL. A row with no
    designator records a string that is deliberately unmapped (junk, or only a family is known).
    """

    __tablename__ = "aircraft_type_alias"

    source: Mapped[str] = mapped_column(primary_key=True)
    alias_key: Mapped[str] = mapped_column(primary_key=True)
    alias: Mapped[str]                         # one representative raw spelling, for humans
    designator: Mapped[str | None] = mapped_column(ForeignKey("aircraft_type.designator"))
    family: Mapped[str | None]                 # for strings that only identify a family ('Boeing 737')
    note: Mapped[str | None]


class Aircraft(TimestampMixin, Base):
    """One physical airframe, from the OpenSky aircraft database. Keyed on the ICAO 24-bit address.

    typecode is plain text (no FK): OpenSky covers thousands of general-aviation types we don't curate.
    model_code is OpenSky's free-text model, e.g. 'A321-271NX', kept as given.
    """

    __tablename__ = "aircraft"

    icao24: Mapped[str] = mapped_column(primary_key=True)      # lowercase hex
    registration: Mapped[str | None] = mapped_column(index=True)  # not unique: registrations get reused
    typecode: Mapped[str | None]
    model_code: Mapped[str | None]
    manufacturer: Mapped[str | None]
    operator_name: Mapped[str | None]
    operator_icao: Mapped[str | None]
    operator_iata: Mapped[str | None]
    serial_number: Mapped[str | None]
    built: Mapped[date | None] = mapped_column(Date)
    source_snapshot: Mapped[str]                               # e.g. '2025-08'
