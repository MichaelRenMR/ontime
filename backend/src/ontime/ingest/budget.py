"""Daily provider unit cap. Usage is recorded in api_usage by service.poll_airport."""
from __future__ import annotations

from sqlalchemy.orm import Session

from ontime.repositories.ops import usage_today


def can_afford(session: Session, provider: str, cost_units: int, daily_cap: int) -> bool:
    return usage_today(session, provider) + cost_units <= daily_cap
