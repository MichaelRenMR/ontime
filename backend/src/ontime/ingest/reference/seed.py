"""Seed orchestration: plain functions the CLI calls now and the Prefect flow wraps later."""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from ontime.config import get_settings
from ontime.ingest.reference import openflights, ourairports
from ontime.repositories import reference as repo

log = logging.getLogger(__name__)


def seed_airports(session: Session, tz_lookup: ourairports.TzLookup | None = None) -> dict[str, int]:
    tz_lookup = tz_lookup or ourairports.default_tz_lookup()
    airports = ourairports.parse_airports(ourairports.fetch_csv(ourairports.AIRPORTS_URL), tz_lookup)
    n_airports = repo.upsert_airports(session, airports)
    runways = ourairports.parse_runways(ourairports.fetch_csv(ourairports.RUNWAYS_URL))
    n_runways = repo.replace_runways(session, runways)
    return {"airports": n_airports, "runways": n_runways}


def seed_airlines(session: Session) -> dict[str, int]:
    airlines = openflights.parse_airlines(openflights.fetch_text())
    return {"airlines": repo.replace_airlines(session, airlines)}


def read_poll_tiers(path: Path) -> list[tuple[str, int]]:
    with path.open(newline="") as f:
        return [(r["iata"].strip(), int(r["tier"])) for r in csv.DictReader(f) if r.get("iata", "").strip()]


def seed_poll_tiers(session: Session, path: Path | None = None) -> dict[str, int]:
    path = path or Path(get_settings().poll_tiers_path)
    loaded, unknown = repo.load_poll_tiers(session, read_poll_tiers(path))
    if unknown:
        log.warning("poll tiers reference airports missing from the airport table", extra={"iata": unknown})
    return {"poll_tiers": loaded, "unknown_airports": len(unknown)}
