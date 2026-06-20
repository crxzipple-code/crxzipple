from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any

from crxzipple.modules.llm.domain.exceptions import LlmValidationError
from crxzipple.shared.domain import ValueObject


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LlmProviderKind(StrEnum):
    OPENAI = "openai"
    OPENAI_CODEX = "openai_codex"
    OPENAI_COMPATIBLE = "openai_compatible"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"


class LlmApiFamily(StrEnum):
    OPENAI_RESPONSES = "openai_responses"
    OPENAI_CODEX_RESPONSES = "openai_codex_responses"
    OPENAI_CHAT_COMPATIBLE = "openai_chat_compatible"
    ANTHROPIC_MESSAGES = "anthropic_messages"
    GEMINI_GENERATE_CONTENT = "gemini_generate_content"
    OLLAMA_NATIVE = "ollama_native"


class LlmModelFamily(StrEnum):
    GENERAL = "general"
    CODEX = "codex"
    REASONING = "reasoning"
    VISION = "vision"


class LlmCapability(StrEnum):
    TOOL_CALLING = "tool_calling"
    STRUCTURED_OUTPUT = "structured_output"
    VISION_INPUT = "vision_input"
    STREAMING = "streaming"
    REASONING = "reasoning"
    PROVIDER_NATIVE_CONTINUATION = "provider_native_continuation"
    PROVIDER_WEBSOCKET_TRANSPORT = "provider_websocket_transport"
    PROVIDER_INCREMENTAL_INPUT = "provider_incremental_input"


class LlmSourceKind(StrEnum):
    MANUAL = "manual"
    DISCOVERED = "discovered"
    IMPORTED = "imported"


class LlmInvocationStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class LlmMessageRole(StrEnum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class LlmResponseItemKind(StrEnum):
    ASSISTANT_MESSAGE = "assistant_message"
    REASONING = "reasoning"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    STRUCTURED_OUTPUT = "structured_output"
    PROVIDER_EXTERNAL_ITEM = "provider_external_item"
    COMPACTION = "compaction"
    UNKNOWN = "unknown"


class LlmInputItemKind(StrEnum):
    MESSAGE = "message"
    FUNCTION_CALL = "function_call"
    FUNCTION_CALL_OUTPUT = "function_call_output"
    REASONING = "reasoning"
    PROVIDER_EXTERNAL_ITEM = "provider_external_item"


class LlmMessagePhase(StrEnum):
    COMMENTARY = "commentary"
    FINAL_ANSWER = "final_answer"
    UNKNOWN = "unknown"


class LlmResponseEventType(StrEnum):
    INVOCATION_STARTED = "invocation_started"
    ITEM_STARTED = "item_started"
    TEXT_DELTA = "text_delta"
    REASONING_SUMMARY_DELTA = "reasoning_summary_delta"
    REASONING_RAW_DELTA = "reasoning_raw_delta"
    TOOL_ARGUMENT_DELTA = "tool_argument_delta"
    ITEM_COMPLETED = "item_completed"
    COMPLETED = "completed"
    FAILED = "failed"


class LlmContinuationReason(StrEnum):
    NONE = "none"
    TOOL_CALL = "tool_call"
    PROVIDER_END_TURN_FALSE = "provider_end_turn_false"
    TOOL_ERROR_RESPONSE = "tool_error_response"
    PENDING_EXTERNAL = "pending_external"


@dataclass(frozen=True, slots=True)
class LlmDefaults(ValueObject):
    temperature: float | None = None
    top_p: float | None = None
    max_output_tokens: int | None = None
    reasoning_effort: str | None = None
    provider_transport: str | None = None
    extra_body: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.max_output_tokens is not None and self.max_output_tokens <= 0:
            raise LlmValidationError(
                "LLM max_output_tokens must be greater than zero.",
            )
        if self.provider_transport is not None:
            normalized_transport = self.provider_transport.strip().lower()
            if normalized_transport not in {"auto", "http", "websocket"}:
                raise LlmValidationError(
                    "LLM provider_transport must be auto, http, or websocket.",
                )
            object.__setattr__(self, "provider_transport", normalized_transport)
        object.__setattr__(self, "extra_body", dict(self.extra_body))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.temperature is not None:
            payload["temperature"] = self.temperature
        if self.top_p is not None:
            payload["top_p"] = self.top_p
        if self.max_output_tokens is not None:
            payload["max_output_tokens"] = self.max_output_tokens
        if self.reasoning_effort is not None:
            payload["reasoning_effort"] = self.reasoning_effort
        if self.provider_transport is not None:
            payload["provider_transport"] = self.provider_transport
        if self.extra_body:
            payload["extra_body"] = dict(self.extra_body)
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "LlmDefaults":
        payload = payload or {}
        extra_body_raw = payload.get("extra_body")
        if extra_body_raw is None:
            extra_body: dict[str, Any] = {}
        elif isinstance(extra_body_raw, dict):
            extra_body = dict(extra_body_raw)
        else:
            raise LlmValidationError("LLM extra_body must decode to an object.")
        return cls(
            temperature=(
                float(payload["temperature"])
                if payload.get("temperature") is not None
                else None
            ),
            top_p=float(payload["top_p"]) if payload.get("top_p") is not None else None,
            max_output_tokens=(
                int(payload["max_output_tokens"])
                if payload.get("max_output_tokens") is not None
                else None
            ),
            reasoning_effort=(
                str(payload["reasoning_effort"])
                if payload.get("reasoning_effort") is not None
                else None
            ),
            provider_transport=(
                str(payload["provider_transport"])
                if payload.get("provider_transport") is not None
                else None
            ),
            extra_body=extra_body,
        )


@dataclass(frozen=True, slots=True)
class LlmMessage(ValueObject):
    role: LlmMessageRole
    content: Any
    name: str | None = None
    tool_call_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "role": self.role.value,
            "content": self.content,
        }
        if self.name is not None:
            payload["name"] = self.name
        if self.tool_call_id is not None:
            payload["tool_call_id"] = self.tool_call_id
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LlmMessage":
        return cls(
            role=LlmMessageRole(payload["role"]),
            content=payload.get("content"),
            name=payload.get("name"),
            tool_call_id=payload.get("tool_call_id"),
            metadata=(
                dict(payload.get("metadata"))
                if isinstance(payload.get("metadata"), dict)
                else {}
            ),
        )


