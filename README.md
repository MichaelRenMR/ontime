# OnTime

A backend for global commercial flight and airport information: departure and arrival boards, terminals, runways, and actual-vs-scheduled times, collected from a flight-data provider and stored in Postgres. A web front end and AI question-answering layer are planned but **not built yet**.

## Status

| Area | State |
|---|---|
| Database schema and migrations | Built, tested against Postgres |
| Ingestion (AeroDataBox) | Built and running on a schedule; verified against live JFK data |
| Reference data (airports, runways, airlines) | Built, seeded from public datasets |
| Scheduling and monitoring (Prefect) | Built, runs in Docker |
| Quota protection | Built (daily and monthly caps) |
| API | `/health` and `/health/ready` only |
| Front end, AI layer, other providers | Not started |
| CI (GitHub Actions) | Not started; `make lint` (ruff, pyright) has never been run |

## How it works

```
 AeroDataBox API
       │  one airport board per request (departures + arrivals)
       ▼
 poll_airport()  ── budget check ─► fetch ─► hash ─► save raw payload ─► parse ─► upsert
       │                                                │                          │
       │                                       local dir / S3 bucket        Postgres: movement
       ▼
 Prefect flows (scheduled)  ◄── monitored in the Prefect UI (localhost:4200)

 FastAPI  (/health, /health/ready)  ──►  Postgres
```

- **Raw payloads are saved before parsing**, as gzipped JSON, so a parser bug never costs a re-fetch: `ontime-ingest replay` re-parses stored payloads without calling the provider.
- **Providers are pluggable.** `ingest/base.py` defines a small `Provider` protocol (fetch raw payloads, parse them, report unit cost). Adding a source means one adapter file plus one registry entry.
- **All logic is plain Python** in `ingest/`, `repositories/` and `models/`. Prefect only wraps it in `flows/`, so everything can also be run from the CLI without a Prefect server.

## Repository layout

```
docker-compose.yml        db, migrate, api, prefect-server, flows
Makefile                  common commands
.env.example              settings template (copy to .env)
backend/
  pyproject.toml          dependencies (prefect pinned to match the server image)
  alembic.ini, migrations/  database migrations (0001 = full initial schema)
  data/poll_tiers.csv     which airports are polled, in which tier
  src/ontime/
    config.py             settings, TIERS (poll schedule per tier)
    db.py, logging.py     sync SQLAlchemy engine, JSON logging
    models/               SQLAlchemy models: the schema's source of truth
    repositories/         all SQL: movement upsert, reference loads, usage ledger
    ingest/
      base.py             Movement type, Provider protocol, flight-number normalization
      service.py          poll_airport / poll_tier / replay
      budget.py           quota caps and the schedule cost projection
      rawstore.py         raw payload storage (local directory or S3-compatible)
      windows.py          "yesterday at this airport" in local time (DST-safe)
      providers/aerodatabox.py
      reference/          OurAirports and OpenFlights loaders, seed orchestration
      cli.py              ontime-ingest command
    flows/                Prefect flows and deployment registration (serve.py)
    api/                  FastAPI app and health routes
  tests/                  pytest suite (tests/fixtures/ holds real provider responses; gitignored, local only)
docker/initdb/            creates the prefect and ontime_test databases
```

## Data model

| Table | Purpose |
|---|---|
| `movement` | One departure or arrival event at an airport, per source: scheduled, estimated and actual times, terminal, gate, runway, status, the provider's aircraft type string, tail registration and ICAO 24-bit address, codeshare flag. Identity is the flight on a local calendar day, so an airline retime updates the row instead of duplicating it. Codes are plain text with no foreign keys, so ingestion never drops a row over missing reference data |
| `ingest_log` | One row per provider fetch: status (`ok`, `unchanged`, `parse_error`, `http_error`, `skipped_budget`), window, payload hash, pointer to the raw object |
| `airport_poll` | Which airports are polled, their tier, enabled flag and failure count |
| `api_usage` | Per-provider daily calls and units, used for the quota caps |
| `aircraft_type` | One row per ICAO type designator (`A21N` = every A321neo), with family and category, curated in `data/aircraft_types.csv` |
| `aircraft_type_alias` | Each provider spelling (`Airbus A321 NEO`, `32X`, …) → a designator, a family only, or deliberately unmapped; matched case- and whitespace-insensitively. Curated in `data/aircraft_type_aliases.csv` |
| `aircraft` | One row per airframe from the [OpenSky aircraft database](https://opensky-network.org/data/aircraft): registration, ICAO designator, model code (`A321-271NX`), operator, build date |
| `movement_aircraft` (view) | Each flight's aircraft, resolved at query time: by tail (ICAO address, then registration), else by the provider's type string. `resolution` says which (`tail`, `type_string`, `family`) |
| `airport`, `runway`, `airline` | Reference data, upserted on each source's stable ID (OurAirports airport and runway IDs, OpenFlights airline ID), so row IDs and `created_at` survive re-seeds; rows the source drops are deleted. Airport timezones are derived from coordinates (OurAirports has no timezone column) |

Every table has `created_at` and `updated_at`, maintained by Postgres itself: a `now()` default, and a trigger that sets `updated_at` only when a row's values actually change (so a poll that re-sends identical data doesn't touch it), whoever writes the row. All timestamps are `timestamptz` in UTC. The airport's IANA timezone name is stored, never an offset, so daylight saving is handled at conversion time.

## Schedule and quota

Defaults are set for the AeroDataBox **direct Starter plan** (40,000 units/month; an airport board call is 2 units). Everything is configured in `config.py` (`TIERS`) and `data/poll_tiers.csv`.

