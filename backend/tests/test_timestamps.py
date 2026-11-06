from dataclasses import replace

from sqlalchemy import inspect, select, text

from fakes import MOVE
from ontime.models import AirportPoll, Base, Movement
from ontime.repositories.movements import upsert_movements


def stamps(session, model, *where):
    return session.execute(select(model.created_at, model.updated_at).where(*where)).one()


def pause(session):
    session.execute(text("SELECT pg_sleep(0.01)"))  # make consecutive transactions' now() distinct


def test_every_table_has_both_columns_and_the_trigger(session):
    triggers = set(session.scalars(text(
        "SELECT tgrelid::regclass::text FROM pg_trigger WHERE tgname LIKE 'trg_%_updated_at'")))
    for name, table in Base.metadata.tables.items():
        assert {"created_at", "updated_at"} <= set(table.c.keys()), name
        assert name in triggers, f"{name} has no updated_at trigger"
        cols = {c["name"]: c for c in inspect(session.connection()).get_columns(name)}
        assert not cols["created_at"]["nullable"] and cols["created_at"]["default"], name


def test_insert_sets_both(session):
    upsert_movements(session, [MOVE])
    session.commit()
    created, updated = stamps(session, Movement)
    assert created is not None and created == updated


def test_upsert_with_identical_data_does_not_bump_updated_at(session):
    upsert_movements(session, [MOVE])
    session.commit()
    before = stamps(session, Movement)
    pause(session)
    upsert_movements(session, [MOVE])
    session.commit()
    assert stamps(session, Movement) == before


def test_real_change_bumps_updated_at_but_not_created_at(session):
    upsert_movements(session, [MOVE])
    session.commit()
    created, updated = stamps(session, Movement)
    pause(session)
    upsert_movements(session, [replace(MOVE, terminal="4")])
    session.commit()
    created2, updated2 = stamps(session, Movement)
    assert created2 == created and updated2 > updated


def test_trigger_applies_to_plain_sql_updates_too(session):
    session.add(AirportPoll(airport_iata="JFK", tier=1))
    session.commit()
    _, before = stamps(session, AirportPoll)
    pause(session)
    session.execute(text("UPDATE airport_poll SET tier = 2 WHERE airport_iata = 'JFK'"))
    session.commit()
    _, after = stamps(session, AirportPoll)
    assert after > before
