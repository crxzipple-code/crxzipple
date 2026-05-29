"""add context node content

Revision ID: 0064_context_node_content
Revises: 0063_context_workspace_tables
Create Date: 2026-05-30 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0064_context_node_content"
down_revision = "0063_context_workspace_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "context_node_states",
        sa.Column(
            "content",
            sa.Text(),
            nullable=False,
            server_default="",
        ),
    )
    op.alter_column(
        "context_node_states",
        "content",
        server_default=None,
    )


def downgrade() -> None:
    op.drop_column("context_node_states", "content")
