from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any

from crxzipple.shared.domain import AggregateRoot
from crxzipple.shared.domain.events import Event
from crxzipple.shared.access import AccessCredentialRequirementSet

from crxzipple.modules.tool.domain.exceptions import ToolValidationError
from crxzipple.modules.tool.domain.value_objects import (
    ToolCatalogSourceKind,
    ToolEnvironment,
    ToolFunctionRuntimeKind,
    ToolFunctionStatus,
    ToolRunAssignmentStatus,
    ToolExecutionContext,
    ToolExecutionPolicy,
    ToolRunError,
    ToolRunResult,
    ToolExecutionSupport,
    ToolExecutionTarget,
    ToolExecutionStrategy,
    ToolKind,
    ToolMode,
    ToolParameter,
    ToolProviderBackendStatus,
    ToolProviderCapability,
    ToolRunStatus,
    ToolSourceStatus,
    ToolDefinitionOrigin,
    ToolWorkerStatus,
)
from crxzipple.shared.content_blocks import describe_content_for_text_fallback

DEFAULT_TOOL_RUN_ERROR_MESSAGE = "Tool run failed without an error message."
TOOL_RESULT_ENVELOPE_METADATA_KEY = "tool_result_envelope"


def _normalize_access_requirement_sets(
    values: tuple[tuple[str, ...], ...],
    *,
    fallback_requirements: tuple[str, ...],
) -> tuple[tuple[str, ...], ...]:
    resolved: list[tuple[str, ...]] = []
    for value in values:
        requirement_set = tuple(
            dict.fromkeys(
                requirement.strip()
                for requirement in value
                if requirement is not None and requirement.strip()
            ),
        )
        if requirement_set not in resolved:
            resolved.append(requirement_set)
    if not resolved and fallback_requirements:
        resolved.append(fallback_requirements)
    return tuple(resolved)


def _normalize_tool_run_error(error: str | ToolRunError) -> ToolRunError:
    if isinstance(error, ToolRunError):
        return error
    normalized = str(error).strip()
    return ToolRunError(message=normalized or DEFAULT_TOOL_RUN_ERROR_MESSAGE)


def _tool_result_envelope_payload(result: ToolRunResult) -> dict[str, Any] | None:
    envelope = result.metadata.get(TOOL_RESULT_ENVELOPE_METADATA_KEY)
    if isinstance(envelope, dict):
        return dict(envelope)
    return None


def _worker_capability_signature(payload: dict[str, Any]) -> tuple[Any, Any]:
    return (
        payload.get("runtime_registry"),
        payload.get("concurrency_policy"),
    )


def _coerce_str_enum(
    enum_type: type[StrEnum],
    value: StrEnum | str,
    *,
    field_name: str,
) -> StrEnum:
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ToolValidationError(
            f"Unsupported {field_name}: {value!s}.",
        ) from exc


def _normalize_text(value: str, *, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ToolValidationError(f"{field_name} cannot be empty.")
    return normalized


def _normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


def _normalize_text_tuple(values: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            value.strip()
            for value in values
            if isinstance(value, str) and value.strip()
        ),
    )


def _normalize_json_mapping(value: dict[str, Any]) -> dict[str, Any]:
    return dict(value)


def _normalize_json_mapping_tuple(
    values: tuple[dict[str, Any], ...],
) -> tuple[dict[str, Any], ...]:
    return tuple(dict(value) for value in values)


@dataclass(kw_only=True)
class ToolSource(AggregateRoot[str]):
    display_name: str
    kind: ToolCatalogSourceKind = ToolCatalogSourceKind.LOCAL_PACKAGE
    description: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    credential_requirements: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    runtime_requirements: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    status: ToolSourceStatus = ToolSourceStatus.ACTIVE
    revision: int = 1
    config_hash: str = ""
    last_discovered_at: datetime | None = None
    last_discovery_status: str | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    @property
    def source_id(self) -> str:
        return self.id

    def __post_init__(self) -> None:
        self.id = _normalize_text(self.id, field_name="Tool source id")
        self.kind = _coerce_str_enum(
            ToolCatalogSourceKind,
            self.kind,
            field_name="tool source kind",
        )
        self.display_name = _normalize_text(
            self.display_name,
            field_name="Tool source display_name",
        )
        self.description = self.description.strip()
        self.config = _normalize_json_mapping(self.config)
        self.credential_requirements = _normalize_json_mapping_tuple(
            self.credential_requirements,
        )
        self.runtime_requirements = _normalize_json_mapping_tuple(
            self.runtime_requirements,
        )
        self.status = _coerce_str_enum(
            ToolSourceStatus,
            self.status,
            field_name="tool source status",
        )
        if self.revision < 1:
            raise ToolValidationError("Tool source revision must be at least 1.")
        self.config_hash = self.config_hash.strip()
        self.last_discovery_status = _normalize_optional_text(
            self.last_discovery_status,
        )


