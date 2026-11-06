"""aircraft_type and aircraft_type_alias, plus normalize_alias()

aircraft_type holds one row per ICAO designator; aircraft_type_alias maps each provider spelling to
one. normalize_alias() is the SQL twin of ontime.repositories.aircraft.normalize_alias, so alias
lookups can happen at query time. Rows are loaded by `ontime-ingest seed aircraft-types`.

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)
CATEGORIES = ("narrowbody", "widebody", "regional_jet", "turboprop", "business_jet", "helicopter", "piston", "other")


def timestamps():
    return [
        sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()),
    ]


def upgrade() -> None:
    # Keep in step with normalize_alias() in ontime/repositories/aircraft.py (tests check they agree).
    op.execute("""
        CREATE FUNCTION normalize_alias(s text) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE RETURNS NULL ON NULL INPUT
        AS $$ SELECT lower(btrim(regexp_replace(replace(s, chr(160), ' '), '\\s+', ' ', 'g'))) $$
    """)
    op.create_table(
        "aircraft_type",
        sa.Column("designator", sa.Text(), nullable=False),
        sa.Column("manufacturer", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("family", sa.Text(), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        *timestamps(),
        sa.CheckConstraint(f"category IN {CATEGORIES}", name=op.f("ck_aircraft_type_category")),
        sa.PrimaryKeyConstraint("designator", name=op.f("pk_aircraft_type")),
    )
    op.create_index(op.f("ix_aircraft_type_family"), "aircraft_type", ["family"])
    op.create_table(
        "aircraft_type_alias",
        sa.Column("source", sa.Text(), nullable=False),
        sa.Column("alias_key", sa.Text(), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("designator", sa.Text()),
        sa.Column("family", sa.Text()),
        sa.Column("note", sa.Text()),
        *timestamps(),
        sa.ForeignKeyConstraint(["designator"], ["aircraft_type.designator"],
                                name=op.f("fk_aircraft_type_alias_designator_aircraft_type")),
        sa.PrimaryKeyConstraint("source", "alias_key", name=op.f("pk_aircraft_type_alias")),
    )
    for table in ("aircraft_type", "aircraft_type_alias"):
        op.execute(f"""
            CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table}
            FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*) EXECUTE FUNCTION set_updated_at()
        """)


def downgrade() -> None:
    op.drop_table("aircraft_type_alias")
    op.drop_table("aircraft_type")
    op.execute("DROP FUNCTION normalize_alias(text)")
