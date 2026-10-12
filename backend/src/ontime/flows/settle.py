from __future__ import annotations

from datetime import UTC, datetime

from prefect import flow

from ontime.db import session_scope
from ontime.flows.poll import collect, poll_airport_task
from ontime.ingest.windows import yesterday_local
from ontime.repositories import ops
from ontime.repositories.reference import get_airport_tz


@flow(name="settle")
def settle(provider: str = "aerodatabox") -> dict[str, int]:
    """Re-fetch each enabled airport's previous local day so flights that landed late carry their
    final actual times, terminals and statuses."""
    now = datetime.now(UTC)
    with session_scope() as s:
        targets = [(iata, get_airport_tz(s, iata)) for iata in ops.all_enabled_airports(s)]
    futures = {iata: poll_airport_task.submit(provider, iata, *yesterday_local(tz, now)) for iata, tz in targets}
    return dict(collect(futures))
