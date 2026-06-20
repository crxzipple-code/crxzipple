"""context snapshot parent

Revision ID: 0078_context_snapshot_parent
Revises: 0077_llm_provider_request_preview
Create Date: 2026-06-14 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0078_context_snapshot_parent"
down_revision = "0077_llm_provider_request_preview"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "context_snapshots",
        sa.Column("parent_snapshot_id", sa.String(length=80), nullable=True),
    )
    op.add_column(
        "context_snapshots",
        sa.Column("parent_tree_revision", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_context_snapshots_parent_snapshot_id",
        "context_snapshots",
        ["parent_snapshot_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_context_snapshots_parent_snapshot_id",
        table_name="context_snapshots",
    )
    op.drop_column("context_snapshots", "parent_tree_revision")
    op.drop_column("context_snapshots", "parent_snapshot_id")
