from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.tool.domain import ToolRunError, ToolRunResult
from crxzipple.modules.tool.domain.entities import Tool, ToolRun
from crxzipple.shared.access import (
    AccessCredentialRequirementDeclaration,
    AccessCredentialRequirementSet,
)
from crxzipple.shared.time import (
    format_datetime_utc,
    format_optional_datetime_utc,
)


@dataclass(frozen=True, slots=True)
class ToolParameterDTO:
    name: str
    data_type: str
    description: str
    required: bool


@dataclass(frozen=True, slots=True)
class ToolExecutionPolicyDTO:
    timeout_seconds: int
    requires_confirmation: bool
    mutates_state: bool
    supports_parallel: bool
    resource_scope: str | None
    serial_group_key: str | None


@dataclass(frozen=True, slots=True)
class ToolExecutionSupportDTO:
    supported_modes: tuple[str, ...]
    supported_strategies: tuple[str, ...]
    supported_environments: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ToolDTO:
    id: str
    source_id: str | None
    name: str
    description: str
    kind: str
    parameters: tuple[ToolParameterDTO, ...]
    tags: tuple[str, ...]
    required_effect_ids: tuple[str, ...]
    access_requirements: tuple[str, ...]
    access_requirement_sets: tuple[tuple[str, ...], ...]
    runtime_requirement_sets: tuple[tuple[str, ...], ...]
    context_requirements: tuple[str, ...]
    capability_ids: tuple[str, ...]
    credential_requirements: tuple[dict[str, Any], ...]
    execution_policy: ToolExecutionPolicyDTO
    execution_support: ToolExecutionSupportDTO
    definition_origin: str
    runtime_key: str | None
    enabled: bool

    @classmethod
    def from_entity(cls, tool: Tool) -> "ToolDTO":
        return cls(
            id=tool.id,
            source_id=tool.source_id,
            name=tool.name,
            description=tool.description,
            kind=tool.kind.value,
            parameters=tuple(
                ToolParameterDTO(
                    name=parameter.name,
                    data_type=parameter.data_type,
                    description=parameter.description,
                    required=parameter.required,
                )
                for parameter in tool.parameters
            ),
            tags=tool.tags,
            required_effect_ids=tool.required_effect_ids,
            access_requirements=tool.access_requirements,
            access_requirement_sets=tool.access_requirement_sets,
            runtime_requirement_sets=tool.runtime_requirement_sets,
            context_requirements=tool.context_requirements,
            capability_ids=tool.capability_ids,
            credential_requirements=tuple(
                _credential_requirement_set_payload(requirement_set)
                for requirement_set in tool.credential_requirements
            ),
            execution_policy=ToolExecutionPolicyDTO(
                timeout_seconds=tool.execution_policy.timeout_seconds,
                requires_confirmation=tool.execution_policy.requires_confirmation,
                mutates_state=tool.execution_policy.mutates_state,
                supports_parallel=tool.execution_policy.supports_parallel,
                resource_scope=tool.execution_policy.resource_scope,
                serial_group_key=tool.execution_policy.serial_group_key,
            ),
            execution_support=ToolExecutionSupportDTO(
                supported_modes=tuple(
                    mode.value for mode in tool.execution_support.supported_modes
                ),
                supported_strategies=tuple(
                    strategy.value
                    for strategy in tool.execution_support.supported_strategies
                ),
                supported_environments=tuple(
                    environment.value
                    for environment in tool.execution_support.supported_environments
                ),
            ),
            definition_origin=tool.definition_origin.value,
            runtime_key=tool.runtime_key,
            enabled=tool.enabled,
        )


def _credential_requirement_set_payload(
    requirement_set: AccessCredentialRequirementSet,
) -> dict[str, Any]:
    return {
        "requirement_set_id": requirement_set.requirement_set_id,
        "consumer": {
            "consumer_id": requirement_set.consumer.consumer_id,
            "module": requirement_set.consumer.module,
            "component": requirement_set.consumer.component,
            "runtime_ref": requirement_set.consumer.runtime_ref,
            "metadata": dict(requirement_set.consumer.metadata),
        },
        "requirements": [
            _credential_requirement_payload(requirement)
            for requirement in requirement_set.requirements
        ],
        "alternative": requirement_set.alternative,
        "metadata": dict(requirement_set.metadata),
    }


