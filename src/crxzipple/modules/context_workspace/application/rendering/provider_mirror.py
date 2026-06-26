from __future__ import annotations

from crxzipple.modules.context_workspace.domain import ContextNode

from .provider_mirror_budget import (
    new_tool_schema_mirror_budget,
    provider_schema_estimated_tokens,
    record_default_tool_schema_mirror,
    record_tool_schema_budget_skip,
    record_tool_schema_group_visibility,
    tool_schema_budget_skip_reason,
)
from .provider_mirror_policy import (
    TOOL_SCHEMA_MIRROR_MAX_COUNT,
    TOOL_SCHEMA_MIRROR_MAX_ESTIMATED_TOKENS,
    ToolSurfacePolicy,
    node_matches_default_tool_schema,
    tool_schema_mirror_priority,
)


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
        schema = _tool_node_provider_schema_for_observation(node)
        if schema is not None:
            tool_schema_mirror_available = True
            tool_schema_budget["available_count"] += 1
        if schema is None:
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
        for candidate in provider_artifact_candidates(
            node.metadata.get("artifact_content_candidates"),
        ):
            node_id = candidate.get("node_id")
            if not isinstance(node_id, str) or not node_id.strip():
                node_id = node.id
                candidate["node_id"] = node_id
            if node_id in existing_artifact_node_ids:
                continue
            artifact_id = candidate.get("artifact_id")
            if not isinstance(artifact_id, str) or not artifact_id.strip():
                continue
            artifact_candidates.append(dict(candidate))
            existing_artifact_node_ids.add(node_id)
            mirrored_node_ids.append(node.id)
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


def _tool_node_provider_schema_for_observation(
    node: ContextNode,
) -> dict[str, object] | None:
    schema = node.metadata.get("provider_schema")
    if isinstance(schema, dict):
        return dict(schema)
    schema_name = _metadata_text(node.owner_ref.get("tool_id")) or _metadata_text(
        node.owner_ref.get("function_id"),
    )
    if schema_name is None:
        return None
    description = node.summary.strip() or node.title.strip() or schema_name
    return {
        "name": schema_name,
        "description": description,
        "input_schema": {
            "type": "object",
            "properties": {},
        },
    }


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
