"""Workspace binding state for request-render snapshots."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from crxzipple.modules.orchestration.application.flow_context import (
    FlowContextPayload,
    build_flow_context_payload,
)
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun

from .run_workspace_binding import RunWorkspaceBindingAdapter
from .run_workspace_metadata import build_run_workspace_metadata


@dataclass(frozen=True)
class RequestRenderWorkspaceState:
    workspace: Any
    flow_context: FlowContextPayload
    read_only: bool


def bind_request_render_workspace(
    *,
    adapter: RunWorkspaceBindingAdapter,
    run: OrchestrationRun,
    draft: RuntimeLlmRequestDraft,
    session_key: str,
    agent_id: str,
    persist: bool,
) -> RequestRenderWorkspaceState:
    flow_context = build_flow_context_payload(
        mode=draft.mode,
        hint_payload=draft.flow_hint,
    )
    run_workspace_metadata = build_run_workspace_metadata(
        run=run,
        draft=draft,
        flow_context=flow_context.to_payload(),
    )
    workspace = adapter.workspace_for_request_snapshot(
        session_key=session_key,
        agent_id=agent_id,
        metadata=run_workspace_metadata,
        persist=persist,
    )
    return RequestRenderWorkspaceState(
        workspace=workspace,
        flow_context=flow_context,
        read_only=not persist,
    )
