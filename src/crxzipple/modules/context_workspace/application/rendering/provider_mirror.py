from __future__ import annotations

from dataclasses import dataclass, field
import json

from crxzipple.modules.context_workspace.domain import ContextNode


TOOL_SCHEMA_MIRROR_MAX_COUNT = 32
TOOL_SCHEMA_MIRROR_MAX_ESTIMATED_TOKENS = 24_000


@dataclass(frozen=True, slots=True)
class ToolSurfacePolicy:
    default_schema_ids: frozenset[str] = frozenset()
    default_schema_source: str = "runtime_policy"
    default_group_refs: tuple[dict[str, str], ...] = ()
    default_group_matches: tuple[dict[str, str], ...] = ()
    default_schema_priorities: dict[str, int] = field(default_factory=dict)
    default_schema_reasons: dict[str, str] = field(default_factory=dict)
    max_count: int = TOOL_SCHEMA_MIRROR_MAX_COUNT
    max_estimated_tokens: int = TOOL_SCHEMA_MIRROR_MAX_ESTIMATED_TOKENS

    @classmethod
    def from_metadata(cls, metadata: dict[str, object]) -> "ToolSurfacePolicy":
        return cls(
            default_schema_ids=default_tool_schema_ids_from_metadata(metadata),
            default_schema_source=default_tool_schema_source_from_metadata(metadata),
            default_group_refs=default_tool_schema_group_refs_from_metadata(metadata),
            default_group_matches=default_tool_schema_group_matches_from_metadata(
                metadata,
            ),
            default_schema_priorities=default_tool_schema_priorities_from_metadata(
                metadata,
            ),
            default_schema_reasons=default_tool_schema_reasons_from_metadata(metadata),
            max_count=positive_int_from_metadata(
                metadata.get("tool_schema_mirror_max_count"),
                fallback=TOOL_SCHEMA_MIRROR_MAX_COUNT,
            ),
            max_estimated_tokens=positive_int_from_metadata(
                metadata.get("tool_schema_mirror_max_estimated_tokens"),
                fallback=TOOL_SCHEMA_MIRROR_MAX_ESTIMATED_TOKENS,
            ),
        )

    def priority_for(
        self,
        node: ContextNode,
        *,
        schema_name: str,
        enabled_by_default: bool,
    ) -> int:
        if schema_name.startswith("context_tree."):
            return 0
        tool_id = node.owner_ref.get("tool_id")
        if isinstance(tool_id, str) and tool_id.startswith("context_tree."):
            return 0
        if enabled_by_default:
            for key in (schema_name, tool_id, node.id):
                if isinstance(key, str) and key in self.default_schema_priorities:
                    return self.default_schema_priorities[key]
            return 100
        return 10_000

    def reason_for(self, node: ContextNode, *, schema_name: str) -> str | None:
        tool_id = node.owner_ref.get("tool_id")
        for key in (schema_name, tool_id, node.id):
            if isinstance(key, str):
                reason = self.default_schema_reasons.get(key)
                if reason:
                    return reason
        return None

    def budget_metadata(self) -> dict[str, object]:
        metadata: dict[str, object] = {
            "policy_kind": "tool_surface_policy",
            "max_count": self.max_count,
            "max_estimated_tokens": self.max_estimated_tokens,
        }
        if self.default_schema_ids:
            metadata["default_schema_source"] = self.default_schema_source
            metadata["default_requested_count"] = len(self.default_schema_ids)
        if self.default_group_refs:
            metadata["default_group_refs"] = [
                dict(ref) for ref in self.default_group_refs
            ]
            metadata["default_group_ref_count"] = len(self.default_group_refs)
        if self.default_group_matches:
            metadata["default_group_matches"] = [
                dict(match) for match in self.default_group_matches
            ]
            metadata["default_group_match_count"] = len(self.default_group_matches)
        if self.default_schema_priorities:
            metadata["default_schema_priorities"] = dict(
                self.default_schema_priorities,
            )
        if self.default_schema_reasons:
            metadata["default_schema_reasons"] = dict(self.default_schema_reasons)
        return metadata


