"""stable source ids on runway and airline

Lets reference seeds upsert instead of deleting and re-inserting every row, so row ids and created_at
survive re-seeds. Existing rows have no source id; the next seed replaces them once.

Revision ID: 0003
Revises: 0002
Create Date: 2026-11-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("runway", sa.Column("ourairports_id", sa.BigInteger()))
    op.create_unique_constraint(op.f("uq_runway_ourairports_id"), "runway", ["ourairports_id"])
    op.add_column("airline", sa.Column("openflights_id", sa.Integer()))
    op.create_unique_constraint(op.f("uq_airline_openflights_id"), "airline", ["openflights_id"])


def downgrade() -> None:
    op.drop_constraint(op.f("uq_airline_openflights_id"), "airline", type_="unique")
    op.drop_column("airline", "openflights_id")
    op.drop_constraint(op.f("uq_runway_ourairports_id"), "runway", type_="unique")
    op.drop_column("runway", "ourairports_id")
