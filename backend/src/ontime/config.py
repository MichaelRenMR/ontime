from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


@dataclass(frozen=True)
class Tier:
    interval_min: int   # how often the tier is polled (the Prefect schedule reads this)
    back_h: int         # window start, hours before now
    ahead_h: int        # window end, hours after now


# Cadence lives in code (reviewed in git); which airports are in which tier lives in the DB.
TIERS: dict[int, Tier] = {
    1: Tier(interval_min=15, back_h=3, ahead_h=6),
    2: Tier(interval_min=60, back_h=3, ahead_h=12),
    3: Tier(interval_min=360, back_h=0, ahead_h=24),
}


class Settings(BaseSettings):
    # Runs from backend/ locally and from the repo root in compose, so look in both places.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), extra="ignore")

    database_url: str = "postgresql+psycopg://ontime:ontime@localhost:5432/ontime"
    raw_store_url: str = "file://./data/raw"  # or s3://bucket/prefix
    cors_origins: str = "http://localhost:3000"
    log_level: str = "INFO"

    # AeroDataBox. Defaults target RapidAPI; override for API.Market or a direct plan.
    adb_api_key: str = ""
    adb_base_url: str = "https://aerodatabox.p.rapidapi.com"
    adb_key_header: str = "X-RapidAPI-Key"
    adb_host_header: str = "X-RapidAPI-Host"
    adb_host_value: str = "aerodatabox.p.rapidapi.com"

    provider_daily_unit_cap: int = 5000
    provider_max_concurrency: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()