@dataclass(frozen=True, slots=True)
class LlmInputItem(ValueObject):
    kind: LlmInputItemKind
    payload: dict[str, Any]
    source: str = "projection"
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "payload", dict(self.payload))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "kind": self.kind.value,
            "payload": dict(self.payload),
            "source": self.source,
        }
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LlmInputItem":
        return cls(
            kind=LlmInputItemKind(str(payload.get("kind", "message"))),
            payload=(
                dict(payload.get("payload"))
                if isinstance(payload.get("payload"), dict)
                else {}
            ),
            source=str(payload.get("source") or "projection"),
            metadata=(
                dict(payload.get("metadata"))
                if isinstance(payload.get("metadata"), dict)
                else {}
            ),
        )


@dataclass(frozen=True, slots=True)
class ToolSchema(ValueObject):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise LlmValidationError("Tool schema name cannot be empty.")
        object.__setattr__(self, "input_schema", dict(self.input_schema))

    def to_payload(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": dict(self.input_schema),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ToolSchema":
        return cls(
            name=str(payload.get("name", "")),
            description=str(payload.get("description", "")),
            input_schema=(
                dict(payload.get("input_schema"))
                if isinstance(payload.get("input_schema"), dict)
                else {}
            ),
        )


@dataclass(frozen=True, slots=True)
class ToolCallIntent(ValueObject):
    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise LlmValidationError("Tool call id cannot be empty.")
        if not self.name.strip():
            raise LlmValidationError("Tool call name cannot be empty.")
        object.__setattr__(self, "arguments", dict(self.arguments))

    def to_payload(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "arguments": dict(self.arguments),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "ToolCallIntent":
        return cls(
            id=str(payload.get("id", "")),
            name=str(payload.get("name", "")),
            arguments=(
                dict(payload.get("arguments"))
                if isinstance(payload.get("arguments"), dict)
                else {}
            ),
        )


@dataclass(frozen=True, slots=True)
class LlmUsage(ValueObject):
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None
    reasoning_tokens: int | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.input_tokens is not None:
            payload["input_tokens"] = self.input_tokens
        if self.output_tokens is not None:
            payload["output_tokens"] = self.output_tokens
        if self.total_tokens is not None:
            payload["total_tokens"] = self.total_tokens
        if self.reasoning_tokens is not None:
            payload["reasoning_tokens"] = self.reasoning_tokens
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "LlmUsage | None":
        if not payload:
            return None
        return cls(
            input_tokens=(
                int(payload["input_tokens"])
                if payload.get("input_tokens") is not None
                else None
            ),
            output_tokens=(
                int(payload["output_tokens"])
                if payload.get("output_tokens") is not None
                else None
            ),
            total_tokens=(
                int(payload["total_tokens"])
                if payload.get("total_tokens") is not None
                else None
            ),
            reasoning_tokens=(
                int(payload["reasoning_tokens"])
                if payload.get("reasoning_tokens") is not None
                else None
            ),
        )


@dataclass(frozen=True, slots=True)
class LlmResult(ValueObject):
    text: str | None = None
    tool_calls: tuple[ToolCallIntent, ...] = field(default_factory=tuple)
    structured_output: Any | None = None
    usage: LlmUsage | None = None
    finish_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tool_calls", tuple(self.tool_calls))
        object.__setattr__(self, "metadata", dict(self.metadata))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "tool_calls": [tool_call.to_payload() for tool_call in self.tool_calls],
            "metadata": dict(self.metadata),
        }
        if self.text is not None:
            payload["text"] = self.text
        if self.structured_output is not None:
            payload["structured_output"] = self.structured_output
        if self.usage is not None:
            payload["usage"] = self.usage.to_payload()
        if self.finish_reason is not None:
            payload["finish_reason"] = self.finish_reason
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "LlmResult | None":
        if not payload:
            return None
        tool_calls_raw = payload.get("tool_calls")
        return cls(
            text=payload.get("text"),
            tool_calls=tuple(
                ToolCallIntent.from_payload(item)
                for item in tool_calls_raw
                if isinstance(item, dict)
            )
            if isinstance(tool_calls_raw, list)
            else (),
            structured_output=payload.get("structured_output"),
            usage=LlmUsage.from_payload(payload.get("usage")),
            finish_reason=payload.get("finish_reason"),
            metadata=(
                dict(payload.get("metadata"))
                if isinstance(payload.get("metadata"), dict)
                else {}
            ),
        )

    @classmethod
    def from_response_items(
        cls,
        response_items: tuple["LlmResponseItem", ...],
        *,
        usage: LlmUsage | None = None,
        finish_reason: str | None = None,
        metadata: dict[str, Any] | None = None,
        structured_output: Any | None = None,
        text_fallback: str | None = None,
    ) -> "LlmResult":
        text_fragments: list[str] = []
        tool_calls: list[ToolCallIntent] = []
        for item in response_items:
            if item.kind is LlmResponseItemKind.ASSISTANT_MESSAGE:
                text = _response_item_text(item)
                if text is not None:
                    text_fragments.append(text)
                continue
            if item.kind is LlmResponseItemKind.TOOL_CALL and item.tool_name:
                arguments = item.content_payload.get("arguments")
                tool_calls.append(
                    ToolCallIntent(
                        id=item.call_id or item.provider_item_id or item.id,
                        name=item.tool_name,
                        arguments=dict(arguments) if isinstance(arguments, dict) else {},
                    ),
                )
        text = "".join(text_fragments) or text_fallback
        return cls(
            text=text or None,
            tool_calls=tuple(tool_calls),
            structured_output=structured_output,
            usage=usage,
            finish_reason=finish_reason,
            metadata=dict(metadata or {}),
        )


@dataclass(frozen=True, slots=True)
class LlmResponseItem(ValueObject):
    id: str
    invocation_id: str
    sequence_no: int
    kind: LlmResponseItemKind
    role: LlmMessageRole | None = None
    phase: LlmMessagePhase = LlmMessagePhase.UNKNOWN
    content_payload: dict[str, Any] = field(default_factory=dict)
    provider_payload: dict[str, Any] = field(default_factory=dict)
    provider_item_id: str | None = None
    provider_item_type: str | None = None
    call_id: str | None = None
    tool_name: str | None = None
    provider_replay_candidate: bool = True
    user_timeline_candidate: bool = False
    created_at: datetime = field(default_factory=utcnow)
    completed_at: datetime | None = None

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise LlmValidationError("LLM response item id cannot be empty.")
        if not self.invocation_id.strip():
            raise LlmValidationError("LLM response item invocation_id cannot be empty.")
        if self.sequence_no < 0:
            raise LlmValidationError("LLM response item sequence_no cannot be negative.")
        object.__setattr__(self, "content_payload", dict(self.content_payload))
        object.__setattr__(self, "provider_payload", dict(self.provider_payload))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "invocation_id": self.invocation_id,
            "sequence_no": self.sequence_no,
            "kind": self.kind.value,
            "phase": self.phase.value,
            "content_payload": dict(self.content_payload),
            "provider_payload": dict(self.provider_payload),
            "provider_replay_candidate": self.provider_replay_candidate,
            "user_timeline_candidate": self.user_timeline_candidate,
            "created_at": self.created_at.isoformat(),
        }
        if self.role is not None:
            payload["role"] = self.role.value
        if self.provider_item_id is not None:
            payload["provider_item_id"] = self.provider_item_id
        if self.provider_item_type is not None:
            payload["provider_item_type"] = self.provider_item_type
        if self.call_id is not None:
            payload["call_id"] = self.call_id
        if self.tool_name is not None:
            payload["tool_name"] = self.tool_name
        if self.completed_at is not None:
            payload["completed_at"] = self.completed_at.isoformat()
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LlmResponseItem":
        return cls(
            id=str(payload.get("id", "")),
            invocation_id=str(payload.get("invocation_id", "")),
            sequence_no=int(payload.get("sequence_no", 0)),
            kind=LlmResponseItemKind(str(payload.get("kind", LlmResponseItemKind.UNKNOWN))),
            role=(
                LlmMessageRole(str(payload["role"]))
                if payload.get("role") is not None
                else None
            ),
            phase=LlmMessagePhase(str(payload.get("phase", LlmMessagePhase.UNKNOWN))),
            content_payload=(
                dict(payload.get("content_payload"))
                if isinstance(payload.get("content_payload"), dict)
                else {}
            ),
            provider_payload=(
                dict(payload.get("provider_payload"))
                if isinstance(payload.get("provider_payload"), dict)
                else {}
            ),
            provider_item_id=(
                str(payload["provider_item_id"])
                if payload.get("provider_item_id") is not None
                else None
            ),
            provider_item_type=(
                str(payload["provider_item_type"])
                if payload.get("provider_item_type") is not None
                else None
            ),
            call_id=str(payload["call_id"]) if payload.get("call_id") is not None else None,
            tool_name=(
                str(payload["tool_name"]) if payload.get("tool_name") is not None else None
            ),
            provider_replay_candidate=bool(payload.get("provider_replay_candidate", True)),
            user_timeline_candidate=bool(payload.get("user_timeline_candidate", False)),
            created_at=_datetime_from_payload(payload.get("created_at")) or utcnow(),
            completed_at=_datetime_from_payload(payload.get("completed_at")),
        )


