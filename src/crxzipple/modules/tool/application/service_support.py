from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol

from crxzipple.modules.dispatch.domain import DispatchTaskRepository
from crxzipple.modules.tool.application.ports import (
    ToolAccessReadinessPort,
    ToolArtifactWritePort,
    ToolRuntimeReadinessPort,
    ToolOrchestrationDispatchPort,
)
from crxzipple.modules.tool.domain.entities import Tool
from crxzipple.modules.tool.domain.entities import ToolFunction
from crxzipple.modules.tool.domain.value_objects import (
    ToolEnvironment,
    ToolExecutionContext,
    ToolExecutionPolicy,
    ToolExecutionStrategy,
    ToolExecutionSupport,
    ToolExecutionTarget,
    ToolKind,
    ToolMode,
    ToolParameter,
    ToolRunError,
    ToolRunResult,
    ToolDefinitionOrigin,
)
from crxzipple.shared.domain.aggregates import AggregateRoot
from crxzipple.shared.runtime_metrics import RuntimeMetricsRegistry
from crxzipple.shared.access import (
    AccessConsumerRef,
    AccessCredentialKind,
    AccessCredentialRequirementDeclaration,
    AccessCredentialRequirementSet,
    AccessCredentialSlotRef,
    AccessCredentialTransport,
    AccessSetupFlowHint,
    AccessSetupFlowKind,
)

DISPATCH_LEASE_EXPIRED_REASON = "Worker lease expired before completion."
DISPATCH_LEASE_EXHAUSTED_REASON = "Worker lease expired and retry budget exhausted."
SYSTEM_MANAGED_TOOL_TAG = "system-managed"


@dataclass(frozen=True, slots=True)
class ExecuteToolInput:
    tool_id: str
    arguments: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    mode: ToolMode = ToolMode.INLINE
    strategy: ToolExecutionStrategy = ToolExecutionStrategy.ASYNC
    environment: ToolEnvironment = ToolEnvironment.LOCAL
    run_id: str | None = None
    execution_context: ToolExecutionContext | None = None


@dataclass(frozen=True, slots=True)
class PreparedToolRunExecution:
    tool: Tool
    arguments: dict[str, Any]
    run_id: str
    target: ToolExecutionTarget
    worker_id: str | None
    execution_context: ToolExecutionContext | None


@dataclass(frozen=True, slots=True)
class PreparedToolRunRequest:
    data: ExecuteToolInput
    tool: Tool
    target: ToolExecutionTarget
    function: ToolFunction
    source_revision: int | None = None
    provider_backend_payload: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class PreparedToolRunCompletion:
    run_id: str
    output: ToolRunResult | None = None
    error_message: str | ToolRunError | None = None


class ToolUnitOfWork(Protocol):
    dispatch_tasks: DispatchTaskRepository
    tool_sources: Any
    tool_functions: Any
    tool_provider_backends: Any
    tool_runs: Any
    tool_run_assignments: Any
    tool_workers: Any

    def __enter__(self) -> "ToolUnitOfWork":
        ...

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: Any,
    ) -> None:
        ...

    def collect(self, aggregate: AggregateRoot[Any]) -> None:
        ...

    def commit(self) -> None:
        ...

    def rollback(self) -> None:
        ...


class ToolRuntimeGateway(Protocol):
    def list_registered_tools(self) -> list[Tool]:
        ...

    async def execute(
        self,
        tool: Tool,
        target: ToolExecutionTarget,
        arguments: dict[str, Any],
        execution_context: ToolExecutionContext | None = None,
    ) -> ToolRunResult:
        ...


@dataclass(slots=True)
class ToolServiceDependencies:
    uow_factory: Callable[[], ToolUnitOfWork]
    runtime_gateway: ToolRuntimeGateway
    runtime_registry: Any | None
    dispatch_port: ToolOrchestrationDispatchPort
    access_readiness: ToolAccessReadinessPort | None
    runtime_readiness: ToolRuntimeReadinessPort | None
    artifact_service: ToolArtifactWritePort | None
    default_max_attempts: int
    worker_lease_seconds: int
    worker_heartbeat_seconds: float
    details_max_chars: int
    worker_default_run_concurrency: int
    worker_image_run_concurrency: int
    worker_shared_state_run_concurrency: int
    metrics: RuntimeMetricsRegistry


