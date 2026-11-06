from __future__ import annotations

from datetime import UTC, datetime, timedelta

from prefect import flow, get_run_logger, task
from prefect.client.orchestration import get_client
from prefect.client.schemas.filters import FlowRunFilter, FlowRunFilterStartTime, FlowRunFilterState, FlowRunFilterStateType
from prefect.client.schemas.objects import StateType

from ontime.config import get_settings
from ontime.db import session_scope
from ontime.repositories import ops


@task(name="pause-failing-airports")
def pause_failing_airports_task() -> dict:
    logger = get_run_logger()
    with session_scope() as s:
        paused, outage = ops.pause_failing_airports(s, get_settings().airport_pause_after)
    if outage:
        logger.warning("most enabled airports are failing; suspecting a provider outage or bad key, pausing none")
    elif paused:
        logger.warning("paused airports after repeated failures: %s", ", ".join(paused))
    return {"paused": paused, "suspected_outage": outage}


@task(name="report-unmatched-codes")
def report_unmatched_codes_task() -> dict[str, list[str]]:
    with session_scope() as s:
        codes = ops.unmatched_codes(s)
    if any(codes.values()):
        get_run_logger().warning("codes missing from reference data: %s", codes)
    return codes


@task(name="prune-flow-runs")
def prune_flow_runs_task() -> int:
    """Delete finished Prefect runs past retention so the Prefect database doesn't grow forever."""
    cutoff = datetime.now(UTC) - timedelta(days=get_settings().flow_run_retention_days)
    finished = [StateType.COMPLETED, StateType.FAILED, StateType.CRASHED, StateType.CANCELLED]
    run_filter = FlowRunFilter(
        start_time=FlowRunFilterStartTime(before_=cutoff),
        state=FlowRunFilterState(type=FlowRunFilterStateType(any_=finished)),
    )
    deleted = 0
    with get_client(sync_client=True) as client:
        while runs := client.read_flow_runs(flow_run_filter=run_filter, limit=200):
            for run in runs:
                client.delete_flow_run(run.id)
                deleted += 1
    return deleted


@flow(name="maintenance")
def maintenance() -> dict:
    return {
        "pause": pause_failing_airports_task(),
        "unmatched": report_unmatched_codes_task(),
        "pruned_flow_runs": prune_flow_runs_task(),
    }
