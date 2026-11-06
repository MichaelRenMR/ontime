from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, FetchedValue, MetaData, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)
    type_annotation_map = {
        str: Text,
        datetime: DateTime(timezone=True),
    }


class TimestampMixin:
    """created_at / updated_at on every table, maintained by the database itself, so they are right no
    matter who writes the row (the app, raw SQL, a desktop client).

    created_at defaults to now(). updated_at is bumped by the set_updated_at() trigger (migration 0002)
    only when a row's values actually change, so re-sending identical data doesn't touch it.
    """

    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), server_onupdate=FetchedValue())
