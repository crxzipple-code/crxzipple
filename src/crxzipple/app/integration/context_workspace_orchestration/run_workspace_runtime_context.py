"""Runtime context text projection for run-scoped Context Workspace nodes."""

from __future__ import annotations

from crxzipple.app.integration.context_workspace_orchestration.runtime_context_message import (
    build_runtime_context_message,
)
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)

from .run_workspace_metadata_values import metadata_int
from ._metadata import metadata_text


def runtime_context_content(draft: RuntimeLlmRequestDraft) -> str:
    facts = dict(draft.runtime_context)
    agent_id = metadata_text(facts.get("agent_id"))
    llm_id = metadata_text(facts.get("llm_id"))
    if not agent_id or not llm_id:
        return ""
    available_tool_ids = tuple(
        item
        for item in facts.get("available_tool_ids", ())
        if isinstance(item, str) and item.strip()
    )
    return build_runtime_context_message(
        agent_id=agent_id,
        llm_id=llm_id,
        home_dir=metadata_text(facts.get("agent_home_dir")) or None,
        workspace_dir=metadata_text(facts.get("workspace_dir")) or None,
        available_tool_ids=available_tool_ids,
        current_step=metadata_int(facts.get("current_step")),
        max_steps=metadata_int(facts.get("max_steps")),
        remaining_steps=metadata_int(facts.get("remaining_steps")),
        step_budget_status=metadata_text(facts.get("step_budget_status")),
    )
