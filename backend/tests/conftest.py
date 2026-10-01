"""Tests that touch the DB run against a real Postgres (ontime_test), migrated with Alembic.

Start one with `make up` (compose creates the ontime_test database). If it is unreachable the
DB tests are skipped, so pure-logic tests still run anywhere.
"""
import os

import pytest

TEST_DB_URL = os.environ.get("TEST_DATABASE_URL", "postgresql+psycopg://ontime:ontime@localhost:5432/ontime_test")
os.environ["DATABASE_URL"] = TEST_DB_URL  # must be set before ontime.config is first used

from alembic import command  # noqa: E402
from alembic.config import Config  # noqa: E402
from sqlalchemy import text  # noqa: E402

from ontime.config import get_settings  # noqa: E402
from ontime.db import get_engine, session_scope  # noqa: E402

get_settings.cache_clear()


@pytest.fixture(scope="session")
def migrated_engine():
    engine = get_engine()
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"test database unavailable: {exc.__class__.__name__}")
    cfg = Config(os.path.join(os.path.dirname(__file__), "..", "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(os.path.dirname(__file__), "..", "migrations"))
    command.upgrade(cfg, "head")
    return engine


@pytest.fixture
def session(migrated_engine):
    with session_scope() as s:
        yield s
    with migrated_engine.begin() as conn:
        conn.execute(text("TRUNCATE movement, ingest_log, airport_poll, api_usage RESTART IDENTITY"))