@dataclass(kw_only=True)
class ToolFunction(AggregateRoot[str]):
    source_id: str
    stable_key: str
    name: str
    display_name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    runtime_kind: ToolFunctionRuntimeKind = ToolFunctionRuntimeKind.LOCAL
    handler_ref: dict[str, Any] = field(default_factory=dict)
    capability_ids: tuple[str, ...] = field(default_factory=tuple)
    credential_requirements: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    access_requirement_sets: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    runtime_requirements: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    required_effect_ids: tuple[str, ...] = field(default_factory=tuple)
    execution_support: ToolExecutionSupport = field(
        default_factory=ToolExecutionSupport,
    )
    enabled: bool = True
    trust_policy: dict[str, Any] = field(default_factory=dict)
    approval_policy: dict[str, Any] = field(default_factory=dict)
    credential_binding_overrides: dict[str, str] = field(default_factory=dict)
    required_effect_overrides: tuple[str, ...] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    schema_hash: str = ""
    status: ToolFunctionStatus = ToolFunctionStatus.ACTIVE
    revision: int = 1
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    last_seen_at: datetime | None = None
    stale_since: datetime | None = None
    deprecated_at: datetime | None = None

    @property
    def function_id(self) -> str:
        return self.id

    def __post_init__(self) -> None:
        self.id = _normalize_text(self.id, field_name="Tool function id")
        self.source_id = _normalize_text(
            self.source_id,
            field_name="Tool function source_id",
        )
        self.stable_key = _normalize_text(
            self.stable_key,
            field_name="Tool function stable_key",
        )
        self.name = _normalize_text(self.name, field_name="Tool function name")
        self.display_name = _normalize_text(
            self.display_name,
            field_name="Tool function display_name",
        )
        self.description = self.description.strip()
        self.input_schema = _normalize_json_mapping(self.input_schema)
        self.runtime_kind = _coerce_str_enum(
            ToolFunctionRuntimeKind,
            self.runtime_kind,
            field_name="tool function runtime kind",
        )
        self.handler_ref = _normalize_json_mapping(self.handler_ref)
        self.capability_ids = _normalize_text_tuple(self.capability_ids)
        self.credential_requirements = _normalize_json_mapping_tuple(
            self.credential_requirements,
        )
        self.access_requirement_sets = _normalize_access_requirement_sets(
            self.access_requirement_sets,
            fallback_requirements=(),
        )
        self.runtime_requirements = _normalize_json_mapping_tuple(
            self.runtime_requirements,
        )
        self.required_effect_ids = _normalize_text_tuple(self.required_effect_ids)
        self.trust_policy = _normalize_json_mapping(self.trust_policy)
        self.approval_policy = _normalize_json_mapping(self.approval_policy)
        self.credential_binding_overrides = {
            _normalize_text(str(key), field_name="Tool function credential override key"): (
                _normalize_text(
                    str(value),
                    field_name="Tool function credential override value",
                )
            )
            for key, value in self.credential_binding_overrides.items()
        }
        if self.required_effect_overrides is not None:
            self.required_effect_overrides = _normalize_text_tuple(
                self.required_effect_overrides,
            )
        self.metadata = _normalize_json_mapping(self.metadata)
        self.schema_hash = self.schema_hash.strip()
        self.status = _coerce_str_enum(
            ToolFunctionStatus,
            self.status,
            field_name="tool function status",
        )
        if self.revision < 1:
            raise ToolValidationError("Tool function revision must be at least 1.")


