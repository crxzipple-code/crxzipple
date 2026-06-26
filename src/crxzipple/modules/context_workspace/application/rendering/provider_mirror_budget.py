from __future__ import annotations

import json

from crxzipple.modules.context_workspace.domain import ContextNode

from .provider_mirror_policy import ToolSurfacePolicy


def new_tool_schema_mirror_budget(
    existing_schemas: list[dict[str, object]],
    *,
    policy: ToolSurfacePolicy | None = None,
) -> dict[str, object]:
    if policy is None:
        policy = ToolSurfacePolicy()
    estimated_tokens = sum(
        provider_schema_estimated_tokens(schema) for schema in existing_schemas
    )
    budget = {
        "status": "ok",
        "max_count": policy.max_count,
        "max_estimated_tokens": policy.max_estimated_tokens,
        "initial_count": len(existing_schemas),
        "initial_estimated_tokens": estimated_tokens,
        "available_count": 0,
        "enabled_candidate_count": 0,
        "default_schema_source": None,
        "default_requested_count": 0,
        "default_candidate_count": 0,
        "default_mirrored_count": 0,
        "duplicate_count": 0,
        "mirrored_count": len(existing_schemas),
        "mirrored_added_count": 0,
        "estimated_tokens": estimated_tokens,
        "skipped_count": 0,
        "skipped_by_reason": {},
        "skipped": [],
        "default_mirrored": [],
        "groups": [],
        "group_count": 0,
        "visible_group_count": 0,
        "collapsed_group_count": 0,
        "default_group_count": 0,
    }
    budget.update(policy.budget_metadata())
    return budget


def record_tool_schema_group_visibility(
    budget: dict[str, object],
    *,
    nodes: tuple[ContextNode, ...],
    policy: ToolSurfacePolicy,
) -> None:
    groups: list[dict[str, object]] = []
    visible_count = 0
    collapsed_count = 0
    default_count = 0
    for node in nodes:
        if node.owner != "tool":
            continue
        if node.kind not in {"tool_bundle", "tool_bundle_group", "tool_cli_source"}:
            continue
        source_id = _node_text(node.owner_ref.get("source_id")) or _node_text(
            node.metadata.get("source_id"),
        )
        group_key = _node_text(node.owner_ref.get("group_key")) or _node_text(
            node.metadata.get("group_key"),
        )
        if node.kind == "tool_bundle":
            group_key = group_key or "source"
        if source_id is None and group_key is None:
            continue
        is_default_group = _group_matches_default_refs(
            node_id=node.id,
            source_id=source_id,
            group_key=group_key,
            refs=policy.default_group_refs,
        )
        if is_default_group:
            default_count += 1
        if node.state.snapshot_visible:
            visible_count += 1
        if node.state.collapsed:
            collapsed_count += 1
        default_schema_ids = _node_text_list(
            node.metadata.get("default_tool_schema_ids"),
        )
        group_record: dict[str, object] = {
            "node_id": node.id,
            "kind": node.kind,
            "title": node.title,
            "state": _node_state_label(node),
            "visibility": (
                "visible_collapsed" if node.state.collapsed else "visible_expanded"
            ),
            "function_count": _node_int(
                node.owner_ref.get("function_count"),
                fallback=_node_int(node.metadata.get("function_count")),
            ),
            "capability_ids": _node_text_list(node.metadata.get("capability_ids")),
            "default_group": is_default_group,
            "default_schema_count": len(default_schema_ids),
        }
        if source_id is not None:
            group_record["source_id"] = source_id
        if group_key is not None:
            group_record["group_key"] = group_key
        source_kind = _node_text(node.metadata.get("source_kind"))
        if source_kind is not None:
            group_record["source_kind"] = source_kind
        if default_schema_ids:
            group_record["default_schema_ids"] = default_schema_ids[:16]
        default_schema_source = _node_text(
            node.metadata.get("default_tool_schema_source"),
        )
        if default_schema_source is not None:
            group_record["default_schema_source"] = default_schema_source
        groups.append(group_record)
    budget["groups"] = groups[:64]
    budget["group_count"] = len(groups)
    budget["visible_group_count"] = visible_count
    budget["collapsed_group_count"] = collapsed_count
    budget["default_group_count"] = default_count


