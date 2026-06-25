from __future__ import annotations

from crxzipple.app.integration.context_workspace_session_content_values import (
    optional_int,
    optional_text,
    text_estimate,
)
from crxzipple.app.integration.context_workspace_session_segment_values import node_part
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


def tool_interaction_range_preview(seed: ContextNodeSeed) -> str:
    if bool(seed.metadata.get("frontier")) and not seed.state.collapsed and seed.content:
        return seed.content
    if seed.summary:
        return f"tool_interaction: {seed.summary}"
    content_digest = optional_text(seed.metadata.get("content_digest"))
    if content_digest is not None:
        return f"tool_interaction: collapsed; content_sha256={content_digest[:12]}."
    return "tool_interaction: collapsed; expand for refs."


def collapse_consumed_tool_history_seeds(
    seeds: tuple[ContextNodeSeed, ...],
    *,
    parent_id: str,
    visible_limit: int,
) -> tuple[ContextNodeSeed, ...]:
    consumed_tool_seeds = tuple(
        seed
        for seed in seeds
        if seed.kind == "tool_interaction"
        and bool(seed.metadata.get("consumed"))
        and not bool(seed.metadata.get("frontier"))
    )
    if not consumed_tool_seeds:
        return seeds
    visible_count = max(int(visible_limit), 0)
    hidden_count = max(len(consumed_tool_seeds) - visible_count, 0)
    if hidden_count <= 0:
        return seeds
    visible_ids = {
        seed.node_id
        for seed in sorted(
            consumed_tool_seeds,
            key=lambda item: int(item.metadata.get("result_sequence_no") or 0),
        )[-visible_count:]
    }
    hidden_seeds = tuple(
        seed for seed in consumed_tool_seeds if seed.node_id not in visible_ids
    )
    hidden_ids = {seed.node_id for seed in hidden_seeds}
    range_seed = _consumed_tool_history_range_seed(
        hidden_seeds,
        parent_id=parent_id,
    )
    if range_seed is None:
        return seeds
    output: list[ContextNodeSeed] = []
    inserted = False
    for seed in seeds:
        if seed.node_id not in hidden_ids:
            output.append(seed)
            continue
        if not inserted:
            output.append(range_seed)
            inserted = True
    return tuple(output)


def _consumed_tool_history_range_seed(
    hidden_seeds: tuple[ContextNodeSeed, ...],
    *,
    parent_id: str,
) -> ContextNodeSeed | None:
    if not hidden_seeds:
        return None
    ordered = tuple(sorted(hidden_seeds, key=lambda seed: seed.display_order))
    first = ordered[0]
    last = ordered[-1]
    session_key = optional_text(first.owner_ref.get("session_key"))
    session_id = optional_text(first.owner_ref.get("session_id"))
    first_sequence = optional_int(first.owner_ref.get("call_sequence_no"))
    last_sequence = optional_int(last.owner_ref.get("result_sequence_no"))
    if session_key is None or session_id is None:
        return None
    if first_sequence is None or last_sequence is None:
        return None
    status_counts: dict[str, int] = {}
    tool_counts: dict[str, int] = {}
    for seed in ordered:
        status = str(
            seed.metadata.get("lifecycle_status")
            or seed.metadata.get("status")
            or "unknown",
        )
        seed_tool_name = str(seed.metadata.get("tool_name") or "tool")
        status_counts[status] = status_counts.get(status, 0) + 1
        tool_counts[seed_tool_name] = tool_counts.get(seed_tool_name, 0) + 1
    status_label = _count_label(status_counts)
    tool_label = _count_label(tool_counts, limit=6)
    summary = (
        f"{len(ordered)} consumed tool interactions are folded into this active "
        f"session history range, sequences {first_sequence}-{last_sequence}."
    )
    if status_label:
        summary = f"{summary} Status: {status_label}."
    if tool_label:
        summary = f"{summary} Tools: {tool_label}."
    return ContextNodeSeed(
        node_id=(
            f"session.tool_interactions.consumed.{node_part(session_id)}."
            f"{first_sequence}.{last_sequence}"
        ),
        parent_id=parent_id,
        owner="session",
        kind="session_tool_interaction_range",
        title=f"Consumed Tool History {first_sequence}-{last_sequence}",
        summary=summary,
        state=ContextNodeState(collapsed=True, loaded=True),
        actions=_BASIC_ACTIONS,
        owner_ref={
            "session_key": session_key,
            "session_id": session_id,
            "from_sequence_no": first_sequence,
            "to_sequence_no": last_sequence,
            "hidden_tool_interaction_count": len(ordered),
        },
        estimate=text_estimate(summary),
        display_order=first.display_order,
        metadata={
            "hidden_tool_interaction_count": len(ordered),
            "status_counts": status_counts,
            "tool_counts": tool_counts,
            "from_sequence_no": first_sequence,
            "to_sequence_no": last_sequence,
            "range_reason_code": "active_consumed_tool_history_fold",
        },
    )


def _count_label(counts: dict[str, int], *, limit: int = 4) -> str:
    if not counts:
        return ""
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    visible = ordered[: max(limit, 1)]
    label = ", ".join(f"{key}={count}" for key, count in visible)
    omitted = len(ordered) - len(visible)
    if omitted > 0:
        label = f"{label}, +{omitted} more"
    return label
