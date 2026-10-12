from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo


def yesterday_local(tz_name: str | None, now: datetime) -> tuple[datetime, datetime]:
    """[start, end) of the previous calendar day at an airport, as UTC instants.

    Built from local midnights, so on a DST day the span is 23 or 25 hours, not 24.
    Airports with no known timezone fall back to the UTC day.
    """
    zone = ZoneInfo(tz_name or "UTC")
    today = now.astimezone(zone).date()
    start = datetime.combine(today - timedelta(days=1), time.min, tzinfo=zone)
    end = datetime.combine(today, time.min, tzinfo=zone)
    return start.astimezone(UTC), end.astimezone(UTC)
