from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import json
from collections.abc import Sequence
from typing import Any

from crxzipple.shared.domain import ValueObject
from crxzipple.shared.content_blocks import (
    is_content_block,
    normalize_content_blocks,
    text_content_block,
)

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


class ToolDefinitionOrigin(StrEnum):
    LOCAL_DISCOVERY = "local_discovery"
    REMOTE_DISCOVERY = "remote_discovery"


class ToolCatalogSourceKind(StrEnum):
    LOCAL_PACKAGE = "local_package"
    MCP = "mcp"
    OPENAPI = "openapi"
    CLI = "cli"
    PROVIDER_BACKEND = "provider_backend"


class ToolSourceStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"
    DELETED = "deleted"


class ToolFunctionRuntimeKind(StrEnum):
    LOCAL = "local"
    REMOTE = "remote"
    SANDBOX = "sandbox"
    MCP = "mcp"
    OPENAPI = "openapi"
    CLI = "cli"
    PROVIDER_BACKEND = "provider_backend"


class ToolFunctionStatus(StrEnum):
    ACTIVE = "active"
    STALE = "stale"
    DEPRECATED = "deprecated"
    DISABLED = "disabled"
    DELETED = "deleted"


class ToolProviderCapability(StrEnum):
    IMAGE_GENERATION = "image_generation"
    WEB_SEARCH = "web_search"
    SPEECH = "speech"
    MEDIA = "media"
    BROWSER = "browser"
    CUSTOM = "custom"


class ToolProviderBackendStatus(StrEnum):
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"
    DELETED = "deleted"


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


class ToolRunAssignmentStatus(StrEnum):
    ASSIGNED = "assigned"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"
    EXPIRED = "expired"


class ToolWorkerStatus(StrEnum):
    ONLINE = "online"
    STALE = "stale"


@dataclass(frozen=True, slots=True)
class ToolRunResult(ValueObject):
    content: Any
    details: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        try:
            normalized_content = _normalize_tool_run_result_blocks(self.content)
        except ValueError as exc:
            raise ToolValidationError(
                str(exc),
            ) from exc
        object.__setattr__(self, "content", normalized_content)
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_payload(self) -> Any:
        payload = {
            _TOOL_RUN_RESULT_MARKER: True,
            "content": [dict(block) for block in self.blocks],
        }
        if self.details is not None:
            payload["details"] = self.details
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    @classmethod
    def from_payload(cls, payload: Any) -> "ToolRunResult":
        if isinstance(payload, dict) and payload.get(_TOOL_RUN_RESULT_MARKER) is True:
            metadata = payload.get("metadata")
            content = payload.get("content")
            return cls(
                content=content,
                details=payload.get("details"),
                metadata=dict(metadata) if isinstance(metadata, dict) else {},
            )
        raise ToolValidationError(
            "Tool run result payload is not in the standardized serialized format.",
        )

    @classmethod
    def structured(
        cls,
        *,
        content: Any,
        details: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ToolRunResult":
        return cls(
            content=content,
            details=details,
            metadata=dict(metadata or {}),
        )

    @classmethod
    def text(
        cls,
        text: str,
        *,
        details: Any | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> "ToolRunResult":
        return cls.structured(
            details=details,
            content=[text_content_block(text)],
            metadata=metadata,
        )

    @property
    def blocks(self) -> tuple[dict[str, Any], ...]:
        return tuple(dict(block) for block in self.content)


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


@dataclass(frozen=True, slots=True)
class ToolExecutionContext(ValueObject):
    attrs: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "attrs", dict(self.attrs))

    def to_payload(self) -> dict[str, Any]:
        return dict(self.attrs)

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "ToolExecutionContext | None":
        if payload is None:
            return None
        return cls(attrs=payload)

    def get_str(self, key: str) -> str | None:
        value = self.attrs.get(key)
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None


def _normalize_tool_run_result_blocks(value: Any) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        raise ValueError(
            "Tool run result content must be a non-empty content block sequence.",
        )
    normalized: list[dict[str, Any]] = []
    for item in value:
        if not is_content_block(item):
            raise ValueError(
                "Tool run result content must be a non-empty content block sequence.",
            )
        blocks = normalize_content_blocks([item])
        normalized.extend(dict(block) for block in blocks)
    if not normalized:
        raise ValueError(
            "Tool run result content must include at least one content block.",
        )
    return tuple(normalized)
