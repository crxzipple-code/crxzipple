"""Run workspace metadata helpers for Context Workspace orchestration integration."""

from __future__ import annotations

import json
from hashlib import sha256

from crxzipple.modules.llm.domain import LlmMessage
from crxzipple.modules.orchestration.application.prompt_input import RunPromptInput
from crxzipple.modules.orchestration.domain import OrchestrationRun

from ._metadata import estimate_text_tokens, metadata_text


EVIDENCE_FRONTIER_SCHEMA_VERSION = "2026-06-14"


def build_run_workspace_metadata(
    *,
    run: OrchestrationRun,
    prompt: RunPromptInput,
    flow_context: dict[str, object],
) -> dict[str, object]:
    return {
        "source": "orchestration",
        "last_run_id": run.id,
        "workspace_dir": prompt.workspace_dir,
        "prompt_input": prompt.surface_policy.surface,
        "prompt_mode": prompt.mode.value,
        "agent_instruction_node": _context_node_payload(
            prompt,
            kind="agent_instruction",
        ),
        "run_flow_node": flow_context,
        "run_goal_node": build_run_goal_payload(run),
        "run_environment_node": build_run_environment_payload(run, prompt=prompt),
        "run_permissions_node": build_run_permissions_payload(run, prompt=prompt),
        "run_provider_node": build_run_provider_payload(prompt),
        "run_context_budget_node": build_run_context_budget_payload(prompt),
        "run_constraints_node": build_run_constraints_payload(run, prompt=prompt),
        "evidence_frontier_node": build_evidence_frontier_payload(run, prompt=prompt),
        "execution_continuation_node": build_execution_continuation_payload(run),
        "available_skill_names": _available_skill_names(prompt),
        "available_tool_names": _available_tool_names(prompt),
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
    prompt: RunPromptInput,
) -> dict[str, object]:
    runtime_metadata = _context_block_metadata(prompt, kind="runtime_context")
    runtime_content = _context_block_content(prompt, kind="runtime_context")
    agent_home_dir = metadata_text(runtime_metadata.get("agent_home_dir"))
    workspace_dir = metadata_text(prompt.workspace_dir) or metadata_text(
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
        lines.extend(("", "Runtime context block:", runtime_content))
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
    prompt: RunPromptInput,
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
    surface_policy = prompt.surface_policy.to_payload()
    lines = [
        f"Surface: {prompt.surface_policy.surface}",
        f"Surface contract: {prompt.surface_policy.surface_contract}",
        f"Provider tool schemas included: {_yes_no(prompt.surface_policy.include_tool_schemas)}",
        f"Visible callable tool schemas: {len(prompt.tool_schemas)}",
        f"Require tool call: {_yes_no(prompt.surface_policy.require_tool_call)}",
        f"Pending approval: {pending_approval_request_id or '-'}",
        "Only visible and authorized tool schemas may be called.",
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
            "tool_schema_count": len(prompt.tool_schemas),
            "pending_approval": pending_approval is not None,
            "pending_approval_request_id": pending_approval_request_id,
        },
    }


def build_run_provider_payload(prompt: RunPromptInput) -> dict[str, object]:
    capability_values = [
        capability.value if hasattr(capability, "value") else str(capability)
        for capability in prompt.llm_capabilities
    ]
    lines = [
        f"LLM profile: {prompt.llm_id}",
        f"Mode: {prompt.mode.value}",
        f"Capabilities: {', '.join(capability_values) if capability_values else '-'}",
        f"Direct transcript messages: {len(prompt.messages)}",
        f"Provider tool schemas: {len(prompt.tool_schemas)}",
    ]
    return {
        "summary": "Current LLM profile, capabilities, and request surface.",
        "content": "\n".join(lines),
        "metadata": {
            "llm_id": prompt.llm_id,
            "mode": prompt.mode.value,
            "llm_capabilities": capability_values,
            "message_count": len(prompt.messages),
            "tool_schema_count": len(prompt.tool_schemas),
        },
    }


def build_run_context_budget_payload(prompt: RunPromptInput) -> dict[str, object]:
    report_payload = prompt.report.to_payload() if prompt.report is not None else {}
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
        f"Provider tool schemas: {len(prompt.tool_schemas)}",
    ]
    return {
        "summary": (
            "Prompt surface budget for context blocks, transcript, tools, and "
            "attachments."
        ),
        "content": "\n".join(lines),
        "metadata": {
            "report": report_payload,
            "estimated_total_tokens": estimated_total_tokens,
            "tool_schema_count": len(prompt.tool_schemas),
        },
    }


