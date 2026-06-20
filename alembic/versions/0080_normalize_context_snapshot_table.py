"""normalize context snapshot table name

Revision ID: 0080_normalize_context_snapshot_table
Revises: 0079_llm_invocation_input_items
Create Date: 2026-06-16 00:00:00
"""

from __future__ import annotations

revision = "0080_normalize_context_snapshot_table"
down_revision = "0079_llm_invocation_input_items"
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Current rebuildable schema already creates canonical context_snapshots."""


def downgrade() -> None:
    """No compatibility downgrade for retired context render snapshot schema."""
