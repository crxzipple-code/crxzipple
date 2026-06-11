"""Snapshot metadata helpers for Context Workspace orchestration integration."""

from __future__ import annotations

from crxzipple.modules.context_workspace.application import (
    CONTEXT_INSTRUCTIONS_NODE_ID,
    CONTEXT_TREE_SCHEMA_VERSION,
    EXECUTION_CURRENT_NODE_ID,
    SESSION_CURRENT_NODE_ID,
)
from crxzipple.modules.llm.domain import ToolSchema
from crxzipple.modules.orchestration.application.prompt_input import RunPromptInput
from crxzipple.modules.orchestration.domain import OrchestrationRun
from crxzipple.shared.context_render_budget import context_render_budget_metadata

from ._metadata import (
    estimate_text_tokens,
    estimate_text_tokens_from_chars,
    metadata_dict,
    metadata_int,
    metadata_text,
)
from .artifact_mirror import artifact_content_budget


def build_snapshot_provider_attachments(
    rendered_attachments: dict[str, object],
    *,
    prompt: RunPromptInput,
) -> dict[str, object]:
    payload = dict(rendered_attachments)
    payload["prompt_input"] = {
        "llm_id": prompt.llm_id,
        "llm_capabilities": [
            capability.value for capability in prompt.llm_capabilities
        ],
        "message_count": len(prompt.messages),
        "tool_schema_count": len(prompt.tool_schemas),
        "context_block_count": len(prompt.context_blocks),
    }
    return payload