def build_run_constraints_payload(
    run: OrchestrationRun,
    *,
    prompt: RunPromptInput,
) -> dict[str, object]:
    lines = [
        "Tool call/result pairs must stay protocol-complete.",
        "Long owner results should be read through handles or compact summaries.",
        "Do not invent facts from collapsed nodes; expand or use owner tools when needed.",
        "Use evidence-producing paths before repeating brittle UI actions.",
        "Browser mutating actions against the same target are serial until resource policy says otherwise.",
        "Update the visible plan only for phase changes, verified facts, blockers, or recovery.",
        f"Current step: {run.current_step}",
        f"Max steps: {run.max_steps}",
        f"Auto-continue inline tools: {_yes_no(prompt.surface_policy.auto_continue_inline_tools)}",
    ]
    return {
        "summary": (
            "Current run hard constraints for tool use, evidence, and continuation."
        ),
        "content": "\n".join(lines),
        "metadata": {
            "current_step": run.current_step,
            "max_steps": run.max_steps,
            "surface_contract": prompt.surface_policy.surface_contract,
            "auto_continue_inline_tools": prompt.surface_policy.auto_continue_inline_tools,
        },
    }


def build_evidence_frontier_payload(
    run: OrchestrationRun,
    *,
    prompt: RunPromptInput,
) -> dict[str, object]:
    pending_tool_run_ids = tuple(run.pending_tool_run_ids)
    items = _evidence_frontier_items(run, prompt=prompt)
    verified_facts = [
        str(item["summary"])
        for item in items
        if item.get("status") in {"verified", "success"}
    ]
    failed_paths = [
        str(item["summary"])
        for item in items
        if item.get("status") in {"failed", "blocked"}
    ]
    remaining_gaps = [
        str(item["summary"])
        for item in items
        if item.get("status") in {"open", "gap", "unknown"}
    ]
    latest_messages = prompt.messages[-3:]
    latest_lines = [
        _message_frontier_line(index=index, message=message)
        for index, message in enumerate(latest_messages, start=1)
    ]
    lines = [
        f"Schema: {EVIDENCE_FRONTIER_SCHEMA_VERSION}",
        f"Run status: {run.status.value}",
        f"Run stage: {run.stage.value}",
        f"Direct transcript messages: {len(prompt.messages)}",
        f"Pending background tool runs: {len(pending_tool_run_ids)}",
        f"Evidence items: {len(items)}",
        f"Verified facts: {len(verified_facts)}",
        f"Failed evidence paths: {len(failed_paths)}",
        f"Remaining gaps: {len(remaining_gaps)}",
    ]
    if items:
        lines.append("Evidence frontier:")
        lines.extend(
            f"- [{item.get('status')}] {item.get('summary')}"
            for item in items
        )
    if latest_lines:
        lines.append("Latest direct transcript tail:")
        lines.extend(latest_lines)
    else:
        lines.append("Latest direct transcript tail: -")
    fingerprint = _evidence_frontier_fingerprint(items)
    return {
        "summary": "Latest evidence tail the next model call should handle first.",
        "content": "\n".join(lines),
        "metadata": {
            "schema_version": EVIDENCE_FRONTIER_SCHEMA_VERSION,
            "status": run.status.value,
            "stage": run.stage.value,
            "message_count": len(prompt.messages),
            "pending_tool_run_count": len(pending_tool_run_ids),
            "pending_tool_run_ids": list(pending_tool_run_ids),
            "latest_roles": [_message_role(message) for message in latest_messages],
            "item_count": len(items),
            "items": items,
            "verified_fact_count": len(verified_facts),
            "verified_facts": verified_facts,
            "failed_evidence_path_count": len(failed_paths),
            "failed_evidence_paths": failed_paths,
            "remaining_gap_count": len(remaining_gaps),
            "remaining_gaps": remaining_gaps,
            "fingerprint": fingerprint,
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


def _available_skill_names(prompt: RunPromptInput) -> list[str]:
    catalog = prompt.skills_catalog
    if catalog is None:
        return []
    raw_names = catalog.metadata.get("available_skill_names")
    if not isinstance(raw_names, list):
        return []
    names: list[str] = []
    for item in raw_names:
        if not isinstance(item, str):
            continue
        normalized = item.strip()
        if normalized and normalized not in names:
            names.append(normalized)
    return names


def _available_tool_names(prompt: RunPromptInput) -> list[str]:
    return [
        schema.name
        for schema in prompt.tool_schemas
        if schema.name.strip()
    ]


def _context_node_payload(
    prompt: RunPromptInput,
    *,
    kind: str,
) -> dict[str, object] | None:
    for block in prompt.context_blocks:
        if block.kind != kind:
            continue
        return {
            "summary": _summary_for_context_block(block.kind, block.metadata),
            "content": block.content,
            "metadata": {
                **dict(block.metadata),
                "kind": block.kind,
                "estimated_tokens": estimate_text_tokens(block.content),
                "truncated": block.truncated,
            },
            "truncated": block.truncated,
        }
    return None


def _context_block_metadata(
    prompt: RunPromptInput,
    *,
    kind: str,
) -> dict[str, object]:
    for block in prompt.context_blocks:
        if block.kind == kind:
            return dict(block.metadata)
    return {}


def _context_block_content(
    prompt: RunPromptInput,
    *,
    kind: str,
) -> str:
    for block in prompt.context_blocks:
        if block.kind == kind:
            return block.content
    return ""


def _summary_for_context_block(
    kind: str,
    metadata: dict[str, object],
) -> str:
    if kind == "agent_instruction":
        return "Agent identity, role, and operating instructions."
    if kind == "runtime_context":
        agent_id = metadata.get("agent_id")
        llm_id = metadata.get("llm_id")
        if agent_id and llm_id:
            return f"Run context for agent '{agent_id}' using LLM '{llm_id}'."
        return "Current run runtime bindings and provider context."
    return "Prompt context block."


def _message_frontier_line(*, index: int, message: LlmMessage) -> str:
    role = _message_role(message)
    content = _payload_text(message.content, limit=240)
    return f"{index}. {role}: {content or '-'}"


def _message_role(message: LlmMessage) -> str:
    role = message.role
    return role.value if hasattr(role, "value") else str(role)


def _evidence_frontier_items(
    run: OrchestrationRun,
    *,
    prompt: RunPromptInput,
) -> list[dict[str, object]]:
    explicit = _explicit_evidence_items(run.metadata.get("evidence_frontier"))
    items = list(explicit)
    seen_ids = {str(item.get("id")) for item in items if item.get("id")}
    for tool_run_id in run.pending_tool_run_ids:
        item_id = f"pending-tool:{tool_run_id}"
        if item_id in seen_ids:
            continue
        items.append(
            {
                "id": item_id,
                "kind": "tool_pending",
                "status": "open",
                "summary": f"Background tool run is still pending: {tool_run_id}",
                "source_kind": "orchestration_run",
                "source_id": run.id,
                "confidence": "system",
            },
        )
        seen_ids.add(item_id)
    for message in prompt.messages:
        role = _message_role(message)
        if role != "tool":
            continue
        metadata = dict(message.metadata)
        sequence_no = metadata.get("sequence_no")
        source_id = metadata_text(metadata.get("source_id")) or metadata_text(
            metadata.get("tool_call_id"),
        )
        item_id = f"tool-message:{source_id or sequence_no or len(items) + 1}"
        if item_id in seen_ids:
            continue
        content = _payload_text(message.content, limit=240)
        items.append(
            {
                "id": item_id,
                "kind": "tool_result",
                "status": _tool_message_status(message),
                "summary": content or "Tool result observed.",
                "source_kind": "session_item",
                "source_id": source_id or str(sequence_no or ""),
                "confidence": "observed",
            },
        )
        seen_ids.add(item_id)
    return items


def _explicit_evidence_items(value: object) -> list[dict[str, object]]:
    if not isinstance(value, list | tuple):
        return []
    items: list[dict[str, object]] = []
    for index, raw in enumerate(value, start=1):
        if not isinstance(raw, dict):
            continue
        summary = metadata_text(raw.get("summary")) or metadata_text(raw.get("fact"))
        if summary is None:
            continue
        item = {
            "id": metadata_text(raw.get("id")) or f"evidence:{index}",
            "kind": metadata_text(raw.get("kind")) or "fact",
            "status": _evidence_status(raw.get("status")),
            "summary": summary,
            "source_kind": metadata_text(raw.get("source_kind")) or "metadata",
            "source_id": metadata_text(raw.get("source_id")) or "",
            "confidence": metadata_text(raw.get("confidence")) or "unspecified",
        }
        metadata = raw.get("metadata")
        if isinstance(metadata, dict) and metadata:
            item["metadata"] = dict(metadata)
        items.append(item)
    return items


def _tool_message_status(message: LlmMessage) -> str:
    metadata = dict(message.metadata)
    status = _evidence_status(metadata.get("status"))
    if status != "unknown":
        return status
    content = _payload_text(message.content, limit=400).lower()
    if "error" in content or "failed" in content or "traceback" in content:
        return "failed"
    return "success"


def _evidence_status(value: object) -> str:
    status = metadata_text(value)
    if status in {"verified", "success", "failed", "blocked", "open", "gap"}:
        return status
    return "unknown"


def _evidence_frontier_fingerprint(items: list[dict[str, object]]) -> str:
    payload = [
        {
            "id": item.get("id"),
            "kind": item.get("kind"),
            "status": item.get("status"),
            "summary": item.get("summary"),
            "source_kind": item.get("source_kind"),
            "source_id": item.get("source_id"),
        }
        for item in items
    ]
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return sha256(encoded.encode("utf-8")).hexdigest()


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
