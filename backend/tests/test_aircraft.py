import csv
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import select, text

from fakes import MOVE
from ontime.ingest.providers.aerodatabox import AeroDataBox
from ontime.ingest.reference import opensky, seed
from ontime.models import Aircraft, AircraftCategory, AircraftTypeAlias
from ontime.repositories import aircraft as repo
from ontime.repositories import ops
from ontime.repositories.movements import upsert_movements

DATA = Path(__file__).parents[1] / "data"


# --- curated data files ---------------------------------------------------------------------------

def read(name):
    with (DATA / name).open(newline="") as f:
        return list(csv.DictReader(f))


def test_curated_csvs_are_consistent():
    types = read("aircraft_types.csv")
    aliases = read("aircraft_type_aliases.csv")
    designators = [t["designator"] for t in types]
    families = {t["family"] for t in types}
    assert len(designators) == len(set(designators))
    assert {t["category"] for t in types} <= {c.value for c in AircraftCategory}
    keys = [(a["source"], repo.normalize_alias(a["alias"])) for a in aliases]
    assert len(keys) == len(set(keys)), "two aliases normalize to the same key"
    for a in aliases:
        assert not a["designator"] or a["designator"] in designators, a
        assert not a["family"] or a["family"] in families, a
        assert a["designator"] or a["family"] or a["note"].startswith("unmapped"), f"say why it's unmapped: {a}"


# --- normalization: Python and SQL must agree --------------------------------------------------------

@pytest.mark.parametrize("raw", [
    "Airbus A320 (Sharklets)", "airbus a320 (sharklets)", "Boeing 737-900 (winglets) ", "  Boeing   737 ",
    "Airbus A321NEO", "Boeing\t777", "78I",
])
def test_python_and_sql_normalize_identically(session, raw):
    assert session.scalar(text("SELECT normalize_alias(:s)"), {"s": raw}) == repo.normalize_alias(raw)


# --- seeding --------------------------------------------------------------------------------------

def test_seed_loads_the_real_files_and_is_idempotent(session):
    first = seed.seed_aircraft_types(session, DATA)
    assert first == seed.seed_aircraft_types(session, DATA)
    assert first["aircraft_types"] == len(read("aircraft_types.csv"))
    assert first["aliases"] == len(read("aircraft_type_aliases.csv"))


def test_alias_sync_drops_aliases_removed_from_the_file(session, tmp_path):
    (tmp_path / "aircraft_types.csv").write_text(
        "designator,manufacturer,name,family,category\nB738,Boeing,737-800,737,narrowbody\n")
    alias_file = tmp_path / "aircraft_type_aliases.csv"
    alias_file.write_text("source,alias,designator,family,note\nx,Boeing 737-800,B738,,\nx,Old,B738,,\n")
    seed.seed_aircraft_types(session, tmp_path)
    alias_file.write_text("source,alias,designator,family,note\nx,Boeing 737-800,B738,,\n")
    seed.seed_aircraft_types(session, tmp_path)
    assert session.scalars(select(AircraftTypeAlias.alias)).all() == ["Boeing 737-800"]


# --- OpenSky parsing (format copied from the 2025-08 snapshot header) ----------------------------------

HEADER = ("'icao24','timestamp','acars','adsb','built','categoryDescription','country','engines','firstFlightDate',"
          "'firstSeen','icaoAircraftClass','lineNumber','manufacturerIcao','manufacturerName','model','modes',"
          "'nextReg','notes','operator','operatorCallsign','operatorIata','operatorIcao','owner','prevReg',"
          "'regUntil','registered','registration','selCal','serialNumber','status','typecode','vdl'")


def osky(icao24, reg, typecode, model, built="2018-03-01"):
    return (f"'{icao24}','2025-01-01 00:00:00',0,0,{built},'',,'',,,L2J,'',AIRBUS,'Airbus',{model},0,'','',"
            f"'American Airlines','AMERICAN','aa','aal','','',,,{reg},'','6789','',{typecode},0")


