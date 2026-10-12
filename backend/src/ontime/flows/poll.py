"""Prefect wrappers for polling. All logic lives in ontime.ingest.service; this adds scheduling,
retries, per-airport task visibility in the UI, and a per-provider concurrency cap."""
from __future__ import annotations

from collections import Counter
from datetime import UTC, datetime, timedelta

import httpx
from prefect import flow, task
from prefect.concurrency.sync import concurrency
from prefect.futures import PrefectFuture
from prefect.runtime import flow_run

from ontime.config import TIERS, get_settings
from ontime.db import session_scope
from ontime.ingest import rawstore, service
from ontime.ingest.providers import get_provider
from ontime.repositories import ops


def _should_retry(task, task_run, state) -> bool:
    """Retry network errors and 5xx. A 429 is retried once (a burst limit may clear), then we stop:
    repeated 429s mean we are over a limit, and every further attempt may count against the quota.
    A 401/403/404 won't fix itself, so don't hammer the API."""
    try:
        state.result()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 429:
            return task_run.run_count < 2
        return exc.response.status_code >= 500
    except httpx.HTTPError:
        return True
    except Exception:
        return False
    return False


@task(name="poll-airport", retries=3, retry_delay_seconds=[10, 60, 300], retry_condition_fn=_should_retry)
def poll_airport_task(provider_name: str, iata: str, start_utc: datetime, end_utc: datetime) -> str:
    provider = get_provider(provider_name)
    store = rawstore.from_url(get_settings().raw_store_url)
    # Caps parallel provider calls. The limit is created at serve startup; without it this is a no-op.
    with concurrency(provider_name, occupy=1):
        result = service.poll_airport(provider, iata, start_utc, end_utc, store=store, flow_run_id=flow_run.id)
    return result.status


def collect(futures: dict[str, PrefectFuture]) -> Counter[str]:
    """Wait for per-airport tasks; count outcomes and raise at the end if any failed, so the flow
    run shows red in the UI while still having processed every other airport."""
    summary: Counter[str] = Counter()
    failed: list[str] = []
    for iata, future in futures.items():
        outcome = future.result(raise_on_failure=False)
        if isinstance(outcome, BaseException):
            summary["error"] += 1
            failed.append(iata)
        else:
            summary[outcome] += 1
    if failed:
        raise RuntimeError(f"{len(failed)}/{len(futures)} airports failed: {', '.join(failed)} ({dict(summary)})")
    return summary


@flow(name="poll")
def poll(tier: int, provider: str = "aerodatabox") -> dict[str, int]:
    t, now = TIERS[tier], datetime.now(UTC)
    start, end = now - timedelta(hours=t.back_h), now + timedelta(hours=t.ahead_h)
    with session_scope() as s:
        airports = ops.enabled_airports_in_tier(s, tier)
    futures = {iata: poll_airport_task.submit(provider, iata, start, end) for iata in airports}
    return dict(collect(futures))