class ToolServiceBase:
    def __init__(self, deps: ToolServiceDependencies) -> None:
        self.deps = deps

    @property
    def uow_factory(self) -> Callable[[], ToolUnitOfWork]:
        return self.deps.uow_factory

    @property
    def runtime_gateway(self) -> ToolRuntimeGateway:
        return self.deps.runtime_gateway

    @property
    def dispatch_port(self) -> ToolOrchestrationDispatchPort:
        return self.deps.dispatch_port

    @property
    def access_readiness(self) -> ToolAccessReadinessPort | None:
        return self.deps.access_readiness

    @property
    def runtime_readiness(self) -> ToolRuntimeReadinessPort | None:
        return self.deps.runtime_readiness

    @property
    def artifact_service(self) -> ToolArtifactWritePort | None:
        return self.deps.artifact_service

    @property
    def default_max_attempts(self) -> int:
        return self.deps.default_max_attempts

    @property
    def worker_lease_seconds(self) -> int:
        return self.deps.worker_lease_seconds

    @property
    def worker_heartbeat_seconds(self) -> float:
        return self.deps.worker_heartbeat_seconds

    @property
    def details_max_chars(self) -> int:
        return self.deps.details_max_chars

    @property
    def metrics(self) -> RuntimeMetricsRegistry:
        return self.deps.metrics


def build_tool_from_function(function: ToolFunction) -> Tool:
    metadata = dict(function.metadata)
    return Tool(
        id=function.function_id,
        source_id=function.source_id,
        name=function.name,
        description=function.description,
        kind=_tool_kind_from_metadata(metadata),
        parameters=_parameters_from_input_schema(function.input_schema),
        tags=tuple(
            str(tag).strip()
            for tag in metadata.get("tags", ())
            if str(tag).strip()
        ),
        required_effect_ids=function.required_effect_overrides
        if function.required_effect_overrides is not None
        else function.required_effect_ids,
        access_requirement_sets=function.access_requirement_sets,
        runtime_requirement_sets=_runtime_requirement_sets(function),
        context_requirements=_context_requirements(metadata),
        capability_ids=function.capability_ids,
        credential_requirements=credential_requirement_sets_from_payload(
            function.credential_requirements,
        ),
        execution_policy=_execution_policy_from_metadata(metadata),
        execution_support=_execution_support_from_metadata(
            metadata,
            default=function.execution_support,
        ),
        definition_origin=_tool_definition_origin_from_metadata(metadata),
        runtime_key=_runtime_key_from_function(function),
        enabled=function.enabled,
    )


def _tool_kind_from_metadata(metadata: Mapping[str, Any]) -> ToolKind:
    value = str(metadata.get("tool_kind") or ToolKind.FUNCTION.value)
    try:
        return ToolKind(value)
    except ValueError:
        return ToolKind.FUNCTION


def _tool_definition_origin_from_metadata(
    metadata: Mapping[str, Any],
) -> ToolDefinitionOrigin:
    value = str(
        metadata.get("definition_origin") or ToolDefinitionOrigin.LOCAL_DISCOVERY.value,
    )
    try:
        return ToolDefinitionOrigin(value)
    except ValueError:
        return ToolDefinitionOrigin.LOCAL_DISCOVERY


def _execution_policy_from_metadata(metadata: Mapping[str, Any]) -> ToolExecutionPolicy:
    raw_policy = metadata.get("execution_policy")
    policy = raw_policy if isinstance(raw_policy, Mapping) else {}
    return ToolExecutionPolicy(
        timeout_seconds=max(int(policy.get("timeout_seconds") or 30), 1),
        requires_confirmation=bool(policy.get("requires_confirmation", False)),
        mutates_state=bool(policy.get("mutates_state", False)),
        supports_parallel=bool(policy.get("supports_parallel", True)),
        resource_scope=_optional_policy_text(policy.get("resource_scope")),
        serial_group_key=_optional_policy_text(policy.get("serial_group_key")),
    )


