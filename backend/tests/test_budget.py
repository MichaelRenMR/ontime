from datetime import UTC, datetime, timedelta

from ontime.ingest.budget import Caps, can_afford
from ontime.repositories import ops

TODAY = datetime.now(UTC).date()
LAST_MONTH = TODAY.replace(day=1) - timedelta(days=1)


def afford(session, units=2, requests=1, **caps):
    base = dict(daily_units=1000, monthly_units=1000, monthly_requests=0) | caps
    return can_afford(session, "p", units=units, requests=requests, caps=Caps(**base))


def test_monthly_unit_cap_counts_the_whole_month_but_not_last_month(session):
    ops.charge_usage(session, "p", 90, calls=45, day=LAST_MONTH)  # must not count
    ops.charge_usage(session, "p", 96, calls=48, day=TODAY)
    assert ops.usage_month(session, "p") == (96, 48)
    assert afford(session, monthly_units=98)        # 96 + 2 fits exactly
    assert not afford(session, monthly_units=97)    # would cross by 1


def test_monthly_cap_can_be_hit_while_the_daily_cap_is_fine(session):
    ops.charge_usage(session, "p", 8, calls=4, day=TODAY.replace(day=1))
    if TODAY.day != 1:  # usage earlier in the month, none today
        assert not afford(session, monthly_units=9, daily_units=1000)
        assert afford(session, monthly_units=10, daily_units=1000)


def test_daily_cap(session):
    ops.charge_usage(session, "p", 8, calls=4, day=TODAY)
    assert afford(session, daily_units=10)
    assert not afford(session, daily_units=9)


def test_request_cap_is_optional_and_independent_of_units(session):
    ops.charge_usage(session, "p", 4, calls=1599, day=TODAY)  # few units, many requests
    assert afford(session, requests=1, monthly_requests=0)    # 0 = no request cap
    assert afford(session, requests=1, monthly_requests=1600)
    assert not afford(session, requests=2, monthly_requests=1600)


def test_other_providers_usage_is_ignored(session):
    ops.charge_usage(session, "other", 10_000, calls=5_000, day=TODAY)
    assert afford(session, monthly_units=10, daily_units=10)
