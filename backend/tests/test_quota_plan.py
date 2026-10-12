"""Guards the schedule against the plan: any change to TIERS or poll_tiers.csv that would blow the
monthly quota fails here, before it can burn real units."""
from collections import Counter
from datetime import timedelta
from pathlib import Path

from ontime.config import TIERS, Settings
from ontime.ingest.budget import projected_monthly_units
from ontime.ingest.providers.aerodatabox import COST, MAX_WINDOW
from ontime.ingest.reference.seed import read_poll_tiers

CSV = Path(__file__).parents[1] / "data" / "poll_tiers.csv"


def project(**override):
    counts = Counter(tier for _, tier in read_poll_tiers(CSV))
    return projected_monthly_units(
        TIERS, dict(counts), units_per_request=COST["board"], max_window=MAX_WINDOW,
        settle_airports=sum(counts.values()), **override)


def test_every_poll_window_is_a_single_request():
    for tier, t in TIERS.items():
        assert timedelta(hours=t.back_h + t.ahead_h) <= MAX_WINDOW, f"tier {tier} needs more than one request"


def test_tiers_are_staggered_so_polls_do_not_burst_together():
    starts = [(h, t.minute) for t in TIERS.values() for h in t.hours]
    assert len(starts) == len(set(starts))


def test_projected_usage_is_twice_daily_polls_plus_settle():
    # 10 tier-1 + 20 tier-2 airports x 2 polls x 1 request x 2 units x 30 days = 3,600
    # settle: 30 airports x 3 requests (24h window) x 2 units x 30 days = 5,400
    assert project() == 9_000


def test_projection_fits_the_default_monthly_cap_with_room_for_retries():
    cap = Settings.model_fields["provider_monthly_unit_cap"].default
    assert project() <= cap * 0.5
