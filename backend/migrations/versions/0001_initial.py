"""initial schema

Hand-written to match ontime.models (no database was available to autogenerate against).
Run `make migrate` then `alembic check` once a DB is up; any reported diff means this file
and the models disagree and this file should be regenerated.

Revision ID: 0001
Revises:
Create Date: 2026-10-01
"""
import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "airport",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("iata", sa.Text()),
        sa.Column("icao", sa.Text()),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("city", sa.Text()),
        sa.Column("country", sa.Text()),
        sa.Column("lat", sa.Float()),
        sa.Column("lon", sa.Float()),
        sa.Column("tz", sa.Text(), nullable=False),
        sa.Column("ourairports_id", sa.BigInteger()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_airport")),
        sa.UniqueConstraint("iata", name=op.f("uq_airport_iata")),
        sa.UniqueConstraint("icao", name=op.f("uq_airport_icao")),
        sa.UniqueConstraint("ourairports_id", name=op.f("uq_airport_ourairports_id")),
    )

    op.create_table(
        "runway",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("airport_id", sa.Integer(), nullable=False),
        sa.Column("le_ident", sa.Text()),
        sa.Column("he_ident", sa.Text()),
        sa.Column("le_heading", sa.Float()),
        sa.Column("he_heading", sa.Float()),
        sa.Column("length_ft", sa.Integer()),
        sa.Column("surface", sa.Text()),
        sa.Column("closed", sa.Boolean(), nullable=False, server_default="false"),
        sa.ForeignKeyConstraint(
            ["airport_id"], ["airport.id"], name=op.f("fk_runway_airport_id_airport"), ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runway")),
    )
    op.create_index(op.f("ix_runway_airport_id"), "runway", ["airport_id"])

    op.create_table(
        "airline",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("iata", sa.Text()),
        sa.Column("icao", sa.Text()),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("country", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default="true"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_airline")),
    )
    op.create_index(op.f("ix_airline_iata"), "airline", ["iata"])
    op.create_index(op.f("ix_airline_icao"), "airline", ["icao"])

    op.create_table(
        "movement",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("airport_iata", sa.Text(), nullable=False),
        sa.Column("side", sa.Text(), nullable=False),
        sa.Column("other_iata", sa.Text()),
        sa.Column("airline_iata", sa.Text(), nullable=False),
        sa.Column("flight_number", sa.Text(), nullable=False),
        sa.Column("flight_number_raw", sa.Text()),
        sa.Column("sched_date_local", sa.Date(), nullable=False),
        sa.Column("sched_utc", TS, nullable=False),
        sa.Column("estimated_utc", TS),
        sa.Column("actual_utc", TS),
        sa.Column("terminal", sa.Text()),
        sa.Column("gate", sa.Text()),
        sa.Column("runway", sa.Text()),
        sa.Column("status", sa.Text()),
        sa.Column("aircraft_type", sa.Text()),
        sa.Column("is_codeshare", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("first_seen_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("side IN ('dep', 'arr')", name=op.f("ck_movement_side")),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_movement")),
        sa.UniqueConstraint(
            "source", "airport_iata", "side", "airline_iata", "flight_number", "sched_date_local",
            name="uq_movement_identity",
        ),
    )
    op.create_index("ix_movement_board", "movement", ["airport_iata", "side", "sched_utc"])
    op.create_index("ix_movement_flight", "movement", ["flight_number", "sched_date_local"])
    op.create_index(
        "ix_movement_open", "movement", ["sched_utc"], postgresql_where=sa.text("actual_utc IS NULL")
    )

    op.create_table(
        "ingest_log",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("airport_iata", sa.Text(), nullable=False),
        sa.Column("window_start", TS),
        sa.Column("window_end", TS),
        sa.Column("fetched_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("raw_key", sa.Text()),
        sa.Column("payload_sha256", sa.Text()),
        sa.Column("error", sa.Text()),
        sa.Column("movements_upserted", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("flow_run_id", sa.Text()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_ingest_log")),
    )
    op.create_index(
        "ix_ingest_log_recent", "ingest_log", ["source", "airport_iata", sa.text("fetched_at DESC")]
    )

    op.create_table(
        "airport_poll",
        sa.Column("airport_iata", sa.Text(), nullable=False),
        sa.Column("tier", sa.SmallInteger(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("last_polled_at", TS),
        sa.Column("last_status", sa.Text()),
        sa.Column("consecutive_failures", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("airport_iata", name=op.f("pk_airport_poll")),
    )

    op.create_table(
        "api_usage",
        sa.Column("provider", sa.Text(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("calls", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("units", sa.BigInteger(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("provider", "day", name=op.f("pk_api_usage")),
    )


def downgrade() -> None:
    for table in ("api_usage", "airport_poll", "ingest_log", "movement", "airline", "runway", "airport"):
        op.drop_table(table)