def _response_item_text(item: LlmResponseItem) -> str | None:
    text = item.content_payload.get("text")
    if text is not None:
        return str(text)
    summary = item.content_payload.get("summary")
    if isinstance(summary, str):
        return summary
    if isinstance(summary, list):
        fragments: list[str] = []
        for block in summary:
            if isinstance(block, dict) and block.get("text") is not None:
                fragments.append(str(block.get("text")))
            elif isinstance(block, str):
                fragments.append(block)
        return "".join(fragments) or None
    return None


@dataclass(frozen=True, slots=True)
class LlmResponseEvent(ValueObject):
    id: str
    invocation_id: str
    sequence_no: int
    type: LlmResponseEventType
    item_id: str | None = None
    delta_payload: dict[str, Any] = field(default_factory=dict)
    provider_payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise LlmValidationError("LLM response event id cannot be empty.")
        if not self.invocation_id.strip():
            raise LlmValidationError("LLM response event invocation_id cannot be empty.")
        if self.sequence_no < 0:
            raise LlmValidationError("LLM response event sequence_no cannot be negative.")
        object.__setattr__(self, "delta_payload", dict(self.delta_payload))
        object.__setattr__(self, "provider_payload", dict(self.provider_payload))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.id,
            "invocation_id": self.invocation_id,
            "sequence_no": self.sequence_no,
            "type": self.type.value,
            "delta_payload": dict(self.delta_payload),
            "provider_payload": dict(self.provider_payload),
            "created_at": self.created_at.isoformat(),
        }
        if self.item_id is not None:
            payload["item_id"] = self.item_id
        return payload

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "LlmResponseEvent":
        return cls(
            id=str(payload.get("id", "")),
            invocation_id=str(payload.get("invocation_id", "")),
            sequence_no=int(payload.get("sequence_no", 0)),
            type=LlmResponseEventType(str(payload.get("type", LlmResponseEventType.FAILED))),
            item_id=str(payload["item_id"]) if payload.get("item_id") is not None else None,
            delta_payload=(
                dict(payload.get("delta_payload"))
                if isinstance(payload.get("delta_payload"), dict)
                else {}
            ),
            provider_payload=(
                dict(payload.get("provider_payload"))
                if isinstance(payload.get("provider_payload"), dict)
                else {}
            ),
            created_at=_datetime_from_payload(payload.get("created_at")) or utcnow(),
        )


