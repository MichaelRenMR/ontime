from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select

from ontime.ingest.base import Movement
from ontime.models import Movement as MovementRow
from ontime.repositories.movements import upsert_movements

SCHED = datetime(2026, 10, 1, 17, 0, tzinfo=UTC)


def make(**kw) -> Movement:
    base = Movement(
        source="test", airport_iata="JFK", side="dep", airline_iata="UA", flight_number="888",
        sched_date_local=date(2026, 10, 1), sched_utc=SCHED,
    )
    return replace(base, **kw)


def count(session) -> int:
    return session.scalar(select(func.count()).select_from(MovementRow))


def test_upsert_is_idempotent(session):
    m = make(terminal="7")
    upsert_movements(session, [m])
    upsert_movements(session, [m])
    assert count(session) == 1


def test_retime_updates_instead_of_duplicating(session):
    upsert_movements(session, [make()])
    upsert_movements(session, [make(sched_utc=SCHED + timedelta(minutes=45))])
    assert count(session) == 1
    assert session.scalar(select(MovementRow.sched_utc)) == SCHED + timedelta(minutes=45)


def test_sparse_update_does_not_erase_known_values(session):
    upsert_movements(session, [make(terminal="7", gate="B22", actual_utc=SCHED)])
    upsert_movements(session, [make(terminal=None, gate=None, actual_utc=None, status="Departed")])
    row = session.scalars(select(MovementRow)).one()
    assert (row.terminal, row.gate, row.actual_utc, row.status) == ("7", "B22", SCHED, "Departed")


def test_duplicates_within_one_batch(session):
    assert upsert_movements(session, [make(terminal="1"), make(terminal="2")]) == 1
    assert session.scalars(select(MovementRow)).one().terminal == "2"