def _execution_support_from_metadata(
    metadata: Mapping[str, Any],
    *,
    default: ToolExecutionSupport,
) -> ToolExecutionSupport:
    raw_support = metadata.get("execution_support")
    support = raw_support if isinstance(raw_support, Mapping) else {}
    if not support:
        return default
    return ToolExecutionSupport(
        supported_modes=_enum_tuple_from_metadata(
            support.get("supported_modes"),
            enum_type=ToolMode,
            default=default.supported_modes,
        ),
        supported_strategies=_enum_tuple_from_metadata(
            support.get("supported_strategies"),
            enum_type=ToolExecutionStrategy,
            default=default.supported_strategies,
        ),
        supported_environments=_enum_tuple_from_metadata(
            support.get("supported_environments"),
            enum_type=ToolEnvironment,
            default=default.supported_environments,
        ),
    )


def _enum_tuple_from_metadata(
    value: object,
    *,
    enum_type: Any,
    default: tuple[Any, ...],
) -> tuple[Any, ...]:
    if not isinstance(value, list | tuple):
        return default
    parsed: list[Any] = []
    for item in value:
        try:
            parsed.append(enum_type(str(item)))
        except ValueError:
            continue
    return tuple(dict.fromkeys(parsed)) or default


def _parameters_from_input_schema(
    input_schema: Mapping[str, Any],
) -> tuple[ToolParameter, ...]:
    raw_properties = input_schema.get("properties")
    properties = raw_properties if isinstance(raw_properties, Mapping) else {}
    raw_required = input_schema.get("required")
    required = {
        str(item).strip()
        for item in raw_required
        if str(item).strip()
    } if isinstance(raw_required, list | tuple) else set()
    parameters: list[ToolParameter] = []
    for name, raw_schema in properties.items():
        if not isinstance(name, str) or not name.strip():
            continue
        schema = raw_schema if isinstance(raw_schema, Mapping) else {}
        parameters.append(
            ToolParameter(
                name=name,
                data_type=_parameter_data_type(schema),
                description=str(schema.get("description") or ""),
                required=name in required,
            ),
        )
    return tuple(parameters)


def _parameter_data_type(schema: Mapping[str, Any]) -> str:
    explicit = schema.get("x-crxzipple-data-type")
    if isinstance(explicit, str) and explicit.strip():
        return explicit.strip()
    value = schema.get("type")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "string"


def _runtime_requirement_sets(function: ToolFunction) -> tuple[tuple[str, ...], ...]:
    values: list[tuple[str, ...]] = []
    for item in function.runtime_requirements:
        raw_requirements = item.get("requirements")
        if isinstance(raw_requirements, list | tuple):
            normalized = tuple(
                dict.fromkeys(
                    str(requirement).strip()
                    for requirement in raw_requirements
                    if str(requirement).strip()
                ),
            )
            if normalized:
                values.append(normalized)
            continue
        raw_requirement = item.get("requirement")
        if isinstance(raw_requirement, str) and raw_requirement.strip():
            values.append((raw_requirement.strip(),))
    return tuple(values)


def _context_requirements(metadata: Mapping[str, Any]) -> tuple[str, ...]:
    raw_values = metadata.get("context_requirements")
    if not isinstance(raw_values, list | tuple):
        return ()
    return tuple(
        dict.fromkeys(
            str(value).strip()
            for value in raw_values
            if str(value).strip()
        ),
    )


def _runtime_key_from_function(function: ToolFunction) -> str:
    for key in ("ref", "runtime_key", "handler"):
        value = function.handler_ref.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return function.function_id


def credential_requirement_sets_from_payload(
    payload: tuple[dict[str, Any], ...],
) -> tuple[AccessCredentialRequirementSet, ...]:
    requirement_sets: list[AccessCredentialRequirementSet] = []
    for item in payload:
        if isinstance(item, Mapping):
            requirement_sets.append(_credential_requirement_set_from_payload(item))
    return tuple(requirement_sets)