def render_provider_attachments(
    nodes: tuple[ContextNode, ...],
    *,
    base: dict[str, object],
    render_metadata: dict[str, object],
) -> tuple[dict[str, object], tuple[str, ...], bool, dict[str, object]]:
    attachments = dict(base)
    tool_schemas = list(provider_tool_schemas(attachments.get("tool_schemas")))
    artifact_candidates = list(
        provider_artifact_candidates(attachments.get("artifact_content_candidates")),
    )
    tool_surface_policy = ToolSurfacePolicy.from_metadata(render_metadata)
    mirrored_node_ids: list[str] = []
    mirrored_tool_node_ids: set[str] = set()
    tool_schema_mirror_available = False
    tool_schema_budget = new_tool_schema_mirror_budget(
        tool_schemas,
        policy=tool_surface_policy,
    )
    record_tool_schema_group_visibility(
        tool_schema_budget,
        nodes=nodes,
        policy=tool_surface_policy,
    )
    existing_tool_names = {
        schema.get("name")
        for schema in tool_schemas
        if isinstance(schema.get("name"), str)
    }
    tool_nodes: list[tuple[int, int, ContextNode, dict[str, object], str, bool]] = []
    for index, node in enumerate(nodes):
        if node.owner != "tool" or node.kind != "tool_function":
            continue
        if isinstance(node.metadata.get("provider_schema"), dict):
            tool_schema_mirror_available = True
            tool_schema_budget["available_count"] += 1
        schema = node.metadata.get("provider_schema")
        if not isinstance(schema, dict):
            continue
        schema_name = schema.get("name")
        if not isinstance(schema_name, str) or not schema_name.strip():
            continue
        enabled_by_default = node_matches_default_tool_schema(
            node,
            schema_name=schema_name,
            policy=tool_surface_policy,
        )
        if not node.state.schema_enabled and not enabled_by_default:
            continue
        tool_schema_budget["enabled_candidate_count"] += 1
        if enabled_by_default:
            tool_schema_budget["default_candidate_count"] += 1
        tool_nodes.append(
            (
                tool_schema_mirror_priority(
                    node,
                    schema_name=schema_name,
                    enabled_by_default=enabled_by_default,
                    policy=tool_surface_policy,
                ),
                index,
                node,
                schema,
                schema_name,
                enabled_by_default,
            ),
        )
    for (
        _priority,
        _index,
        node,
        schema,
        schema_name,
        enabled_by_default,
    ) in sorted(tool_nodes):
        if schema_name in existing_tool_names:
            tool_schema_budget["duplicate_count"] += 1
            continue
        schema_tokens = provider_schema_estimated_tokens(schema)
        skip_reason = tool_schema_budget_skip_reason(
            schema_tokens=schema_tokens,
            current_count=len(tool_schemas),
            current_tokens=int(tool_schema_budget["estimated_tokens"]),
            policy=tool_surface_policy,
        )
        if skip_reason is not None:
            record_tool_schema_budget_skip(
                tool_schema_budget,
                node_id=node.id,
                schema_name=schema_name,
                reason=skip_reason,
                schema_tokens=schema_tokens,
                selection="default" if enabled_by_default else "state",
                priority=tool_surface_policy.priority_for(
                    node,
                    schema_name=schema_name,
                    enabled_by_default=enabled_by_default,
                ),
                bootstrap_reason=tool_surface_policy.reason_for(
                    node,
                    schema_name=schema_name,
                ),
            )
            continue
        tool_schemas.append(dict(schema))
        existing_tool_names.add(schema_name)
        mirrored_node_ids.append(node.id)
        mirrored_tool_node_ids.add(node.id)
        if enabled_by_default:
            tool_schema_budget["default_mirrored_count"] += 1
            record_default_tool_schema_mirror(
                tool_schema_budget,
                node_id=node.id,
                schema_name=schema_name,
                priority=tool_surface_policy.priority_for(
                    node,
                    schema_name=schema_name,
                    enabled_by_default=enabled_by_default,
                ),
                bootstrap_reason=tool_surface_policy.reason_for(
                    node,
                    schema_name=schema_name,
                ),
            )
        tool_schema_budget["estimated_tokens"] = (
            int(tool_schema_budget["estimated_tokens"]) + schema_tokens
        )
    existing_artifact_node_ids = {
        candidate.get("node_id")
        for candidate in artifact_candidates
        if isinstance(candidate.get("node_id"), str)
    }
    for node in nodes:
        if node.owner != "artifacts":
            continue
        if node.kind not in {"artifact_image", "artifact_file"}:
            continue
        if not (node.state.opened or node.state.pinned):
            continue
        artifact_id = node.owner_ref.get("artifact_id")
        if not isinstance(artifact_id, str) or not artifact_id.strip():
            continue
        if node.id in existing_artifact_node_ids:
            continue
        artifact_candidates.append(
            {
                "node_id": node.id,
                "artifact_id": artifact_id.strip(),
                "kind": node.kind,
                "mime_type": node.metadata.get("mime_type"),
                "name": node.metadata.get("name") or node.title,
                "preferred_variant": node.owner_ref.get("preferred_variant"),
            },
        )
        existing_artifact_node_ids.add(node.id)
        mirrored_node_ids.append(node.id)
    if tool_schemas:
        attachments["tool_schemas"] = tool_schemas
    if artifact_candidates:
        attachments["artifact_content_candidates"] = artifact_candidates
    tool_schema_budget["mirrored_count"] = len(tool_schemas)
    tool_schema_budget["mirrored_added_count"] = len(mirrored_tool_node_ids)
    tool_schema_budget["status"] = (
        "limited" if int(tool_schema_budget["skipped_count"]) > 0 else "ok"
    )
    return (
        attachments,
        tuple(mirrored_node_ids),
        tool_schema_mirror_available,
        {"tool_schema_mirror_budget": tool_schema_budget},
    )