def build_context_snapshot_metadata(
    *,
    run: OrchestrationRun,
    prompt: RunPromptInput,
    rendered_prompt_body: str,
    provider_attachments: dict[str, object],
    provider_attachment_report: dict[str, object],
    included_node_ids: tuple[str, ...],
    flow_context: dict[str, object],
    artifact_content_blocks: tuple[dict[str, object], ...],
    estimate_breakdown: dict[str, object],
    runtime_contract: dict[str, object],
    tree_schema_version: str,
    root_node_ids: tuple[str, ...],
    mirrored_node_ids: tuple[str, ...],
    tool_schema_count: int,
) -> dict[str, object]:
    session_budget = metadata_dict(estimate_breakdown.get("session"))
    plan_budget = metadata_dict(estimate_breakdown.get("plan"))
    evidence_budget = metadata_dict(estimate_breakdown.get("evidence"))
    top_rendered_nodes = _top_rendered_nodes(estimate_breakdown)
    rendered_prompt_estimate = metadata_dict(
        estimate_breakdown.get("rendered_prompt"),
    ) or {
        "text_chars": len(rendered_prompt_body or ""),
        "text_tokens": estimate_text_tokens(rendered_prompt_body or ""),
    }
    node_estimate = metadata_dict(estimate_breakdown.get("node_visible"))
    contract_version = metadata_text(runtime_contract.get("contract_version"))
    contract_hash = metadata_text(runtime_contract.get("content_hash"))
    rendered_prompt_chars = len(rendered_prompt_body or "")
    rendered_prompt_tokens = estimate_text_tokens(rendered_prompt_body or "")
    direct_transcript_chars = _direct_transcript_chars(prompt)
    direct_transcript_tokens = estimate_text_tokens_from_chars(direct_transcript_chars)
    tree_tool_interaction_count = sum(
        1
        for node_id in included_node_ids
        if node_id.startswith("session.tool_interaction.")
    )
    tree_evidence_item_count = sum(
        1
        for node_id in included_node_ids
        if node_id.startswith("session.evidence.")
        and node_id != "session.evidence.current"
    )
    tool_schema_budget = metadata_dict(
        provider_attachment_report.get("tool_schema_mirror_budget"),
    )
    mirrored_schema_tokens = mirrored_schema_estimated_tokens(provider_attachments)
    content_budget = artifact_content_budget(
        provider_attachments=provider_attachments,
        artifact_content_blocks=artifact_content_blocks,
    )
    browser_affordance = browser_investigation_affordance_metadata(
        provider_attachments,
    )
    artifact_content_tokens = metadata_int(
        content_budget,
        "estimated_tokens",
    )
    duplicate_delivery_risk = (
        tree_tool_interaction_count > 0
        and any(message.role.value == "tool" for message in prompt.messages)
    )
    payload: dict[str, object] = {
        "parallel_recording": True,
        "tree_schema_version": tree_schema_version or CONTEXT_TREE_SCHEMA_VERSION,
        "root_node_ids": list(root_node_ids),
        "context_instructions_node_id": CONTEXT_INSTRUCTIONS_NODE_ID,
        "execution_current_node_id": EXECUTION_CURRENT_NODE_ID,
        "session_current_node_id": SESSION_CURRENT_NODE_ID,
        "history_delivery": "context_tree",
        "runtime_contract": dict(runtime_contract),
        "runtime_contract_version": contract_version,
        "runtime_contract_hash": contract_hash,
        "mirrored_tool_schema_count": tool_schema_count,
        "mirrored_tool_schema_estimated_tokens": mirrored_schema_tokens,
        "tool_schema_mirror_budget": dict(tool_schema_budget),
        "tool_schema_mirror_budget_status": (
            metadata_text(tool_schema_budget.get("status")) or "ok"
        ),
        "tool_schema_mirror_default_schema_source": metadata_text(
            tool_schema_budget.get("default_schema_source"),
        ),
        "tool_schema_mirror_available_count": metadata_int(
            tool_schema_budget,
            "available_count",
        ),
        "tool_schema_mirror_enabled_candidate_count": metadata_int(
            tool_schema_budget,
            "enabled_candidate_count",
        ),
        "tool_schema_mirror_default_requested_count": metadata_int(
            tool_schema_budget,
            "default_requested_count",
        ),
        "tool_schema_mirror_default_candidate_count": metadata_int(
            tool_schema_budget,
            "default_candidate_count",
        ),
        "tool_schema_mirror_default_mirrored_count": metadata_int(
            tool_schema_budget,
            "default_mirrored_count",
        ),
        "tool_schema_mirror_duplicate_count": metadata_int(
            tool_schema_budget,
            "duplicate_count",
        ),
        "tool_schema_mirror_groups": _metadata_dict_list(
            tool_schema_budget.get("groups"),
        ),
        "tool_schema_mirror_group_count": metadata_int(
            tool_schema_budget,
            "group_count",
        ),
        "tool_schema_mirror_visible_group_count": metadata_int(
            tool_schema_budget,
            "visible_group_count",
        ),
        "tool_schema_mirror_collapsed_group_count": metadata_int(
            tool_schema_budget,
            "collapsed_group_count",
        ),
        "tool_schema_mirror_default_group_count": metadata_int(
            tool_schema_budget,
            "default_group_count",
        ),
        "tool_schema_mirror_default_group_refs": _metadata_dict_list(
            tool_schema_budget.get("default_group_refs"),
        ),
        "tool_schema_mirror_default_group_ref_count": metadata_int(
            tool_schema_budget,
            "default_group_ref_count",
        ),
        "tool_schema_mirror_default_group_matches": _metadata_dict_list(
            tool_schema_budget.get("default_group_matches"),
        ),
        "tool_schema_mirror_default_group_match_count": metadata_int(
            tool_schema_budget,
            "default_group_match_count",
        ),
        "tool_schema_mirror_default_schema_priorities": metadata_dict(
            tool_schema_budget.get("default_schema_priorities"),
        ),
        "tool_schema_mirror_default_schema_reasons": metadata_dict(
            tool_schema_budget.get("default_schema_reasons"),
        ),
        "tool_schema_mirror_default_mirrored": _metadata_dict_list(
            tool_schema_budget.get("default_mirrored"),
        ),
        "tool_schema_mirror_skipped": _metadata_dict_list(
            tool_schema_budget.get("skipped"),
        ),
        "tool_schema_mirror_skipped_by_reason": metadata_dict(
            tool_schema_budget.get("skipped_by_reason"),
        ),
        "tool_schema_mirror_skipped_count": metadata_int(
            tool_schema_budget,
            "skipped_count",
        ),
        "tool_schema_mirror_max_count": metadata_int(
            tool_schema_budget,
            "max_count",
        ),
        "tool_schema_mirror_max_estimated_tokens": metadata_int(
            tool_schema_budget,
            "max_estimated_tokens",
        ),
        **browser_affordance,
        "mirrored_node_count": len(mirrored_node_ids),
        "rendered_prompt_estimate": dict(rendered_prompt_estimate),
        "node_visible_estimate": dict(node_estimate),
        "node_estimate_breakdown": dict(estimate_breakdown),
        "top_rendered_nodes": top_rendered_nodes,
        "active_session_id": prompt.active_session_id,
        "mode": prompt.mode.value,
        "flow_context": flow_context,
        "workspace_dir": prompt.workspace_dir,
        "prompt_report": (
            prompt.report.to_payload()
            if prompt.report is not None
            else None
        ),
        "direct_transcript_message_count": len(prompt.messages),
        "direct_transcript_roles": [message.role.value for message in prompt.messages],
        "direct_transcript_chars": direct_transcript_chars,
        "direct_transcript_estimated_tokens": direct_transcript_tokens,
        "rendered_prompt_chars": rendered_prompt_chars,
        "rendered_prompt_estimated_tokens": rendered_prompt_tokens,
        "estimated_provider_prompt_tokens": (
            rendered_prompt_tokens
            + direct_transcript_tokens
            + mirrored_schema_tokens
            + artifact_content_tokens
        ),
        "artifact_content_budget": dict(content_budget),
        "artifact_content_estimated_tokens": artifact_content_tokens,
        "artifact_content_candidate_count": metadata_int(
            content_budget,
            "candidate_count",
        ),
        "artifact_content_text_block_count": metadata_int(
            content_budget,
            "text_block_count",
        ),
        "artifact_content_image_count": metadata_int(
            content_budget,
            "image_count",
        ),
        "artifact_content_file_count": metadata_int(
            content_budget,
            "file_count",
        ),
        "artifact_content_omitted_count": metadata_int(
            content_budget,
            "omitted_count",
        ),
        "duplicate_tool_delivery_risk": duplicate_delivery_risk,
        "tree_session_message_count": sum(
            1 for node_id in included_node_ids if node_id.startswith("session.message.")
        ),
        "session_message_node_refs": _session_message_node_refs(included_node_ids),
        "current_inbound_node_id": _current_inbound_node_id(
            run=run,
            prompt=prompt,
            included_node_ids=included_node_ids,
        ),
        "tree_tool_interaction_count": tree_tool_interaction_count,
        "tool_interaction_node_refs": _tool_interaction_node_refs(included_node_ids),
        "tree_evidence_item_count": tree_evidence_item_count,
        "evidence_node_refs": _evidence_node_refs(included_node_ids),
        "session_estimated_text_tokens": metadata_int(
            session_budget,
            "text_tokens",
        ),
        "session_estimated_text_chars": metadata_int(
            session_budget,
            "text_chars",
        ),
        "session_segment_node_count": metadata_int(
            session_budget,
            "segment_node_count",
        ),
        "session_message_range_node_count": metadata_int(
            session_budget,
            "range_node_count",
        ),
        "session_range_warning_count": metadata_int(
            session_budget,
            "range_warning_count",
        ),
        "session_range_blocked_count": metadata_int(
            session_budget,
            "range_blocked_count",
        ),
        "session_range_limited_count": metadata_int(
            session_budget,
            "range_limited_count",
        ),
        "session_budget_status": metadata_text(session_budget.get("status")) or "ok",
        "work_plan_status": metadata_text(plan_budget.get("status")),
        "work_plan_phase": metadata_text(plan_budget.get("plan_phase")),
        "work_plan_update_reason": metadata_text(plan_budget.get("update_reason")),
        "work_plan_phase_changed": bool(plan_budget.get("phase_changed")),
        "work_plan_update_count": metadata_int(plan_budget, "plan_update_count"),
        "final_response_requires_evidence_path": bool(
            evidence_budget.get("final_response_requires_evidence_path"),
        ),
        "verified_evidence_path_count": metadata_int(
            evidence_budget,
            "verified_evidence_path_count",
        ),
        "verified_evidence_paths": _metadata_text_list(
            evidence_budget.get("verified_evidence_paths"),
        ),
        "browser_verified_evidence_path_count": metadata_int(
            evidence_budget,
            "browser_verified_evidence_path_count",
        ),
        "browser_verified_evidence_paths": _metadata_text_list(
            evidence_budget.get("browser_verified_evidence_paths"),
        ),
        "unverified_evidence_paths": _metadata_text_list(
            evidence_budget.get("unverified_evidence_paths"),
        ),
        "browser_tool_interaction_count": metadata_int(
            evidence_budget,
            "browser_tool_interaction_count",
        ),
        "browser_evidence_path_no_terminal_fact": bool(
            evidence_budget.get("browser_evidence_path_no_terminal_fact"),
        ),
        "browser_investigation_warning_count": metadata_int(
            evidence_budget,
            "browser_investigation_warning_count",
        ),
        "browser_investigation_warnings": _metadata_dict_list(
            evidence_budget.get("browser_investigation_warnings"),
        ),
        "browser_investigation_warning_types": _metadata_text_list(
            evidence_budget.get("browser_investigation_warning_types"),
        ),
        "folded_history_node_count": sum(
            1
            for node_id in included_node_ids
            if node_id.startswith("session.segment.compacted.")
            or node_id.startswith("session.segment.closed.")
            or node_id.startswith("session.segment.messages.")
        ),
        "artifact_content_block_count": len(artifact_content_blocks),
        "current_inbound_message_id": _current_inbound_message_id(
            run=run,
            prompt=prompt,
        ),
    }
    payload.update(context_render_budget_metadata(payload))
    return payload


