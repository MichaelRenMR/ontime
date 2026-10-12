"""Parser behavior pinned against REAL AeroDataBox airport-board entries (tests/fixtures, local only),
captured from a live JFK call and trimmed to one example of each interesting case."""
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from ontime.ingest.providers.aerodatabox import AeroDataBox

FIXTURE = Path(__file__).parent / "fixtures" / "aerodatabox_board_jfk.json"

# The fixture is real provider data and is gitignored, so it only exists where it was captured.
pytestmark = pytest.mark.skipif(not FIXTURE.exists(), reason="local-only fixture of real provider responses")


@pytest.fixture(scope="module")
def moves():
    payload = json.loads(FIXTURE.read_text())
    parsed = AeroDataBox().parse_board("JFK", payload)
    assert len(parsed) == len(payload["departures"]) + len(payload["arrivals"])  # nothing silently dropped
    return parsed


def find(moves, airline, number, side=None, nth=0):
    hits = [m for m in moves if (m.airline_iata, m.flight_number) == (airline, number) and side in (None, m.side)]
    return hits[nth]


def utc(*args):
    return datetime(*args, tzinfo=UTC)


def test_arrived_flight_maps_every_field(moves):
    m = find(moves, "AA", "657")
    assert (m.source, m.airport_iata, m.side) == ("aerodatabox", "JFK", "arr")
    assert m.other_iata == "CLT"            # movement.airport is the OTHER airport
    assert m.flight_number_raw == "AA 657"
    assert m.sched_utc == utc(2026, 10, 12, 0, 4)
    assert m.sched_date_local == date(2026, 10, 11)  # taken from the provider's local time, not the UTC date
    assert m.estimated_utc == utc(2026, 10, 12, 4, 20)
    assert m.actual_utc == utc(2026, 10, 12, 4, 12)
    assert (m.terminal, m.runway, m.gate) == ("8", "04R", None)
    assert (m.status, m.aircraft_type, m.is_codeshare) == ("Arrived", "Boeing 737-800", False)


def test_runway_time_of_an_expected_flight_is_a_prediction_not_an_actual(moves):
    # Live, status Expected, runwayTime 06:34Z was later than the moment the board was fetched.
    m = find(moves, "AA", "2278")
    assert m.status == "Expected"
    assert m.actual_utc is None
    assert m.estimated_utc == utc(2026, 10, 12, 6, 42)


def test_contradictory_provider_data_yields_only_an_estimate(moves):
    # Status Expected, but runwayTime (Oct 11 21:49Z) is hours BEFORE the revised time (Oct 12 05:37Z).
    m = find(moves, "DL", "532")
    assert m.actual_utc is None
    assert m.estimated_utc == utc(2026, 10, 12, 5, 37)


def test_departed_flight_has_an_actual(moves):
    m = find(moves, "B6", "308", side="dep")
    assert m.status == "Departed" and m.actual_utc is not None


def test_codeshare_is_flagged(moves):
    assert find(moves, "QX", "2626").is_codeshare
    assert find(moves, "QX", "2613").is_codeshare


def test_carrier_without_an_iata_code_comes_from_the_flight_number(moves):
    m = find(moves, "LVL", "285J")
    assert (m.airline_iata, m.flight_number, m.flight_number_raw) == ("LVL", "285J", "LVL 285J")


def test_statuses_are_kept_verbatim_including_unknown_and_uncertain(moves):
    assert find(moves, "AV", "7396").status == "Unknown"
    assert find(moves, "B6", "528").status == "CanceledUncertain"


def test_same_flight_number_twice_in_a_day_parses_to_two_movements(moves):
    # Seen live. The parser keeps both; the upsert collapses them by identity and logs a warning.
    first, second = find(moves, "2K", "7393", nth=0), find(moves, "2K", "7393", nth=1)
    assert first.sched_utc != second.sched_utc
    assert first.sched_date_local == second.sched_date_local