def test_opensky_rows_are_normalized_and_filtered():
    lines = iter([
        HEADER,
        osky("A1B2C3", "n123aa", "a21n", "'A321-253NX'"),
        osky("000001", "", "AN2", "'Antonov 2'"),      # no registration: skipped
        osky("000002", "N1", "", "''"),                # no type information: skipped
    ])
    rows = list(opensky.parse_rows(lines, "2025-08"))
    assert len(rows) == 1
    r = rows[0]
    assert (r["icao24"], r["registration"], r["typecode"], r["model_code"]) == ("a1b2c3", "N123AA", "A21N", "A321-253NX")
    assert (r["operator_icao"], r["operator_iata"], r["built"].year, r["source_snapshot"]) == ("AAL", "AA", 2018, "2025-08")


# --- the provider parser keeps tails --------------------------------------------------------------

def test_parser_keeps_registration_and_icao24():
    entry = {"movement": {"airport": {"iata": "CLT"}, "scheduledTime": {"utc": "2026-10-12 00:04Z",
             "local": "2026-10-11 20:04-04:00"}}, "number": "AA 657", "status": "Arrived",
             "airline": {"iata": "AA"}, "aircraft": {"reg": " n302sa", "modeS": "A32851", "model": "Boeing 737-800"}}
    bare = {**entry, "number": "AA 658", "aircraft": {"model": "Boeing 737-800"}}
    with_tail, without = AeroDataBox().parse_board("JFK", {"arrivals": [entry, bare]})
    assert (with_tail.aircraft_reg, with_tail.aircraft_icao24) == ("N302SA", "a32851")
    assert (without.aircraft_reg, without.aircraft_icao24) == (None, None)


# --- resolution view ------------------------------------------------------------------------------

def test_movement_aircraft_resolution_paths(session, tmp_path):
    (tmp_path / "aircraft_types.csv").write_text(
        "designator,manufacturer,name,family,category\n"
        "A21N,Airbus,A321neo,A320,narrowbody\nB738,Boeing,737-800,737,narrowbody\n")
    (tmp_path / "aircraft_type_aliases.csv").write_text(
        "source,alias,designator,family,note\n"
        "fake,Boeing 737-800,B738,,\nfake,Boeing 737,,737,\nfake,Unknown,,,unmapped: no information\n")
    seed.seed_aircraft_types(session, tmp_path)
    session.add_all([
        Aircraft(icao24="a1b2c3", registration="N123AA", typecode="A21N", model_code="A321-253NX",
                 operator_icao="AAL", source_snapshot="2025-08"),
        Aircraft(icao24="ffff01", registration="N999ZZ", typecode="B738", source_snapshot="2025-08"),
    ])
    flights = {
        "1": dict(aircraft_icao24="a1b2c3", aircraft_type="Boeing 737"),  # tail wins over the type string
        "2": dict(aircraft_reg="N999ZZ", aircraft_type="Unknown"),        # matched by registration only
        "3": dict(aircraft_type="boeing 737-800 "),                       # type string, normalized
        "4": dict(aircraft_type="Boeing 737"),                            # family only
        "5": dict(aircraft_type="Unknown"),                               # deliberately unmapped
        "6": dict(aircraft_type="Never Seen"),                            # no alias at all
    }
    upsert_movements(session, [replace(MOVE, flight_number=n, **kw) for n, kw in flights.items()])
    session.flush()
    got = {r.flight_number: r for r in session.execute(text("""
        SELECT m.flight_number, v.designator, v.family, v.resolution, v.model_code, v.tail_operator_icao, v.category
        FROM movement_aircraft v JOIN movement m ON m.id = v.movement_id"""))}
    assert (got["1"].designator, got["1"].resolution, got["1"].model_code, got["1"].tail_operator_icao) == (
        "A21N", "tail", "A321-253NX", "AAL")
    assert (got["1"].family, got["1"].category) == ("A320", "narrowbody")
    assert (got["2"].designator, got["2"].resolution) == ("B738", "tail")
    assert (got["3"].designator, got["3"].resolution) == ("B738", "type_string")
    assert (got["4"].designator, got["4"].family, got["4"].resolution) == (None, "737", "family")
    assert got["5"].resolution is None and got["6"].resolution is None
    assert ops.unmatched_codes(session)["aircraft_types"] == ["Never Seen"]  # 'Unknown' is known-unmapped
