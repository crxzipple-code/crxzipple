"""drop orchestration scheduler signals table

Revision ID: 0066_drop_orchestration_scheduler_signals
Revises: 0065_orchestration_execution_chain
Create Date: 2026-06-01 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "0066_drop_orchestration_scheduler_signals"
down_revision = "0065_orchestration_execution_chain"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table("orchestration_scheduler_signals")


def downgrade() -> None:
    op.create_table(
        "orchestration_scheduler_signals",
        sa.Column("id", sa.String(length=150), nullable=False),
        sa.Column("signal_kind", sa.String(length=50), nullable=False),
        sa.Column("signal_payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("worker_id", sa.String(length=100), nullable=True),
        sa.Column("error_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_orchestration_scheduler_signals_signal_kind",
        "orchestration_scheduler_signals",
        ["signal_kind"],
    )
    op.create_index(
        "ix_orchestration_scheduler_signals_status",
        "orchestration_scheduler_signals",
        ["status"],
    )
    op.create_index(
        "ix_orchestration_scheduler_signals_worker_id",
        "orchestration_scheduler_signals",
        ["worker_id"],
    )