def _credential_requirement_payload(
    requirement: AccessCredentialRequirementDeclaration,
) -> dict[str, Any]:
    return {
        "requirement_id": requirement.requirement_id,
        "consumer": {
            "consumer_id": requirement.consumer.consumer_id,
            "module": requirement.consumer.module,
            "component": requirement.consumer.component,
            "runtime_ref": requirement.consumer.runtime_ref,
            "metadata": dict(requirement.consumer.metadata),
        },
        "slot": {
            "slot": requirement.slot.slot,
            "expected_kind": requirement.slot.expected_kind.value,
            "binding_id": requirement.slot.binding_id,
            "required": requirement.slot.required,
            "display_name": requirement.slot.display_name,
            "scopes": list(requirement.slot.scopes),
            "metadata": dict(requirement.slot.metadata),
        },
        "provider": requirement.provider,
        "transport": requirement.transport.value,
        "parameter_name": requirement.parameter_name,
        "setup_flow_hint": {
            "flow_kind": requirement.setup_flow_hint.flow_kind.value,
            "provider": requirement.setup_flow_hint.provider,
            "authorization_url": requirement.setup_flow_hint.authorization_url,
            "token_url": requirement.setup_flow_hint.token_url,
            "device_code_url": requirement.setup_flow_hint.device_code_url,
            "callback_url": requirement.setup_flow_hint.callback_url,
            "metadata": dict(requirement.setup_flow_hint.metadata),
        },
        "metadata": dict(requirement.metadata),
    }


@dataclass(frozen=True, slots=True)
class ToolExecutionTargetDTO:
    mode: str
    strategy: str
    environment: str


@dataclass(frozen=True, slots=True)
class ToolRunResultDTO:
    content: Any | None
    details: Any | None
    metadata: dict[str, Any]

    @classmethod
    def from_value_object(cls, result: ToolRunResult) -> "ToolRunResultDTO":
        return cls(
            content=[dict(block) for block in result.blocks],
            details=result.details,
            metadata=dict(result.metadata),
        )


@dataclass(frozen=True, slots=True)
class ToolRunErrorDTO:
    message: str
    code: str
    details: dict[str, Any]

    @classmethod
    def from_value_object(cls, error: ToolRunError) -> "ToolRunErrorDTO":
        return cls(
            message=error.message,
            code=error.code,
            details=dict(error.details),
        )


@dataclass(frozen=True, slots=True)
class ToolRunDTO:
    id: str
    tool_id: str
    call_id: str | None
    tool_surface_id: str | None
    function_id: str | None
    function_revision: int | None
    source_id: str | None
    source_revision: int | None
    schema_hash: str | None
    target: ToolExecutionTargetDTO
    status: str
    input_payload: dict[str, Any]
    metadata: dict[str, Any]
    result: ToolRunResultDTO | None
    error: ToolRunErrorDTO | None
    output_payload: Any | None
    result_envelope_payload: dict[str, Any] | None
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

    @classmethod
    def from_entity(cls, tool_run: ToolRun) -> "ToolRunDTO":
        return cls(
            id=tool_run.id,
            tool_id=tool_run.tool_id,
            call_id=tool_run.call_id,
            tool_surface_id=tool_run.tool_surface_id,
            function_id=tool_run.function_id,
            function_revision=tool_run.function_revision,
            source_id=tool_run.source_id,
            source_revision=tool_run.source_revision,
            schema_hash=tool_run.schema_hash,
            target=ToolExecutionTargetDTO(
                mode=tool_run.target.mode.value,
                strategy=tool_run.target.strategy.value,
                environment=tool_run.target.environment.value,
            ),
            status=tool_run.status.value,
            input_payload=dict(tool_run.input_payload),
            metadata=dict(tool_run.metadata),
            result=(
                ToolRunResultDTO.from_value_object(tool_run.result)
                if tool_run.result is not None
                else None
            ),
            error=(
                ToolRunErrorDTO.from_value_object(tool_run.error)
                if tool_run.error is not None
                else None
            ),
            output_payload=tool_run.output_payload,
            result_envelope_payload=(
                dict(tool_run.result_envelope_payload)
                if tool_run.result_envelope_payload is not None
                else None
            ),
            error_message=tool_run.error_message,
            created_at=format_datetime_utc(tool_run.created_at),
            started_at=format_optional_datetime_utc(tool_run.started_at),
            completed_at=format_optional_datetime_utc(tool_run.completed_at),
            attempt_count=tool_run.attempt_count,
            max_attempts=tool_run.max_attempts,
            worker_id=tool_run.worker_id,
            heartbeat_at=format_optional_datetime_utc(tool_run.heartbeat_at),
            lease_expires_at=format_optional_datetime_utc(
                tool_run.lease_expires_at,
            ),
            cancel_requested_at=format_optional_datetime_utc(
                tool_run.cancel_requested_at,
            ),
        )
