"""tool run surface and call refs

Revision ID: 0075_tool_run_surface_call_refs
Revises: 0074_context_snapshot_refs
Create Date: 2026-06-12 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0075_tool_run_surface_call_refs"
down_revision = "0074_context_snapshot_refs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tool_runs",
        sa.Column("call_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "tool_runs",
        sa.Column("tool_surface_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "tool_runs",
        sa.Column("result_envelope_payload", sa.JSON(), nullable=True),
    )
    op.create_index("ix_tool_runs_call_id", "tool_runs", ["call_id"])
    op.create_index(
        "ix_tool_runs_tool_surface_id",
        "tool_runs",
        ["tool_surface_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tool_runs_tool_surface_id", table_name="tool_runs")
    op.drop_index("ix_tool_runs_call_id", table_name="tool_runs")
    op.drop_column("tool_runs", "result_envelope_payload")
    op.drop_column("tool_runs", "tool_surface_id")
    op.drop_column("tool_runs", "call_id")
