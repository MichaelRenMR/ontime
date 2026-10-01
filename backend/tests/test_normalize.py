import pytest

from ontime.ingest.base import normalize_flight_number


@pytest.mark.parametrize(
    "raw, airline, expected",
    [
        ("UA 888", "UA", ("UA", "888")),
        ("UA888", None, ("UA", "888")),
        ("ua 0888", None, ("UA", "888")),
        ("UA 0888", "UA", ("UA", "888")),
        ("3K 123", "3K", ("3K", "123")),
        ("3K123", None, ("3K", "123")),
        ("U2 4567", "U2", ("U2", "4567")),
        ("BA 15A", "BA", ("BA", "15A")),
        ("UAL888", None, ("UAL", "888")),
    ],
)
def test_normalize(raw, airline, expected):
    assert normalize_flight_number(raw, airline) == expected


@pytest.mark.parametrize("raw", ["", "888", "UA", "UA 12345"])
def test_normalize_rejects_garbage(raw):
    with pytest.raises(ValueError):
        normalize_flight_number(raw)