@dataclass(kw_only=True)
class ToolProviderBackend(AggregateRoot[str]):
    source_id: str
    display_name: str
    capability: ToolProviderCapability = ToolProviderCapability.CUSTOM
    credential_requirements: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    runtime_ref: dict[str, Any] = field(default_factory=dict)
    priority: int = 100
    enabled: bool = True
    status: ToolProviderBackendStatus = ToolProviderBackendStatus.ACTIVE
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    updated_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )

    @property
    def backend_id(self) -> str:
        return self.id

    def __post_init__(self) -> None:
        self.id = _normalize_text(self.id, field_name="Tool provider backend id")
        self.source_id = _normalize_text(
            self.source_id,
            field_name="Tool provider backend source_id",
        )
        self.capability = _coerce_str_enum(
            ToolProviderCapability,
            self.capability,
            field_name="tool provider capability",
        )
        self.display_name = _normalize_text(
            self.display_name,
            field_name="Tool provider backend display_name",
        )
        self.credential_requirements = _normalize_json_mapping_tuple(
            self.credential_requirements,
        )
        self.runtime_ref = _normalize_json_mapping(self.runtime_ref)
        self.priority = int(self.priority)
        self.status = _coerce_str_enum(
            ToolProviderBackendStatus,
            self.status,
            field_name="tool provider backend status",
        )


@dataclass(kw_only=True)
class Tool(AggregateRoot[str]):
    name: str
    description: str
    source_id: str | None = None
    kind: ToolKind = ToolKind.FUNCTION
    parameters: tuple[ToolParameter, ...] = field(default_factory=tuple)
    tags: tuple[str, ...] = field(default_factory=tuple)
    required_effect_ids: tuple[str, ...] = field(default_factory=tuple)
    access_requirements: tuple[str, ...] = field(default_factory=tuple)
    access_requirement_sets: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    runtime_requirement_sets: tuple[tuple[str, ...], ...] = field(default_factory=tuple)
    context_requirements: tuple[str, ...] = field(default_factory=tuple)
    capability_ids: tuple[str, ...] = field(default_factory=tuple)
    credential_requirements: tuple[AccessCredentialRequirementSet, ...] = (
        field(default_factory=tuple)
    )
    execution_policy: ToolExecutionPolicy = field(default_factory=ToolExecutionPolicy)
    execution_support: ToolExecutionSupport = field(
        default_factory=ToolExecutionSupport,
    )
    definition_origin: ToolDefinitionOrigin = ToolDefinitionOrigin.LOCAL_DISCOVERY
    runtime_key: str | None = None
    enabled: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ToolValidationError("Tool name cannot be empty.")
        if not self.description.strip():
            raise ToolValidationError("Tool description cannot be empty.")
        self.source_id = _normalize_optional_text(self.source_id)

        parameter_names = [parameter.name for parameter in self.parameters]
        if len(parameter_names) != len(set(parameter_names)):
            raise ToolValidationError("Tool parameter names must be unique.")

        self.tags = tuple(
            dict.fromkeys(
                tag.strip().lower()
                for tag in self.tags
                if tag is not None and tag.strip()
            ),
        )
        self.required_effect_ids = tuple(
            dict.fromkeys(
                effect_id.strip()
                for effect_id in self.required_effect_ids
                if effect_id is not None and effect_id.strip()
            ),
        )
        self.access_requirements = tuple(
            dict.fromkeys(
                requirement.strip()
                for requirement in self.access_requirements
                if requirement is not None and requirement.strip()
            ),
        )
        self.access_requirement_sets = _normalize_access_requirement_sets(
            self.access_requirement_sets,
            fallback_requirements=self.access_requirements,
        )
        self.runtime_requirement_sets = _normalize_access_requirement_sets(
            self.runtime_requirement_sets,
            fallback_requirements=(),
        )
        self.context_requirements = _normalize_text_tuple(self.context_requirements)
        self.capability_ids = tuple(
            dict.fromkeys(
                capability_id.strip()
                for capability_id in self.capability_ids
                if capability_id is not None and capability_id.strip()
            ),
        )
        self.credential_requirements = tuple(self.credential_requirements)
        self.parameters = tuple(self.parameters)

    def supports(self, target: ToolExecutionTarget) -> bool:
        return self.execution_support.supports(target)

    def resolved_runtime_key(self) -> str:
        return self.runtime_key or self.id

    def enable(self) -> bool:
        if self.enabled:
            return False
        self.enabled = True
        self.record_event(
            Event(
                name="tool.enabled",
                payload={"tool_id": self.id, "tool_name": self.name},
            ),
        )
        return True

    def disable(self) -> bool:
        if not self.enabled:
            return False
        self.enabled = False
        self.record_event(
            Event(
                name="tool.disabled",
                payload={"tool_id": self.id, "tool_name": self.name},
            ),
        )
        return True


