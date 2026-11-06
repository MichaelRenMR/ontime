"""Seed orchestration: plain functions the CLI calls now and the Prefect flow wraps later."""
from __future__ import annotations

import csv
import logging
from pathlib import Path

from sqlalchemy.orm import Session

from ontime.config import get_settings
from ontime.ingest.reference import openflights, opensky, ourairports
from ontime.repositories import aircraft as aircraft_repo
from ontime.repositories import reference as repo

log = logging.getLogger(__name__)


def seed_airports(session: Session, tz_lookup: ourairports.TzLookup | None = None) -> dict[str, int]:
    tz_lookup = tz_lookup or ourairports.default_tz_lookup()
    airports = ourairports.parse_airports(ourairports.fetch_csv(ourairports.AIRPORTS_URL), tz_lookup)
    n_airports = repo.upsert_airports(session, airports)
    runways = ourairports.parse_runways(ourairports.fetch_csv(ourairports.RUNWAYS_URL))
    n_runways = repo.upsert_runways(session, runways)
    return {"airports": n_airports, "runways": n_runways}


def seed_airlines(session: Session) -> dict[str, int]:
    airlines = openflights.parse_airlines(openflights.fetch_text())
    return {"airlines": repo.upsert_airlines(session, airlines)}


def read_poll_tiers(path: Path) -> list[tuple[str, int]]:
    with path.open(newline="") as f:
        return [(r["iata"].strip(), int(r["tier"])) for r in csv.DictReader(f) if r.get("iata", "").strip()]


def seed_poll_tiers(session: Session, path: Path | None = None) -> dict[str, int]:
    path = path or Path(get_settings().poll_tiers_path)
    loaded, unknown = repo.load_poll_tiers(session, read_poll_tiers(path))
    if unknown:
        log.warning("poll tiers reference airports missing from the airport table", extra={"iata": unknown})
    return {"poll_tiers": loaded, "unknown_airports": len(unknown)}


def seed_aircraft_types(session: Session, data_dir: Path | None = None) -> dict[str, int]:
    """Load the curated designators and provider aliases (data/aircraft_types.csv, aircraft_type_aliases.csv)."""
    data_dir = data_dir or Path(get_settings().data_dir)
    with (data_dir / "aircraft_types.csv").open(newline="") as f:
        types = [dict(r) for r in csv.DictReader(f)]
    with (data_dir / "aircraft_type_aliases.csv").open(newline="") as f:
        aliases = [{k: (v or None) for k, v in r.items()} for r in csv.DictReader(f)]
    n_types = aircraft_repo.upsert_aircraft_types(session, types)
    n_aliases = 0
    for source in sorted({a["source"] for a in aliases}):
        rows = [{k: a[k] for k in ("alias", "designator", "family", "note")} for a in aliases if a["source"] == source]
        n_aliases += aircraft_repo.sync_aliases(session, source, rows)
    return {"aircraft_types": n_types, "aliases": n_aliases}


def seed_aircraft(session: Session, force: bool = False) -> dict[str, int | str]:
    """Import the newest OpenSky aircraft database snapshot (about 100 MB), unless it's already loaded."""
    url, snapshot = opensky.latest_snapshot()
    if not force and aircraft_repo.snapshot_loaded(session, snapshot):
        return {"snapshot": snapshot, "aircraft": 0, "skipped": "already loaded"}
    return {"snapshot": snapshot, "aircraft": aircraft_repo.upsert_aircraft(session, opensky.stream_rows(url, snapshot))}
