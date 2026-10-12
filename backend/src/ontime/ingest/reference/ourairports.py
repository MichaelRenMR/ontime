"""OurAirports (public domain) -> airport and runway rows. Pure parsing; no DB access."""
from __future__ import annotations

import csv
import io
import logging
from collections.abc import Callable, Iterable

import httpx

log = logging.getLogger(__name__)

AIRPORTS_URL = "https://davidmegginson.github.io/ourairports-data/airports.csv"
RUNWAYS_URL = "https://davidmegginson.github.io/ourairports-data/runways.csv"

_EXCLUDED_TYPES = {"closed", "heliport", "seaplane_base", "balloonport"}
_RANK = {"large_airport": 0, "medium_airport": 1}

TzLookup = Callable[[float, float], str | None]


def fetch_csv(url: str) -> list[dict[str, str]]:
    r = httpx.get(url, follow_redirects=True, timeout=120)
    r.raise_for_status()
    return list(csv.DictReader(io.StringIO(r.text)))


def default_tz_lookup() -> TzLookup:
    from timezonefinder import TimezoneFinder

    tf = TimezoneFinder()
    return lambda lat, lon: tf.timezone_at(lat=lat, lng=lon)


def _clean(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


def _float(v: str | None) -> float | None:
    try:
        return float(v) if v else None
    except ValueError:
        return None


def parse_airports(rows: Iterable[dict[str, str]], tz_lookup: TzLookup) -> list[dict]:
    """Keep airports with an IATA code that are large/medium or have scheduled service.

    OurAirports has no timezone column, so it is derived from lat/lon. Airports whose timezone
    can't be determined are skipped (airport.tz is required). Duplicate IATA/ICAO codes keep the
    largest airport; a duplicate ICAO is nulled rather than dropped.
    """
    best: dict[str, tuple[int, dict]] = {}
    skipped_tz = 0
    for r in rows:
        iata = (_clean(r.get("iata_code")) or "").upper()
        kind = r.get("type", "")
        if not iata or kind in _EXCLUDED_TYPES:
            continue
        if kind not in _RANK and r.get("scheduled_service") != "yes":
            continue
        lat, lon = _float(r.get("latitude_deg")), _float(r.get("longitude_deg"))
        tz = tz_lookup(lat, lon) if lat is not None and lon is not None else None
        if not tz:
            skipped_tz += 1
            continue
        rank = _RANK.get(kind, 2)
        if iata in best and best[iata][0] <= rank:
            continue
        best[iata] = (rank, {
            "iata": iata,
            "icao": _clean(r.get("icao_code")) or _clean(r.get("gps_code")),
            "name": r["name"],
            "city": _clean(r.get("municipality")),
            "country": _clean(r.get("iso_country")),
            "lat": lat,
            "lon": lon,
            "tz": tz,
            "ourairports_id": int(r["id"]),
        })
    if skipped_tz:
        log.warning("airports skipped: no timezone found", extra={"count": skipped_tz})

    seen_icao: set[str] = set()
    out = []
    for _, row in sorted(best.values(), key=lambda t: t[0]):
        if row["icao"] in seen_icao:
            row["icao"] = None
        elif row["icao"]:
            seen_icao.add(row["icao"])
        out.append(row)
    return out


def parse_runways(rows: Iterable[dict[str, str]]) -> list[dict]:
    """Runway rows keyed by `ourairports_id` of their airport; the repository maps that to airport.id."""
    out = []
    for r in rows:
        try:
            airport_ref = int(r["airport_ref"])
        except (KeyError, ValueError):
            continue
        out.append({
            "ourairports_id": airport_ref,
            "le_ident": _clean(r.get("le_ident")),
            "he_ident": _clean(r.get("he_ident")),
            "le_heading": _float(r.get("le_heading_degT")),
            "he_heading": _float(r.get("he_heading_degT")),
            "length_ft": int(f) if (f := _float(r.get("length_ft"))) is not None else None,
            "surface": _clean(r.get("surface")),
            "closed": r.get("closed") == "1",
        })
    return out
