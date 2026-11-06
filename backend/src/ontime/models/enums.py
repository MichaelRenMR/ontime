"""Closed vocabularies the code branches on. Stored as text with a CHECK constraint generated from the
enum (SQLAlchemy Enum with native_enum=False), not as a Postgres ENUM type, so the Python enum and the
database can't drift; adding a value is a migration that updates the constraint.

Open, data-driven vocabularies (aircraft type designators, airports, airlines) are lookup tables
instead, not enums.
"""
from __future__ import annotations

from enum import StrEnum

from sqlalchemy import Enum


class AircraftCategory(StrEnum):
    NARROWBODY = "narrowbody"
    WIDEBODY = "widebody"
    REGIONAL_JET = "regional_jet"
    TURBOPROP = "turboprop"
    BUSINESS_JET = "business_jet"
    HELICOPTER = "helicopter"
    PISTON = "piston"
    OTHER = "other"


def text_enum(enum_cls: type[StrEnum], name: str) -> Enum:
    """Column type: stores the enum's values as text, enforced by a named CHECK constraint."""
    return Enum(
        enum_cls, name=name, native_enum=False, create_constraint=True, length=32,
        values_callable=lambda e: [m.value for m in e], validate_strings=True,
    )