@dataclass(kw_only=True)
class ToolRun(AggregateRoot[str]):
    tool_id: str
    target: ToolExecutionTarget
    call_id: str | None = None
    tool_surface_id: str | None = None
    function_id: str | None = None
    function_revision: int | None = None
    source_id: str | None = None
    source_revision: int | None = None
    schema_hash: str | None = None
    status: ToolRunStatus = ToolRunStatus.CREATED
    input_payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    invocation_context_payload: dict[str, Any] | None = None
    result_payload: Any | None = None
    result_envelope_payload: dict[str, Any] | None = None
    error_payload: str | None = None
    created_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    started_at: datetime | None = None
    completed_at: datetime | None = None
    attempt_count: int = 0
    max_attempts: int = 3
    worker_id: str | None = None
    heartbeat_at: datetime | None = None
    lease_expires_at: datetime | None = None
    cancel_requested_at: datetime | None = None

    def __post_init__(self) -> None:
        self.input_payload = dict(self.input_payload)
        self.metadata = dict(self.metadata)
        self.call_id = _normalize_optional_text(self.call_id)
        self.tool_surface_id = _normalize_optional_text(self.tool_surface_id)
        self.function_id = _normalize_optional_text(self.function_id)
        self.source_id = _normalize_optional_text(self.source_id)
        self.schema_hash = _normalize_optional_text(self.schema_hash)
        if self.function_revision is not None and self.function_revision < 1:
            raise ToolValidationError("Tool run function_revision must be at least 1.")
        if self.source_revision is not None and self.source_revision < 1:
            raise ToolValidationError("Tool run source_revision must be at least 1.")
        self.invocation_context_payload = (
            dict(self.invocation_context_payload)
            if self.invocation_context_payload is not None
            else None
        )
        self.result_envelope_payload = (
            dict(self.result_envelope_payload)
            if isinstance(self.result_envelope_payload, dict)
            else None
        )
        if self.attempt_count < 0:
            raise ToolValidationError("Tool run attempt_count cannot be negative.")
        if self.max_attempts < 1:
            raise ToolValidationError("Tool run max_attempts must be at least 1.")

    @property
    def result(self) -> ToolRunResult | None:
        if self.result_payload is None:
            return None
        return ToolRunResult.from_payload(self.result_payload)

    @property
    def error(self) -> ToolRunError | None:
        if self.error_payload is None:
            return None
        if not self.error_payload.strip():
            return ToolRunError(message=DEFAULT_TOOL_RUN_ERROR_MESSAGE)
        return ToolRunError.from_storage(self.error_payload)

    @property
    def output_payload(self) -> Any | None:
        result = self.result
        if result is None:
            return None
        if result.details is not None:
            return result.details
        if result.blocks:
            return describe_content_for_text_fallback(result.blocks)
        return None

    @property
    def invocation_context(self) -> ToolExecutionContext | None:
        return ToolExecutionContext.from_payload(self.invocation_context_payload)

    @property
    def error_message(self) -> str | None:
        error = self.error
        if error is None:
            return None
        return error.message

    @property
    def stored_output_payload(self) -> Any | None:
        return self.result_payload

    @property
    def stored_error_payload(self) -> str | None:
        return self.error_payload

    @classmethod
    def create(
        cls,
        *,
        run_id: str,
        tool_id: str,
        input_payload: dict[str, Any],
        metadata: dict[str, Any] | None = None,
        invocation_context_payload: dict[str, Any] | None = None,
        target: ToolExecutionTarget,
        call_id: str | None = None,
        tool_surface_id: str | None = None,
        function_id: str | None = None,
        function_revision: int | None = None,
        source_id: str | None = None,
        source_revision: int | None = None,
        schema_hash: str | None = None,
        max_attempts: int = 3,
    ) -> "ToolRun":
        run = cls(
            id=run_id,
            tool_id=tool_id,
            call_id=call_id,
            tool_surface_id=tool_surface_id,
            function_id=function_id,
            function_revision=function_revision,
            source_id=source_id,
            source_revision=source_revision,
            schema_hash=schema_hash,
            input_payload=input_payload,
            metadata=metadata or {},
            invocation_context_payload=invocation_context_payload,
            target=target,
            max_attempts=max_attempts,
        )
        run.record_event(
            Event(
                name="tool.run.created",
                payload={
                    "run_id": run.id,
                    "tool_id": run.tool_id,
                    "call_id": run.call_id,
                    "tool_surface_id": run.tool_surface_id,
                    "function_id": run.function_id,
                    "function_revision": run.function_revision,
                    "source_id": run.source_id,
                    "source_revision": run.source_revision,
                    "schema_hash": run.schema_hash,
                    "mode": run.target.mode.value,
                    "strategy": run.target.strategy.value,
                    "environment": run.target.environment.value,
                    "metadata": dict(run.metadata),
                },
            ),
        )
        return run

    def queue(self) -> None:
        self.status = ToolRunStatus.QUEUED
        self.worker_id = None
        self.heartbeat_at = None
        self.lease_expires_at = None
        self.cancel_requested_at = None
        self.started_at = None
        self.completed_at = None
        self.result_payload = None
        self.result_envelope_payload = None
        self.error_payload = None
        self.record_event(
            Event(
                name="tool.run.queued",
                payload={
                    "run_id": self.id,
                    "tool_id": self.tool_id,
                    "call_id": self.call_id,
                    "tool_surface_id": self.tool_surface_id,
                    "function_id": self.function_id,
                    "source_id": self.source_id,
                },
            ),
        )

    def dispatch(self, *, worker_id: str, lease_seconds: int) -> None:
        now = datetime.now(timezone.utc)
        self.status = ToolRunStatus.DISPATCHING
        self.attempt_count += 1
        self.worker_id = worker_id
        self.heartbeat_at = now
        self.lease_expires_at = now + timedelta(seconds=lease_seconds)
        self.started_at = None
        self.completed_at = None
        self.result_payload = None
        self.result_envelope_payload = None
        self.error_payload = None
        self.record_event(
            Event(
                name="tool.run.dispatching",
                payload={
                    "run_id": self.id,
                    "tool_id": self.tool_id,
                    "call_id": self.call_id,
                    "tool_surface_id": self.tool_surface_id,
                    "function_id": self.function_id,
                    "source_id": self.source_id,
                    "worker_id": worker_id,
                    "attempt_count": self.attempt_count,
                },
            ),
        )

    def start(self) -> None:
        self.status = ToolRunStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)
        self.completed_at = None
        self.error_payload = None
        self.result_payload = None
        self.result_envelope_payload = None
        self.record_event(
            Event(
                name="tool.run.started",
                payload={
                    "run_id": self.id,
                    "tool_id": self.tool_id,
                    "call_id": self.call_id,
                    "tool_surface_id": self.tool_surface_id,
                    "function_id": self.function_id,
                    "source_id": self.source_id,
                },
            ),
        )

    def heartbeat(self, *, lease_seconds: int) -> None:
        if self.status not in {
            ToolRunStatus.DISPATCHING,
            ToolRunStatus.RUNNING,
            ToolRunStatus.CANCEL_REQUESTED,
        }:
            return
        now = datetime.now(timezone.utc)
        self.heartbeat_at = now
        self.lease_expires_at = now + timedelta(seconds=lease_seconds)
        self.record_event(
            Event(
                name="tool.run.heartbeated",
                payload={
                    "run_id": self.id,
                    "tool_id": self.tool_id,
                    "worker_id": self.worker_id,
                    "status": self.status.value,
                    "attempt_count": self.attempt_count,
                    "heartbeat_at": self.heartbeat_at.isoformat(),
                    "lease_expires_at": self.lease_expires_at.isoformat(),
                },
            ),
        )

    def succeed(self, output_payload: ToolRunResult) -> None:
        self.status = ToolRunStatus.SUCCEEDED
        self.result_payload = output_payload.to_payload()
        self.result_envelope_payload = _tool_result_envelope_payload(output_payload)
        self.error_payload = None
        self.completed_at = datetime.now(timezone.utc)
        self.heartbeat_at = self.completed_at
        self.lease_expires_at = None
        self.record_event(
            Event(
                name="tool.run.succeeded",
                payload=self._terminal_event_payload(),
            ),
        )

    def fail(self, error_message: str | ToolRunError) -> None:
        self.status = ToolRunStatus.FAILED
        normalized_error = _normalize_tool_run_error(error_message)
        self.error_payload = normalized_error.to_storage()
        self.result_payload = None
        self.result_envelope_payload = None
        self.completed_at = datetime.now(timezone.utc)
        self.heartbeat_at = self.completed_at
        self.lease_expires_at = None
        self.record_event(
            Event(
                name="tool.run.failed",
                payload={
                    **self._terminal_event_payload(),
                    "error_message": normalized_error.message,
                },
            ),
        )

    def requeue(self, reason: str | ToolRunError) -> None:
        self.status = ToolRunStatus.QUEUED
        normalized_error = _normalize_tool_run_error(reason)
        self.error_payload = normalized_error.to_storage()
        self.result_payload = None
        self.result_envelope_payload = None
        self.started_at = None
        self.completed_at = None
        self.worker_id = None
        self.heartbeat_at = None
        self.lease_expires_at = None
        self.cancel_requested_at = None
        self.record_event(
            Event(
                name="tool.run.requeued",
                payload={
                    "run_id": self.id,
                    "tool_id": self.tool_id,
                    "attempt_count": self.attempt_count,
                    "reason": normalized_error.message,
                },
            ),
        )

    def request_cancel(self) -> None:
        self.cancel_requested_at = datetime.now(timezone.utc)
        self.status = ToolRunStatus.CANCEL_REQUESTED
        self.record_event(
            Event(
                name="tool.run.cancel_requested",
                payload={"run_id": self.id, "tool_id": self.tool_id},
            ),
        )

    def cancel(self) -> None:
        self.status = ToolRunStatus.CANCELLED
        self.result_payload = None
        self.result_envelope_payload = None
        self.completed_at = datetime.now(timezone.utc)
        self.heartbeat_at = self.completed_at
        self.lease_expires_at = None
        self.record_event(
            Event(
                name="tool.run.cancelled",
                payload=self._terminal_event_payload(),
            ),
        )

    def timeout(self) -> None:
        self.status = ToolRunStatus.TIMED_OUT
        self.result_payload = None
        self.result_envelope_payload = None
        self.completed_at = datetime.now(timezone.utc)
        self.heartbeat_at = self.completed_at
        self.lease_expires_at = None
        self.record_event(
            Event(
                name="tool.run.timed_out",
                payload=self._terminal_event_payload(),
            ),
        )

    def is_terminal(self) -> bool:
        return self.status in {
            ToolRunStatus.SUCCEEDED,
            ToolRunStatus.FAILED,
            ToolRunStatus.CANCELLED,
            ToolRunStatus.TIMED_OUT,
        }

    def _terminal_event_payload(self) -> dict[str, object]:
        return {
            "run_id": self.id,
            "tool_id": self.tool_id,
            "call_id": self.call_id,
            "tool_surface_id": self.tool_surface_id,
            "function_id": self.function_id,
            "function_revision": self.function_revision,
            "source_id": self.source_id,
            "source_revision": self.source_revision,
            "schema_hash": self.schema_hash,
            "mode": self.target.mode.value,
            "strategy": self.target.strategy.value,
            "environment": self.target.environment.value,
        }

    def can_retry(self) -> bool:
        return self.attempt_count < self.max_attempts


