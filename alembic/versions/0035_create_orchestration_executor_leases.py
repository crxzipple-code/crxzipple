"""create orchestration executor leases

Revision ID: 0035_create_orchestration_executor_leases
Revises: 0034_create_orchestration_scheduler_signals
Create Date: 2026-04-21 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0035_create_orchestration_executor_leases"
down_revision = "0034_create_orchestration_scheduler_signals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("orchestration_executor_leases"):
        return

    op.create_table(
        "orchestration_executor_leases",
        sa.Column("worker_id", sa.String(length=100), primary_key=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column(
            "max_inflight_assignments",
            sa.Integer(),
            nullable=False,
            server_default="1",
        ),
        sa.Column(
            "inflight_assignment_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
        sa.Column("metadata_payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_orchestration_executor_leases_status",
        "orchestration_executor_leases",
        ["status"],
    )
    op.create_index(
        "ix_orchestration_executor_leases_lease_expires_at",
        "orchestration_executor_leases",
        ["lease_expires_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("orchestration_executor_leases"):
        return
    op.drop_index(
        "ix_orchestration_executor_leases_lease_expires_at",
        table_name="orchestration_executor_leases",
    )
    op.drop_index(
        "ix_orchestration_executor_leases_status",
        table_name="orchestration_executor_leases",
    )
    op.drop_table("orchestration_executor_leases")
