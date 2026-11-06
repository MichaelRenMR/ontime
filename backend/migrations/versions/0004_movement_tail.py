"""tail registration and ICAO 24-bit address on movement

The provider sends both for roughly 40% of flights; they were previously dropped. Existing rows are
backfilled by `ontime-ingest replay` from the stored raw payloads (no API calls).

Revision ID: 0004
Revises: 0003
Create Date: 2026-11-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("movement", sa.Column("aircraft_reg", sa.Text()))
    op.add_column("movement", sa.Column("aircraft_icao24", sa.Text()))
    op.create_index("ix_movement_aircraft_reg", "movement", ["aircraft_reg"])
    op.create_index("ix_movement_aircraft_icao24", "movement", ["aircraft_icao24"])


def downgrade() -> None:
    op.drop_index("ix_movement_aircraft_icao24", "movement")
    op.drop_index("ix_movement_aircraft_reg", "movement")
    op.drop_column("movement", "aircraft_icao24")
    op.drop_column("movement", "aircraft_reg")
