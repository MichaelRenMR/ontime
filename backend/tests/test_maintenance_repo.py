from datetime import date, datetime, UTC

from sqlalchemy import select

from fakes import MOVE
from ontime.models import Airline, Airport, AirportPoll
from ontime.repositories import ops
from ontime.repositories.movements import upsert_movements


def add_polls(session, failures: dict[str, int]):
    session.add_all(AirportPoll(airport_iata=i, tier=1, consecutive_failures=n) for i, n in failures.items())
    session.flush()


def enabled(session) -> set[str]:
    return set(session.scalars(select(AirportPoll.airport_iata).where(AirportPoll.enabled.is_(True))))


def test_pauses_only_the_failing_minority(session):
    add_polls(session, {"AAA": 25, "BBB": 0, "CCC": 1, "DDD": 0, "EEE": 2})
    paused, outage = ops.pause_failing_airports(session, threshold=20)
    assert (paused, outage) == (["AAA"], False)
    assert enabled(session) == {"BBB", "CCC", "DDD", "EEE"}


def test_mass_failure_is_treated_as_an_outage_and_pauses_nothing(session):
    add_polls(session, {"AAA": 25, "BBB": 30, "CCC": 21, "DDD": 0})
    paused, outage = ops.pause_failing_airports(session, threshold=20)
    assert (paused, outage) == ([], True)
    assert len(enabled(session)) == 4


def test_nothing_failing(session):
    add_polls(session, {"AAA": 3})
    assert ops.pause_failing_airports(session, threshold=20) == ([], False)


def test_unmatched_codes(session):
    upsert_movements(session, [MOVE])  # JFK dep, UA, no destination
    session.add(Airport(iata="JFK", name="JFK", tz="America/New_York"))
    session.flush()
    assert ops.unmatched_codes(session) == {"airports": [], "airlines": ["UA"], "aircraft_types": []}
    session.add(Airline(iata="UA", name="United"))
    session.flush()
    assert ops.unmatched_codes(session) == {"airports": [], "airlines": [], "aircraft_types": []}