@dataclass(frozen=True, slots=True)
class LlmResponseEventRetentionPolicy(ValueObject):
    full_event_window_seconds: int
    detail_event_limit: int
    durable_fact: str
    overflow_action: str

    def __post_init__(self) -> None:
        if self.full_event_window_seconds <= 0:
            raise LlmValidationError(
                "LLM response event retention window must be greater than zero.",
            )
        if self.detail_event_limit <= 0:
            raise LlmValidationError(
                "LLM response event detail limit must be greater than zero.",
            )
        object.__setattr__(self, "durable_fact", str(self.durable_fact).strip())
        object.__setattr__(self, "overflow_action", str(self.overflow_action).strip())
        if not self.durable_fact:
            raise LlmValidationError("LLM response event durable fact cannot be empty.")
        if not self.overflow_action:
            raise LlmValidationError("LLM response event overflow action cannot be empty.")

    def to_payload(self) -> dict[str, Any]:
        return {
            "full_event_window_seconds": self.full_event_window_seconds,
            "detail_event_limit": self.detail_event_limit,
            "durable_fact": self.durable_fact,
            "overflow_action": self.overflow_action,
        }

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any],
    ) -> "LlmResponseEventRetentionPolicy":
        return cls(
            full_event_window_seconds=int(payload.get("full_event_window_seconds", 0)),
            detail_event_limit=int(payload.get("detail_event_limit", 0)),
            durable_fact=str(payload.get("durable_fact", "")),
            overflow_action=str(payload.get("overflow_action", "")),
        )


