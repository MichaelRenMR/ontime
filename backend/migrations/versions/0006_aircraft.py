"""aircraft (airframes from OpenSky) and the movement_aircraft resolution view

movement_aircraft resolves each flight's aircraft at query time: by tail (ICAO 24-bit address, then
registration) against the aircraft table, falling back to the provider's type string through
aircraft_type_alias. Fixing an alias or importing a new snapshot takes effect immediately.

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)


def upgrade() -> None:
    op.create_table(
        "aircraft",
        sa.Column("icao24", sa.Text(), nullable=False),
        sa.Column("registration", sa.Text()),
        sa.Column("typecode", sa.Text()),
        sa.Column("model_code", sa.Text()),
        sa.Column("manufacturer", sa.Text()),
        sa.Column("operator_name", sa.Text()),
        sa.Column("operator_icao", sa.Text()),
        sa.Column("operator_iata", sa.Text()),
        sa.Column("serial_number", sa.Text()),
        sa.Column("built", sa.Date()),
        sa.Column("source_snapshot", sa.Text(), nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("icao24", name=op.f("pk_aircraft")),
    )
    op.create_index(op.f("ix_aircraft_registration"), "aircraft", ["registration"])
    op.execute("""
        CREATE TRIGGER trg_aircraft_updated_at BEFORE UPDATE ON aircraft
        FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*) EXECUTE FUNCTION set_updated_at()
    """)
    op.execute("""
        CREATE VIEW movement_aircraft AS
        SELECT
            m.id                                   AS movement_id,
            m.aircraft_reg,
            m.aircraft_icao24,
            m.aircraft_type                        AS aircraft_type_raw,
            a.icao24                               AS tail_icao24,
            a.model_code,
            a.operator_icao                        AS tail_operator_icao,
            a.operator_iata                        AS tail_operator_iata,
            coalesce(a.typecode, al.designator)    AS designator,
            coalesce(t.family, al.family)          AS family,
            t.category,
            t.manufacturer,
            t.name                                 AS type_name,
            CASE
                WHEN a.typecode IS NOT NULL THEN 'tail'
                WHEN al.designator IS NOT NULL THEN 'type_string'
                WHEN al.family IS NOT NULL THEN 'family'
            END                                    AS resolution
        FROM movement m
        LEFT JOIN LATERAL (
            -- Prefer the ICAO address (fixed to the transponder); fall back to the registration.
            SELECT x.* FROM aircraft x
            WHERE x.icao24 = m.aircraft_icao24 OR x.registration = m.aircraft_reg
            ORDER BY (x.icao24 = m.aircraft_icao24) DESC NULLS LAST
            LIMIT 1
        ) a ON true
        LEFT JOIN aircraft_type_alias al
               ON al.source = m.source AND al.alias_key = normalize_alias(m.aircraft_type)
        LEFT JOIN aircraft_type t ON t.designator = coalesce(a.typecode, al.designator)
    """)


def downgrade() -> None:
    op.execute("DROP VIEW movement_aircraft")
    op.drop_table("aircraft")