def mirrored_schema_estimated_tokens(provider_attachments: dict[str, object]) -> int:
    raw_schemas = provider_attachments.get("tool_schemas")
    if not isinstance(raw_schemas, list):
        return 0
    total_chars = 0
    for schema in raw_schemas:
        if not isinstance(schema, dict):
            continue
        total_chars += len(str(schema.get("name") or ""))
        total_chars += len(str(schema.get("description") or ""))
        total_chars += len(str(schema.get("input_schema") or ""))
    return estimate_text_tokens_from_chars(total_chars)


def browser_investigation_affordance_metadata(
    provider_attachments: dict[str, object],
) -> dict[str, object]:
    schema_names = _provider_tool_schema_names(provider_attachments)
    browser_names = tuple(name for name in schema_names if name.startswith("browser."))
    runtime_code = tuple(
        name
        for name in browser_names
        if name
        in {
            "browser.runtime.inspect",
            "browser.script.find_request",
            "browser.code.search",
            "browser.script.extract_request",
            "browser.runtime.probe_client",
            "browser.runtime.call_client",
            "browser.script.inspect",
            "browser.script.list",
        }
    )
    network = tuple(
        name
        for name in browser_names
        if name.startswith("browser.network.")
    )
    stateful = tuple(
        name
        for name in browser_names
        if name
        in {
            "browser.action",
            "browser.action.trace",
            "browser.form.inspect",
            "browser.form.fill",
            "browser.overlay.observe",
            "browser.overlay.select",
            "browser.dom.inspect",
            "browser.dom.clickability",
            "browser.click",
            "browser.type",
        }
    )
    present_paths: list[str] = []
    missing_paths: list[str] = []
    if runtime_code:
        present_paths.append("runtime_and_code")
    else:
        missing_paths.append("runtime_and_code")
    if network:
        present_paths.append("network_truth")
    else:
        missing_paths.append("network_truth")
    if stateful:
        present_paths.append("stateful_interaction")
    else:
        missing_paths.append("stateful_interaction")
    status = "ok"
    route_bias = "balanced"
    if not browser_names:
        status = "missing_browser_tools"
        route_bias = "no_browser_affordance"
    elif runtime_code and network:
        status = "ok"
        route_bias = "runtime_network_visible"
    elif stateful and not runtime_code and not network:
        status = "dom_form_only"
        route_bias = "dom_form_click_bias"
    else:
        status = "partial"
        route_bias = "missing_evidence_path"
    return {
        "browser_investigation_affordance_status": status,
        "browser_investigation_route_bias": route_bias,
        "browser_investigation_present_paths": present_paths,
        "browser_investigation_missing_paths": missing_paths,
        "browser_evidence_path_ladder": _browser_evidence_path_ladder(
            present_paths=tuple(present_paths),
            runtime_code=runtime_code,
            network=network,
            stateful=stateful,
        ),
        "browser_investigation_schema_names": list(browser_names),
        "browser_investigation_runtime_code_schema_names": list(runtime_code),
        "browser_investigation_network_schema_names": list(network),
        "browser_investigation_stateful_schema_names": list(stateful),
    }


