"""orchestration runs

Revision ID: 0010_orchestration_runs
Revises: 0009_structured_session_transcript
Create Date: 2026-03-23 01:40:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0010_orchestration_runs"
down_revision = "0009_structured_session_transcript"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orchestration_runs",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("stage", sa.String(length=50), nullable=False),
        sa.Column("bulk_key", sa.String(length=255), nullable=True),
        sa.Column("active_session_id", sa.String(length=100), nullable=True),
        sa.Column("agent_id", sa.String(length=100), nullable=True),
        sa.Column("lane_key", sa.String(length=255), nullable=True),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("current_step", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("max_steps", sa.Integer(), nullable=False, server_default=sa.text("12")),
        sa.Column(
            "pending_tool_run_ids",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'[]'"),
        ),
        sa.Column("waiting_reason", sa.String(length=100), nullable=True),
        sa.Column(
            "inbound_instruction_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("delivery_target_payload", sa.JSON(), nullable=True),
        sa.Column("result_payload", sa.JSON(), nullable=True),
        sa.Column("error_payload", sa.JSON(), nullable=True),
        sa.Column(
            "metadata_payload",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
        sa.Column("worker_id", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_orchestration_runs_status"),
        "orchestration_runs",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_orchestration_runs_bulk_key"),
        "orchestration_runs",
        ["bulk_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_orchestration_runs_active_session_id"),
        "orchestration_runs",
        ["active_session_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_orchestration_runs_agent_id"),
        "orchestration_runs",
        ["agent_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_orchestration_runs_lane_key"),
        "orchestration_runs",
        ["lane_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_orchestration_runs_worker_id"),
        "orchestration_runs",
        ["worker_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_orchestration_runs_worker_id"), table_name="orchestration_runs")
    op.drop_index(op.f("ix_orchestration_runs_lane_key"), table_name="orchestration_runs")
    op.drop_index(op.f("ix_orchestration_runs_agent_id"), table_name="orchestration_runs")
    op.drop_index(
        op.f("ix_orchestration_runs_active_session_id"),
        table_name="orchestration_runs",
    )
    op.drop_index(op.f("ix_orchestration_runs_bulk_key"), table_name="orchestration_runs")
    op.drop_index(op.f("ix_orchestration_runs_status"), table_name="orchestration_runs")
    op.drop_table("orchestration_runs")
