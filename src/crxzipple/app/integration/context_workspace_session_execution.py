from __future__ import annotations

from typing import Any

from crxzipple.app.integration.context_workspace_session_content_values import (
    json_fragment,
    optional_int,
    optional_text,
    text_estimate,
    truncate,
)
from crxzipple.modules.context_workspace.domain import (
    ContextAction,
    ContextNodeSeed,
    ContextNodeState,
)


_BASIC_ACTIONS = (
    ContextAction.EXPAND,
    ContextAction.COLLAPSE,
    ContextAction.PIN,
    ContextAction.UNPIN,
    ContextAction.ESTIMATE,
)


def execution_step_item_summaries(
    execution_query: Any,
    turn_id: str,
) -> tuple[dict[str, object], ...]:
    summaries: list[dict[str, object]] = []
    for chain in execution_query.list_execution_chains(turn_id):
        chain_id = getattr(chain, "id", None)
        if not isinstance(chain_id, str) or not chain_id.strip():
            continue
        for step in execution_query.list_execution_steps(chain_id):
            step_id = getattr(step, "id", None)
            if not isinstance(step_id, str) or not step_id.strip():
                continue
            for item in execution_query.list_execution_step_items(step_id):
                summary = getattr(item, "summary_payload", None)
                if isinstance(summary, dict):
                    summaries.append(summary)
    return tuple(summaries)


def execution_step_node_seeds(
    execution_query: Any,
    turn_id: str,
    *,
    parent_id: str,
) -> tuple[ContextNodeSeed, ...]:
    seeds: list[ContextNodeSeed] = []
    display_order = 10
    for chain in execution_query.list_execution_chains(turn_id):
        chain_id = _entity_id(chain)
        if chain_id is None:
            continue
        for step in execution_query.list_execution_steps(chain_id):
            step_id = _entity_id(step)
            if step_id is None:
                continue
            kind = _value_label(getattr(step, "kind", None)) or "step"
            status = _value_label(getattr(step, "status", None)) or "unknown"
            step_index = optional_int(getattr(step, "step_index", None)) or 0
            item_count = len(execution_query.list_execution_step_items(step_id))
            summary = (
                f"Execution step {step_index}: {kind}; status={status}; "
                f"items={item_count}."
            )
            seeds.append(
                ContextNodeSeed(
                    node_id=f"session.step.{_node_part(step_id)}",
                    parent_id=parent_id,
                    owner="session",
                    kind="session_step",
                    title=f"{step_index}. {kind}",
                    summary=summary,
                    state=ContextNodeState(collapsed=False, loaded=True),
                    actions=_BASIC_ACTIONS,
                    owner_ref={
                        "turn_id": turn_id,
                        "run_id": turn_id,
                        "chain_id": chain_id,
                        "step_id": step_id,
                        "step_index": step_index,
                        "kind": kind,
                        "status": status,
                    },
                    estimate=text_estimate(summary),
                    display_order=display_order + step_index,
                    metadata={
                        "item_count": item_count,
                        "chain_status": _value_label(getattr(chain, "status", None))
                        or "",
                    },
                ),
            )
            display_order += 10
    return tuple(seeds)


def execution_step_item_node_seeds(
    execution_query: Any,
    step_id: str,
    *,
    parent_id: str,
) -> tuple[ContextNodeSeed, ...]:
    seeds: list[ContextNodeSeed] = []
    for index, item in enumerate(
        execution_query.list_execution_step_items(step_id),
        start=1,
    ):
        item_id = _entity_id(item)
        if item_id is None:
            continue
        item_kind = _value_label(getattr(item, "kind", None)) or "execution_item"
        status = _value_label(getattr(item, "status", None)) or "unknown"
        summary_payload = getattr(item, "summary_payload", None)
        runtime_semantic_kind = _runtime_semantic_kind(summary_payload)
        runtime_kind = _runtime_node_kind_for_execution_item(
            item_kind,
            runtime_semantic_kind=runtime_semantic_kind,
        )
        summary = _execution_item_summary(
            item_kind=item_kind,
            status=status,
            summary_payload=summary_payload,
        )
        owner_ref = _execution_item_owner_ref(item)
        owner_ref.update(
            {
                "step_id": step_id,
                "execution_step_item_id": item_id,
                "kind": item_kind,
                "status": status,
            },
        )
        seeds.append(
            ContextNodeSeed(
                node_id=f"session.step.item.{_node_part(item_id)}",
                parent_id=parent_id,
                owner="session",
                kind=runtime_kind,
                title=f"{index}. {item_kind}",
                summary=summary,
                state=ContextNodeState(collapsed=True, loaded=True),
                actions=_BASIC_ACTIONS,
                owner_ref=owner_ref,
                estimate=text_estimate(summary),
                display_order=index * 10,
                metadata={
                    **(
                        {"runtime_semantic_kind": runtime_semantic_kind}
                        if runtime_semantic_kind is not None
                        else {}
                    ),
                    "summary_payload_keys": sorted(str(key) for key in summary_payload)
                    if isinstance(summary_payload, dict)
                    else [],
                },
            ),
        )
    return tuple(seeds)


