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


RW = {"ourairports_id": 555, "airport_ourairports_id": 3797, "le_ident": "04L", "he_ident": "22R",
      "le_heading": 31.0, "he_heading": 211.0, "length_ft": 12079, "surface": "ASP", "closed": False}
AL = {"openflights_id": 1, "iata": "UA", "icao": "UAL", "name": "United", "country": "US", "active": True}


def test_runway_reseed_keeps_ids_and_created_at_updates_changes_and_drops_removed(session):
    repo.upsert_airports(session, [JFK])
    other = {**RW, "ourairports_id": 556, "le_ident": "13L"}
    unknown_airport = {**RW, "ourairports_id": 557, "airport_ourairports_id": 999999}
    assert repo.upsert_runways(session, [RW, other, unknown_airport]) == 2
    session.commit()
    rid, created = session.execute(select(Runway.id, Runway.created_at).where(Runway.ourairports_id == 555)).one()

    repo.upsert_runways(session, [{**RW, "length_ft": 12000}])  # 556 is gone from the source
    session.commit()
    assert session.execute(select(Runway.ourairports_id, Runway.id, Runway.created_at, Runway.length_ft)).all() == [
        (555, rid, created, 12000)]


def test_legacy_rows_without_a_source_id_are_replaced(session):
    repo.upsert_airports(session, [JFK])
    airport_id = session.scalar(select(Airport.id))
    session.add(Runway(airport_id=airport_id, le_ident="OLD"))
    session.add(Airline(name="Old", iata="UA"))
    session.flush()
    repo.upsert_runways(session, [RW])
    repo.upsert_airlines(session, [AL])
    assert session.scalars(select(Runway.le_ident)).all() == ["04L"]
    assert session.scalars(select(Airline.name)).all() == ["United"]


def test_empty_source_leaves_tables_untouched(session):
    repo.upsert_airlines(session, [AL])
    assert repo.upsert_airlines(session, []) == 0
    assert n(session, Airline) == 1


def test_airline_reseed_is_idempotent(session):
    repo.upsert_airlines(session, [AL])
    repo.upsert_airlines(session, [{**AL, "name": "United Airlines"}])
    assert session.execute(select(Airline.openflights_id, Airline.name)).all() == [(1, "United Airlines")]


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
