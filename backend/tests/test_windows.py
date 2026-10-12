from datetime import UTC, datetime, timedelta

from ontime.ingest.windows import yesterday_local


def test_yesterday_is_the_previous_local_day():
    # 04:00 UTC on Oct 2 is 00:00 EDT on Oct 2, so "yesterday" in New York is all of Oct 1 (04:00Z-04:00Z).
    start, end = yesterday_local("America/New_York", datetime(2026, 10, 2, 4, 0, tzinfo=UTC))
    assert (start, end) == (datetime(2026, 10, 1, 4, 0, tzinfo=UTC), datetime(2026, 10, 2, 4, 0, tzinfo=UTC))


def test_dst_days_are_23_or_25_hours():
    spring = yesterday_local("America/New_York", datetime(2026, 3, 9, 12, 0, tzinfo=UTC))  # Mar 8: clocks skip an hour
    fall = yesterday_local("America/New_York", datetime(2026, 11, 2, 12, 0, tzinfo=UTC))   # Nov 1: clocks repeat one
    assert spring[1] - spring[0] == timedelta(hours=23)
    assert fall[1] - fall[0] == timedelta(hours=25)


def test_unknown_timezone_falls_back_to_utc_day():
    start, end = yesterday_local(None, datetime(2026, 10, 2, 9, 30, tzinfo=UTC))
    assert (start, end) == (datetime(2026, 10, 1, tzinfo=UTC), datetime(2026, 10, 2, tzinfo=UTC))
