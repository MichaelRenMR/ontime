"""AeroDataBox adapter.

Field mapping is written from AeroDataBox's documented airport FIDS response and has NOT yet
been checked against live data. After the first real call, inspect a stored payload and
confirm: which airport `movement.airport` refers to, and how terminal/runway/revisedTime/
runwayTime are populated. Then pin it with a fixture test.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import httpx

from ontime.config import get_settings
from ontime.ingest.base import Movement, normalize_flight_number

log = logging.getLogger(__name__)

# AeroDataBox caps the FIDS window at 12h of LOCAL time. We window in UTC, and on a spring-forward
# day 12h of UTC is 13h of wall clock, so use 11h: the local span is then never more than 12h.
MAX_WINDOW = timedelta(hours=11)

# runwayTime is the actual takeoff/landing time only once it has happened; before that the API fills it
# with a prediction (seen live: status Expected with a runwayTime in the future). So it is trusted as
# "actual" only for these statuses. Gate (off/in-block) times are not provided.
_HAPPENED = {
    "dep": {"Departed", "EnRoute", "Approaching", "Arrived", "Diverted"},
    "arr": {"Arrived"},
}

# Billing units per request. PLACEHOLDERS: verify against your plan's pricing page.
COST = {"board": 2, "airport": 1}


def _utc(ts: dict | None) -> datetime | None:
    if not ts or not ts.get("utc"):
        return None
    return datetime.fromisoformat(ts["utc"].replace("Z", "+00:00")).astimezone(timezone.utc)


def _local_date(ts: dict) -> date | None:
    local = ts.get("local")
    return date.fromisoformat(local[:10]) if local else None


class AeroDataBox:
    name = "aerodatabox"
    max_window = MAX_WINDOW

    def __init__(self) -> None:
        s = get_settings()
        self.base_url = s.adb_base_url.rstrip("/")
        headers = {s.adb_key_header: s.adb_api_key}
        if s.adb_host_header and s.adb_host_value:
            headers[s.adb_host_header] = s.adb_host_value
        self.client = httpx.Client(headers=headers, timeout=30)

    def cost_units(self, kind: str) -> int:
        return COST[kind]

    def _airport_tz(self, airport_iata: str) -> str:
        r = self.client.get(f"{self.base_url}/airports/iata/{airport_iata}")
        r.raise_for_status()
        return r.json()["timeZone"]

    def fetch_board_payloads(
        self, airport_iata: str, start_utc: datetime, end_utc: datetime, tz: str | None
    ) -> list[dict]:
        zone = ZoneInfo(tz or self._airport_tz(airport_iata))
        payloads: list[dict] = []
        cur = start_utc
        while cur < end_utc:
            nxt = min(cur + MAX_WINDOW, end_utc)
            frm = cur.astimezone(zone).strftime("%Y-%m-%dT%H:%M")
            to = nxt.astimezone(zone).strftime("%Y-%m-%dT%H:%M")
            r = self.client.get(
                f"{self.base_url}/flights/airports/iata/{airport_iata}/{frm}/{to}",
                params={"direction": "Both", "withCancelled": "true", "withCodeshared": "true",
                        "withCargo": "false", "withPrivate": "false", "withLocation": "false"},
            )
            r.raise_for_status()
            payloads.append(r.json())
            cur = nxt
        return payloads

    def parse_board(self, airport_iata: str, payload: dict) -> list[Movement]:
        out: list[Movement] = []
        for side, key in (("dep", "departures"), ("arr", "arrivals")):
            for f in payload.get(key, []):
                m = f.get("movement") or {}
                sched_ts = m.get("scheduledTime") or {}
                sched = _utc(sched_ts)
                raw_number = (f.get("number") or "").strip()
                # Some carriers have no IATA code ('LVL 285J'); the carrier then comes from the flight number.
                airline = ((f.get("airline") or {}).get("iata") or "").strip().upper() or None
                if not (sched and raw_number):
                    continue
                try:
                    carrier, number = normalize_flight_number(raw_number, airline)
                except ValueError:
                    log.warning("skipping unparseable flight number", extra={"raw": raw_number})
                    continue
                status = f.get("status")
                out.append(Movement(
                    source=self.name,
                    airport_iata=airport_iata,
                    side=side,
                    airline_iata=carrier,
                    flight_number=number,
                    flight_number_raw=raw_number,
                    sched_date_local=_local_date(sched_ts) or sched.date(),
                    sched_utc=sched,
                    other_iata=(m.get("airport") or {}).get("iata"),
                    estimated_utc=_utc(m.get("revisedTime")),
                    actual_utc=_utc(m.get("runwayTime")) if status in _HAPPENED[side] else None,
                    terminal=m.get("terminal"),
                    gate=m.get("gate"),
                    runway=m.get("runway"),
                    status=status,
                    aircraft_type=(f.get("aircraft") or {}).get("model"),
                    is_codeshare=(f.get("codeshareStatus") == "IsCodeshared"),
                ))
        return out
