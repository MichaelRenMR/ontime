"""The core unit of work: poll one airport. Plain functions; Prefect only wraps these (flows/).

poll_airport:  budget check -> fetch -> hash -> store raw -> parse -> upsert -> log, with the
raw payload saved before parsing so a parser bug never costs a re-fetch.
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections import Counter
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from math import ceil

import httpx
from sqlalchemy import select, update

from ontime.config import TIERS, get_settings
from ontime.db import session_scope
from ontime.ingest import budget, rawstore
from ontime.ingest.base import Provider
from ontime.models import IngestLog
from ontime.repositories import ops
from ontime.repositories.movements import upsert_movements
from ontime.repositories.reference import get_airport_tz

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PollResult:
    status: str  # ok | unchanged | parse_error | skipped_budget  (http errors raise)
    movements: int = 0
    raw_key: str | None = None


def _digest(payloads: list[dict]) -> str:
    return hashlib.sha256(json.dumps(payloads, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def poll_airport(
    provider: Provider,
    airport_iata: str,
    start_utc: datetime,
    end_utc: datetime,
    *,
    store: rawstore.RawStore,
    flow_run_id: str | None = None,
) -> PollResult:
    iata = airport_iata.upper()
    base = dict(source=provider.name, airport_iata=iata, window_start=start_utc, window_end=end_utc,
                flow_run_id=flow_run_id)

    with session_scope() as s:
        tz = get_airport_tz(s, iata)
        board_requests = max(1, ceil((end_utc - start_utc) / provider.max_window))
        requests = board_requests + (0 if tz else 1)  # an unknown timezone costs one extra lookup request
        cost = board_requests * provider.cost_units("board") + (0 if tz else provider.cost_units("airport"))
        if not budget.can_afford(s, provider.name, units=cost, requests=requests,
                                 caps=budget.Caps.from_settings(get_settings())):
            ops.add_ingest_log(s, status="skipped_budget", **base)
            return PollResult("skipped_budget")

    try:
        payloads = provider.fetch_board_payloads(iata, start_utc, end_utc, tz)
    except httpx.HTTPError as exc:
        # Assumption: a request the provider answered with 429/5xx may still count against the quota, so
        # charge one board request for it (conservative: a hard monthly cap should err toward stopping early).
        # Auth errors and transport failures never reach the metered path and are not charged.
        billed = isinstance(exc, httpx.HTTPStatusError) and (
            exc.response.status_code == 429 or exc.response.status_code >= 500)
        with session_scope() as s:
            if billed:
                ops.charge_usage(s, provider.name, provider.cost_units("board"), calls=1)
            ops.add_ingest_log(s, status="http_error", error=str(exc)[:500], **base)
            ops.record_poll_result(s, iata, "http_error", failed=True)
        raise

    digest = _digest(payloads)
    with session_scope() as s:
        ops.charge_usage(s, provider.name, cost, calls=requests)
        if ops.last_ok_hash(s, provider.name, iata) == digest:
            ops.add_ingest_log(s, status="unchanged", payload_sha256=digest, **base)
            ops.record_poll_result(s, iata, "unchanged", failed=False)
            return PollResult("unchanged")

    key = rawstore.raw_key(provider.name, iata, datetime.now(UTC))
    store.put(key, rawstore.pack(payloads))

    try:
        movements = [m for p in payloads for m in provider.parse_board(iata, p)]
    except Exception as exc:  # a parser bug must not lose data: the raw payload is saved, replay later
        log.exception("parse failed", extra={"airport": iata, "raw_key": key})
        with session_scope() as s:
            ops.add_ingest_log(s, status="parse_error", error=repr(exc)[:500], raw_key=key,
                               payload_sha256=digest, **base)
            ops.record_poll_result(s, iata, "parse_error", failed=False)
        return PollResult("parse_error", raw_key=key)

    with session_scope() as s:
        n = upsert_movements(s, movements)
        ops.add_ingest_log(s, status="ok", raw_key=key, payload_sha256=digest, movements_upserted=n, **base)
        ops.record_poll_result(s, iata, "ok", failed=False)
    return PollResult("ok", n, key)


def poll_tier(provider: Provider, tier: int, *, store: rawstore.RawStore) -> dict[str, int]:
    """Poll every enabled airport in a tier, one at a time; one airport failing doesn't stop the rest."""
    t, now = TIERS[tier], datetime.now(UTC)
    with session_scope() as s:
        airports = ops.enabled_airports_in_tier(s, tier)
    summary: Counter[str] = Counter()
    for iata in airports:
        try:
            result = poll_airport(provider, iata, now - timedelta(hours=t.back_h),
                                  now + timedelta(hours=t.ahead_h), store=store)
            summary[result.status] += 1
        except Exception:
            log.exception("poll failed", extra={"airport": iata})
            summary["error"] += 1
    return dict(summary)


def replay(
    provider: Provider, *, store: rawstore.RawStore, since: datetime, airport_iata: str | None = None
) -> dict[str, int]:
    """Re-parse stored raw payloads and upsert them, oldest first so the newest data wins.
    Rows that previously failed to parse are marked ok."""
    with session_scope() as s:
        q = (select(IngestLog.id, IngestLog.airport_iata, IngestLog.raw_key, IngestLog.status)
             .where(IngestLog.source == provider.name, IngestLog.raw_key.is_not(None),
                    IngestLog.status.in_(("ok", "parse_error")), IngestLog.fetched_at >= since)
             .order_by(IngestLog.id))
        if airport_iata:
            q = q.where(IngestLog.airport_iata == airport_iata.upper())
        rows = s.execute(q).all()

    replayed = movements = 0
    for log_id, iata, key, status in rows:
        parsed = [m for p in rawstore.unpack(store.get(key)) for m in provider.parse_board(iata, p)]
        with session_scope() as s:
            n = upsert_movements(s, parsed)
            if status == "parse_error":
                s.execute(update(IngestLog).where(IngestLog.id == log_id)
                          .values(status="ok", error=None, movements_upserted=n))
        replayed += 1
        movements += n
    return {"payloads": replayed, "movements": movements}
