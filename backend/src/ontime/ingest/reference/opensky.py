"""OpenSky Network aircraft database -> aircraft rows. Parsing only; no DB access.

The database is published irregularly as CSV snapshots in OpenSky's public S3 bucket. OpenSky
describes it as unlicensed and not kept current: confirm terms before commercial use, and expect
recently delivered airframes to be missing (flights then fall back to the provider's type string).
"""
from __future__ import annotations

import csv
import re
from collections.abc import Iterator
from datetime import date

import httpx

BUCKET = "https://s3.opensky-network.org/data-samples"
_SNAPSHOT = re.compile(r"<Key>(metadata/aircraft-database-complete-(\d{4}-\d{2})\.csv)</Key>")


def latest_snapshot() -> tuple[str, str]:
    """(url, 'YYYY-MM') of the newest complete snapshot in the bucket."""
    r = httpx.get(BUCKET, params={"list-type": "2", "prefix": "metadata/aircraft-database-complete-"}, timeout=60)
    r.raise_for_status()
    found = sorted(_SNAPSHOT.findall(r.text), key=lambda m: m[1])
    if not found:
        raise RuntimeError("no aircraft-database-complete snapshot found in the OpenSky bucket")
    key, snapshot = found[-1]
    return f"{BUCKET}/{key}", snapshot


def _clean(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


def _date(v: str | None) -> date | None:
    try:
        return date.fromisoformat(v.strip()[:10]) if v and v.strip() else None
    except ValueError:
        return None


def parse_rows(lines: Iterator[str], snapshot: str) -> Iterator[dict]:
    """Rows of the snapshot CSV (single-quoted fields) -> aircraft rows. Skips airframes with no
    registration or no type information, which are useless for resolving flights."""
    reader = csv.DictReader(lines, quotechar="'")
    for r in reader:
        icao24 = (_clean(r.get("icao24")) or "").lower()
        registration = (_clean(r.get("registration")) or "").upper() or None
        typecode = (_clean(r.get("typecode")) or "").upper() or None
        model = _clean(r.get("model"))
        if not (icao24 and registration and (typecode or model)):
            continue
        yield {
            "icao24": icao24,
            "registration": registration,
            "typecode": typecode,
            "model_code": model,
            "manufacturer": _clean(r.get("manufacturerName")),
            "operator_name": _clean(r.get("operator")),
            "operator_icao": (_clean(r.get("operatorIcao")) or "").upper() or None,
            "operator_iata": (_clean(r.get("operatorIata")) or "").upper() or None,
            "serial_number": _clean(r.get("serialNumber")),
            "built": _date(r.get("built")),
            "source_snapshot": snapshot,
        }


def stream_rows(url: str, snapshot: str) -> Iterator[dict]:
    with httpx.stream("GET", url, timeout=httpx.Timeout(60, read=300), follow_redirects=True) as r:
        r.raise_for_status()
        yield from parse_rows(r.iter_lines(), snapshot)