def _browser_evidence_path_ladder(
    *,
    present_paths: tuple[str, ...],
    runtime_code: tuple[str, ...],
    network: tuple[str, ...],
    stateful: tuple[str, ...],
) -> list[dict[str, object]]:
    present = set(present_paths)
    return [
        {
            "path": "runtime_and_code",
            "status": "present" if "runtime_and_code" in present else "missing",
            "schema_count": len(runtime_code),
            "schemas": list(runtime_code),
        },
        {
            "path": "network_truth",
            "status": "present" if "network_truth" in present else "missing",
            "schema_count": len(network),
            "schemas": list(network),
        },
        {
            "path": "stateful_interaction",
            "status": "present" if "stateful_interaction" in present else "missing",
            "schema_count": len(stateful),
            "schemas": list(stateful),
        },
    ]


def _provider_tool_schema_names(
    provider_attachments: dict[str, object],
) -> tuple[str, ...]:
    raw_schemas = provider_attachments.get("tool_schemas")
    if not isinstance(raw_schemas, list):
        return ()
    names: list[str] = []
    for schema in raw_schemas:
        if not isinstance(schema, dict):
            continue
        name = metadata_text(schema.get("name"))
        if name is not None:
            names.append(name)
    return tuple(dict.fromkeys(names))


def _top_rendered_nodes(estimate_breakdown: dict[str, object]) -> list[dict[str, object]]:
    value = estimate_breakdown.get("top_rendered_nodes")
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def mirrored_tool_schemas(
    provider_attachments: dict[str, object],
    *,
    mirror_available: bool,
) -> tuple[ToolSchema, ...] | None:
    if not mirror_available:
        return None
    raw_schemas = provider_attachments.get("tool_schemas")
    if not isinstance(raw_schemas, list):
        return ()
    schemas: list[ToolSchema] = []
    for raw_schema in raw_schemas:
        if not isinstance(raw_schema, dict):
            continue
        name = raw_schema.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        input_schema = raw_schema.get("input_schema")
        schemas.append(
            ToolSchema(
                name=name,
                description=(
                    str(raw_schema.get("description"))
                    if raw_schema.get("description") is not None
                    else ""
                ),
                input_schema=(
                    dict(input_schema) if isinstance(input_schema, dict) else {}
                ),
            ),
        )
    return tuple(schemas)


