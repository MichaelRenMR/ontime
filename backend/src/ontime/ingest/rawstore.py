"""Where raw provider payloads live: a local directory in dev, any S3-compatible bucket in prod.

Payloads are stored as gzipped JSON lists (one list element per provider request), so a stored
object can be re-parsed later without calling the provider again.
"""
from __future__ import annotations

import gzip
import json
from datetime import datetime
from pathlib import Path
from typing import Protocol
from urllib.parse import urlparse


class RawStore(Protocol):
    def put(self, key: str, data: bytes) -> None: ...
    def get(self, key: str) -> bytes: ...


class LocalRawStore:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def put(self, key: str, data: bytes) -> None:
        path = self.root / key
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)

    def get(self, key: str) -> bytes:
        return (self.root / key).read_bytes()


class S3RawStore:
    """Any S3-compatible service. Credentials and a custom endpoint (R2, MinIO, GCS interop)
    come from the standard AWS_* environment variables that boto3 reads."""

    def __init__(self, bucket: str, prefix: str = "") -> None:
        import boto3

        self.bucket = bucket
        self.prefix = prefix.strip("/")
        self.client = boto3.client("s3")

    def _key(self, key: str) -> str:
        return f"{self.prefix}/{key}" if self.prefix else key

    def put(self, key: str, data: bytes) -> None:
        self.client.put_object(Bucket=self.bucket, Key=self._key(key), Body=data)

    def get(self, key: str) -> bytes:
        return self.client.get_object(Bucket=self.bucket, Key=self._key(key))["Body"].read()


def from_url(url: str) -> RawStore:
    """`file://./data/raw` (relative or absolute path) or `s3://bucket/optional/prefix`."""
    if url.startswith("file://"):
        return LocalRawStore(url.removeprefix("file://"))
    parsed = urlparse(url)
    if parsed.scheme == "s3" and parsed.netloc:
        return S3RawStore(parsed.netloc, parsed.path)
    raise ValueError(f"unsupported RAW_STORE_URL: {url!r}")


def raw_key(source: str, airport_iata: str, fetched_at: datetime) -> str:
    return f"{source}/{fetched_at:%Y/%m/%d}/{airport_iata}/{fetched_at:%Y%m%dT%H%M%S}.json.gz"


def pack(payloads: list[dict]) -> bytes:
    return gzip.compress(json.dumps(payloads, separators=(",", ":")).encode())


def unpack(data: bytes) -> list[dict]:
    return json.loads(gzip.decompress(data))
