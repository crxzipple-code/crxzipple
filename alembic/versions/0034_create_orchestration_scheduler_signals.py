"""create orchestration scheduler signals

Revision ID: 0034_create_orchestration_scheduler_signals
Revises: 0033_create_orchestration_ingress_requests
Create Date: 2026-04-19 20:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0034_create_orchestration_scheduler_signals"
down_revision = "0033_create_orchestration_ingress_requests"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("orchestration_scheduler_signals"):
        return

    op.create_table(
        "orchestration_scheduler_signals",
        sa.Column("id", sa.String(length=150), primary_key=True),
        sa.Column("signal_kind", sa.String(length=50), nullable=False),
        sa.Column("signal_payload", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("worker_id", sa.String(length=100), nullable=True),
        sa.Column("error_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
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


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("orchestration_scheduler_signals"):
        return
    op.drop_index(
        "ix_orchestration_scheduler_signals_worker_id",
        table_name="orchestration_scheduler_signals",
    )
    op.drop_index(
        "ix_orchestration_scheduler_signals_status",
        table_name="orchestration_scheduler_signals",
    )
    op.drop_index(
        "ix_orchestration_scheduler_signals_signal_kind",
        table_name="orchestration_scheduler_signals",
    )
    op.drop_table("orchestration_scheduler_signals")