@dataclass(kw_only=True)
class ToolRunAssignment(AggregateRoot[str]):
    run_id: str
    tool_id: str
    worker_id: str
    status: ToolRunAssignmentStatus = ToolRunAssignmentStatus.ASSIGNED
    attempt_count: int = 1
    assigned_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    started_at: datetime | None = None
    heartbeat_at: datetime | None = None
    lease_expires_at: datetime | None = None
    completed_at: datetime | None = None
    terminal_reason: str | None = None

    @classmethod
    def create(
        cls,
        *,
        assignment_id: str,
        run_id: str,
        tool_id: str,
        worker_id: str,
        attempt_count: int,
        lease_seconds: int,
    ) -> "ToolRunAssignment":
        now = datetime.now(timezone.utc)
        assignment = cls(
            id=assignment_id,
            run_id=run_id,
            tool_id=tool_id,
            worker_id=worker_id,
            attempt_count=attempt_count,
            assigned_at=now,
            heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
        )
        assignment.record_event(
            Event(
                name="tool.assignment.created",
                payload={
                    "assignment_id": assignment.id,
                    "run_id": assignment.run_id,
                    "tool_id": assignment.tool_id,
                    "worker_id": assignment.worker_id,
                    "attempt_count": assignment.attempt_count,
                },
            ),
        )
        return assignment

    def start(self) -> None:
        if self.status is ToolRunAssignmentStatus.RUNNING:
            return
        self.status = ToolRunAssignmentStatus.RUNNING
        self.started_at = datetime.now(timezone.utc)
        self.record_event(
            Event(
                name="tool.assignment.started",
                payload={
                    "assignment_id": self.id,
                    "run_id": self.run_id,
                    "tool_id": self.tool_id,
                    "worker_id": self.worker_id,
                },
            ),
        )

    def heartbeat(self, *, lease_seconds: int) -> None:
        if self.status not in {
            ToolRunAssignmentStatus.ASSIGNED,
            ToolRunAssignmentStatus.RUNNING,
        }:
            return
        now = datetime.now(timezone.utc)
        self.heartbeat_at = now
        self.lease_expires_at = now + timedelta(seconds=lease_seconds)
        self.record_event(
            Event(
                name="tool.assignment.heartbeated",
                payload={
                    "assignment_id": self.id,
                    "run_id": self.run_id,
                    "tool_id": self.tool_id,
                    "worker_id": self.worker_id,
                    "status": self.status.value,
                    "attempt_count": self.attempt_count,
                    "heartbeat_at": self.heartbeat_at.isoformat(),
                    "lease_expires_at": self.lease_expires_at.isoformat(),
                },
            ),
        )

    def succeed(self) -> None:
        self._complete(ToolRunAssignmentStatus.SUCCEEDED)

    def fail(self, reason: str) -> None:
        self._complete(ToolRunAssignmentStatus.FAILED, reason=reason)

    def cancel(self, *, reason: str | None = None) -> None:
        self._complete(ToolRunAssignmentStatus.CANCELLED, reason=reason)

    def expire(self, *, reason: str) -> None:
        self._complete(ToolRunAssignmentStatus.EXPIRED, reason=reason)

    def is_terminal(self) -> bool:
        return self.status in {
            ToolRunAssignmentStatus.SUCCEEDED,
            ToolRunAssignmentStatus.FAILED,
            ToolRunAssignmentStatus.CANCELLED,
            ToolRunAssignmentStatus.EXPIRED,
        }

    def _complete(
        self,
        status: ToolRunAssignmentStatus,
        *,
        reason: str | None = None,
    ) -> None:
        self.status = status
        self.completed_at = datetime.now(timezone.utc)
        self.heartbeat_at = self.completed_at
        self.lease_expires_at = None
        self.terminal_reason = reason
        self.record_event(
            Event(
                name=f"tool.assignment.{status.value}",
                payload={
                    "assignment_id": self.id,
                    "run_id": self.run_id,
                    "tool_id": self.tool_id,
                    "worker_id": self.worker_id,
                    "reason": reason,
                },
            ),
        )


