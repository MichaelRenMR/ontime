from sqlalchemy import func, select

from ontime.models import Airline, Airport, AirportPoll, Runway
from ontime.repositories import reference as repo

JFK = {"iata": "JFK", "icao": "KJFK", "name": "JFK", "city": "New York", "country": "US",
       "lat": 40.6, "lon": -73.8, "tz": "America/New_York", "ourairports_id": 3797}
LHR = {**JFK, "iata": "LHR", "icao": "EGLL", "name": "Heathrow", "tz": "Europe/London", "ourairports_id": 2434}


def n(session, model) -> int:
    return session.scalar(select(func.count()).select_from(model))


def test_airport_upsert_is_idempotent_and_updates_in_place(session):
    repo.upsert_airports(session, [JFK, LHR])
    repo.upsert_airports(session, [{**JFK, "name": "John F. Kennedy"}, LHR])
    assert n(session, Airport) == 2
    assert session.scalar(select(Airport.name).where(Airport.iata == "JFK")) == "John F. Kennedy"
    assert repo.get_airport_tz(session, "lhr") == "Europe/London"
    assert repo.get_airport_tz(session, "ZZZ") is None


def test_runways_map_to_airports_and_reload_cleanly(session):
    repo.upsert_airports(session, [JFK])
    rw = {"ourairports_id": 3797, "le_ident": "04L", "he_ident": "22R", "le_heading": 31.0,
          "he_heading": 211.0, "length_ft": 12079, "surface": "ASP", "closed": False}
    orphan = {**rw, "ourairports_id": 999999}
    assert repo.replace_runways(session, [rw, orphan]) == 1
    assert repo.replace_runways(session, [rw]) == 1
    assert n(session, Runway) == 1


def test_airlines_reload(session):
    row = {"iata": "UA", "icao": "UAL", "name": "United", "country": "US", "active": True}
    repo.replace_airlines(session, [row])
    repo.replace_airlines(session, [row])
    assert n(session, Airline) == 1


def test_poll_tiers_reseed_keeps_enabled_and_reports_unknown(session):
    repo.upsert_airports(session, [JFK])
    loaded, unknown = repo.load_poll_tiers(session, [("JFK", 1), ("ZZZ", 2)])
    assert (loaded, unknown) == (2, ["ZZZ"])

    row = session.get(AirportPoll, "JFK")
    row.enabled, row.consecutive_failures = False, 4
    session.flush()

    repo.load_poll_tiers(session, [("JFK", 2)])
    session.refresh(row)
    assert (row.tier, row.enabled, row.consecutive_failures) == (2, False, 4)
