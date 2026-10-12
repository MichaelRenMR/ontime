"""Registers every deployment with the Prefect server and runs them. Entry point of the `flows` container:

    python -m ontime.flows.serve
"""
from __future__ import annotations

import logging
import time

from prefect import serve
from prefect.client.orchestration import get_client
from prefect.client.schemas.objects import ConcurrencyLimitConfig, ConcurrencyLimitStrategy
from prefect.deployments.runner import RunnerDeployment

from ontime.config import TIERS, get_settings
from ontime.flows.maintenance import maintenance
from ontime.flows.poll import poll
from ontime.flows.reference import seed_reference
from ontime.flows.settle import settle
from ontime.ingest.providers import REGISTRY
from ontime.logging import setup_logging

log = logging.getLogger(__name__)


def build_deployments() -> list[RunnerDeployment]:
    settings = get_settings()
    # Without a provider key every poll would just fail, so deployments that call the provider start paused.
    paused = not settings.adb_api_key
    if paused:
        log.warning("ADB_API_KEY is empty: poll and settle deployments are created paused")

    # One poll deployment per tier. CANCEL_NEW means a tier skips its tick if the previous run is
    # still going, instead of stacking runs behind a slow provider.
    no_overlap = ConcurrencyLimitConfig(limit=1, collision_strategy=ConcurrencyLimitStrategy.CANCEL_NEW)
    deployments = [
        poll.to_deployment(
            name=f"poll-tier-{tier}",
            parameters={"tier": tier},
            cron=t.cron,
            concurrency_limit=no_overlap,
            paused=paused,
        )
        for tier, t in TIERS.items()
    ]
    deployments += [
        settle.to_deployment(name="settle", cron="0 4 * * *", concurrency_limit=no_overlap, paused=paused),
        seed_reference.to_deployment(name="seed-reference", cron="0 5 1 * *", concurrency_limit=no_overlap),
        maintenance.to_deployment(name="maintenance", cron="30 4 * * *", concurrency_limit=no_overlap),
    ]
    return deployments


def ensure_concurrency_limits(retries: int = 30) -> None:
    """Create the per-provider global concurrency limits that poll tasks acquire. Retries while the
    Prefect server is still starting."""
    limit = get_settings().provider_max_concurrency
    for attempt in range(retries):
        try:
            with get_client(sync_client=True) as client:
                for name in REGISTRY:
                    client.upsert_global_concurrency_limit_by_name(name, limit)
            return
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(2)


def main() -> None:
    setup_logging()
    ensure_concurrency_limits()
    serve(*build_deployments())


if __name__ == "__main__":
    main()
