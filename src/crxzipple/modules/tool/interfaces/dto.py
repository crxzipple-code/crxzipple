from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.tool.application import ToolDiscoveryProviderDescriptor
from crxzipple.modules.tool.domain import ToolRunError, ToolRunResult
from crxzipple.modules.tool.domain.entities import Tool, ToolRun


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


@dataclass(frozen=True, slots=True)
class ToolExecutionSupportDTO:
    supported_modes: tuple[str, ...]
    supported_strategies: tuple[str, ...]
    supported_environments: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ToolDiscoveryProviderDTO:
    name: str
    description: str
    source_kind: str

    @classmethod
    def from_descriptor(
        cls,
        descriptor: ToolDiscoveryProviderDescriptor,
    ) -> "ToolDiscoveryProviderDTO":
        return cls(
            name=descriptor.name,
            description=descriptor.description,
            source_kind=descriptor.source_kind.value,
        )


@dataclass(frozen=True, slots=True)
class ToolDTO:
    id: str
    name: str
    description: str
    kind: str
    parameters: tuple[ToolParameterDTO, ...]
    tags: tuple[str, ...]
    required_effect_ids: tuple[str, ...]
    execution_policy: ToolExecutionPolicyDTO
    execution_support: ToolExecutionSupportDTO
    source_kind: str
    runtime_key: str | None
    enabled: bool

    @classmethod
    def from_entity(cls, tool: Tool) -> "ToolDTO":
        return cls(
            id=tool.id,
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
            execution_policy=ToolExecutionPolicyDTO(
                timeout_seconds=tool.execution_policy.timeout_seconds,
                requires_confirmation=tool.execution_policy.requires_confirmation,
                mutates_state=tool.execution_policy.mutates_state,
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
            source_kind=tool.source_kind.value,
            runtime_key=tool.runtime_key,
            enabled=tool.enabled,
        )


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
    target: ToolExecutionTargetDTO
    status: str
    input_payload: dict[str, Any]
    result: ToolRunResultDTO | None
    error: ToolRunErrorDTO | None
    output_payload: Any | None
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
            target=ToolExecutionTargetDTO(
                mode=tool_run.target.mode.value,
                strategy=tool_run.target.strategy.value,
                environment=tool_run.target.environment.value,
            ),
            status=tool_run.status.value,
            input_payload=dict(tool_run.input_payload),
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
            error_message=tool_run.error_message,
            created_at=tool_run.created_at.isoformat(),
            started_at=(
                tool_run.started_at.isoformat()
                if tool_run.started_at is not None
                else None
            ),
            completed_at=(
                tool_run.completed_at.isoformat()
                if tool_run.completed_at is not None
                else None
            ),
            attempt_count=tool_run.attempt_count,
            max_attempts=tool_run.max_attempts,
            worker_id=tool_run.worker_id,
            heartbeat_at=(
                tool_run.heartbeat_at.isoformat()
                if tool_run.heartbeat_at is not None
                else None
            ),
            lease_expires_at=(
                tool_run.lease_expires_at.isoformat()
                if tool_run.lease_expires_at is not None
                else None
            ),
            cancel_requested_at=(
                tool_run.cancel_requested_at.isoformat()
                if tool_run.cancel_requested_at is not None
                else None
            ),
        )
