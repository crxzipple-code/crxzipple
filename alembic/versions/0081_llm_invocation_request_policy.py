"""add llm invocation request policy

Revision ID: 0081_llm_invocation_request_policy
Revises: 0080_normalize_context_snapshot_table
Create Date: 2026-06-16 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0081_llm_invocation_request_policy"
down_revision = "0080_normalize_context_snapshot_table"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    op.add_column(
        "llm_invocations",
        sa.Column(
            "request_policy",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    if bind.dialect.name == "sqlite":
        return
    op.alter_column("llm_invocations", "request_policy", server_default=None)


def downgrade() -> None:
    op.drop_column("llm_invocations", "request_policy")
