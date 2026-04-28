"""add followup fields to intake_events

Revision ID: 20260428_0002
Revises: 20260428_0001
Create Date: 2026-04-28 19:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260428_0002"
down_revision: Union[str, None] = "20260428_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("intake_events")}

    if "nag_count" not in existing_columns:
        op.add_column(
            "intake_events",
            sa.Column("nag_count", sa.Integer(), nullable=False, server_default="0"),
        )
    if "last_nag_at" not in existing_columns:
        op.add_column(
            "intake_events",
            sa.Column("last_nag_at", sa.DateTime(timezone=True), nullable=True),
        )
    if "escalation_sent_at" not in existing_columns:
        op.add_column(
            "intake_events",
            sa.Column("escalation_sent_at", sa.DateTime(timezone=True), nullable=True),
        )


def downgrade() -> None:
    op.drop_column("intake_events", "escalation_sent_at")
    op.drop_column("intake_events", "last_nag_at")
    op.drop_column("intake_events", "nag_count")
