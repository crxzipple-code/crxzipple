from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class TraceContext:
    trace_id: str
    correlation_id: str | None = None
    source_event_id: str | None = None
    source_owner: str | None = None
    source_surface_id: str | None = None
    source_event_name: str | None = None
    observed_event_id: str | None = None
    observed_event_name: str | None = None
    session_key: str | None = None
    session_id: str | None = None
    turn_id: str | None = None
    run_id: str | None = None
    step_id: str | None = None
    execution_item_id: str | None = None
    tool_run_id: str | None = None
    tool_call_id: str | None = None
    llm_invocation_id: str | None = None
    llm_response_item_id: str | None = None
    request_render_snapshot_id: str | None = None
    session_item_id: str | None = None
    continuation_decision_id: str | None = None
    artifact_id: str | None = None
    approval_request_id: str | None = None

    def to_payload(self) -> dict[str, Any]:
        return {
            key: value
            for key, value in {
                "trace_id": self.trace_id,
                "correlation_id": self.correlation_id,
                "source_event_id": self.source_event_id,
                "source_owner": self.source_owner,
                "source_surface_id": self.source_surface_id,
                "source_event_name": self.source_event_name,
                "observed_event_id": self.observed_event_id,
                "observed_event_name": self.observed_event_name,
                "session_key": self.session_key,
                "session_id": self.session_id,
                "turn_id": self.turn_id,
                "run_id": self.run_id,
                "step_id": self.step_id,
                "execution_item_id": self.execution_item_id,
                "tool_run_id": self.tool_run_id,
                "tool_call_id": self.tool_call_id,
                "llm_invocation_id": self.llm_invocation_id,
                "llm_response_item_id": self.llm_response_item_id,
                "request_render_snapshot_id": self.request_render_snapshot_id,
                "session_item_id": self.session_item_id,
                "continuation_decision_id": self.continuation_decision_id,
                "artifact_id": self.artifact_id,
                "approval_request_id": self.approval_request_id,
            }.items()
            if value is not None
        }


@dataclass(frozen=True, slots=True)
class LinkedEntity:
    entity_type: str
    entity_id: str
    label: str | None = None
    trace: TraceContext | None = None


@dataclass(frozen=True, slots=True)
class RuntimeAction:
    id: str
    label: str
    owner: str
    risk_level: str = "normal"
    allowed: bool = True
    requires_confirmation: bool = False
    reason_required: bool = False
    trace: TraceContext | None = None


@dataclass(frozen=True, slots=True)
class ConsoleSectionError:
    code: str
    message: str
    retryable: bool = False
    trace_id: str | None = None


@dataclass(frozen=True, slots=True)
class ConsoleSection:
    id: str
    owner: str
    status: str
    updated_at: str | None
    data: Any | None = None
    error: ConsoleSectionError | None = None
    linked_entities: tuple[LinkedEntity, ...] = field(default_factory=tuple)