@dataclass(frozen=True, slots=True)
class LlmContinuationSignal(ValueObject):
    end_turn: bool | None = None
    needs_follow_up: bool = False
    reason: LlmContinuationReason = LlmContinuationReason.NONE
    provider_payload: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "provider_payload", dict(self.provider_payload))

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "needs_follow_up": self.needs_follow_up,
            "reason": self.reason.value,
            "provider_payload": dict(self.provider_payload),
        }
        if self.end_turn is not None:
            payload["end_turn"] = self.end_turn
        return payload

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> "LlmContinuationSignal | None":
        if not payload:
            return None
        return cls(
            end_turn=(
                bool(payload["end_turn"]) if payload.get("end_turn") is not None else None
            ),
            needs_follow_up=bool(payload.get("needs_follow_up", False)),
            reason=LlmContinuationReason(
                str(payload.get("reason", LlmContinuationReason.NONE)),
            ),
            provider_payload=(
                dict(payload.get("provider_payload"))
                if isinstance(payload.get("provider_payload"), dict)
                else {}
            ),
        )


@dataclass(frozen=True, slots=True)
class LlmProviderContinuation(ValueObject):
    mode: str
    previous_response_id: str | None = None
    previous_invocation_id: str | None = None
    provider_family: str | None = None
    transport: str | None = None
    input_item_fingerprints: tuple[str, ...] = field(default_factory=tuple)
    input_item_count: int | None = None
    instructions_fingerprint: str | None = None
    tool_fingerprints: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        mode = self.mode.strip()
        if not mode:
            raise LlmValidationError("LLM provider continuation mode cannot be empty.")
        object.__setattr__(self, "mode", mode)
        object.__setattr__(
            self,
            "previous_response_id",
            _optional_stripped_text(self.previous_response_id),
        )
        object.__setattr__(
            self,
            "previous_invocation_id",
            _optional_stripped_text(self.previous_invocation_id),
        )
        object.__setattr__(
            self,
            "provider_family",
            _optional_stripped_text(self.provider_family),
        )
        object.__setattr__(
            self,
            "transport",
            _optional_stripped_text(self.transport),
        )
        object.__setattr__(
            self,
            "input_item_fingerprints",
            tuple(
                fingerprint.strip()
                for fingerprint in self.input_item_fingerprints
                if isinstance(fingerprint, str) and fingerprint.strip()
            ),
        )
        object.__setattr__(
            self,
            "instructions_fingerprint",
            _optional_stripped_text(self.instructions_fingerprint),
        )
        object.__setattr__(
            self,
            "tool_fingerprints",
            tuple(
                fingerprint.strip()
                for fingerprint in self.tool_fingerprints
                if isinstance(fingerprint, str) and fingerprint.strip()
            ),
        )
        if self.input_item_count is not None and self.input_item_count < 0:
            raise LlmValidationError(
                "LLM provider continuation input_item_count cannot be negative.",
            )

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"mode": self.mode}
        if self.previous_response_id is not None:
            payload["previous_response_id"] = self.previous_response_id
        if self.previous_invocation_id is not None:
            payload["previous_invocation_id"] = self.previous_invocation_id
        if self.provider_family is not None:
            payload["provider_family"] = self.provider_family
        if self.transport is not None:
            payload["transport"] = self.transport
        if self.input_item_fingerprints:
            payload["input_item_fingerprints"] = list(self.input_item_fingerprints)
        if self.input_item_count is not None:
            payload["input_item_count"] = self.input_item_count
        if self.instructions_fingerprint is not None:
            payload["instructions_fingerprint"] = self.instructions_fingerprint
        if self.tool_fingerprints:
            payload["tool_fingerprints"] = list(self.tool_fingerprints)
        return payload

    @classmethod
    def from_payload(
        cls,
        payload: dict[str, Any] | None,
    ) -> "LlmProviderContinuation | None":
        if not payload:
            return None
        return cls(
            mode=str(payload.get("mode") or ""),
            previous_response_id=(
                str(payload["previous_response_id"])
                if payload.get("previous_response_id") is not None
                else None
            ),
            previous_invocation_id=(
                str(payload["previous_invocation_id"])
                if payload.get("previous_invocation_id") is not None
                else None
            ),
            provider_family=(
                str(payload["provider_family"])
                if payload.get("provider_family") is not None
                else None
            ),
            transport=(
                str(payload["transport"])
                if payload.get("transport") is not None
                else None
            ),
            input_item_fingerprints=tuple(
                str(item)
                for item in payload.get("input_item_fingerprints", ())
                if isinstance(item, str) and item.strip()
            )
            if isinstance(payload.get("input_item_fingerprints"), list | tuple)
            else (),
            input_item_count=(
                int(payload["input_item_count"])
                if payload.get("input_item_count") is not None
                else None
            ),
            instructions_fingerprint=(
                str(payload["instructions_fingerprint"])
                if payload.get("instructions_fingerprint") is not None
                else None
            ),
            tool_fingerprints=tuple(
                str(item)
                for item in payload.get("tool_fingerprints", ())
                if isinstance(item, str) and item.strip()
            )
            if isinstance(payload.get("tool_fingerprints"), list | tuple)
            else (),
        )


def _optional_stripped_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def _datetime_from_payload(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value
    if isinstance(value, str) and value.strip():
        parsed = datetime.fromisoformat(value)
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=timezone.utc)
        return parsed
    return None


@dataclass(frozen=True, slots=True)
class LlmErrorPayload(ValueObject):
    message: str
    code: str = "invocation_failed"
    details: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.message.strip():
            raise LlmValidationError("LLM error message cannot be empty.")
        if not self.code.strip():
            raise LlmValidationError("LLM error code cannot be empty.")
        object.__setattr__(self, "details", dict(self.details))

    def to_payload(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "code": self.code,
            "details": dict(self.details),
        }

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "LlmErrorPayload | None":
        if not payload:
            return None
        return cls(
            message=str(payload.get("message", "")).strip(),
            code=str(payload.get("code", "invocation_failed")).strip()
            or "invocation_failed",
            details=(
                dict(payload.get("details"))
                if isinstance(payload.get("details"), dict)
                else {}
            ),
        )
