"""create orchestration execution chain tables

Revision ID: 0065_orchestration_execution_chain
Revises: 0064_context_node_content
Create Date: 2026-06-01 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0065_orchestration_execution_chain"
down_revision = "0064_context_node_content"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "orchestration_execution_chains",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("turn_id", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("active_step_id", sa.String(length=100), nullable=True),
        sa.Column("step_count", sa.Integer(), nullable=False),
        sa.Column("error_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["orchestration_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_orchestration_execution_chains_turn_id",
        "orchestration_execution_chains",
        ["turn_id"],
    )
    op.create_index(
        "ix_orchestration_execution_chains_status",
        "orchestration_execution_chains",
        ["status"],
    )
    op.create_index(
        "ix_orchestration_execution_chains_active_step_id",
        "orchestration_execution_chains",
        ["active_step_id"],
    )
    op.create_index(
        "ix_orchestration_execution_chains_updated_at",
        "orchestration_execution_chains",
        ["updated_at"],
    )

    op.create_table(
        "orchestration_execution_steps",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("chain_id", sa.String(length=100), nullable=False),
        sa.Column("turn_id", sa.String(length=100), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("dispatch_task_id", sa.String(length=100), nullable=True),
        sa.Column("owner_kind", sa.String(length=80), nullable=True),
        sa.Column("owner_id", sa.String(length=160), nullable=True),
        sa.Column("correlation_key", sa.String(length=255), nullable=True),
        sa.Column("error_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["chain_id"],
            ["orchestration_execution_chains.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["orchestration_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "chain_id",
            "step_index",
            name="uq_orchestration_execution_steps_chain_index",
        ),
        sa.UniqueConstraint("correlation_key"),
    )
    for column in (
        "chain_id",
        "turn_id",
        "kind",
        "status",
        "dispatch_task_id",
        "updated_at",
    ):
        op.create_index(
            f"ix_orchestration_execution_steps_{column}",
            "orchestration_execution_steps",
            [column],
        )
    op.create_index(
        "ix_orchestration_execution_steps_owner",
        "orchestration_execution_steps",
        ["owner_kind", "owner_id"],
    )

    op.create_table(
        "orchestration_execution_step_items",
        sa.Column("id", sa.String(length=100), nullable=False),
        sa.Column("step_id", sa.String(length=100), nullable=False),
        sa.Column("chain_id", sa.String(length=100), nullable=False),
        sa.Column("turn_id", sa.String(length=100), nullable=False),
        sa.Column("item_index", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=50), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("owner_kind", sa.String(length=80), nullable=True),
        sa.Column("owner_id", sa.String(length=160), nullable=True),
        sa.Column("correlation_key", sa.String(length=255), nullable=True),
        sa.Column("source_event_id", sa.String(length=160), nullable=True),
        sa.Column("payload_ref", sa.JSON(), nullable=True),
        sa.Column("summary_payload", sa.JSON(), nullable=True),
        sa.Column("error_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["step_id"],
            ["orchestration_execution_steps.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["chain_id"],
            ["orchestration_execution_chains.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["turn_id"],
            ["orchestration_runs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "step_id",
            "item_index",
            name="uq_orchestration_execution_step_items_step_index",
        ),
    )
    for column in (
        "step_id",
        "chain_id",
        "turn_id",
        "kind",
        "status",
        "correlation_key",
        "source_event_id",
        "updated_at",
    ):
        op.create_index(
            f"ix_orchestration_execution_step_items_{column}",
            "orchestration_execution_step_items",
            [column],
        )
    op.create_index(
        "ix_orchestration_execution_step_items_owner",
        "orchestration_execution_step_items",
        ["owner_kind", "owner_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_orchestration_execution_step_items_owner",
        table_name="orchestration_execution_step_items",
    )
    for column in (
        "step_id",
        "chain_id",
        "turn_id",
        "kind",
        "status",
        "correlation_key",
        "source_event_id",
        "updated_at",
    ):
        op.drop_index(
            f"ix_orchestration_execution_step_items_{column}",
            table_name="orchestration_execution_step_items",
        )
    op.drop_table("orchestration_execution_step_items")

    op.drop_index(
        "ix_orchestration_execution_steps_owner",
        table_name="orchestration_execution_steps",
    )
    for column in (
        "chain_id",
        "turn_id",
        "kind",
        "status",
        "dispatch_task_id",
        "updated_at",
    ):
        op.drop_index(
            f"ix_orchestration_execution_steps_{column}",
            table_name="orchestration_execution_steps",
        )
    op.drop_table("orchestration_execution_steps")

    op.drop_index(
        "ix_orchestration_execution_chains_updated_at",
        table_name="orchestration_execution_chains",
    )
    op.drop_index(
        "ix_orchestration_execution_chains_active_step_id",
        table_name="orchestration_execution_chains",
    )
    op.drop_index(
        "ix_orchestration_execution_chains_status",
        table_name="orchestration_execution_chains",
    )
    op.drop_index(
        "ix_orchestration_execution_chains_turn_id",
        table_name="orchestration_execution_chains",
    )
    op.drop_table("orchestration_execution_chains")
