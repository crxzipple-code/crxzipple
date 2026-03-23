from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import json
from typing import Any

from crxzipple.shared.domain import ValueObject

from crxzipple.modules.tool.domain.exceptions import ToolValidationError


_TOOL_RUN_RESULT_MARKER = "__crxzipple_tool_run_result__"
_TOOL_RUN_ERROR_PREFIX = "__crxzipple_tool_run_error__:"


class ToolKind(StrEnum):
    FUNCTION = "function"
    HTTP = "http"
    MCP = "mcp"
    WORKFLOW = "workflow"


class ToolMode(StrEnum):
    INLINE = "inline"
    BACKGROUND = "background"


class ToolExecutionStrategy(StrEnum):
    ASYNC = "async"
    THREAD = "thread"
    PROCESS = "process"


class ToolEnvironment(StrEnum):
    LOCAL = "local"
    SANDBOX = "sandbox"
    REMOTE = "remote"


class ToolSourceKind(StrEnum):
    MANUAL = "manual"
    LOCAL_DISCOVERY = "local_discovery"
    REMOTE_REGISTRY = "remote_registry"


class ToolRunStatus(StrEnum):
    CREATED = "created"
    QUEUED = "queued"
    DISPATCHING = "dispatching"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCEL_REQUESTED = "cancel_requested"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


@dataclass(frozen=True, slots=True)
class ToolRunResult(ValueObject):
    content: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_payload(self) -> Any:
        if not self.metadata:
            return self.content
        return {
            _TOOL_RUN_RESULT_MARKER: True,
            "content": self.content,
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_payload(cls, payload: Any) -> "ToolRunResult":
        if isinstance(payload, dict) and payload.get(_TOOL_RUN_RESULT_MARKER) is True:
            metadata = payload.get("metadata")
            return cls(
                content=payload.get("content"),
                metadata=dict(metadata) if isinstance(metadata, dict) else {},
            )
        return cls(content=payload)


@dataclass(frozen=True, slots=True)
class ToolRunError(ValueObject):
    message: str
    code: str = "execution_failed"
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise ToolValidationError("Tool run error message cannot be empty.")
        if not self.code.strip():
            raise ToolValidationError("Tool run error code cannot be empty.")
        object.__setattr__(self, "details", dict(self.details))

    def to_storage(self) -> str:
        if self.code == "execution_failed" and not self.details:
            return self.message
        return _TOOL_RUN_ERROR_PREFIX + json.dumps(
            {
                "message": self.message,
                "code": self.code,
                "details": self.details,
            },
            sort_keys=True,
        )

    @classmethod
    def from_storage(cls, raw: str) -> "ToolRunError":
        if raw.startswith(_TOOL_RUN_ERROR_PREFIX):
            payload_raw = raw.removeprefix(_TOOL_RUN_ERROR_PREFIX)
            try:
                payload = json.loads(payload_raw)
            except json.JSONDecodeError:
                return cls(message=raw)
            if isinstance(payload, dict):
                return cls(
                    message=str(payload.get("message", "")).strip() or raw,
                    code=str(payload.get("code", "execution_failed")).strip()
                    or "execution_failed",
                    details=(
                        dict(payload.get("details"))
                        if isinstance(payload.get("details"), dict)
                        else {}
                    ),
                )
        return cls(message=raw)


@dataclass(frozen=True, slots=True)
class ToolParameter(ValueObject):
    name: str
    data_type: str
    description: str = ""
    required: bool = True

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ToolValidationError("Tool parameter name cannot be empty.")
        if not self.data_type.strip():
            raise ToolValidationError("Tool parameter data type cannot be empty.")


@dataclass(frozen=True, slots=True)
class ToolExecutionPolicy(ValueObject):
    timeout_seconds: int = 30
    requires_confirmation: bool = False
    mutates_state: bool = False

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ToolValidationError("Tool timeout_seconds must be greater than zero.")


@dataclass(frozen=True, slots=True)
class ToolExecutionSupport(ValueObject):
    supported_modes: tuple[ToolMode, ...] = (ToolMode.INLINE,)
    supported_strategies: tuple[ToolExecutionStrategy, ...] = (
        ToolExecutionStrategy.ASYNC,
    )
    supported_environments: tuple[ToolEnvironment, ...] = (ToolEnvironment.LOCAL,)

    def __post_init__(self) -> None:
        if not self.supported_modes:
            raise ToolValidationError("Tool must support at least one execution mode.")
        if not self.supported_strategies:
            raise ToolValidationError(
                "Tool must support at least one execution strategy.",
            )
        if not self.supported_environments:
            raise ToolValidationError(
                "Tool must support at least one execution environment.",
            )

        object.__setattr__(
            self,
            "supported_modes",
            tuple(dict.fromkeys(self.supported_modes)),
        )
        object.__setattr__(
            self,
            "supported_strategies",
            tuple(dict.fromkeys(self.supported_strategies)),
        )
        object.__setattr__(
            self,
            "supported_environments",
            tuple(dict.fromkeys(self.supported_environments)),
        )

    def supports(self, target: "ToolExecutionTarget") -> bool:
        return (
            target.mode in self.supported_modes
            and target.strategy in self.supported_strategies
            and target.environment in self.supported_environments
        )


@dataclass(frozen=True, slots=True)
class ToolExecutionTarget(ValueObject):
    mode: ToolMode = ToolMode.INLINE
    strategy: ToolExecutionStrategy = ToolExecutionStrategy.ASYNC
    environment: ToolEnvironment = ToolEnvironment.LOCAL
