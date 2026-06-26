from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolMode,
)


class ToolExecutionPolicyResponse(BaseModel):
    timeout_seconds: int
    requires_confirmation: bool
    mutates_state: bool
    supports_parallel: bool
    resource_scope: str | None = None
    serial_group_key: str | None = None


class ToolExecutionSupportResponse(BaseModel):
    supported_modes: list[str]
    supported_strategies: list[str]
    supported_environments: list[str]


class ToolExecutionTargetResponse(BaseModel):
    mode: str
    strategy: str
    environment: str


class ToolParameterResponse(BaseModel):
    name: str
    data_type: str
    description: str
    required: bool


class ExecuteToolRunRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    mode: ToolMode = ToolMode.INLINE
    strategy: ToolExecutionStrategy = ToolExecutionStrategy.ASYNC
    environment: ToolEnvironment = ToolEnvironment.LOCAL
    run_id: str | None = None


class ToolResponse(BaseModel):
    id: str
    source_id: str | None = None
    name: str
    description: str
    kind: str
    parameters: list[ToolParameterResponse]
    tags: list[str]
    required_effect_ids: list[str]
    access_requirements: list[str]
    access_requirement_sets: list[list[str]]
    runtime_requirement_sets: list[list[str]]
    context_requirements: list[str]
    credential_requirements: list[dict[str, Any]]
    execution_policy: ToolExecutionPolicyResponse
    execution_support: ToolExecutionSupportResponse
    definition_origin: str
    runtime_key: str | None
    enabled: bool


class ToolRootResponse(BaseModel):
    path: str
    exists: bool


class ToolSourceResponse(BaseModel):
    source_id: str
    kind: str
    display_name: str
    description: str
    config: dict[str, Any]
    credential_requirements: list[dict[str, Any]]
    runtime_requirements: list[str]
    status: str
    revision: int
    config_hash: str
    last_discovered_at: str | None
    last_discovery_status: str | None
    created_at: str | None
    updated_at: str | None


class ToolSourceDiscoveryRunResponse(BaseModel):
    discovery_run_id: str
    source_id: str
    source_revision: int
    config_hash: str
    status: str
    discovered_at: str
    function_count: int
    provider_backend_count: int
    error_message: str | None
    metadata: dict[str, Any]


class ToolSourceSyncResponse(BaseModel):
    source: ToolSourceResponse
    skipped: bool
    error_message: str | None
    discovery: ToolSourceDiscoveryRunResponse | None


class ToolSourceWriteRequest(BaseModel):
    source_id: str
    kind: str
    display_name: str
    description: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    credential_requirements: list[dict[str, Any]] = Field(default_factory=list)
    runtime_requirements: list[str] = Field(default_factory=list)
    status: str = "active"


class ToolFunctionResponse(BaseModel):
    function_id: str
    source_id: str
    stable_key: str
    name: str
    description: str
    input_schema: dict[str, Any]
    runtime_kind: str
    handler_ref: str
    capabilities: list[str]
    kind: str
    parameters: list[ToolParameterResponse]
    tags: list[str]
    required_effect_ids: list[str]
    access_requirement_sets: list[list[str]]
    runtime_requirement_sets: list[list[str]]
    context_requirements: list[str]
    credential_requirements: list[dict[str, Any]]
    execution_policy: ToolExecutionPolicyResponse
    execution_support: ToolExecutionSupportResponse
    definition_origin: str
    runtime_key: str | None
    schema_hash: str
    status: str
    enabled: bool
    revision: int
    trust_policy: dict[str, Any]
    approval_policy: dict[str, Any]
    credential_binding_overrides: dict[str, str]
    required_effect_overrides: list[str] | None
    metadata: dict[str, Any]
    created_at: str | None
    updated_at: str | None
    last_seen_at: str | None
    stale_since: str | None
    deprecated_at: str | None


class ToolProviderBackendResponse(BaseModel):
    backend_id: str
    source_id: str
    capability: str
    display_name: str
    credential_requirements: list[dict[str, Any]]
    runtime_ref: dict[str, Any]
    priority: int
    enabled: bool
    status: str
    readiness: dict[str, Any] | None = None
    created_at: str
    updated_at: str


class ToolFunctionPolicyRequest(BaseModel):
    trust_policy: dict[str, Any] = Field(default_factory=dict)
    approval_policy: dict[str, Any] = Field(default_factory=dict)
    credential_binding_overrides: dict[str, str] = Field(default_factory=dict)
    required_effect_overrides: list[str] | None = None


class ToolRunResponse(BaseModel):
    id: str
    tool_id: str
    call_id: str | None = None
    tool_surface_id: str | None = None
    function_id: str | None
    function_revision: int | None
    source_id: str | None
    source_revision: int | None
    schema_hash: str | None
    target: ToolExecutionTargetResponse
    status: str
    input_payload: dict[str, Any]
    metadata: dict[str, Any]
    result: "ToolRunResultResponse | None" = None
    error: "ToolRunErrorResponse | None" = None
    output_payload: Any | None
    result_envelope_payload: dict[str, Any] | None = None
    error_message: str | None
    created_at: str
    started_at: str | None
    completed_at: str | None
    attempt_count: int
    max_attempts: int
    worker_id: str | None
    heartbeat_at: str | None
    lease_expires_at: str | None
    cancel_requested_at: str | None


class ToolRunResultResponse(BaseModel):
    content: Any | None
    details: Any | None
    metadata: dict[str, Any]


class ToolRunErrorResponse(BaseModel):
    message: str
    code: str
    details: dict[str, Any]


class PruneExpiredToolWorkersResponse(BaseModel):
    pruned_count: int
    worker_ids: list[str]
    cutoff: str
