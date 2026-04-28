"""add user email fallback fields

Revision ID: 20260428_0003
Revises: 20260428_0002
Create Date: 2026-04-28 20:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "20260428_0003"
down_revision: Union[str, None] = "20260428_0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    existing_columns = {column["name"] for column in inspector.get_columns("users")}

    if "email" not in existing_columns:
        op.add_column("users", sa.Column("email", sa.String(length=255), nullable=True))
    if "notify_email_enabled" not in existing_columns:
        op.add_column(
            "users",
            sa.Column("notify_email_enabled", sa.Boolean(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    op.drop_column("users", "notify_email_enabled")
    op.drop_column("users", "email")

