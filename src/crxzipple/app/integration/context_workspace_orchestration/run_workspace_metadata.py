"""Run workspace metadata helpers for Context Workspace orchestration integration."""

from __future__ import annotations

import json

from crxzipple.modules.orchestration.application.runtime_llm_request_draft import RuntimeLlmRequestDraft
from crxzipple.app.integration.context_workspace_orchestration.runtime_context_message import (
    build_runtime_context_message,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun

from ._metadata import estimate_text_tokens, metadata_text


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
        "agent_instruction_node": _agent_instruction_node_payload(draft),
        "run_flow_node": flow_context,
        "run_goal_node": build_run_goal_payload(run),
        "run_environment_node": build_run_environment_payload(run, draft=draft),
        "run_permissions_node": build_run_permissions_payload(run, draft=draft),
        "run_provider_node": build_run_provider_payload(draft),
        "run_context_budget_node": build_run_context_budget_payload(draft),
        "run_constraints_node": build_run_constraints_payload(run, draft=draft),
        "execution_continuation_node": build_execution_continuation_payload(run),
        "available_tool_names": _available_tool_names(draft),
        "available_skill_names": _metadata_list(
            skill_runtime_request_metadata.get("available_skill_names"),
        ),
        "resolved_skills": _metadata_list(
            skill_runtime_request_metadata.get("resolved_skills"),
        ),
        "skill_runtime_request": skill_runtime_request_metadata,
    }


def build_run_goal_payload(run: OrchestrationRun) -> dict[str, object]:
    session_key = metadata_text(run.metadata.get("session_key"))
    instruction_content = _payload_text(run.inbound_instruction.content)
    lines = [
        f"Run ID: {run.id}",
        f"Source: {run.inbound_instruction.source}",
        f"Session key: {session_key or '-'}",
        f"Active session: {run.active_session_id or '-'}",
        "Current user goal:",
        instruction_content or "-",
    ]
    return {
        "summary": "Latest inbound instruction that defines the current run goal.",
        "content": "\n".join(lines),
        "metadata": {
            "run_id": run.id,
            "source": run.inbound_instruction.source,
            "session_key": session_key,
            "active_session_id": run.active_session_id,
            "instruction_estimated_tokens": estimate_text_tokens(instruction_content),
        },
    }


def build_run_environment_payload(
    run: OrchestrationRun,
    *,
    draft: RuntimeLlmRequestDraft,
) -> dict[str, object]:
    runtime_metadata = dict(draft.runtime_context)
    runtime_content = _runtime_context_content(draft)
    agent_home_dir = metadata_text(runtime_metadata.get("agent_home_dir"))
    workspace_dir = metadata_text(draft.workspace_dir) or metadata_text(
        runtime_metadata.get("workspace_dir"),
    )
    queue_policy = (
        run.queue_policy.value
        if hasattr(run.queue_policy, "value")
        else str(run.queue_policy)
    )
    lines = [
        f"Agent: {run.agent_id or '-'}",
        f"Active session: {run.active_session_id or '-'}",
        f"Workspace: {workspace_dir or '-'}",
        f"Agent home: {agent_home_dir or '-'}",
        f"Inbound source: {run.inbound_instruction.source}",
        f"Lane key: {run.lane_key or '-'}",
        f"Lane lock key: {run.lane_lock_key or '-'}",
        f"Queue policy: {queue_policy or '-'}",
    ]
    if runtime_content:
        lines.extend(("", "Runtime context:", runtime_content))
    return {
        "summary": (
            "Current run environment, session binding, workspace, lane, and queue."
        ),
        "content": "\n".join(lines),
        "metadata": {
            "agent_id": run.agent_id,
            "active_session_id": run.active_session_id,
            "workspace_dir": workspace_dir,
            "agent_home_dir": agent_home_dir,
            "inbound_source": run.inbound_instruction.source,
            "lane_key": run.lane_key,
            "lane_lock_key": run.lane_lock_key,
            "queue_policy": queue_policy,
            "runtime_context_estimated_tokens": estimate_text_tokens(runtime_content),
        },
    }


def build_run_permissions_payload(
    run: OrchestrationRun,
    *,
    draft: RuntimeLlmRequestDraft,
) -> dict[str, object]:
    pending_approval = (
        dict(run.pending_approval_request_payload)
        if run.pending_approval_request_payload is not None
        else None
    )
    pending_approval_request_id = (
        metadata_text(pending_approval.get("request_id"))
        if pending_approval is not None
        else None
    )
    surface_policy = draft.surface_policy.to_payload()
    lines = [
        f"Surface: {draft.surface_policy.surface}",
        f"Surface contract: {draft.surface_policy.surface_contract}",
        f"Candidate tool schemas allowed: {_yes_no(draft.surface_policy.include_tool_schemas)}",
        f"Candidate callable tool schemas: {len(draft.tool_schemas)}",
        f"Require tool call: {_yes_no(draft.surface_policy.require_tool_call)}",
        f"Pending approval: {pending_approval_request_id or '-'}",
        "Only schemas selected by the Context Slice tool surface may be called.",
        "If a capability is missing, inspect visible Context Tree handles before claiming absence.",
    ]
    return {
        "summary": (
            "Authorization, access, tool visibility, and approval boundaries for "
            "this run."
        ),
        "content": "\n".join(lines),
        "metadata": {
            "surface_policy": surface_policy,
            "candidate_tool_schema_count": len(draft.tool_schemas),
            "pending_approval": pending_approval is not None,
            "pending_approval_request_id": pending_approval_request_id,
        },
    }


