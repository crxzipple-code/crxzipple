from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from crxzipple.modules.orchestration.domain.exceptions import (
    OrchestrationValidationError,
)
from crxzipple.shared.domain import ValueObject
from crxzipple.shared.time import coerce_utc_datetime, format_datetime_utc


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class OrchestrationRunStatus(StrEnum):
    ACCEPTED = "accepted"
    QUEUED = "queued"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class OrchestrationIngressStatus(StrEnum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class OrchestrationIngressRequestKind(StrEnum):
    ROUTED_TURN = "routed_turn"
    BOUND_TURN = "bound_turn"


class OrchestrationExecutorLeaseStatus(StrEnum):
    ONLINE = "online"
    DRAINING = "draining"
    OFFLINE = "offline"


class OrchestrationRunStage(StrEnum):
    ACCEPTED = "accepted"
    ROUTED = "routed"
    BULK_READY = "bulk_ready"
    QUEUED = "queued"
    RUNNING = "running"
    LLM = "llm"
    TOOL = "tool"
    WAITING_ON_TOOL = "waiting_on_tool"
    WAITING_FOR_CONFIRMATION = "waiting_for_confirmation"
    FINALIZING = "finalizing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionChainStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionStepKind(StrEnum):
    INTAKE = "intake"
    PROMPT_RENDER = "prompt_render"
    LLM = "llm"
    TOOL_BATCH = "tool_batch"
    APPROVAL = "approval"
    TOOL_RESUME = "tool_resume"
    FINAL_RESPONSE = "final_response"
    ERROR = "error"
    MAINTENANCE = "maintenance"


class ExecutionStepStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ExecutionStepItemKind(StrEnum):
    LLM_INVOCATION = "llm_invocation"
    CONTINUATION_DECISION = "continuation_decision"
    TOOL_CALL = "tool_call"
    TOOL_RUN = "tool_run"
    TOOL_RESULT = "tool_result"
    APPROVAL_REQUEST = "approval_request"
    SESSION_MESSAGE = "session_message"
    CONTEXT_SNAPSHOT = "context_snapshot"


class ExecutionStepItemStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    WAITING = "waiting"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    LATE_OBSERVED = "late_observed"
    LATE_IGNORED = "late_ignored"


class ExecutionOwnerKind(StrEnum):
    ORCHESTRATION_RUN = "orchestration_run"
    ORCHESTRATION_INGRESS_REQUEST = "orchestration_ingress_request"
    DISPATCH_TASK = "dispatch_task"
    LLM_INVOCATION = "llm_invocation"
    LLM_CONTINUATION = "llm_continuation"
    TOOL_CALL = "tool_call"
    TOOL_RUN = "tool_run"
    SESSION_ITEM = "session_item"
    SESSION_MESSAGE = "session_message"
    APPROVAL_REQUEST = "approval_request"


class OrchestrationQueuePolicy(StrEnum):
    FIFO = "fifo"
    JUMP_QUEUE = "jump_queue"
    LANE_JUMP_QUEUE = "lane_jump_queue"
    RESUME_FIRST = "resume_first"


class CapabilityRequestScopeHint(StrEnum):
    ONCE = "once"
    SESSION = "session"
    AGENT_DEFAULT = "agent_default"


class ApprovalDecision(StrEnum):
    ALLOW_ONCE = "allow_once"
    ALLOW_FOR_SESSION = "allow_for_session"
    ALWAYS_FOR_AGENT = "always_for_agent"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class ExecutionOwnerReference(ValueObject):
    owner_kind: str
    owner_id: str

    def __post_init__(self) -> None:
        owner_kind = self.owner_kind.strip()
        owner_id = self.owner_id.strip()
        if not owner_kind:
            raise OrchestrationValidationError(
                "Execution owner reference owner_kind cannot be empty.",
            )
        if not owner_id:
            raise OrchestrationValidationError(
                "Execution owner reference owner_id cannot be empty.",
            )
        object.__setattr__(self, "owner_kind", owner_kind)
        object.__setattr__(self, "owner_id", owner_id)

    def to_payload(self) -> dict[str, str]:
        return {
            "owner_kind": self.owner_kind,
            "owner_id": self.owner_id,
        }

    @classmethod
    def of(
        cls,
        owner_kind: ExecutionOwnerKind | str,
        owner_id: str,
    ) -> "ExecutionOwnerReference":
        raw_kind = owner_kind.value if isinstance(owner_kind, ExecutionOwnerKind) else owner_kind
        return cls(owner_kind=raw_kind, owner_id=owner_id)

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> "ExecutionOwnerReference | None":
        if not payload:
            return None
        owner_kind = payload.get("owner_kind")
        owner_id = payload.get("owner_id")
        if owner_kind is None or owner_id is None:
            return None
        return cls(owner_kind=str(owner_kind), owner_id=str(owner_id))

    @classmethod
    def llm_invocation(cls, invocation_id: str) -> "ExecutionOwnerReference":
        return cls.of(ExecutionOwnerKind.LLM_INVOCATION, invocation_id)

    @classmethod
    def llm_continuation(cls, continuation_id: str) -> "ExecutionOwnerReference":
        return cls.of(ExecutionOwnerKind.LLM_CONTINUATION, continuation_id)

    @classmethod
    def tool_call(cls, tool_call_id: str) -> "ExecutionOwnerReference":
        return cls.of(ExecutionOwnerKind.TOOL_CALL, tool_call_id)

    @classmethod
    def tool_run(cls, tool_run_id: str) -> "ExecutionOwnerReference":
        return cls.of(ExecutionOwnerKind.TOOL_RUN, tool_run_id)

    @classmethod
    def session_item(cls, item_id: str) -> "ExecutionOwnerReference":
        return cls.of(ExecutionOwnerKind.SESSION_ITEM, item_id)

    @classmethod
    def session_message(cls, message_id: str) -> "ExecutionOwnerReference":
        return cls.of(ExecutionOwnerKind.SESSION_MESSAGE, message_id)


@dataclass(frozen=True, slots=True)
class ContinuationDecision(ValueObject):
    llm_invocation_id: str
    continuation_id: str
    reason: str | None = None
    end_turn: bool | None = None
    needs_follow_up: bool | None = None

    def __post_init__(self) -> None:
        llm_invocation_id = self.llm_invocation_id.strip()
        continuation_id = self.continuation_id.strip()
        if not llm_invocation_id:
            raise OrchestrationValidationError(
                "Continuation decision llm_invocation_id cannot be empty.",
            )
        if not continuation_id:
            raise OrchestrationValidationError(
                "Continuation decision continuation_id cannot be empty.",
            )
        reason = self.reason.strip() if isinstance(self.reason, str) else self.reason
        object.__setattr__(self, "llm_invocation_id", llm_invocation_id)
        object.__setattr__(self, "continuation_id", continuation_id)
        object.__setattr__(self, "reason", reason or None)

    @classmethod
    def from_payload(
        cls,
        *,
        llm_invocation_id: str,
        continuation_id: str,
        payload: dict[str, object],
    ) -> "ContinuationDecision":
        reason_value = payload.get("reason")
        end_turn_value = payload.get("end_turn")
        return cls(
            llm_invocation_id=llm_invocation_id,
            continuation_id=continuation_id,
            reason=reason_value if isinstance(reason_value, str) else None,
            end_turn=end_turn_value if isinstance(end_turn_value, bool) else None,
            needs_follow_up=(
                bool(payload["needs_follow_up"])
                if "needs_follow_up" in payload
                else None
            ),
        )

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "llm_invocation_id": self.llm_invocation_id,
            "continuation_id": self.continuation_id,
        }
        if self.reason is not None:
            payload["reason"] = self.reason
        if self.end_turn is not None:
            payload["end_turn"] = self.end_turn
        if self.needs_follow_up is not None:
            payload["needs_follow_up"] = self.needs_follow_up
        return payload