def provider_schema_estimated_tokens(schema: dict[str, object]) -> int:
    try:
        chars = len(json.dumps(schema, ensure_ascii=False, sort_keys=True))
    except TypeError:
        chars = len(str(schema))
    return max((chars + 3) // 4, 1)


def tool_schema_budget_skip_reason(
    *,
    schema_tokens: int,
    current_count: int,
    current_tokens: int,
    policy: ToolSurfacePolicy | None = None,
) -> str | None:
    if policy is None:
        policy = ToolSurfacePolicy()
    if current_count >= policy.max_count:
        return "count_limit"
    if current_tokens + schema_tokens > policy.max_estimated_tokens:
        return "token_limit"
    return None


def record_tool_schema_budget_skip(
    budget: dict[str, object],
    *,
    node_id: str,
    schema_name: str,
    reason: str,
    schema_tokens: int,
    selection: str = "state",
    priority: int | None = None,
    bootstrap_reason: str | None = None,
) -> None:
    budget["skipped_count"] = int(budget.get("skipped_count") or 0) + 1
    skipped_by_reason = budget.get("skipped_by_reason")
    if not isinstance(skipped_by_reason, dict):
        skipped_by_reason = {}
        budget["skipped_by_reason"] = skipped_by_reason
    skipped_by_reason[reason] = int(skipped_by_reason.get(reason) or 0) + 1
    skipped = budget.get("skipped")
    if not isinstance(skipped, list):
        skipped = []
        budget["skipped"] = skipped
    if len(skipped) < 16:
        skipped.append(
            {
                "node_id": node_id,
                "name": schema_name,
                "reason": reason,
                "estimated_tokens": schema_tokens,
                "selection": selection,
                **({"priority": priority} if priority is not None else {}),
                **(
                    {"bootstrap_reason": bootstrap_reason}
                    if bootstrap_reason is not None
                    else {}
                ),
            },
        )


def record_default_tool_schema_mirror(
    budget: dict[str, object],
    *,
    node_id: str,
    schema_name: str,
    priority: int,
    bootstrap_reason: str | None,
) -> None:
    mirrored = budget.get("default_mirrored")
    if not isinstance(mirrored, list):
        mirrored = []
        budget["default_mirrored"] = mirrored
    if len(mirrored) >= 32:
        return
    mirrored.append(
        {
            "node_id": node_id,
            "name": schema_name,
            "priority": priority,
            **(
                {"bootstrap_reason": bootstrap_reason}
                if bootstrap_reason is not None
                else {}
            ),
        },
    )


def _group_matches_default_refs(
    *,
    node_id: str | None,
    source_id: str | None,
    group_key: str | None,
    refs: tuple[dict[str, str], ...],
) -> bool:
    for ref in refs:
        ref_node_id = _node_text(ref.get("node_id"))
        ref_source_id = _node_text(ref.get("source_id"))
        ref_group_key = _node_text(ref.get("group_key"))
        if ref_node_id is not None and ref_node_id != node_id:
            continue
        if ref_source_id is not None and ref_source_id != source_id:
            continue
        if ref_group_key is not None and ref_group_key != group_key:
            continue
        if ref_node_id is None and ref_source_id is None and ref_group_key is None:
            continue
        return True
    return False


def _node_state_label(node: ContextNode) -> str:
    if node.state.opened:
        return "opened"
    return "collapsed" if node.state.collapsed else "expanded"


def _node_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _node_text_list(value: object) -> list[str]:
    if isinstance(value, str):
        values: tuple[object, ...] = (value,)
    elif isinstance(value, (list, tuple, set, frozenset)):
        values = tuple(value)
    else:
        values = ()
    result: list[str] = []
    for item in values:
        text = _node_text(item)
        if text is not None and text not in result:
            result.append(text)
    return result


def _node_int(value: object, *, fallback: int = 0) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return max(value, 0)
    if isinstance(value, float):
        return max(int(value), 0)
    if isinstance(value, str) and value.strip():
        try:
            parsed = int(value.strip())
        except ValueError:
            return fallback
        return max(parsed, 0)
    return fallback


__all__ = [
    "new_tool_schema_mirror_budget",
    "provider_schema_estimated_tokens",
    "record_default_tool_schema_mirror",
    "record_tool_schema_budget_skip",
    "record_tool_schema_group_visibility",
    "tool_schema_budget_skip_reason",
]
