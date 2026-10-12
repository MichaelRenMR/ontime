from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class Tier:
    hours: tuple[int, ...]  # UTC hours of the day at which the tier is polled
    minute: int             # minute within each hour; tiers are staggered to avoid request bursts
    back_h: int             # window start, hours before the poll
    ahead_h: int            # window end, hours after the poll

    @property
    def cron(self) -> str:
        return f"{self.minute} {','.join(str(h) for h in self.hours)} * * *"

    @property
    def polls_per_day(self) -> int:
        return len(self.hours)


# Cadence lives in code (reviewed in git); which airports are in which tier lives in the DB.
# Cost is per REQUEST, not per hour of window, and a provider request covers up to its max_window
# (11h for AeroDataBox), so every window here is exactly one request. test_quota_plan.py enforces that
# and that the projected monthly units fit the plan.
TIERS: dict[int, Tier] = {
    1: Tier(hours=(6, 18), minute=0, back_h=5, ahead_h=6),
    2: Tier(hours=(6, 18), minute=10, back_h=5, ahead_h=6),
    3: Tier(hours=(7, 19), minute=0, back_h=0, ahead_h=11),  # schedule only
}


class Settings(BaseSettings):
    # Runs from backend/ locally and from the repo root in compose, so look in both places.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://ontime:ontime@localhost:5432/ontime"
    raw_store_url: str = "file://./data/raw"  # or s3://bucket/prefix
    poll_tiers_path: str = "data/poll_tiers.csv"  # relative to backend/ (and to /app in the image)
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"

    # AeroDataBox direct API (https://aerodatabox.com). Only the key is normally needed. To use a marketplace
    # instead (RapidAPI, API.Market), override the URL and header settings, e.g. for RapidAPI:
    #   ADB_BASE_URL=https://aerodatabox.p.rapidapi.com  ADB_KEY_HEADER=X-RapidAPI-Key
    #   ADB_HOST_HEADER=X-RapidAPI-Host  ADB_HOST_VALUE=aerodatabox.p.rapidapi.com
    adb_api_key: str = ""
    adb_base_url: str = "https://api.aerodatabox.com"
    adb_key_header: str = "X-Api-Key"
    adb_host_header: str = ""  # marketplaces only
    adb_host_value: str = ""

    # Budget caps, checked before every provider call. Sized for AeroDataBox direct Starter (40,000
    # units/month) with a 10% margin. The request cap is off (0) because Starter is unit-metered; set it
    # for plans with a request limit (e.g. Basic: 400 units and 1600 requests per month).
    provider_daily_unit_cap: int = 1000
    provider_monthly_unit_cap: int = 36000
    provider_monthly_request_cap: int = 0
    # Failed polls (each Prefect retry counts) before maintenance pauses an airport.
    airport_pause_after: int = 20
    flow_run_retention_days: int = 14
    provider_max_concurrency: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