@dataclass(frozen=True, slots=True)
class OrchestrationBoundSessionTarget(ValueObject):
    agent_id: str
    session_key: str
    active_session_id: str
    lane_key: str | None = None

    def __post_init__(self) -> None:
        if not self.agent_id.strip():
            raise OrchestrationValidationError(
                "Bound session target agent_id cannot be empty.",
            )
        if not self.session_key.strip():
            raise OrchestrationValidationError(
                "Bound session target session_key cannot be empty.",
            )
        if not self.active_session_id.strip():
            raise OrchestrationValidationError(
                "Bound session target active_session_id cannot be empty.",
            )
        object.__setattr__(self, "lane_key", self._normalize_optional(self.lane_key))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "agent_id": self.agent_id,
            "session_key": self.session_key,
            "active_session_id": self.active_session_id,
        }
        if self.lane_key is not None:
            payload["lane_key"] = self.lane_key
        return payload

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> "OrchestrationBoundSessionTarget | None":
        if not payload:
            return None
        return cls(
            agent_id=str(payload.get("agent_id", "")),
            session_key=str(payload.get("session_key", "")),
            active_session_id=str(payload.get("active_session_id", "")),
            lane_key=(
                str(payload["lane_key"])
                if payload.get("lane_key") is not None
                else None
            ),
        )

    @staticmethod
    def _normalize_optional(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


@dataclass(frozen=True, slots=True)
class InboundInstruction(ValueObject):
    source: str
    content: Any | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.source.strip():
            raise OrchestrationValidationError("Inbound instruction source cannot be empty.")
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "source": self.source,
            "metadata": dict(self.metadata),
        }
        if self.content is not None:
            payload["content"] = self.content
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "InboundInstruction":
        payload = payload or {}
        return cls(
            source=str(payload.get("source", "")),
            content=payload.get("content"),
            metadata=(
                dict(payload.get("metadata"))
                if isinstance(payload.get("metadata"), dict)
                else {}
            ),
        )


