"""dispatch tasks

Revision ID: 0012_dispatch_tasks
Revises: 0011_orchestration_queue_policy
Create Date: 2026-03-23 11:55:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0012_dispatch_tasks"
down_revision = "0011_orchestration_queue_policy"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dispatch_tasks",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("owner_kind", sa.String(length=100), nullable=False),
        sa.Column("owner_id", sa.String(length=100), nullable=False),
        sa.Column("lane_key", sa.String(length=255), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column(
            "policy",
            sa.String(length=50),
            nullable=False,
            server_default=sa.text("'fifo'"),
        ),
        sa.Column(
            "priority",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("100"),
        ),
        sa.Column("payload_ref", sa.String(length=255), nullable=True),
        sa.Column("metadata_payload", sa.JSON(), nullable=False),
        sa.Column("waiting_reason", sa.String(length=100), nullable=True),
        sa.Column("error_payload", sa.JSON(), nullable=True),
        sa.Column("claimed_by", sa.String(length=100), nullable=True),
        sa.Column("claim_token", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_dispatch_tasks_owner_kind"), "dispatch_tasks", ["owner_kind"])
    op.create_index(op.f("ix_dispatch_tasks_owner_id"), "dispatch_tasks", ["owner_id"])
    op.create_index(op.f("ix_dispatch_tasks_lane_key"), "dispatch_tasks", ["lane_key"])
    op.create_index(op.f("ix_dispatch_tasks_status"), "dispatch_tasks", ["status"])
    op.create_index(op.f("ix_dispatch_tasks_claimed_by"), "dispatch_tasks", ["claimed_by"])
    op.create_index(op.f("ix_dispatch_tasks_claim_token"), "dispatch_tasks", ["claim_token"])


def downgrade() -> None:
    op.drop_index(op.f("ix_dispatch_tasks_claim_token"), table_name="dispatch_tasks")
    op.drop_index(op.f("ix_dispatch_tasks_claimed_by"), table_name="dispatch_tasks")
    op.drop_index(op.f("ix_dispatch_tasks_status"), table_name="dispatch_tasks")
    op.drop_index(op.f("ix_dispatch_tasks_lane_key"), table_name="dispatch_tasks")
    op.drop_index(op.f("ix_dispatch_tasks_owner_id"), table_name="dispatch_tasks")
    op.drop_index(op.f("ix_dispatch_tasks_owner_kind"), table_name="dispatch_tasks")
    op.drop_table("dispatch_tasks")
