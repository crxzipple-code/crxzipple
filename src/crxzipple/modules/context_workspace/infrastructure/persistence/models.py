from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from crxzipple.core.db import Base


class ContextWorkspaceModel(Base):
    __tablename__ = "context_workspaces"

    workspace_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    session_key: Mapped[str] = mapped_column(
        String(240),
        nullable=False,
        unique=True,
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    active_revision: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON(),
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )


class ContextNodeStateModel(Base):
    __tablename__ = "context_node_states"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "node_id",
            name="uq_context_node_states_workspace_node",
        ),
    )

    row_id: Mapped[int] = mapped_column(Integer(), primary_key=True, autoincrement=True)
    workspace_id: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        index=True,
    )
    node_id: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    parent_id: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)
    owner: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    summary: Mapped[str] = mapped_column(String(2000), nullable=False, default="")
    content: Mapped[str] = mapped_column(Text(), nullable=False, default="")
    state: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    actions: Mapped[list[str]] = mapped_column(JSON(), nullable=False)
    owner_ref: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    estimate: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    revision: Mapped[str | None] = mapped_column(String(240), nullable=True)
    freshness: Mapped[str] = mapped_column(String(40), nullable=False, default="live")
    display_order: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON(),
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )


class ContextOperationModel(Base):
    __tablename__ = "context_operations"

    operation_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        index=True,
    )
    session_key: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    run_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    node_id: Mapped[str | None] = mapped_column(String(240), nullable=True, index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    actor_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    reason: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    result: Mapped[dict[str, object] | None] = mapped_column(JSON(), nullable=True)
    tree_revision: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )


class ContextSnapshotModel(Base):
    __tablename__ = "context_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        index=True,
    )
    session_key: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    tree_revision: Mapped[int] = mapped_column(Integer(), nullable=False)
    debug_body: Mapped[str] = mapped_column(Text(), nullable=False)
    provider_attachments: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
    )
    estimate: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    included_node_ids: Mapped[list[str]] = mapped_column(JSON(), nullable=False)
    mirrored_node_ids: Mapped[list[str]] = mapped_column(JSON(), nullable=False)
    included_refs: Mapped[list[dict[str, object]]] = mapped_column(
        JSON(),
        nullable=False,
        default=list,
    )
    collapsed_refs: Mapped[list[dict[str, object]]] = mapped_column(
        JSON(),
        nullable=False,
        default=list,
    )
    protocol_required_refs: Mapped[list[dict[str, object]]] = mapped_column(
        JSON(),
        nullable=False,
        default=list,
    )
    parent_snapshot_id: Mapped[str | None] = mapped_column(
        String(80),
        nullable=True,
        index=True,
    )
    parent_tree_revision: Mapped[int | None] = mapped_column(
        Integer(),
        nullable=True,
    )
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON(),
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )


class ContextRequestRenderSnapshotModel(Base):
    __tablename__ = "context_request_render_snapshots"

    snapshot_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    workspace_id: Mapped[str] = mapped_column(
        String(80),
        nullable=False,
        index=True,
    )
    session_key: Mapped[str] = mapped_column(String(240), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(160), nullable=False, index=True)
    tree_revision: Mapped[int] = mapped_column(Integer(), nullable=False)
    turn_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    step_id: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    llm_invocation_id: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
        index=True,
    )
    provider: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    transport: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    model: Mapped[str | None] = mapped_column(String(160), nullable=True, index=True)
    renderer_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    renderer_version: Mapped[str | None] = mapped_column(String(80), nullable=True)
    session_frontier_revision: Mapped[str | None] = mapped_column(
        String(160),
        nullable=True,
    )
    input_item_refs: Mapped[list[dict[str, object]]] = mapped_column(
        JSON(),
        nullable=False,
        default=list,
    )
    projected_input_items: Mapped[list[dict[str, object]]] = mapped_column(
        JSON(),
        nullable=False,
        default=list,
    )
    tool_schema_refs: Mapped[list[dict[str, object]]] = mapped_column(
        JSON(),
        nullable=False,
        default=list,
    )
    resource_refs: Mapped[list[dict[str, object]]] = mapped_column(
        JSON(),
        nullable=False,
        default=list,
    )
    request_hash: Mapped[str | None] = mapped_column(String(160), nullable=True)
    estimated_tokens: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    render_report: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    timings: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
        default=dict,
    )
    metadata_: Mapped[dict[str, object]] = mapped_column(
        "metadata",
        JSON(),
        nullable=False,
        default=dict,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )


__all__ = [
    "ContextNodeStateModel",
    "ContextOperationModel",
    "ContextRequestRenderSnapshotModel",
    "ContextSnapshotModel",
    "ContextWorkspaceModel",
]