@dataclass(kw_only=True)
class ToolWorkerRegistration(AggregateRoot[str]):
    status: ToolWorkerStatus = ToolWorkerStatus.ONLINE
    max_in_flight: int = 1
    current_in_flight: int = 0
    capabilities_payload: dict[str, Any] = field(default_factory=dict)
    registered_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    heartbeat_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc),
    )
    lease_expires_at: datetime | None = None

    @classmethod
    def create(
        cls,
        *,
        worker_id: str,
        lease_seconds: int,
        max_in_flight: int = 1,
        capabilities_payload: dict[str, Any] | None = None,
    ) -> "ToolWorkerRegistration":
        now = datetime.now(timezone.utc)
        worker = cls(
            id=worker_id,
            max_in_flight=max(int(max_in_flight), 1),
            capabilities_payload=dict(capabilities_payload or {}),
            registered_at=now,
            heartbeat_at=now,
            lease_expires_at=now + timedelta(seconds=lease_seconds),
        )
        worker.record_event(
            Event(
                name="tool.worker.registered",
                payload={
                    "worker_id": worker.id,
                    "max_in_flight": worker.max_in_flight,
                },
            ),
        )
        return worker

    def refresh(
        self,
        *,
        lease_seconds: int,
        max_in_flight: int | None = None,
        capabilities_payload: dict[str, Any] | None = None,
    ) -> None:
        previous_status = self.status
        previous_lease_expires_at = self.lease_expires_at
        previous_max_in_flight = self.max_in_flight
        previous_capability_signature = _worker_capability_signature(
            self.capabilities_payload,
        )
        now = datetime.now(timezone.utc)
        self.status = ToolWorkerStatus.ONLINE
        if max_in_flight is not None:
            self.max_in_flight = max(int(max_in_flight), 1)
        if capabilities_payload is not None:
            self.capabilities_payload = dict(capabilities_payload)
        self.heartbeat_at = now
        self.lease_expires_at = self.heartbeat_at + timedelta(seconds=lease_seconds)
        recovered = previous_status is not ToolWorkerStatus.ONLINE or (
            previous_lease_expires_at is not None
            and previous_lease_expires_at <= now
        )
        if recovered:
            self.record_event(
                Event(
                    name="tool.worker.recovered",
                    payload={
                        "worker_id": self.id,
                        "previous_status": previous_status.value,
                        "previous_lease_expires_at": (
                            previous_lease_expires_at.isoformat()
                            if previous_lease_expires_at is not None
                            else None
                        ),
                        "max_in_flight": self.max_in_flight,
                        "current_in_flight": self.current_in_flight,
                        "lease_expires_at": self.lease_expires_at.isoformat(),
                    },
                ),
            )
        if (
            previous_max_in_flight != self.max_in_flight
            or previous_capability_signature
            != _worker_capability_signature(self.capabilities_payload)
        ):
            self.record_event(
                Event(
                    name="tool.worker.capabilities_updated",
                    payload={
                        "worker_id": self.id,
                        "max_in_flight": self.max_in_flight,
                        "current_in_flight": self.current_in_flight,
                        "lease_expires_at": self.lease_expires_at.isoformat(),
                    },
                ),
            )

    def reserve_slot(self) -> None:
        if self.current_in_flight >= self.max_in_flight:
            raise ToolValidationError("Tool worker has no remaining execution slots.")
        self.current_in_flight += 1

    def release_slot(self) -> None:
        if self.current_in_flight > 0:
            self.current_in_flight -= 1

    def sync_current_in_flight(self, current_in_flight: int) -> None:
        self.current_in_flight = max(int(current_in_flight), 0)

    def mark_stale(self) -> None:
        self.status = ToolWorkerStatus.STALE
        self.current_in_flight = 0
        self.lease_expires_at = None
        self.record_event(
            Event(
                name="tool.worker.stale",
                payload={"worker_id": self.id},
            ),
        )


__all__ = [
    "Tool",
    "ToolCatalogSourceKind",
    "ToolEnvironment",
    "ToolFunction",
    "ToolFunctionRuntimeKind",
    "ToolFunctionStatus",
    "ToolExecutionPolicy",
    "ToolExecutionSupport",
    "ToolExecutionTarget",
    "ToolExecutionStrategy",
    "ToolKind",
    "ToolMode",
    "ToolParameter",
    "ToolProviderBackend",
    "ToolProviderBackendStatus",
    "ToolProviderCapability",
    "ToolRun",
    "ToolRunAssignment",
    "ToolRunAssignmentStatus",
    "ToolRunStatus",
    "ToolSource",
    "ToolDefinitionOrigin",
    "ToolSourceStatus",
    "ToolWorkerRegistration",
    "ToolWorkerStatus",
]
