from datetime import timedelta

import httpx
import pytest
from sqlalchemy import func, select

from ontime.config import Settings
from ontime.ingest import rawstore, service
from fakes import END, START, FakeProvider
from ontime.models import ApiUsage, AirportPoll, IngestLog
from ontime.models import Movement as MovementRow
from ontime.repositories import ops
from ontime.repositories.reference import upsert_airports

@pytest.fixture
def store(tmp_path):
    return rawstore.LocalRawStore(tmp_path)


@pytest.fixture
def jfk(session):
    upsert_airports(session, [{"iata": "JFK", "icao": "KJFK", "name": "JFK", "city": None, "country": "US",
                               "lat": 40.6, "lon": -73.8, "tz": "America/New_York", "ourairports_id": 1}])
    session.add(AirportPoll(airport_iata="JFK", tier=1))
    session.commit()


def logs(session):
    return [r.status for r in session.scalars(select(IngestLog).order_by(IngestLog.id))]


def test_ok_path_stores_raw_upserts_logs_and_charges(session, jfk, store, tmp_path):
    p = FakeProvider()
    result = service.poll_airport(p, "jfk", START, END, store=store)

    assert (result.status, result.movements) == ("ok", 1)
    assert p.seen_tz == ["America/New_York"]  # timezone came from the airport table, not the provider
    assert rawstore.unpack(store.get(result.raw_key)) == [p.board]
    assert session.scalar(select(func.count()).select_from(MovementRow)) == 1
    assert logs(session) == ["ok"]
    usage = session.scalars(select(ApiUsage)).one()
    assert (usage.calls, usage.units) == (1, 2)
    poll = session.get(AirportPoll, "JFK")
    assert (poll.last_status, poll.consecutive_failures) == ("ok", 0) and poll.last_polled_at


def test_identical_payload_is_unchanged_and_not_stored_twice(session, jfk, store, tmp_path):
    p = FakeProvider()
    service.poll_airport(p, "JFK", START, END, store=store)
    second = service.poll_airport(p, "JFK", START, END, store=store)
    assert second.status == "unchanged"
    assert logs(session) == ["ok", "unchanged"]
    assert len(list(tmp_path.rglob("*.json.gz"))) == 1


def test_changed_payload_is_processed(session, jfk, store):
    service.poll_airport(FakeProvider(), "JFK", START, END, store=store)
    r = service.poll_airport(FakeProvider(board={"flights": [1, 2]}), "JFK", START, END, store=store)
    assert r.status == "ok"


def test_budget_exhausted_skips_without_calling_provider(session, jfk, store, monkeypatch):
    monkeypatch.setattr(service, "get_settings", lambda: Settings(provider_daily_unit_cap=3))
    ops.charge_usage(session, "fake", 2)
    session.commit()
    p = FakeProvider()
    assert service.poll_airport(p, "JFK", START, END, store=store).status == "skipped_budget"
    assert p.fetches == 0 and logs(session) == ["skipped_budget"]


def test_unknown_airport_charges_for_the_timezone_lookup(session, store):
    p = FakeProvider()
    service.poll_airport(p, "XXX", START, END, store=store)
    assert p.seen_tz == [None]
    usage = session.scalars(select(ApiUsage)).one()
    assert (usage.units, usage.calls) == (3, 2)  # board 2 units + airport lookup 1 unit; 2 requests


def test_http_error_is_logged_counted_and_raised(session, jfk, store):
    p = FakeProvider(fail=httpx.ConnectError("boom"))
    with pytest.raises(httpx.ConnectError):
        service.poll_airport(p, "JFK", START, END, store=store)
    assert logs(session) == ["http_error"]
    assert session.get(AirportPoll, "JFK").consecutive_failures == 1
    assert session.scalar(select(func.count()).select_from(ApiUsage)) == 0  # failed calls aren't charged


def test_parse_error_keeps_raw_and_replay_recovers(session, jfk, store):
    bad = FakeProvider(parse_error=True)
    r = service.poll_airport(bad, "JFK", START, END, store=store)
    assert r.status == "parse_error" and r.raw_key
    assert session.scalar(select(func.count()).select_from(MovementRow)) == 0
    assert session.get(AirportPoll, "JFK").consecutive_failures == 0  # a parser bug isn't the airport's fault

    out = service.replay(FakeProvider(), store=store, since=START - timedelta(days=365 * 10))
    assert out == {"payloads": 1, "movements": 1}
    assert session.scalar(select(func.count()).select_from(MovementRow)) == 1
    assert logs(session) == ["ok"]


def test_poll_tier_continues_past_a_failing_airport(session, jfk, store):
    session.add(AirportPoll(airport_iata="LHR", tier=1))
    session.commit()

    class Flaky(FakeProvider):
        def fetch_board_payloads(self, airport_iata, *a, **k):
            if airport_iata == "JFK":
                raise httpx.ConnectError("boom")
            return super().fetch_board_payloads(airport_iata, *a, **k)

    summary = service.poll_tier(Flaky(), 1, store=store)
    assert summary == {"error": 1, "ok": 1}



def status_error(code):
    return httpx.HTTPStatusError("x", request=httpx.Request("GET", "http://x"), response=httpx.Response(code))


@pytest.mark.parametrize("error, charged", [
    (status_error(503), True),
    (status_error(429), True),
    (status_error(401), False),
    (httpx.ConnectError("boom"), False),
])
def test_only_calls_the_provider_answered_with_429_or_5xx_are_charged_on_failure(session, jfk, store, error, charged):
    with pytest.raises(httpx.HTTPError):
        service.poll_airport(FakeProvider(fail=error), "JFK", START, END, store=store)
    usage = session.scalars(select(ApiUsage)).all()
    assert [(u.calls, u.units) for u in usage] == ([(1, 2)] if charged else [])
