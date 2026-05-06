"""create orchestration ingress requests

Revision ID: 0033_create_orchestration_ingress_requests
Revises: 0032_rename_reply_payload_columns
Create Date: 2026-04-19 13:20:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0033_create_orchestration_ingress_requests"
down_revision = "0032_rename_reply_payload_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("orchestration_ingress_requests"):
        return

    op.create_table(
        "orchestration_ingress_requests",
        sa.Column("id", sa.String(length=100), primary_key=True),
        sa.Column(
            "run_id",
            sa.String(length=100),
            sa.ForeignKey("orchestration_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("route_context_payload", sa.JSON(), nullable=False),
        sa.Column("requested_llm_id", sa.String(length=100), nullable=True),
        sa.Column("ensure_session", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("touch_activity", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("reset_policy_payload", sa.JSON(), nullable=False),
        sa.Column("prepare_metadata_payload", sa.JSON(), nullable=False),
        sa.Column("queue_policy", sa.String(length=50), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=True),
        sa.Column("worker_id", sa.String(length=100), nullable=True),
        sa.Column("error_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("run_id", name="uq_orchestration_ingress_requests_run_id"),
    )
    op.create_index(
        "ix_orchestration_ingress_requests_status",
        "orchestration_ingress_requests",
        ["status"],
    )
    op.create_index(
        "ix_orchestration_ingress_requests_run_id",
        "orchestration_ingress_requests",
        ["run_id"],
    )
    op.create_index(
        "ix_orchestration_ingress_requests_worker_id",
        "orchestration_ingress_requests",
        ["worker_id"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("orchestration_ingress_requests"):
        return
    op.drop_index(
        "ix_orchestration_ingress_requests_worker_id",
        table_name="orchestration_ingress_requests",
    )
    op.drop_index(
        "ix_orchestration_ingress_requests_run_id",
        table_name="orchestration_ingress_requests",
    )
    op.drop_index(
        "ix_orchestration_ingress_requests_status",
        table_name="orchestration_ingress_requests",
    )
    op.drop_table("orchestration_ingress_requests")
