"""llm invocation input items

Revision ID: 0079_llm_invocation_input_items
Revises: 0078_context_snapshot_parent
Create Date: 2026-06-14 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0079_llm_invocation_input_items"
down_revision = "0078_context_snapshot_parent"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column(
        "llm_invocations",
        sa.Column("input_items", sa.JSON(), nullable=False, server_default="[]"),
    )
    if bind.dialect.name == "sqlite":
        return
    op.alter_column("llm_invocations", "input_items", server_default=None)


def downgrade() -> None:
    op.drop_column("llm_invocations", "input_items")
