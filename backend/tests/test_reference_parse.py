from ontime.ingest.reference.openflights import parse_airlines
from ontime.ingest.reference.ourairports import parse_airports, parse_runways


def ap(**kw):
    base = {"id": "1", "type": "large_airport", "name": "Test", "latitude_deg": "40.6", "longitude_deg": "-73.8",
            "iso_country": "US", "municipality": "New York", "scheduled_service": "yes",
            "icao_code": "KJFK", "gps_code": "KJFK", "iata_code": "JFK"}
    return {**base, **kw}


def tz(lat, lon):
    return "America/New_York"


def test_keeps_scheduled_airports_with_iata_and_derives_tz():
    rows = parse_airports([ap()], tz)
    assert rows == [{
        "iata": "JFK", "icao": "KJFK", "name": "Test", "city": "New York", "country": "US",
        "lat": 40.6, "lon": -73.8, "tz": "America/New_York", "ourairports_id": 1,
    }]


def test_filters():
    rows = parse_airports([
        ap(id="1", iata_code=""),                                        # no IATA
        ap(id="2", iata_code="HEL1", type="heliport"),                   # excluded type
        ap(id="3", iata_code="SML", type="small_airport", scheduled_service="no"),
        ap(id="4", iata_code="SCH", type="small_airport", scheduled_service="yes"),  # small but scheduled
        ap(id="5", iata_code="OCN", latitude_deg="0", longitude_deg="0"),  # tz lookup below returns None
    ], lambda lat, lon: None if lat == 0 else "UTC")
    assert [r["iata"] for r in rows] == ["SCH"]


def test_duplicate_iata_keeps_largest():
    rows = parse_airports([
        ap(id="1", type="small_airport", name="Small", icao_code="AAAA", gps_code=""),
        ap(id="2", type="large_airport", name="Large", icao_code="BBBB", gps_code=""),
    ], tz)
    assert [(r["name"], r["ourairports_id"]) for r in rows] == [("Large", 2)]


def test_duplicate_icao_is_nulled_not_dropped():
    rows = parse_airports([
        ap(id="1", iata_code="AAA", icao_code="XXXX"),
        ap(id="2", iata_code="BBB", icao_code="XXXX", type="medium_airport"),
    ], tz)
    assert sorted((r["iata"], r["icao"]) for r in rows) == [("AAA", "XXXX"), ("BBB", None)]


def test_runways():
    rows = parse_runways([
        {"id": "555", "airport_ref": "1", "le_ident": "04L", "he_ident": "22R", "le_heading_degT": "31.5",
         "he_heading_degT": "211.5", "length_ft": "12079", "surface": "ASP", "closed": "0"},
        {"airport_ref": "", "le_ident": "X"},
    ])
    assert rows == [{
        "ourairports_id": 555, "airport_ourairports_id": 1, "le_ident": "04L", "he_ident": "22R", "le_heading": 31.5,
        "he_heading": 211.5, "length_ft": 12079, "surface": "ASP", "closed": False,
    }]


def test_airlines():
    text = "\n".join([
        '-1,"Unknown",\\N,"-","N/A","","","Y"',
        '1,"United Airlines",\\N,"UA","UAL","UNITED","United States","Y"',
        '2,"Defunct Air",\\N,"DD","DDD","","France","N"',
        '3,"No Codes",\\N,"-","N/A","","Spain","Y"',
        '4,"Icao Only",\\N,"","ICA","","\\N","Y"',
    ])
    assert parse_airlines(text) == [
        {"openflights_id": 1, "iata": "UA", "icao": "UAL", "name": "United Airlines", "country": "United States",
         "active": True},
        {"openflights_id": 4, "iata": None, "icao": "ICA", "name": "Icao Only", "country": None, "active": True},
    ]