def build_run_provider_payload(draft: RuntimeLlmRequestDraft) -> dict[str, object]:
    capability_values = [
        capability.value if hasattr(capability, "value") else str(capability)
        for capability in draft.llm_capabilities
    ]
    lines = [
        f"LLM profile: {draft.llm_id}",
        f"Mode: {draft.mode.value}",
        f"Capabilities: {', '.join(capability_values) if capability_values else '-'}",
        f"Direct transcript messages: {len(draft.messages)}",
        f"Candidate tool schemas: {len(draft.tool_schemas)}",
    ]
    return {
        "summary": "Current LLM profile, capabilities, and request surface.",
        "content": "\n".join(lines),
        "metadata": {
            "llm_id": draft.llm_id,
            "mode": draft.mode.value,
            "llm_capabilities": capability_values,
            "message_count": len(draft.messages),
            "candidate_tool_schema_count": len(draft.tool_schemas),
        },
    }


def build_run_context_budget_payload(draft: RuntimeLlmRequestDraft) -> dict[str, object]:
    report_payload = draft.report.to_payload() if draft.report is not None else {}
    context_budget = _dict_payload(report_payload.get("context_budget"))
    context = _dict_payload(report_payload.get("context"))
    transcript = _dict_payload(report_payload.get("transcript"))
    estimated_total_tokens = report_payload.get("estimated_total_tokens")
    lines = [
        f"Budget source: {metadata_text(context_budget.get('source')) or '-'}",
        f"Context max tokens: {_display_number(context_budget.get('max_estimated_tokens'))}",
        f"LLM context window: {_display_number(context_budget.get('llm_context_window_tokens'))}",
        f"Context tokens: {_display_number(context.get('estimated_tokens'))}",
        f"Transcript tokens: {_display_number(transcript.get('estimated_tokens'))}",
        f"Estimated total tokens: {_display_number(estimated_total_tokens)}",
        f"Direct transcript messages: {_display_number(transcript.get('message_count'))}",
        f"Candidate tool schemas: {len(draft.tool_schemas)}",
    ]
    return {
        "summary": (
            "Runtime request budget for context snapshot, transcript, tools, and "
            "attachments."
        ),
        "content": "\n".join(lines),
        "metadata": {
            "report": report_payload,
            "estimated_total_tokens": estimated_total_tokens,
            "candidate_tool_schema_count": len(draft.tool_schemas),
        },
    }


def build_run_constraints_payload(
    run: OrchestrationRun,
    *,
    draft: RuntimeLlmRequestDraft,
) -> dict[str, object]:
    lines = [
        "Tool call/result pairs must stay protocol-complete.",
        "Long owner results should be read through handles or compact summaries.",
        "Do not invent facts from collapsed nodes; expand or use owner tools when needed.",
        "Use evidence-producing paths before repeating brittle UI actions.",
        "Browser mutating actions against the same target are serial until resource policy says otherwise.",
        "Update the visible plan only for phase changes, observed facts, uncertainty, blockers, or recovery.",
        f"Current step: {run.current_step}",
        f"Max steps: {run.max_steps}",
        f"Auto-continue inline tools: {_yes_no(draft.surface_policy.auto_continue_inline_tools)}",
    ]
    return {
        "summary": (
            "Current run hard constraints for tool use, evidence, and continuation."
        ),
        "content": "\n".join(lines),
        "metadata": {
            "current_step": run.current_step,
            "max_steps": run.max_steps,
            "surface_contract": draft.surface_policy.surface_contract,
            "auto_continue_inline_tools": draft.surface_policy.auto_continue_inline_tools,
        },
    }


