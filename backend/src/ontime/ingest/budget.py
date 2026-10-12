"""Provider quota guard: daily and monthly unit caps and an optional monthly request cap.

Usage is recorded in api_usage by service.poll_airport. The caps are checked BEFORE a call, so a
call that would cross a cap is skipped (logged as skipped_budget) instead of being made.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from math import ceil

from sqlalchemy.orm import Session

from ontime.config import Settings, Tier
from ontime.repositories.ops import usage_month, usage_today


@dataclass(frozen=True)
class Caps:
    daily_units: int
    monthly_units: int
    monthly_requests: int = 0  # 0 = no request cap

    @classmethod
    def from_settings(cls, s: Settings) -> Caps:
        return cls(s.provider_daily_unit_cap, s.provider_monthly_unit_cap, s.provider_monthly_request_cap)


def can_afford(session: Session, provider: str, *, units: int, requests: int, caps: Caps) -> bool:
    if usage_today(session, provider) + units > caps.daily_units:
        return False
    month_units, month_requests = usage_month(session, provider)
    if month_units + units > caps.monthly_units:
        return False
    return not (caps.monthly_requests and month_requests + requests > caps.monthly_requests)


def projected_monthly_units(
    tiers: dict[int, Tier],
    airports_per_tier: dict[int, int],
    *,
    units_per_request: int,
    max_window: timedelta,
    settle_airports: int,
    days: int = 30,
) -> int:
    """Units the schedule would consume in `days` days, assuming no retries and known timezones."""
    requests_per_day = sum(
        n * tiers[tier].polls_per_day * ceil(timedelta(hours=tiers[tier].back_h + tiers[tier].ahead_h) / max_window)
        for tier, n in airports_per_tier.items()
    )
    requests_per_day += settle_airports * ceil(timedelta(hours=24) / max_window)  # one 24h window a day
    return requests_per_day * units_per_request * days
