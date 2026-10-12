"""Flows run in-process against Prefect's temporary test server and the real test Postgres."""
import httpx
import pytest
from prefect.testing.utilities import prefect_test_harness
from sqlalchemy import select

from fakes import FakeProvider
from ontime.flows import poll as poll_module
from ontime.config import Settings
from ontime.flows import serve as serve_module
from ontime.flows.serve import build_deployments
from ontime.models import AirportPoll, IngestLog, Movement


@pytest.fixture(scope="module", autouse=True)
def prefect_server():
    with prefect_test_harness():
        yield


@pytest.fixture
def wired(session, tmp_path, monkeypatch):
    """Route the flow's provider and raw store to fakes, and make retries instant."""
    provider = FakeProvider()
    monkeypatch.setattr(poll_module, "get_provider", lambda name: provider)
    monkeypatch.setattr(poll_module, "get_settings",
                        lambda: type("S", (), {"raw_store_url": f"file://{tmp_path}"})())
    monkeypatch.setattr(poll_module, "poll_airport_task",
                        poll_module.poll_airport_task.with_options(retry_delay_seconds=[0, 0, 0]))
    session.add_all([AirportPoll(airport_iata="JFK", tier=1), AirportPoll(airport_iata="LHR", tier=1),
                     AirportPoll(airport_iata="SIN", tier=2)])
    session.commit()
    return provider


def test_poll_flow_polls_only_enabled_airports_of_the_tier(session, wired):
    session.get(AirportPoll, "LHR").enabled = False
    session.commit()
    assert poll_module.poll(tier=1) == {"ok": 1}
    assert [r.airport_iata for r in session.scalars(select(IngestLog))] == ["JFK"]
    assert session.scalars(select(Movement)).one().terminal == "7"


def test_5xx_is_retried_and_then_succeeds(session, wired):
    wired.fail_first = httpx.HTTPStatusError(
        "bad gateway", request=httpx.Request("GET", "http://x"), response=httpx.Response(503))
    session.get(AirportPoll, "LHR").enabled = False
    session.commit()
    assert poll_module.poll(tier=1) == {"ok": 1}
    assert wired.fetches == 2
    assert [r.status for r in session.scalars(select(IngestLog).order_by(IngestLog.id))] == ["http_error", "ok"]


def test_401_is_not_retried_and_the_flow_fails_visibly(session, wired):
    wired.fail = httpx.HTTPStatusError(
        "unauthorized", request=httpx.Request("GET", "http://x"), response=httpx.Response(401))
    with pytest.raises(RuntimeError, match="2/2 airports failed"):
        poll_module.poll(tier=1)
    assert wired.fetches == 2  # one attempt per airport, no retries
    assert session.get(AirportPoll, "JFK").consecutive_failures == 1


def test_429_is_retried_once_then_gives_up(session, wired):
    wired.fail = httpx.HTTPStatusError(
        "slow down", request=httpx.Request("GET", "http://x"), response=httpx.Response(429))
    session.get(AirportPoll, "LHR").enabled = False
    session.commit()
    with pytest.raises(RuntimeError, match="1/1 airports failed"):
        poll_module.poll(tier=1)
    assert wired.fetches == 2  # first attempt + exactly one retry, not 4


def test_deployments_are_registered_and_provider_ones_start_paused_without_a_key():
    by_name = {d.name: d for d in build_deployments()}
    assert set(by_name) == {"poll-tier-1", "poll-tier-2", "poll-tier-3", "settle", "seed-reference", "maintenance"}
    assert [s.schedule.cron for s in by_name["poll-tier-1"].schedules] == ["0 6,18 * * *"]
    assert by_name["poll-tier-1"].paused and by_name["settle"].paused
    assert not by_name["maintenance"].paused and not by_name["seed-reference"].paused


def test_deployments_are_active_once_a_key_is_configured(monkeypatch):
    monkeypatch.setattr(serve_module, "get_settings", lambda: Settings(adb_api_key="not-a-real-key"))
    assert not any(d.paused for d in build_deployments())
