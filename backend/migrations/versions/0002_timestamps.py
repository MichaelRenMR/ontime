"""created_at / updated_at on every table, maintained by the database

Every table gets created_at and updated_at (timestamptz, default now()), and a BEFORE UPDATE trigger
that sets updated_at = now() whenever a row's values actually change. movement.first_seen_at already
meant "created", so it is renamed and keeps its history. Existing ingest_log rows are backfilled from
fetched_at; other existing rows get the migration time.

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

TS = sa.DateTime(timezone=True)
ALL_TABLES = ("airport", "runway", "airline", "movement", "ingest_log", "airport_poll", "api_usage")
NEW_COLUMNS = tuple(t for t in ALL_TABLES if t != "movement")  # movement already has updated_at


def upgrade() -> None:
    op.execute("""
        CREATE FUNCTION set_updated_at() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.updated_at := now();
            RETURN NEW;
        END
        $$
    """)
    op.alter_column("movement", "first_seen_at", new_column_name="created_at")
    for table in NEW_COLUMNS:
        # A non-volatile default: Postgres adds these without rewriting the table.
        op.add_column(table, sa.Column("created_at", TS, nullable=False, server_default=sa.func.now()))
        op.add_column(table, sa.Column("updated_at", TS, nullable=False, server_default=sa.func.now()))
    op.execute("UPDATE ingest_log SET created_at = fetched_at, updated_at = fetched_at")  # before the triggers exist
    for table in ALL_TABLES:
        op.execute(f"""
            CREATE TRIGGER trg_{table}_updated_at BEFORE UPDATE ON {table}
            FOR EACH ROW WHEN (OLD.* IS DISTINCT FROM NEW.*) EXECUTE FUNCTION set_updated_at()
        """)


def downgrade() -> None:
    for table in ALL_TABLES:
        op.execute(f"DROP TRIGGER trg_{table}_updated_at ON {table}")
    op.execute("DROP FUNCTION set_updated_at()")
    for table in NEW_COLUMNS:
        op.drop_column(table, "updated_at")
        op.drop_column(table, "created_at")
    op.alter_column("movement", "created_at", new_column_name="first_seen_at")
