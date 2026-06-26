from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol

from crxzipple.modules.llm.domain import (
    LlmCapability,
    LlmInputItem,
    LlmMessage,
    ToolSchema,
)
from crxzipple.modules.orchestration.application.runtime_request_mode import (
    RuntimeRequestMode,
)
from crxzipple.modules.orchestration.application.runtime_request_report import (
    RuntimeRequestReport,
    RunSurfacePolicy,
)
from crxzipple.modules.session.domain import Session, SessionItem


class SkillRuntimeRequestResolutionPort(Protocol):
    def resolve_runtime_request_catalog(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
        available_tool_ids: tuple[str, ...],
        interface: str | None = None,
        agent_id: str | None = None,
        run_id: str | None = None,
        session_key: str | None = None,
        active_session_id: str | None = None,
    ) -> Any:
        ...


@dataclass(frozen=True, slots=True)
class RuntimeLlmRequestDraft:
    llm_id: str
    session_key: str
    active_session_id: str
    messages: tuple[LlmMessage, ...]
    input_items: tuple[LlmInputItem, ...] = ()
    transcript_policy: dict[str, object] = field(default_factory=dict)
    llm_capabilities: tuple[LlmCapability, ...] = ()
    llm_api_family: str | None = None
    runtime_llm_defaults: dict[str, object] = field(default_factory=dict)
    llm_defaults: dict[str, object] = field(default_factory=dict)
    llm_policy: dict[str, object] = field(default_factory=dict)
    mode: RuntimeRequestMode = RuntimeRequestMode.NORMAL_TURN
    report: RuntimeRequestReport | None = None
    agent_instruction: str | None = None
    runtime_context: dict[str, object] = field(default_factory=dict)
    workspace_dir: str | None = None
    tool_schemas: tuple[ToolSchema, ...] = ()
    flow_hint: dict[str, object] = field(default_factory=dict)
    surface_policy: RunSurfacePolicy = field(default_factory=RunSurfacePolicy)
    skill_runtime_request_metadata: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class SessionDraftContext:
    session: Session
    lightweight_items: tuple[SessionItem, ...] = ()
    replay_window: object | None = None

    @property
    def replay_items(self) -> tuple[SessionItem, ...]:
        if self.replay_window is None:
            return self.lightweight_items
        items = getattr(self.replay_window, "items", ())
        return tuple(items or ())
