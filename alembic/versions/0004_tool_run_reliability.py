"""tool run reliability

Revision ID: 0004_tool_run_reliability
Revises: 0003_tool_runtime_lifecycle
Create Date: 2026-03-22 03:30:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0004_tool_run_reliability"
down_revision = "0003_tool_runtime_lifecycle"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tool_runs",
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "tool_runs",
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
    )
    op.add_column(
        "tool_runs",
        sa.Column("worker_id", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "tool_runs",
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tool_runs",
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "tool_runs",
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_tool_runs_lease_expires_at", "tool_runs", ["lease_expires_at"])
    op.create_index("ix_tool_runs_worker_id", "tool_runs", ["worker_id"])


def downgrade() -> None:
    op.drop_index("ix_tool_runs_worker_id", table_name="tool_runs")
    op.drop_index("ix_tool_runs_lease_expires_at", table_name="tool_runs")
    op.drop_column("tool_runs", "cancel_requested_at")
    op.drop_column("tool_runs", "lease_expires_at")
    op.drop_column("tool_runs", "heartbeat_at")
    op.drop_column("tool_runs", "worker_id")
    op.drop_column("tool_runs", "max_attempts")
    op.drop_column("tool_runs", "attempt_count")
