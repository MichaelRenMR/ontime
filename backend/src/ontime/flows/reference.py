from __future__ import annotations

from prefect import flow, task

from ontime.db import session_scope
from ontime.ingest.reference import seed


@task(name="seed-airports", retries=2, retry_delay_seconds=30)
def seed_airports_task() -> dict[str, int]:
    with session_scope() as s:
        return seed.seed_airports(s)


@task(name="seed-airlines", retries=2, retry_delay_seconds=30)
def seed_airlines_task() -> dict[str, int]:
    with session_scope() as s:
        return seed.seed_airlines(s)


@task(name="seed-poll-tiers")
def seed_poll_tiers_task() -> dict[str, int]:
    with session_scope() as s:
        return seed.seed_poll_tiers(s)


@task(name="seed-aircraft-types")
def seed_aircraft_types_task() -> dict[str, int]:
    with session_scope() as s:
        return seed.seed_aircraft_types(s)


@task(name="seed-aircraft", retries=2, retry_delay_seconds=60)
def seed_aircraft_task() -> dict:
    with session_scope() as s:
        return seed.seed_aircraft(s)


@flow(name="seed-reference")
def seed_reference() -> dict[str, dict[str, int]]:
    # Airports before tiers: the tier load reports codes missing from the airport table.
    airports = seed_airports_task()
    return {"airports": airports, "airlines": seed_airlines_task(), "tiers": seed_poll_tiers_task(),
            "aircraft_types": seed_aircraft_types_task(), "aircraft": seed_aircraft_task()}
