"""add context request render snapshots

Revision ID: 0085_context_request_render_snapshots
Revises: 0084_drop_obsolete_llm_response_visibility_columns
Create Date: 2026-06-18
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0085_context_request_render_snapshots"
down_revision = "0084_drop_obsolete_llm_response_visibility_columns"
branch_labels = None
depends_on = None


def _table_names() -> set[str]:
    bind = op.get_bind()
    return set(sa.inspect(bind).get_table_names())


def upgrade() -> None:
    if "context_request_render_snapshots" in _table_names():
        return
    op.create_table(
        "context_request_render_snapshots",
        sa.Column("snapshot_id", sa.String(length=80), primary_key=True),
        sa.Column("workspace_id", sa.String(length=80), nullable=False),
        sa.Column("session_key", sa.String(length=240), nullable=False),
        sa.Column("run_id", sa.String(length=160), nullable=False),
        sa.Column("tree_revision", sa.Integer(), nullable=False),
        sa.Column("turn_id", sa.String(length=160), nullable=True),
        sa.Column("step_id", sa.String(length=160), nullable=True),
        sa.Column("llm_invocation_id", sa.String(length=160), nullable=True),
        sa.Column("provider", sa.String(length=80), nullable=True),
        sa.Column("transport", sa.String(length=80), nullable=True),
        sa.Column("model", sa.String(length=160), nullable=True),
        sa.Column("renderer_id", sa.String(length=160), nullable=True),
        sa.Column("renderer_version", sa.String(length=80), nullable=True),
        sa.Column("session_frontier_revision", sa.String(length=160), nullable=True),
        sa.Column("input_item_refs", sa.JSON(), nullable=False),
        sa.Column("projected_input_items", sa.JSON(), nullable=False),
        sa.Column("tool_schema_refs", sa.JSON(), nullable=False),
        sa.Column("resource_refs", sa.JSON(), nullable=False),
        sa.Column("request_hash", sa.String(length=160), nullable=True),
        sa.Column("estimated_tokens", sa.Integer(), nullable=True),
        sa.Column("render_report", sa.JSON(), nullable=False),
        sa.Column("timings", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    for column_name in (
        "workspace_id",
        "session_key",
        "run_id",
        "turn_id",
        "step_id",
        "llm_invocation_id",
        "provider",
        "transport",
        "model",
        "created_at",
    ):
        op.create_index(
            f"ix_context_request_render_snapshots_{column_name}",
            "context_request_render_snapshots",
            [column_name],
        )


def downgrade() -> None:
    if "context_request_render_snapshots" in _table_names():
        op.drop_table("context_request_render_snapshots")
