from datetime import UTC, datetime, timedelta
from urllib.parse import urlparse

import httpx

from ontime.ingest.providers.aerodatabox import AeroDataBox


def capture(start, end):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(urlparse(str(request.url)).path.split("/")[-2:])
        return httpx.Response(200, json={"departures": [], "arrivals": []})

    p = AeroDataBox()
    p.client = httpx.Client(transport=httpx.MockTransport(handler))
    payloads = p.fetch_board_payloads("JFK", start, end, "America/New_York")
    return seen, payloads


def test_long_window_is_split_and_covers_everything():
    start = datetime(2026, 10, 1, 0, 0, tzinfo=UTC)
    seen, payloads = capture(start, start + timedelta(hours=24))
    assert len(seen) == len(payloads) == 3  # ceil(24h / 11h)
    assert seen[0][0] == "2026-09-30T20:00"          # 00:00 UTC is 20:00 EDT the day before
    assert seen[0][1] == seen[1][0] and seen[1][1] == seen[2][0]  # contiguous, no gaps


def test_spring_forward_day_never_exceeds_12_local_hours():
    # 2026-03-08: New York skips 02:00-03:00. Walk the day and check each request's wall-clock span.
    start = datetime(2026, 3, 8, 3, 0, tzinfo=UTC)  # 22:00 EST on the 7th
    seen, _ = capture(start, start + timedelta(hours=24))
    for frm, to in seen:
        span = datetime.fromisoformat(to) - datetime.fromisoformat(frm)
        assert span <= timedelta(hours=12), (frm, to)