| Deployment (UTC) | What it does |
|---|---|
| `poll-tier-1` at 06:00, 18:00 | 10 hub airports, window -5h to +6h (one 11-hour request) |
| `poll-tier-2` at 06:10, 18:10 | 20 more airports, same window |
| `poll-tier-3` at 07:00, 19:00 | Schedule only; no airports assigned yet |
| `settle` at 04:00 | Re-fetches each airport's previous local day to capture final actuals |
| `maintenance` at 04:30 | Pauses persistently failing airports (but not when most are failing, which suggests an outage), reports unmatched codes, prunes old Prefect runs |
| `seed-reference` on the 1st, 05:00 | Reloads airports, runways, airlines and poll tiers |

Projected use is about 9,000 units/month (`tests/test_quota_plan.py` fails if a schedule change breaks the one-request windows or the cap). Before each call the budget check enforces a daily cap, a monthly unit cap and an optional monthly request cap. A 429 or 5xx response is charged as one request, a 429 is retried once, and the poll deployments start **paused** while `ADB_API_KEY` is empty.

## Quick start

Requires Docker (OrbStack or Docker Desktop) and [uv](https://docs.astral.sh/uv/) for the `make` targets that run on the host.

```bash
cp .env.example .env       # then set ADB_API_KEY (never commit .env)
make up                    # db, migrations, api, prefect-server, flows
make seed                  # first-time load of airports, runways, airlines and poll tiers
```

Polling stays paused while `ADB_API_KEY` is empty; with a key set it starts on the schedule above. The monthly `seed-reference` job only runs on the 1st, so run `make seed` once yourself, otherwise there are no airports to poll.

| URL | |
|---|---|
| `http://localhost:8000/health` | liveness (does not touch the database) |
| `http://localhost:8000/health/ready` | readiness: database reachable, plus ingest lag |
| `http://localhost:4200` | Prefect UI: runs, per-airport tasks, retries, failures |

### Commands

| | |
|---|---|
| `make up` / `make down` / `make logs` | start, stop, tail the Docker stack |
| `make migrate` / `make revision m="..."` | apply / autogenerate Alembic migrations |
| `make test` | run the test suite (needs the db container up for the Postgres tests) |
| `make lint` | ruff and pyright (not yet run on this codebase) |
| `make seed` | load reference data, poll tiers, aircraft types and the OpenSky airframe snapshot (~100 MB download) |
| `make poll tier=1` | poll a tier now (spends provider units) |
| `make psql` | open a psql shell |
| `ontime-ingest board --airport JFK` | poll specific airports now |
| `ontime-ingest replay --days 7` | re-parse stored raw payloads, no API calls |

## Configuration

Set in `.env` (see `.env.example`). Only the API key is required.

| Variable | Default | Meaning |
|---|---|---|
| `ADB_API_KEY` | (empty) | AeroDataBox direct API key, sent as `X-Api-Key` |
| `DATABASE_URL` | local Postgres | SQLAlchemy URL; plain `postgresql://` is accepted |
| `RAW_STORE_URL` | `file://./data/raw` | `s3://bucket/prefix` for any S3-compatible store (credentials via standard `AWS_*` variables) |
| `PROVIDER_DAILY_UNIT_CAP` | 1000 | skip polls that would exceed this many units in a UTC day |
| `PROVIDER_MONTHLY_UNIT_CAP` | 36000 | same, per calendar month |
| `PROVIDER_MONTHLY_REQUEST_CAP` | 0 | request cap for request-metered plans (0 = off) |
| `PROVIDER_MAX_CONCURRENCY` | 2 | parallel provider calls |

The AeroDataBox base URL and header names also have settings (`ADB_BASE_URL`, `ADB_KEY_HEADER`, `ADB_HOST_*`) for using RapidAPI or API.Market instead.

## Tests

97 tests: parsing against real provider entries (a local, gitignored fixture; those 8 tests skip without it), the upsert's idempotency and retime handling, budget caps, DST windows, the polling service with a fake provider, and the Prefect flows against a temporary Prefect server. Database tests use a real Postgres (`ontime_test`, migrated with Alembic) and are skipped if it isn't reachable. Tests blank the API key so they can never spend real units.

## Known limitations

- **One provider.** The adapter was written from AeroDataBox's documentation and then corrected against real payloads, but only JFK has been inspected. Terminal coverage at non-US airports is unverified.
- **Gates are never returned** by the provider on this plan, so `movement.gate` is always empty. Runways appear only after a flight has landed or departed, and actual times are runway times (take-off and landing), not gate times.
- **Same flight number twice on one day** from one airport collapses into one row (logged as a warning); this occurs occasionally in real data.
- **Whether the provider bills 429/5xx responses** is assumed (they are counted), not confirmed.
- Not built: stretch data (weather, seat maps, occupancy), a canonical flight table merging multiple sources, `terminal` and `operating_hours` tables, and anything user-facing.

## Data sources and licensing

Airports and runways come from [OurAirports](https://ourairports.com/data/) (public domain); airlines from [OpenFlights](https://openflights.org/data) (community data, now dated); airframes from the [OpenSky aircraft database](https://opensky-network.org/data/aircraft), which OpenSky describes as unlicensed and not kept current (the newest snapshot is August 2025), so confirm its terms before commercial use. Flight movements come from [AeroDataBox](https://aerodatabox.com); check its terms before storing or redistributing that data. Provider response data (stored raw payloads and the test fixture) is gitignored and never committed.
