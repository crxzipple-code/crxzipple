from __future__ import annotations

from dataclasses import dataclass, field

from crxzipple.modules.llm.application.runtime_request import RuntimeLlmRequest
from crxzipple.modules.llm.domain import LlmMessage, ToolSchema
from crxzipple.modules.orchestration.application.ports import (
    RequestRenderSnapshotRecord,
)
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)
from crxzipple.modules.orchestration.application.runtime_request_mode import (
    RuntimeRequestMode,
)
from crxzipple.modules.orchestration.application.runtime_request_report import (
    RuntimeRequestReport,
)
from crxzipple.modules.orchestration.application.tool_resolver import ResolvedToolSet
from crxzipple.modules.orchestration.domain import OrchestrationRun, PendingApprovalRequest


@dataclass(frozen=True, slots=True)
class EngineAdvanceOutcome:
    llm_id: str
    llm_invocation_id: str
    llm_response_item_ids: tuple[str, ...] = field(default_factory=tuple)
    response_text: str | None = None
    user_session_item_id: str | None = None
    session_item_ids: tuple[str, ...] = field(default_factory=tuple)
    assistant_progress_item_ids: tuple[str, ...] = field(default_factory=tuple)
    tool_call_session_item_ids: tuple[str, ...] = field(default_factory=tuple)
    tool_result_session_item_ids: tuple[str, ...] = field(default_factory=tuple)
    completed_inline_tool_run_ids: tuple[str, ...] = field(default_factory=tuple)
    tool_call_names: tuple[str, ...] = field(default_factory=tuple)
    tool_run_links: tuple[dict[str, object], ...] = field(default_factory=tuple)
    pending_tool_run_ids: tuple[str, ...] = field(default_factory=tuple)
    pending_approval_request: PendingApprovalRequest | None = None
    runtime_request_report: RuntimeRequestReport | None = None
    request_render_snapshot_id: str | None = None
    llm_request_metadata: dict[str, object] = field(default_factory=dict)
    yield_requested: bool = False
    yield_reason: str | None = None
    continue_loop: bool = False
    continuation_reason: str | None = None
    continuation_end_turn: bool | None = None
    provider_continuation_state: dict[str, object] = field(default_factory=dict)
    loop_diagnostic: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RuntimeLlmRequestPreview:
    llm_id: str
    mode: RuntimeRequestMode
    messages: tuple[LlmMessage, ...]
    input_items: tuple[dict[str, object], ...] = field(default_factory=tuple)
    tool_schemas: tuple[ToolSchema, ...] = field(default_factory=tuple)
    runtime_request_report: RuntimeRequestReport | None = None
    request_render_snapshot_id: str | None = None
    request_render_snapshot_metadata: dict[str, object] = field(default_factory=dict)
    request_render_snapshot: dict[str, object] = field(default_factory=dict)
    tool_surface: dict[str, object] = field(default_factory=dict)
    runtime_context: dict[str, object] = field(default_factory=dict)
    provider_request_options: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ResolvedRuntimeLlmRequestDraft:
    draft: RuntimeLlmRequestDraft
    resolved_tools: ResolvedToolSet


@dataclass(frozen=True, slots=True)
class AdvanceContext:
    run: OrchestrationRun
    session_key: str
    user_session_item_id: str | None
    draft: RuntimeLlmRequestDraft
    resolved_tools: ResolvedToolSet
    request_envelope: RuntimeLlmRequest
    request_render_snapshot_id: str | None = None
    request_render_snapshot_metadata: dict[str, object] = field(default_factory=dict)


def snapshot_metadata_for_request(
    request_render_snapshot: RequestRenderSnapshotRecord | None,
    *,
    policy_payload: dict[str, object],
) -> dict[str, object]:
    metadata = (
        dict(request_render_snapshot.metadata)
        if request_render_snapshot is not None
        else {}
    )
    metadata["llm_request_policy"] = policy_payload
    return metadata