def _credential_requirement_set_from_payload(
    payload: Mapping[str, Any],
) -> AccessCredentialRequirementSet:
    consumer = _consumer_ref_from_payload(payload.get("consumer"))
    requirements = tuple(
        _credential_requirement_from_payload(item, default_consumer=consumer)
        for item in payload.get("requirements", ())
        if isinstance(item, Mapping)
    )
    return AccessCredentialRequirementSet(
        requirement_set_id=str(payload.get("requirement_set_id", "")).strip(),
        consumer=consumer,
        requirements=requirements,
        alternative=bool(payload.get("alternative", False)),
        metadata=_mapping_payload(payload.get("metadata")),
    )


def _credential_requirement_from_payload(
    payload: Mapping[str, Any],
    *,
    default_consumer: AccessConsumerRef,
) -> AccessCredentialRequirementDeclaration:
    slot_payload = _mapping_payload(payload.get("slot"))
    setup_payload = _mapping_payload(payload.get("setup_flow_hint"))
    return AccessCredentialRequirementDeclaration(
        requirement_id=str(payload.get("requirement_id", "")).strip(),
        consumer=(
            _consumer_ref_from_payload(payload.get("consumer"))
            if isinstance(payload.get("consumer"), Mapping)
            else default_consumer
        ),
        slot=AccessCredentialSlotRef(
            slot=str(slot_payload.get("slot", "")).strip(),
            expected_kind=AccessCredentialKind(
                str(slot_payload.get("expected_kind", AccessCredentialKind.API_KEY.value)),
            ),
            binding_id=(
                str(slot_payload["binding_id"]).strip()
                if slot_payload.get("binding_id") is not None
                else None
            ),
            required=bool(slot_payload.get("required", True)),
            display_name=(
                str(slot_payload["display_name"]).strip()
                if slot_payload.get("display_name") is not None
                else None
            ),
            scopes=tuple(
                str(item).strip()
                for item in slot_payload.get("scopes", ())
                if str(item).strip()
            ),
            metadata=_mapping_payload(slot_payload.get("metadata")),
        ),
        provider=(
            str(payload["provider"]).strip()
            if payload.get("provider") is not None
            else None
        ),
        transport=AccessCredentialTransport(
            str(payload.get("transport", AccessCredentialTransport.RUNTIME_CONTEXT.value)),
        ),
        parameter_name=(
            str(payload["parameter_name"]).strip()
            if payload.get("parameter_name") is not None
            else None
        ),
        setup_flow_hint=AccessSetupFlowHint(
            flow_kind=AccessSetupFlowKind(
                str(setup_payload.get("flow_kind", AccessSetupFlowKind.NONE.value)),
            ),
            provider=(
                str(setup_payload["provider"]).strip()
                if setup_payload.get("provider") is not None
                else None
            ),
            authorization_url=(
                str(setup_payload["authorization_url"]).strip()
                if setup_payload.get("authorization_url") is not None
                else None
            ),
            token_url=(
                str(setup_payload["token_url"]).strip()
                if setup_payload.get("token_url") is not None
                else None
            ),
            device_code_url=(
                str(setup_payload["device_code_url"]).strip()
                if setup_payload.get("device_code_url") is not None
                else None
            ),
            callback_url=(
                str(setup_payload["callback_url"]).strip()
                if setup_payload.get("callback_url") is not None
                else None
            ),
            metadata=_mapping_payload(setup_payload.get("metadata")),
        ),
        metadata=_mapping_payload(payload.get("metadata")),
    )


def _consumer_ref_from_payload(payload: object | None) -> AccessConsumerRef:
    values = _mapping_payload(payload)
    return AccessConsumerRef(
        consumer_id=str(values.get("consumer_id", "")).strip(),
        module=str(values.get("module", "")).strip(),
        component=(
            str(values["component"]).strip()
            if values.get("component") is not None
            else None
        ),
        runtime_ref=(
            str(values["runtime_ref"]).strip()
            if values.get("runtime_ref") is not None
            else None
        ),
        metadata=_mapping_payload(values.get("metadata")),
    )


def _mapping_payload(value: object | None) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _optional_policy_text(value: object | None) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    return normalized or None


def decode_tool_attachment_bytes(data: str) -> bytes | None:
    try:
        return base64.b64decode(data, validate=True)
    except (binascii.Error, ValueError):
        return None
