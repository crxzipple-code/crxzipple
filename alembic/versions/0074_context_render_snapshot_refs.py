"""context render snapshot refs

Revision ID: 0074_context_render_snapshot_refs
Revises: 0073_session_items
Create Date: 2026-06-11 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0074_context_render_snapshot_refs"
down_revision = "0073_session_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "context_render_snapshots",
        sa.Column("included_refs", sa.JSON(), nullable=False),
    )
    op.add_column(
        "context_render_snapshots",
        sa.Column("collapsed_refs", sa.JSON(), nullable=False),
    )
    op.add_column(
        "context_render_snapshots",
        sa.Column("protocol_required_refs", sa.JSON(), nullable=False),
    )


def downgrade() -> None:
    op.drop_column("context_render_snapshots", "protocol_required_refs")
    op.drop_column("context_render_snapshots", "collapsed_refs")
    op.drop_column("context_render_snapshots", "included_refs")