def _entity_id(entity: object) -> str | None:
    return optional_text(getattr(entity, "id", None))


def _value_label(value: object) -> str | None:
    raw_value = getattr(value, "value", value)
    return optional_text(raw_value)


def _runtime_node_kind_for_execution_item(
    item_kind: str,
    *,
    runtime_semantic_kind: str | None = None,
) -> str:
    semantic_kind = _runtime_node_kind_for_semantic_kind(runtime_semantic_kind)
    if semantic_kind is not None:
        return semantic_kind
    return {
        "llm_invocation": "runtime_llm_invocation",
        "continuation_decision": "runtime_continuation_decision",
        "tool_call": "runtime_assistant_tool_call",
        "tool_run": "runtime_tool_run",
        "tool_result": "runtime_tool_result",
        "approval_request": "runtime_approval_request",
        "session_message": "runtime_session_message",
        "context_snapshot": "runtime_context_snapshot",
    }.get(item_kind, "runtime_execution_item")


def _runtime_node_kind_for_semantic_kind(runtime_semantic_kind: str | None) -> str | None:
    if runtime_semantic_kind is None:
        return None
    return {
        "runtime.assistant_progress": "runtime_assistant_progress",
        "runtime.assistant_message": "runtime_assistant_message",
        "runtime.assistant_tool_call": "runtime_assistant_tool_call",
        "runtime.final_answer": "runtime_final_answer",
        "runtime.reasoning": "runtime_reasoning",
        "runtime.tool_result": "runtime_tool_result",
        "runtime.provider_external_activity": "runtime_provider_external_activity",
        "runtime.context_compaction": "runtime_context_compaction",
        "runtime.structured_output": "runtime_structured_output",
        "runtime.blocked_state": "runtime_blocked_state",
    }.get(runtime_semantic_kind)


def _runtime_semantic_kind(summary_payload: object) -> str | None:
    if not isinstance(summary_payload, dict):
        return None
    return optional_text(summary_payload.get("runtime_semantic_kind"))


def _execution_item_summary(
    *,
    item_kind: str,
    status: str,
    summary_payload: object,
) -> str:
    facts: list[str] = [f"{item_kind}; status={status}"]
    if isinstance(summary_payload, dict):
        for key in (
            "assistant_progress_item_ids",
            "assistant_message_item_ids",
            "tool_call_names",
            "tool_call_id",
            "tool_run_id",
            "llm_invocation_id",
            "llm_response_item_id",
            "runtime_semantic_kind",
            "session_item_id",
        ):
            value = summary_payload.get(key)
            if value in (None, "", (), [], {}):
                continue
            facts.append(f"{key}={json_fragment(value)}")
    return truncate("; ".join(facts), 320)


def _execution_item_owner_ref(item: object) -> dict[str, object]:
    owner = getattr(item, "owner", None)
    owner_ref: dict[str, object] = {}
    if owner is not None:
        owner_kind = optional_text(getattr(owner, "owner_kind", None))
        owner_id = optional_text(getattr(owner, "owner_id", None))
        if owner_kind is not None:
            owner_ref["owner_kind"] = owner_kind
        if owner_id is not None:
            owner_ref["owner_id"] = owner_id
    summary_payload = getattr(item, "summary_payload", None)
    if isinstance(summary_payload, dict):
        for key in (
            "llm_invocation_id",
            "llm_response_item_id",
            "runtime_semantic_kind",
            "session_item_id",
            "tool_call_id",
            "tool_run_id",
            "request_render_snapshot_id",
            "approval_request_id",
        ):
            value = optional_text(summary_payload.get(key))
            if value is not None:
                owner_ref[key] = value
    return owner_ref


def _node_part(value: str) -> str:
    return "".join(
        char if char.isalnum() or char in {"-", "_"} else "_"
        for char in value
    )