@dataclass(frozen=True, slots=True)
class ReplyTarget(ValueObject):
    interface_name: str
    address: str | None = None
    reply_to: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.interface_name.strip():
            raise OrchestrationValidationError("Reply target interface_name cannot be empty.")
        object.__setattr__(self, "address", self.address if self.address is None else str(self.address))
        object.__setattr__(self, "reply_to", self.reply_to if self.reply_to is None else str(self.reply_to))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "interface_name": self.interface_name,
            "metadata": dict(self.metadata),
        }
        if self.address is not None:
            payload["address"] = self.address
        if self.reply_to is not None:
            payload["reply_to"] = self.reply_to
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "ReplyTarget | None":
        if not payload:
            return None
        return cls(
            interface_name=str(payload.get("interface_name", "")),
            address=(
                str(payload["address"])
                if payload.get("address") is not None
                else None
            ),
            reply_to=(
                str(payload["reply_to"])
                if payload.get("reply_to") is not None
                else None
            ),
            metadata=(
                dict(payload.get("metadata"))
                if isinstance(payload.get("metadata"), dict)
                else {}
            ),
        )

@dataclass(frozen=True, slots=True)
class OrchestrationErrorPayload(ValueObject):
    message: str
    code: str = "orchestration_failed"
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise OrchestrationValidationError(
                "Orchestration error payload message cannot be empty.",
            )
        if not self.code.strip():
            raise OrchestrationValidationError(
                "Orchestration error payload code cannot be empty.",
            )
        object.__setattr__(self, "details", dict(self.details))

    def to_payload(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "code": self.code,
            "details": dict(self.details),
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> "OrchestrationErrorPayload | None":
        if not payload:
            return None
        return cls(
            message=str(payload.get("message", "")),
            code=str(payload.get("code", "orchestration_failed")),
            details=(
                dict(payload.get("details"))
                if isinstance(payload.get("details"), dict)
                else {}
            ),
        )


@dataclass(frozen=True, slots=True)
class PendingApprovalRequest(ValueObject):
    request_id: str
    effect_id: str
    label: str
    reason: str = ""
    tool_ids: tuple[str, ...] = field(default_factory=tuple)
    tool_name: str | None = None
    tool_arguments: dict[str, Any] = field(default_factory=dict)
    execution_mode: str | None = None
    execution_strategy: str | None = None
    execution_environment: str | None = None
    scope_hint: CapabilityRequestScopeHint | None = None
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise OrchestrationValidationError(
                "Pending approval request_id cannot be empty.",
            )
        if not self.effect_id.strip():
            raise OrchestrationValidationError(
                "Pending approval effect_id cannot be empty.",
            )
        if not self.label.strip():
            raise OrchestrationValidationError(
                "Pending approval label cannot be empty.",
            )
        object.__setattr__(
            self,
            "tool_ids",
            tuple(
                tool_id.strip()
                for tool_id in self.tool_ids
                if tool_id is not None and tool_id.strip()
            ),
        )
        object.__setattr__(self, "tool_arguments", dict(self.tool_arguments))
        object.__setattr__(
            self,
            "tool_name",
            self.tool_name.strip() if self.tool_name is not None and self.tool_name.strip() else None,
        )
        object.__setattr__(
            self,
            "execution_mode",
            (
                self.execution_mode.strip()
                if self.execution_mode is not None and self.execution_mode.strip()
                else None
            ),
        )
        object.__setattr__(
            self,
            "execution_strategy",
            (
                self.execution_strategy.strip()
                if self.execution_strategy is not None and self.execution_strategy.strip()
                else None
            ),
        )
        object.__setattr__(
            self,
            "execution_environment",
            (
                self.execution_environment.strip()
                if self.execution_environment is not None and self.execution_environment.strip()
                else None
            ),
        )

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "request_id": self.request_id,
            "effect_id": self.effect_id,
            "label": self.label,
            "reason": self.reason,
            "tool_ids": list(self.tool_ids),
            "tool_arguments": dict(self.tool_arguments),
            "created_at": format_datetime_utc(self.created_at),
        }
        if self.tool_name is not None:
            payload["tool_name"] = self.tool_name
        if self.execution_mode is not None:
            payload["execution_mode"] = self.execution_mode
        if self.execution_strategy is not None:
            payload["execution_strategy"] = self.execution_strategy
        if self.execution_environment is not None:
            payload["execution_environment"] = self.execution_environment
        if self.scope_hint is not None:
            payload["scope_hint"] = self.scope_hint.value
        return payload

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> "PendingApprovalRequest | None":
        if not payload:
            return None
        raw_scope_hint = payload.get("scope_hint")
        return cls(
            request_id=str(payload.get("request_id", "")),
            effect_id=str(payload.get("effect_id", "")),
            label=str(payload.get("label", "")),
            reason=str(payload.get("reason", "")),
            tool_ids=tuple(payload.get("tool_ids", ()) or ()),
            tool_name=(
                str(payload.get("tool_name", "")).strip() or None
                if payload.get("tool_name") is not None
                else None
            ),
            tool_arguments=(
                dict(payload.get("tool_arguments"))
                if isinstance(payload.get("tool_arguments"), dict)
                else {}
            ),
            execution_mode=(
                str(payload.get("execution_mode", "")).strip() or None
                if payload.get("execution_mode") is not None
                else None
            ),
            execution_strategy=(
                str(payload.get("execution_strategy", "")).strip() or None
                if payload.get("execution_strategy") is not None
                else None
            ),
            execution_environment=(
                str(payload.get("execution_environment", "")).strip() or None
                if payload.get("execution_environment") is not None
                else None
            ),
            scope_hint=(
                CapabilityRequestScopeHint(str(raw_scope_hint))
                if raw_scope_hint is not None and str(raw_scope_hint).strip()
                else None
            ),
            created_at=(
                coerce_utc_datetime(
                    datetime.fromisoformat(str(payload["created_at"])),
                )
                if payload.get("created_at") is not None
                else utcnow()
            ),
        )


@dataclass(frozen=True, slots=True)
class ApprovalResolution(ValueObject):
    request_id: str
    decision: ApprovalDecision
    resolved_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.request_id.strip():
            raise OrchestrationValidationError(
                "Approval resolution request_id cannot be empty.",
            )

    def to_payload(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "decision": self.decision.value,
            "resolved_at": format_datetime_utc(self.resolved_at),
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> "ApprovalResolution | None":
        if not payload:
            return None
        return cls(
            request_id=str(payload.get("request_id", "")),
            decision=ApprovalDecision(str(payload.get("decision", ApprovalDecision.DENY.value))),
            resolved_at=(
                coerce_utc_datetime(
                    datetime.fromisoformat(str(payload["resolved_at"])),
                )
                if payload.get("resolved_at") is not None
                else utcnow()
            ),
        )
