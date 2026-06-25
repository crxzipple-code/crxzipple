from __future__ import annotations

from crxzipple.app.integration.context_workspace_session_content import (
    is_function_call_message,
    tool_call_id,
)
from crxzipple.app.integration.context_workspace_session_message_nodes import (
    current_inbound_sequence_no,
    message_node_seed,
)
from crxzipple.app.integration.context_workspace_session_tool_history import (
    collapse_consumed_tool_history_seeds,
    tool_interaction_range_preview,
)
from crxzipple.app.integration.context_workspace_session_tool_interactions import (
    is_tool_interaction_frontier,
    tool_interaction_node_seed,
    tool_lifecycle_facts_for_result,
)
from crxzipple.modules.context_workspace.domain import ContextNodeSeed
from crxzipple.modules.session.domain import SessionItem

_TOOL_INTERACTION_NODE_REVISION = "2026-06-09.tool_interaction_visible_result.v2"


def message_node_seeds(
    messages: tuple[SessionItem, ...],
    *,
    parent_id: str,
    current_run_id: str | None = None,
    consumed_through_sequence_no: int | None = None,
    tool_lifecycle_facts: dict[str, dict[str, object]] | None = None,
    collapse_consumed_tool_history: bool = False,
    consumed_tool_history_visible_limit: int = 8,
    only_tool_interactions: bool = False,
) -> tuple[ContextNodeSeed, ...]:
    sorted_messages = tuple(sorted(messages, key=lambda item: item.sequence_no))
    inbound_sequence_no = current_inbound_sequence_no(
        sorted_messages,
        current_run_id=current_run_id,
    )
    tool_results_by_call_id = {
        call_id: message
        for message in sorted_messages
        if message.role == "tool"
        for call_id in (tool_call_id(message),)
        if call_id is not None
    }
    paired_message_ids: set[str] = set()
    seeds: list[ContextNodeSeed] = []
    for message in sorted_messages:
        if message.id in paired_message_ids:
            continue
        call_id = tool_call_id(message)
        if is_function_call_message(message) and call_id is not None:
            result = tool_results_by_call_id.get(call_id)
            if result is not None:
                seeds.append(
                    tool_interaction_node_seed(
                        call_message=message,
                        result_message=result,
                        parent_id=parent_id,
                        frontier=is_tool_interaction_frontier(
                            call_message=message,
                            result_message=result,
                            current_inbound_sequence_no=inbound_sequence_no,
                            consumed_through_sequence_no=consumed_through_sequence_no,
                        ),
                        consumed_through_sequence_no=consumed_through_sequence_no,
                        current_run_id=current_run_id,
                        current_inbound_sequence_no=inbound_sequence_no,
                        lifecycle_facts=tool_lifecycle_facts_for_result(
                            result,
                            tool_lifecycle_facts or {},
                        ),
                    ),
                )
                paired_message_ids.add(message.id)
                paired_message_ids.add(result.id)
                continue
        if only_tool_interactions:
            continue
        seeds.append(
            message_node_seed(
                message,
                parent_id=parent_id,
                current_run_id=current_run_id,
            ),
        )
    if not collapse_consumed_tool_history:
        return tuple(seeds)
    return collapse_consumed_tool_history_seeds(
        tuple(seeds),
        parent_id=parent_id,
        visible_limit=consumed_tool_history_visible_limit,
    )


def current_items_range_prompt_content(
    messages: tuple[SessionItem, ...],
    *,
    current_run_id: str | None,
    visible_tool_limit: int,
) -> str:
    if not messages:
        return ""
    first_sequence_no = messages[0].sequence_no
    last_sequence_no = messages[-1].sequence_no
    lines = [
        (
            f"active_segment: {len(messages)} items, "
            f"sequences {first_sequence_no}-{last_sequence_no}."
        ),
    ]
    tool_seeds = tuple(
        seed
        for seed in message_node_seeds(
            messages,
            parent_id="session.items.current.preview",
            current_run_id=current_run_id,
            consumed_through_sequence_no=None,
            collapse_consumed_tool_history=True,
            consumed_tool_history_visible_limit=visible_tool_limit,
            only_tool_interactions=True,
        )
        if seed.kind == "tool_interaction" and seed.content
    )
    if not tool_seeds:
        return "\n".join(lines)
    lines.append("recent_tool_interactions:")
    for seed in tool_seeds:
        lines.extend(
            f"  {line}"
            for line in tool_interaction_range_preview(seed).splitlines()
        )
    return "\n".join(lines)
