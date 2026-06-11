"""create context workspace tables

Revision ID: 0063_context_workspace_tables
Revises: 0062_drop_retired_browser_local_package_manifest
Create Date: 2026-05-29 00:00:00
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "0063_context_workspace_tables"
down_revision = "0062_drop_retired_browser_local_package_manifest"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "context_workspaces",
        sa.Column("workspace_id", sa.String(length=80), nullable=False),
        sa.Column("session_key", sa.String(length=240), nullable=False),
        sa.Column("agent_id", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("active_revision", sa.Integer(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("workspace_id"),
        sa.UniqueConstraint("session_key"),
    )
    op.create_index(
        "ix_context_workspaces_session_key",
        "context_workspaces",
        ["session_key"],
    )
    op.create_index(
        "ix_context_workspaces_agent_id",
        "context_workspaces",
        ["agent_id"],
    )
    op.create_index(
        "ix_context_workspaces_status",
        "context_workspaces",
        ["status"],
    )
    op.create_index(
        "ix_context_workspaces_updated_at",
        "context_workspaces",
        ["updated_at"],
    )

    op.create_table(
        "context_node_states",
        sa.Column("row_id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("workspace_id", sa.String(length=80), nullable=False),
        sa.Column("node_id", sa.String(length=240), nullable=False),
        sa.Column("parent_id", sa.String(length=240), nullable=True),
        sa.Column("owner", sa.String(length=80), nullable=False),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=240), nullable=False),
        sa.Column("summary", sa.String(length=2000), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("actions", sa.JSON(), nullable=False),
        sa.Column("owner_ref", sa.JSON(), nullable=False),
        sa.Column("estimate", sa.JSON(), nullable=False),
        sa.Column("revision", sa.String(length=240), nullable=True),
        sa.Column("freshness", sa.String(length=40), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("row_id"),
        sa.UniqueConstraint(
            "workspace_id",
            "node_id",
            name="uq_context_node_states_workspace_node",
        ),
    )
    for column in (
        "workspace_id",
        "node_id",
        "parent_id",
        "owner",
        "kind",
        "updated_at",
    ):
        op.create_index(
            f"ix_context_node_states_{column}",
            "context_node_states",
            [column],
        )

    op.create_table(
        "context_operations",
        sa.Column("operation_id", sa.String(length=80), nullable=False),
        sa.Column("workspace_id", sa.String(length=80), nullable=False),
        sa.Column("session_key", sa.String(length=240), nullable=False),
        sa.Column("run_id", sa.String(length=160), nullable=True),
        sa.Column("node_id", sa.String(length=240), nullable=True),
        sa.Column("action", sa.String(length=80), nullable=False),
        sa.Column("actor_kind", sa.String(length=40), nullable=False),
        sa.Column("actor_id", sa.String(length=160), nullable=True),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("tree_revision", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("operation_id"),
    )
    for column in (
        "workspace_id",
        "session_key",
        "run_id",
        "node_id",
        "action",
        "status",
        "created_at",
    ):
        op.create_index(
            f"ix_context_operations_{column}",
            "context_operations",
            [column],
        )

    op.create_table(
        "context_render_snapshots",
        sa.Column("snapshot_id", sa.String(length=80), nullable=False),
        sa.Column("workspace_id", sa.String(length=80), nullable=False),
        sa.Column("session_key", sa.String(length=240), nullable=False),
        sa.Column("run_id", sa.String(length=160), nullable=False),
        sa.Column("tree_revision", sa.Integer(), nullable=False),
        sa.Column("prompt_body", sa.Text(), nullable=False),
        sa.Column("provider_attachments", sa.JSON(), nullable=False),
        sa.Column("estimate", sa.JSON(), nullable=False),
        sa.Column("included_node_ids", sa.JSON(), nullable=False),
        sa.Column("mirrored_node_ids", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("snapshot_id"),
    )
    for column in (
        "workspace_id",
        "session_key",
        "run_id",
        "created_at",
    ):
        op.create_index(
            f"ix_context_render_snapshots_{column}",
            "context_render_snapshots",
            [column],
        )


def downgrade() -> None:
    for column in (
        "workspace_id",
        "session_key",
        "run_id",
        "created_at",
    ):
        op.drop_index(
            f"ix_context_render_snapshots_{column}",
            table_name="context_render_snapshots",
        )
    op.drop_table("context_render_snapshots")

    for column in (
        "workspace_id",
        "session_key",
        "run_id",
        "node_id",
        "action",
        "status",
        "created_at",
    ):
        op.drop_index(
            f"ix_context_operations_{column}",
            table_name="context_operations",
        )
    op.drop_table("context_operations")

    for column in (
        "workspace_id",
        "node_id",
        "parent_id",
        "owner",
        "kind",
        "updated_at",
    ):
        op.drop_index(
            f"ix_context_node_states_{column}",
            table_name="context_node_states",
        )
    op.drop_table("context_node_states")

    op.drop_index("ix_context_workspaces_updated_at", table_name="context_workspaces")
    op.drop_index("ix_context_workspaces_status", table_name="context_workspaces")
    op.drop_index("ix_context_workspaces_agent_id", table_name="context_workspaces")
    op.drop_index("ix_context_workspaces_session_key", table_name="context_workspaces")
    op.drop_table("context_workspaces")
