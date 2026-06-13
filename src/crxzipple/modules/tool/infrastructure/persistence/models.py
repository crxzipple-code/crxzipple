from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from crxzipple.core.db import Base


class ToolSourceModel(Base):
    __tablename__ = "tool_sources"

    source_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    kind: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    config_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    credential_requirements_payload: Mapped[list[object]] = mapped_column(
        JSON(),
        nullable=False,
    )
    runtime_requirements_payload: Mapped[list[object]] = mapped_column(
        JSON(),
        nullable=False,
    )
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    config_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    last_discovered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    last_discovery_status: Mapped[str | None] = mapped_column(
        String(50),
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ToolSourceDiscoveryRunModel(Base):
    __tablename__ = "tool_source_discovery_runs"

    discovery_run_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_revision: Mapped[int] = mapped_column(Integer(), nullable=False)
    config_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    discovered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        index=True,
    )
    function_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    provider_backend_count: Mapped[int] = mapped_column(
        Integer(),
        nullable=False,
        default=0,
    )
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    metadata_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)


class ToolFunctionModel(Base):
    __tablename__ = "tool_functions"
    __table_args__ = (
        UniqueConstraint("stable_key", name="uq_tool_functions_stable_key"),
    )

    function_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    stable_key: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str] = mapped_column(Text(), nullable=False)
    input_schema_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    runtime_kind: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    handler_ref_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    capability_ids_payload: Mapped[list[object]] = mapped_column(JSON(), nullable=False)
    credential_requirements_payload: Mapped[list[object]] = mapped_column(
        JSON(),
        nullable=False,
    )
    access_requirement_sets_payload: Mapped[list[object]] = mapped_column(
        JSON(),
        nullable=False,
    )
    runtime_requirements_payload: Mapped[list[object]] = mapped_column(
        JSON(),
        nullable=False,
    )
    required_effect_ids_payload: Mapped[list[object]] = mapped_column(
        JSON(),
        nullable=False,
    )
    execution_support_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
    )
    enabled: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    trust_policy_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    approval_policy_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
    )
    credential_binding_overrides_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
    )
    required_effect_overrides_payload: Mapped[list[object] | None] = mapped_column(
        JSON(),
        nullable=True,
    )
    metadata_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    schema_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    last_seen_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    stale_since: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    deprecated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class ToolProviderBackendModel(Base):
    __tablename__ = "tool_provider_backends"

    backend_id: Mapped[str] = mapped_column(String(100), primary_key=True)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    capability: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    credential_requirements_payload: Mapped[list[object]] = mapped_column(
        JSON(),
        nullable=False,
    )
    runtime_ref_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    priority: Mapped[int] = mapped_column(Integer(), nullable=False, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean(), nullable=False, default=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ToolSurfaceModel(Base):
    __tablename__ = "tool_surfaces"

    surface_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    session_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    run_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    agent_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    policy_version: Mapped[str] = mapped_column(String(100), nullable=False)
    surface_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    estimate_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    diagnostics_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ToolRunModel(Base):
    __tablename__ = "tool_runs"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    tool_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    call_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    tool_surface_id: Mapped[str | None] = mapped_column(
        String(255),
        nullable=True,
        index=True,
    )
    function_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    function_revision: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    source_id: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    source_revision: Mapped[int | None] = mapped_column(Integer(), nullable=True)
    schema_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    mode: Mapped[str] = mapped_column(String(50), nullable=False)
    strategy: Mapped[str] = mapped_column(String(50), nullable=False)
    environment: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    input_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    metadata_payload: Mapped[dict[str, object]] = mapped_column(JSON(), nullable=False)
    invocation_context_payload: Mapped[dict[str, object] | None] = mapped_column(
        JSON(),
        nullable=True,
    )
    output_payload: Mapped[object | None] = mapped_column(JSON(), nullable=True)
    result_envelope_payload: Mapped[dict[str, object] | None] = mapped_column(
        JSON(),
        nullable=True,
    )
    error_message: Mapped[str | None] = mapped_column(Text(), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    attempt_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer(), nullable=False, default=3)
    worker_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )


class ToolRunAssignmentModel(Base):
    __tablename__ = "tool_run_assignments"

    id: Mapped[str] = mapped_column(String(100), primary_key=True)
    run_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    tool_id: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    worker_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    terminal_reason: Mapped[str | None] = mapped_column(Text(), nullable=True)


class ToolWorkerModel(Base):
    __tablename__ = "tool_workers"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    max_in_flight: Mapped[int] = mapped_column(Integer(), nullable=False, default=1)
    current_in_flight: Mapped[int] = mapped_column(Integer(), nullable=False, default=0)
    capabilities_payload: Mapped[dict[str, object]] = mapped_column(
        JSON(),
        nullable=False,
    )
    registered_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    heartbeat_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )
