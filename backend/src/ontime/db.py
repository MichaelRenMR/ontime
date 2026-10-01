"""One sync engine for the whole app: API, flows, CLI and tests all go through here."""
from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from ontime.config import get_settings


def normalize_url(url: str) -> str:
    # Accept plain postgresql:// URLs (what most hosts hand out) and force the psycopg3 driver.
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


@lru_cache
def get_engine() -> Engine:
    return create_engine(normalize_url(get_settings().database_url), pool_pre_ping=True, pool_size=5)


@lru_cache
def _sessionmaker() -> sessionmaker[Session]:
    return sessionmaker(get_engine(), expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    """Commit on success, roll back on error. The unit of work for flows, the CLI and the API."""
    session = _sessionmaker()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
