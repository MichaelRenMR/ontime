from datetime import UTC, datetime

import pytest

from ontime.ingest import rawstore


def test_pack_roundtrip():
    payloads = [{"a": 1}, {"b": [1, 2]}]
    assert rawstore.unpack(rawstore.pack(payloads)) == payloads


def test_local_store_roundtrip(tmp_path):
    store = rawstore.from_url(f"file://{tmp_path}")
    key = rawstore.raw_key("aerodatabox", "JFK", datetime(2026, 10, 1, 12, 5, 9, tzinfo=UTC))
    assert key == "aerodatabox/2026/10/01/JFK/20261001T120509.json.gz"
    store.put(key, b"hello")
    assert store.get(key) == b"hello"


def test_relative_file_url():
    assert rawstore.from_url("file://./data/raw").root.as_posix() == "data/raw"


def test_unsupported_url():
    with pytest.raises(ValueError):
        rawstore.from_url("ftp://nope")