def provider_tool_schemas(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, dict))


def default_tool_schema_ids_from_metadata(metadata: dict[str, object]) -> frozenset[str]:
    value = metadata.get("default_tool_schema_ids")
    if isinstance(value, str):
        values: tuple[object, ...] = (value,)
    elif isinstance(value, (list, tuple, set, frozenset)):
        values = tuple(value)
    else:
        values = ()
    return frozenset(
        item.strip()
        for item in values
        if isinstance(item, str) and item.strip()
    )


def default_tool_schema_source_from_metadata(metadata: dict[str, object]) -> str:
    value = metadata.get("default_tool_schema_source")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return "runtime_policy"


def default_tool_schema_group_refs_from_metadata(
    metadata: dict[str, object],
) -> tuple[dict[str, str], ...]:
    value = metadata.get("default_tool_schema_group_refs")
    if not isinstance(value, (list, tuple)):
        return ()
    refs: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        ref = {
            key: text
            for key in ("node_id", "source_id", "group_key", "reason")
            for text in (_metadata_text(item.get(key)),)
            if text is not None
        }
        if ref:
            refs.append(ref)
    return tuple(refs)


def default_tool_schema_group_matches_from_metadata(
    metadata: dict[str, object],
) -> tuple[dict[str, str], ...]:
    value = metadata.get("default_tool_schema_group_matches")
    if not isinstance(value, (list, tuple)):
        return ()
    matches: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        match = {
            key: text
            for key in ("node_id", "source_id", "group_key", "priority", "reason")
            for text in (_metadata_text(item.get(key)),)
            if text is not None
        }
        if match:
            matches.append(match)
    return tuple(matches)


def default_tool_schema_priorities_from_metadata(
    metadata: dict[str, object],
) -> dict[str, int]:
    value = metadata.get("default_tool_schema_priorities")
    if not isinstance(value, dict):
        return {}
    priorities: dict[str, int] = {}
    for key, raw_priority in value.items():
        text = _metadata_text(key)
        if text is None:
            continue
        priority = positive_int_from_metadata(raw_priority, fallback=0)
        if priority > 0:
            priorities[text] = priority
    return priorities


def default_tool_schema_reasons_from_metadata(
    metadata: dict[str, object],
) -> dict[str, str]:
    value = metadata.get("default_tool_schema_reasons")
    if not isinstance(value, dict):
        return {}
    reasons: dict[str, str] = {}
    for key, raw_reason in value.items():
        text = _metadata_text(key)
        reason = _metadata_text(raw_reason)
        if text is not None and reason is not None:
            reasons[text] = reason
    return reasons


def node_matches_default_tool_schema(
    node: ContextNode,
    *,
    schema_name: str,
    policy: ToolSurfacePolicy,
) -> bool:
    if not policy.default_schema_ids:
        return False
    tool_id = node.owner_ref.get("tool_id")
    return (
        schema_name in policy.default_schema_ids
        or (isinstance(tool_id, str) and tool_id in policy.default_schema_ids)
        or node.id in policy.default_schema_ids
    )


def tool_schema_mirror_priority(
    node: ContextNode,
    *,
    schema_name: str,
    enabled_by_default: bool,
    policy: ToolSurfacePolicy,
) -> int:
    return policy.priority_for(
        node,
        schema_name=schema_name,
        enabled_by_default=enabled_by_default,
    )


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
        if node.state.prompt_visible:
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


def positive_int_from_metadata(value: object, *, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    if isinstance(value, int):
        return value if value > 0 else fallback
    if isinstance(value, float):
        parsed = int(value)
        return parsed if parsed > 0 else fallback
    if isinstance(value, str) and value.strip():
        try:
            parsed = int(value.strip())
        except ValueError:
            return fallback
        return parsed if parsed > 0 else fallback
    return fallback


def _metadata_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def provider_artifact_candidates(value: object) -> tuple[dict[str, object], ...]:
    if not isinstance(value, list):
        return ()
    return tuple(dict(item) for item in value if isinstance(item, dict))


__all__ = [
    "TOOL_SCHEMA_MIRROR_MAX_COUNT",
    "TOOL_SCHEMA_MIRROR_MAX_ESTIMATED_TOKENS",
    "render_provider_attachments",
]
