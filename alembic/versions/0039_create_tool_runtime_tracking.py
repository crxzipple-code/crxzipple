"""create tool runtime tracking

Revision ID: 0039_create_tool_runtime_tracking
Revises: 0038_add_orchestration_ingress_request_kinds
Create Date: 2026-04-24 21:10:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0039_create_tool_runtime_tracking"
down_revision = "0038_add_orchestration_ingress_request_kinds"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if not inspector.has_table("tool_run_assignments"):
        op.create_table(
            "tool_run_assignments",
            sa.Column("id", sa.String(length=100), primary_key=True),
            sa.Column("run_id", sa.String(length=100), nullable=False),
            sa.Column("tool_id", sa.String(length=100), nullable=False),
            sa.Column("worker_id", sa.String(length=255), nullable=False),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
            sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("terminal_reason", sa.Text(), nullable=True),
        )
        op.create_index(
            "ix_tool_run_assignments_run_id",
            "tool_run_assignments",
            ["run_id"],
        )
        op.create_index(
            "ix_tool_run_assignments_tool_id",
            "tool_run_assignments",
            ["tool_id"],
        )
        op.create_index(
            "ix_tool_run_assignments_worker_id",
            "tool_run_assignments",
            ["worker_id"],
        )
        op.create_index(
            "ix_tool_run_assignments_lease_expires_at",
            "tool_run_assignments",
            ["lease_expires_at"],
        )

    if not inspector.has_table("tool_workers"):
        op.create_table(
            "tool_workers",
            sa.Column("id", sa.String(length=255), primary_key=True),
            sa.Column("status", sa.String(length=50), nullable=False),
            sa.Column("max_in_flight", sa.Integer(), nullable=False, server_default="1"),
            sa.Column(
                "current_in_flight",
                sa.Integer(),
                nullable=False,
                server_default="0",
            ),
            sa.Column(
                "capabilities_payload",
                sa.JSON(),
                nullable=False,
                server_default=sa.text("'{}'"),
            ),
            sa.Column("registered_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        )
        op.create_index(
            "ix_tool_workers_lease_expires_at",
            "tool_workers",
            ["lease_expires_at"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)

    if inspector.has_table("tool_workers"):
        with op.batch_alter_table("tool_workers") as batch_op:
            batch_op.drop_index("ix_tool_workers_lease_expires_at")
        op.drop_table("tool_workers")

    if inspector.has_table("tool_run_assignments"):
        with op.batch_alter_table("tool_run_assignments") as batch_op:
            batch_op.drop_index("ix_tool_run_assignments_lease_expires_at")
            batch_op.drop_index("ix_tool_run_assignments_worker_id")
            batch_op.drop_index("ix_tool_run_assignments_tool_id")
            batch_op.drop_index("ix_tool_run_assignments_run_id")
        op.drop_table("tool_run_assignments")