def _session_message_node_refs(
    included_node_ids: tuple[str, ...],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    prefix = "session.message."
    for node_id in included_node_ids:
        if not node_id.startswith(prefix):
            continue
        tail = node_id[len(prefix):]
        session_id, separator, sequence_text = tail.rpartition(".")
        if not separator or not session_id or not sequence_text.isdigit():
            refs.append({"node_id": node_id})
            continue
        refs.append(
            {
                "node_id": node_id,
                "session_id": session_id,
                "sequence_no": int(sequence_text),
            },
        )
    return refs


def _tool_interaction_node_refs(
    included_node_ids: tuple[str, ...],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    prefix = "session.tool_interaction."
    for node_id in included_node_ids:
        if not node_id.startswith(prefix):
            continue
        refs.append({"node_id": node_id})
    return refs


def _evidence_node_refs(
    included_node_ids: tuple[str, ...],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    prefix = "session.evidence."
    for node_id in included_node_ids:
        if not node_id.startswith(prefix) or node_id == "session.evidence.current":
            continue
        refs.append({"node_id": node_id})
    return refs


def _current_inbound_node_id(
    *,
    run: OrchestrationRun,
    prompt: RunPromptInput,
    included_node_ids: tuple[str, ...],
) -> str | None:
    included = set(included_node_ids)
    for message in prompt.messages:
        metadata = message.metadata
        if metadata.get("source_kind") != "orchestration_run":
            continue
        if metadata.get("source_id") != run.id:
            continue
        session_id = metadata.get("session_id")
        sequence_no = metadata.get("sequence_no")
        if not isinstance(session_id, str) or not session_id.strip():
            continue
        if isinstance(sequence_no, int):
            sequence_text = str(sequence_no)
        elif isinstance(sequence_no, str) and sequence_no.strip().isdigit():
            sequence_text = sequence_no.strip()
        else:
            continue
        node_id = f"session.message.{session_id.strip()}.{sequence_text}"
        if node_id in included:
            return node_id
    return None


def _current_inbound_message_id(
    *,
    run: OrchestrationRun,
    prompt: RunPromptInput,
) -> str | None:
    for message in prompt.messages:
        metadata = message.metadata
        if metadata.get("source_kind") != "orchestration_run":
            continue
        if metadata.get("source_id") != run.id:
            continue
        session_message_id = metadata.get("session_message_id")
        if isinstance(session_message_id, str) and session_message_id.strip():
            return session_message_id.strip()
    return None


def _direct_transcript_chars(prompt: RunPromptInput) -> int:
    return sum(_llm_message_content_chars(message.content) for message in prompt.messages)


def _metadata_dict_list(value: object) -> list[dict[str, object]]:
    if not isinstance(value, (list, tuple)):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _metadata_text_list(value: object) -> list[str]:
    if not isinstance(value, (list, tuple)):
        return []
    values = [metadata_text(item) for item in value]
    return list(dict.fromkeys(item for item in values if item is not None))


def _llm_message_content_chars(content: object) -> int:
    if isinstance(content, str):
        return len(content)
    if isinstance(content, list):
        return sum(_llm_content_block_chars(item) for item in content)
    if content is None:
        return 0
    return len(str(content))


def _llm_content_block_chars(value: object) -> int:
    if isinstance(value, dict):
        text = value.get("text")
        if isinstance(text, str):
            return len(text)
        data = value.get("data")
        if isinstance(data, str):
            return len(data)
        return len(str(value))
    if value is None:
        return 0
    return len(str(value))
