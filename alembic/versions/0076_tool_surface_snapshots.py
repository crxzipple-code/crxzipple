"""tool surface snapshots

Revision ID: 0076_tool_surface_snapshots
Revises: 0075_tool_run_surface_call_refs
Create Date: 2026-06-12 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0076_tool_surface_snapshots"
down_revision = "0075_tool_run_surface_call_refs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tool_surfaces",
        sa.Column("surface_id", sa.String(length=255), primary_key=True),
        sa.Column("session_id", sa.String(length=255), nullable=True),
        sa.Column("run_id", sa.String(length=100), nullable=True),
        sa.Column("agent_id", sa.String(length=100), nullable=True),
        sa.Column("policy_version", sa.String(length=100), nullable=False),
        sa.Column("surface_payload", sa.JSON(), nullable=False),
        sa.Column("estimate_payload", sa.JSON(), nullable=False),
        sa.Column("diagnostics_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tool_surfaces_session_id", "tool_surfaces", ["session_id"])
    op.create_index("ix_tool_surfaces_run_id", "tool_surfaces", ["run_id"])
    op.create_index("ix_tool_surfaces_agent_id", "tool_surfaces", ["agent_id"])


def downgrade() -> None:
    op.drop_index("ix_tool_surfaces_agent_id", table_name="tool_surfaces")
    op.drop_index("ix_tool_surfaces_run_id", table_name="tool_surfaces")
    op.drop_index("ix_tool_surfaces_session_id", table_name="tool_surfaces")
    op.drop_table("tool_surfaces")
