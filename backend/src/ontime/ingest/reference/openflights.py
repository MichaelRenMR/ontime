"""OpenFlights airlines.dat -> airline rows. Pure parsing; no DB access.

The dataset is community-maintained and its last large update is old, so treat it as a starting
point. Fields: id, name, alias, iata, icao, callsign, country, active (Y/N); no header; \\N = null.
"""
from __future__ import annotations

import csv
import io

import httpx

AIRLINES_URL = "https://raw.githubusercontent.com/jpatokal/openflights/master/data/airlines.dat"


def fetch_text(url: str = AIRLINES_URL) -> str:
    r = httpx.get(url, follow_redirects=True, timeout=60)
    r.raise_for_status()
    return r.text


def _code(v: str, length: int) -> str | None:
    v = v.strip().upper()
    return v if len(v) == length and v.isalnum() else None


def parse_airlines(text: str) -> list[dict]:
    out = []
    for r in csv.reader(io.StringIO(text)):
        if len(r) < 8 or r[7] != "Y" or r[0] == "-1":
            continue
        name = r[1].strip()
        iata, icao = _code(r[3], 2), _code(r[4], 3)
        if not name or not (iata or icao):
            continue
        country = r[6].strip()
        out.append({
            "openflights_id": int(r[0]),
            "iata": iata,
            "icao": icao,
            "name": name,
            "country": None if country in ("", "\\N") else country,
            "active": True,
        })
    return out
