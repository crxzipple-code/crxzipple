"""Run workspace metadata helpers for Context Workspace orchestration integration."""

from __future__ import annotations

from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun

from .run_workspace_continuation import build_execution_continuation_payload
from .run_workspace_metadata_values import metadata_list
from .run_workspace_nodes import (
    agent_instruction_node_payload,
    available_tool_names,
    build_run_constraints_payload,
    build_run_context_budget_payload,
    build_run_environment_payload,
    build_run_goal_payload,
    build_run_permissions_payload,
    build_run_provider_payload,
)

__all__ = [
    "build_execution_continuation_payload",
    "build_run_constraints_payload",
    "build_run_context_budget_payload",
    "build_run_environment_payload",
    "build_run_goal_payload",
    "build_run_permissions_payload",
    "build_run_provider_payload",
    "build_run_workspace_metadata",
]


def build_run_workspace_metadata(
    *,
    run: OrchestrationRun,
    draft: RuntimeLlmRequestDraft,
    flow_context: dict[str, object],
) -> dict[str, object]:
    skill_runtime_request_metadata = dict(draft.skill_runtime_request_metadata)
    return {
        "source": "orchestration",
        "last_run_id": run.id,
        "workspace_dir": draft.workspace_dir,
        "runtime_request_surface": draft.surface_policy.surface,
        "runtime_request_mode": draft.mode.value,
        "agent_instruction_node": agent_instruction_node_payload(draft),
        "run_flow_node": flow_context,
        "run_goal_node": build_run_goal_payload(run),
        "run_environment_node": build_run_environment_payload(run, draft=draft),
        "run_permissions_node": build_run_permissions_payload(run, draft=draft),
        "run_provider_node": build_run_provider_payload(draft),
        "run_context_budget_node": build_run_context_budget_payload(draft),
        "run_constraints_node": build_run_constraints_payload(run, draft=draft),
        "execution_continuation_node": build_execution_continuation_payload(run),
        "available_tool_names": available_tool_names(draft),
        "available_skill_names": metadata_list(
            skill_runtime_request_metadata.get("available_skill_names"),
        ),
        "resolved_skills": metadata_list(
            skill_runtime_request_metadata.get("resolved_skills"),
        ),
        "skill_runtime_request": skill_runtime_request_metadata,
    }
