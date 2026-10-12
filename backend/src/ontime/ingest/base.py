"""Provider-agnostic ingestion types. Adapters translate vendor JSON into Movement."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal, Protocol

Side = Literal["dep", "arr"]

# Carrier: IATA (two chars, at least one a letter, e.g. 'UA', '3K', 'U2') or ICAO (three letters).
_FLIGHT_RE = re.compile(r"([A-Z][A-Z0-9]|[0-9][A-Z]|[A-Z]{3})0*(\d{1,4}[A-Z]?)")
_NUMBER_RE = re.compile(r"0*(\d{1,4}[A-Z]?)")


def normalize_flight_number(raw: str, airline_iata: str | None = None) -> tuple[str, str]:
    """Split a flight designator into (carrier, number) with providers' formatting differences removed.

    'UA 888', 'UA888', 'ua 0888' -> ('UA', '888'). If the carrier is already known, it is
    stripped from the front of `raw` first, which disambiguates codes like '3K123'.
    """
    s = re.sub(r"\s+", "", raw.upper())
    if airline_iata:
        carrier = airline_iata.upper()
        if s.startswith(carrier) and (m := _NUMBER_RE.fullmatch(s[len(carrier):])):
            return carrier, m.group(1)
    if m := _FLIGHT_RE.fullmatch(s):
        return m.group(1), m.group(2)
    raise ValueError(f"unparseable flight number: {raw!r}")


@dataclass(frozen=True)
class Movement:
    source: str
    airport_iata: str          # the airport this event happens at
    side: Side
    airline_iata: str
    flight_number: str         # normalized number only; see normalize_flight_number
    sched_date_local: date     # scheduled date in the airport's local time
    sched_utc: datetime
    flight_number_raw: str | None = None
    other_iata: str | None = None   # counterpart airport (dest for dep, origin for arr)
    estimated_utc: datetime | None = None
    actual_utc: datetime | None = None
    terminal: str | None = None
    gate: str | None = None
    runway: str | None = None
    status: str | None = None
    aircraft_type: str | None = None
    is_codeshare: bool = False


class Provider(Protocol):
    name: str
    max_window: timedelta  # longest span one board request may cover; longer windows are split

    def cost_units(self, kind: str) -> int:
        """Billing units one request of this kind consumes (for the daily budget)."""
        ...

    def fetch_board_payloads(
        self, airport_iata: str, start_utc: datetime, end_utc: datetime, tz: str | None
    ) -> list[dict]:
        """Fetch raw departures+arrivals JSON for [start_utc, end_utc). One payload per request.

        `tz` is the airport's IANA timezone when known; providers that need local-time windows
        use it and only call their own API for it when it is None.
        """
        ...

    def parse_board(self, airport_iata: str, payload: dict) -> list[Movement]:
        """Pure function from a raw payload to movements. Used live and when replaying stored payloads."""
        ...
