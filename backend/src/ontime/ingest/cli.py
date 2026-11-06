"""Local entry point for ingestion jobs; no Prefect server needed.

  ontime-ingest seed [all|airports|airlines|tiers|aircraft-types|aircraft]
  ontime-ingest board --airport JFK LHR [--provider aerodatabox] [--hours-back 3] [--hours-ahead 6]
  ontime-ingest poll --tier 1 [--provider aerodatabox]
  ontime-ingest replay [--airport JFK] [--days 7] [--provider aerodatabox]
"""
from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta

from ontime.config import TIERS, get_settings
from ontime.db import session_scope
from ontime.ingest import rawstore, service
from ontime.ingest.providers import get_provider
from ontime.ingest.reference import seed
from ontime.logging import setup_logging
from ontime.repositories.reference import count_airports


def cmd_seed(args: argparse.Namespace) -> None:
    # Airports go first: runways and poll-tier checks depend on them.
    steps = {
        "airports": seed.seed_airports,
        "airlines": seed.seed_airlines,
        "tiers": seed.seed_poll_tiers,
        "aircraft-types": seed.seed_aircraft_types,
        "aircraft": seed.seed_aircraft,
    }
    targets = list(steps) if args.target == "all" else [args.target]
    for name in targets:
        with session_scope() as session:  # one transaction per step
            print(name, steps[name](session))
    with session_scope() as session:
        total, with_tz = count_airports(session)
        print(f"airports in db: {total} ({with_tz} with timezone)")


def cmd_board(args: argparse.Namespace) -> None:
    provider, store = get_provider(args.provider), rawstore.from_url(get_settings().raw_store_url)
    now = datetime.now(UTC)
    for iata in args.airport:
        result = service.poll_airport(provider, iata, now - timedelta(hours=args.hours_back),
                                      now + timedelta(hours=args.hours_ahead), store=store)
        print(iata, result)


def cmd_poll(args: argparse.Namespace) -> None:
    provider, store = get_provider(args.provider), rawstore.from_url(get_settings().raw_store_url)
    print(f"tier {args.tier}:", service.poll_tier(provider, args.tier, store=store))


def cmd_replay(args: argparse.Namespace) -> None:
    provider, store = get_provider(args.provider), rawstore.from_url(get_settings().raw_store_url)
    since = datetime.now(UTC) - timedelta(days=args.days)
    print(service.replay(provider, store=store, since=since, airport_iata=args.airport))


def main() -> None:
    setup_logging()
    p = argparse.ArgumentParser(prog="ontime-ingest")
    sub = p.add_subparsers(required=True)

    s = sub.add_parser("seed", help="load reference data and poll tiers")
    s.add_argument("target", nargs="?", default="all", choices=["all", "airports", "airlines", "tiers", "aircraft-types", "aircraft"])
    s.set_defaults(fn=cmd_seed)

    b = sub.add_parser("board", help="poll specific airports now")
    b.add_argument("--airport", required=True, nargs="+", help="IATA code(s)")
    b.add_argument("--provider", default="aerodatabox")
    b.add_argument("--hours-back", type=int, default=3)
    b.add_argument("--hours-ahead", type=int, default=6)
    b.set_defaults(fn=cmd_board)

    t = sub.add_parser("poll", help="poll all enabled airports in a tier")
    t.add_argument("--tier", type=int, required=True, choices=sorted(TIERS))
    t.add_argument("--provider", default="aerodatabox")
    t.set_defaults(fn=cmd_poll)

    r = sub.add_parser("replay", help="re-parse stored raw payloads without calling the provider")
    r.add_argument("--provider", default="aerodatabox")
    r.add_argument("--airport")
    r.add_argument("--days", type=int, default=7)
    r.set_defaults(fn=cmd_replay)

    args = p.parse_args()
    args.fn(args)


if __name__ == "__main__":
    main()
