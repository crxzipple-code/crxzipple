"""tool definition contract

Revision ID: 0002_tool_definition_contract
Revises: 0001_initial_schema
Create Date: 2026-03-22 00:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0002_tool_definition_contract"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tools",
        sa.Column(
            "kind",
            sa.String(length=50),
            nullable=False,
            server_default="function",
        ),
    )
    op.add_column(
        "tools",
        sa.Column("parameters", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "tools",
        sa.Column("tags", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "tools",
        sa.Column(
            "requires_confirmation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "tools",
        sa.Column(
            "mutates_state",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "tools",
        sa.Column(
            "timeout_seconds",
            sa.Integer(),
            nullable=False,
            server_default="30",
        ),
    )


def downgrade() -> None:
    op.drop_column("tools", "timeout_seconds")
    op.drop_column("tools", "mutates_state")
    op.drop_column("tools", "requires_confirmation")
    op.drop_column("tools", "tags")
    op.drop_column("tools", "parameters")
    op.drop_column("tools", "kind")
