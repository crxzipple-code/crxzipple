"""Run-scoped Context Workspace node payload builders."""

from __future__ import annotations

from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)
from crxzipple.modules.orchestration.domain import OrchestrationRun

from ._metadata import estimate_text_tokens, metadata_text
from .run_workspace_runtime_context import runtime_context_content
from .run_workspace_metadata_values import (
    dict_payload,
    display_number,
    metadata_string_list,
    payload_text,
    yes_no,
)


def build_run_goal_payload(run: OrchestrationRun) -> dict[str, object]:
    session_key = metadata_text(run.metadata.get("session_key"))
    instruction_content = payload_text(run.inbound_instruction.content)
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
    runtime_content = runtime_context_content(draft)
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
        f"Candidate tool schemas allowed: {yes_no(draft.surface_policy.include_tool_schemas)}",
        f"Candidate callable tool schemas: {len(draft.tool_schemas)}",
        f"Require tool call: {yes_no(draft.surface_policy.require_tool_call)}",
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
    context_budget = dict_payload(report_payload.get("context_budget"))
    context = dict_payload(report_payload.get("context"))
    transcript = dict_payload(report_payload.get("transcript"))
    estimated_total_tokens = report_payload.get("estimated_total_tokens")
    lines = [
        f"Budget source: {metadata_text(context_budget.get('source')) or '-'}",
        f"Context max tokens: {display_number(context_budget.get('max_estimated_tokens'))}",
        f"LLM context window: {display_number(context_budget.get('llm_context_window_tokens'))}",
        f"Context tokens: {display_number(context.get('estimated_tokens'))}",
        f"Transcript tokens: {display_number(transcript.get('estimated_tokens'))}",
        f"Estimated total tokens: {display_number(estimated_total_tokens)}",
        f"Direct transcript messages: {display_number(transcript.get('message_count'))}",
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
        f"Auto-continue inline tools: {yes_no(draft.surface_policy.auto_continue_inline_tools)}",
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


def available_tool_names(draft: RuntimeLlmRequestDraft) -> list[str]:
    names: list[str] = []
    for schema in draft.tool_schemas:
        name = schema.name.strip()
        if name and name not in names:
            names.append(name)
    for item in metadata_string_list(draft.flow_hint.get("default_tool_schema_ids")):
        if item not in names:
            names.append(item)
    return names


def agent_instruction_node_payload(
    draft: RuntimeLlmRequestDraft,
) -> dict[str, object] | None:
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