def build_execution_continuation_payload(
    run: OrchestrationRun,
) -> dict[str, object]:
    pending_tool_run_ids = tuple(run.pending_tool_run_ids)
    pending_approval = (
        dict(run.pending_approval_request_payload)
        if run.pending_approval_request_payload is not None
        else None
    )
    last_approval = (
        dict(run.last_approval_resolution_payload)
        if run.last_approval_resolution_payload is not None
        else None
    )
    recovery_contract = (
        dict(run.recovery_contract_payload)
        if run.recovery_contract_payload is not None
        else None
    )
    lines = [
        f"Run status: {run.status.value}",
        f"Run stage: {run.stage.value}",
    ]
    if run.waiting_reason:
        lines.append(f"Waiting reason: {run.waiting_reason}")
    if pending_tool_run_ids:
        lines.append(
            "Pending background tool runs: "
            + ", ".join(pending_tool_run_ids),
        )
    if pending_approval is not None:
        lines.append(
            "Pending approval: "
            + _public_payload_summary(
                pending_approval,
                keys=("request_id", "effect_id", "label"),
            ),
        )
    if last_approval is not None:
        lines.append(
            "Last approval resolution: "
            + _public_payload_summary(
                last_approval,
                keys=("request_id", "decision", "resolved_at"),
            ),
        )
    if recovery_contract is not None:
        lines.append(
            "Recovery contract: "
            + _public_payload_summary(
                recovery_contract,
                keys=("kind", "state", "source", "reason"),
            ),
        )
    if len(lines) == 2:
        lines.append("No pending public continuation state.")
    return {
        "summary": _execution_continuation_summary(
            pending_tool_run_count=len(pending_tool_run_ids),
            pending_approval=pending_approval is not None,
            recovery_contract=recovery_contract is not None,
        ),
        "content": "\n".join(lines),
        "metadata": {
            "status": run.status.value,
            "stage": run.stage.value,
            "waiting_reason": run.waiting_reason,
            "pending_tool_run_count": len(pending_tool_run_ids),
            "pending_tool_run_ids": list(pending_tool_run_ids),
            "pending_approval_request_id": (
                metadata_text(pending_approval.get("request_id"))
                if pending_approval is not None
                else None
            ),
            "last_approval_decision": (
                metadata_text(last_approval.get("decision"))
                if last_approval is not None
                else None
            ),
            "recovery_contract_kind": (
                metadata_text(recovery_contract.get("kind"))
                if recovery_contract is not None
                else None
            ),
        },
    }


def _available_tool_names(draft: RuntimeLlmRequestDraft) -> list[str]:
    names: list[str] = []
    for schema in draft.tool_schemas:
        name = schema.name.strip()
        if name and name not in names:
            names.append(name)
    for item in _metadata_string_list(draft.flow_hint.get("default_tool_schema_ids")):
        if item not in names:
            names.append(item)
    return names


def _metadata_list(value: object) -> list[object]:
    return list(value) if isinstance(value, (list, tuple)) else []


def _metadata_string_list(value: object) -> list[str]:
    if isinstance(value, str):
        candidates: tuple[object, ...] = (value,)
    elif isinstance(value, (list, tuple, set, frozenset)):
        candidates = tuple(value)
    else:
        return []
    items: list[str] = []
    for item in candidates:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized and normalized not in items:
            items.append(normalized)
    return items


def _agent_instruction_node_payload(draft: RuntimeLlmRequestDraft) -> dict[str, object] | None:
    content = metadata_text(draft.agent_instruction)
    if not content:
        return None
    return {
        "summary": "Agent identity, role, and operating instructions.",
        "content": content,
        "metadata": {
            "kind": "agent_instruction",
            "estimated_tokens": estimate_text_tokens(content),
        },
        "truncated": False,
    }


def _runtime_context_content(draft: RuntimeLlmRequestDraft) -> str:
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


def _payload_text(value: object, *, limit: int = 4000) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()[:limit].rstrip()
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)[:limit].rstrip()
    except TypeError:
        return str(value).strip()[:limit].rstrip()


def _compact_json(payload: object) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(payload)


def _dict_payload(value: object) -> dict[str, object]:
    return dict(value) if isinstance(value, dict) else {}


def _display_number(value: object) -> str:
    if isinstance(value, int | float):
        return str(value)
    return "-"


def _yes_no(value: bool) -> str:
    return "yes" if value else "no"


def metadata_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    text = metadata_text(value)
    if text is None:
        return None
    try:
        return int(text)
    except ValueError:
        return None


def _execution_continuation_summary(
    *,
    pending_tool_run_count: int,
    pending_approval: bool,
    recovery_contract: bool,
) -> str:
    if pending_approval:
        return "Run is waiting for a public approval decision before it can continue."
    if pending_tool_run_count:
        return f"Run is waiting for {pending_tool_run_count} background tool run(s)."
    if recovery_contract:
        return "Run has a public recovery contract for continuation handling."
    return "No pending public continuation state for this run."


def _public_payload_summary(
    payload: dict[str, object],
    *,
    keys: tuple[str, ...],
) -> str:
    parts: list[str] = []
    for key in keys:
        value = metadata_text(payload.get(key))
        if value is not None:
            parts.append(f"{key}={value}")
    return ", ".join(parts) if parts else "present"
