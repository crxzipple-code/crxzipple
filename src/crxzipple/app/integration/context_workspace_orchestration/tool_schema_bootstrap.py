"""Default tool schema metadata bootstrap for context snapshots."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol
from urllib.parse import quote

from crxzipple.modules.context_workspace.application import (
    ContextActionInput,
    ContextTreeService,
)
from crxzipple.modules.context_workspace.domain import ContextAction
from crxzipple.modules.tool.application import (
    ToolRuntimeRequestBundle,
    ToolRuntimeRequestBundleGroup,
)
from crxzipple.modules.orchestration.application.runtime_llm_request_draft import RuntimeLlmRequestDraft

from ._metadata import (
    metadata_positive_int,
    metadata_string_list,
    metadata_text,
)

_CORE_DEFAULT_TOOL_GROUPS: frozenset[tuple[str, str]] = frozenset(
    {
        ("bundled.local_package.command", "run_and_verify"),
        ("bundled.local_package.command", "background_processes"),
        ("bundled.local_package.context_tree", "capability_discovery"),
    },
)


class ToolRuntimeRequestCatalog(Protocol):
    def list_runtime_request_bundles(
        self,
        function_ids: Iterable[str],
    ) -> tuple[ToolRuntimeRequestBundle, ...]:
        ...


def resolve_draft_tool_schema_metadata(draft: RuntimeLlmRequestDraft) -> dict[str, object]:
    default_tool_schema_ids = metadata_string_list(
        draft.flow_hint.get("default_tool_schema_ids"),
    )
    default_tool_schema_group_refs = metadata_tool_schema_group_refs(
        draft.flow_hint.get("default_tool_schema_group_refs"),
    )
    if not default_tool_schema_ids and not default_tool_schema_group_refs:
        return {}
    metadata: dict[str, object] = {}
    if default_tool_schema_group_refs:
        metadata["default_tool_schema_group_refs"] = [
            dict(ref) for ref in default_tool_schema_group_refs
        ]
    if not default_tool_schema_ids:
        return metadata
    source = metadata_text(draft.flow_hint.get("default_tool_schema_source"))
    metadata["default_tool_schema_ids"] = default_tool_schema_ids
    metadata["default_tool_schema_source"] = source or "runtime_request_flow_hint"
    return metadata


def merge_default_tool_schema_metadata(
    direct_metadata: dict[str, object],
    group_metadata: dict[str, object],
) -> dict[str, object]:
    if not direct_metadata:
        return dict(group_metadata)
    if not group_metadata:
        return dict(direct_metadata)
    metadata = dict(direct_metadata)
    schema_ids: list[str] = []
    for item in metadata_string_list(direct_metadata.get("default_tool_schema_ids")):
        if item not in schema_ids:
            schema_ids.append(item)
    for item in metadata_string_list(group_metadata.get("default_tool_schema_ids")):
        if item not in schema_ids:
            schema_ids.append(item)
    if schema_ids:
        metadata["default_tool_schema_ids"] = schema_ids
    source_values = [
        source
        for source in (
            metadata_text(direct_metadata.get("default_tool_schema_source")),
            metadata_text(group_metadata.get("default_tool_schema_source")),
        )
        if source is not None
    ]
    if source_values:
        metadata["default_tool_schema_source"] = ",".join(dict.fromkeys(source_values))
    for key in ("default_tool_schema_group_refs", "default_tool_schema_group_matches"):
        if key in group_metadata:
            metadata[key] = group_metadata[key]
    return metadata


def resolve_default_tool_schema_metadata(
    *,
    tree_service: ContextTreeService | None,
    runtime_request_catalog: ToolRuntimeRequestCatalog | None = None,
    session_key: str,
    run_id: str,
    draft: RuntimeLlmRequestDraft,
    allow_tree_fallback: bool = True,
) -> dict[str, object]:
    catalog_metadata = _resolve_default_tool_schema_metadata_from_catalog(
        runtime_request_catalog=runtime_request_catalog,
        draft=draft,
    )
    if catalog_metadata:
        return catalog_metadata
    if not allow_tree_fallback:
        return {}
    if tree_service is None:
        return {}
    direct_schema_ids = metadata_string_list(
        draft.flow_hint.get("default_tool_schema_ids"),
    )
    if direct_schema_ids:
        _expand_tool_bundles_for_default_schema_ids(
            tree_service=tree_service,
            session_key=session_key,
            run_id=run_id,
            schema_ids=tuple(direct_schema_ids),
        )
    group_refs = metadata_tool_schema_group_refs(
        draft.flow_hint.get("default_tool_schema_group_refs"),
    )
    group_ref_source = "runtime_request_flow_hint.group_bootstrap"
    if not group_refs:
        group_refs = default_tool_schema_group_refs_from_source_policy(
            tree_service=tree_service,
            session_key=session_key,
            run_id=run_id,
        )
        group_ref_source = "source_runtime_request.default_tool_schema_group_refs"
    if not group_refs:
        return {}
    _expand_context_node_if_present(
        tree_service=tree_service,
        session_key=session_key,
        run_id=run_id,
        node_id="tools.available",
    )
    bundle_nodes = tree_service.list_tool_nodes_by_kind(
        session_key,
        kinds=("tool_bundle",),
    )
    for ref in group_refs:
        source_id = ref.get("source_id")
        if source_id is None:
            continue
        bundle_node = next(
            (
                node
                for node in bundle_nodes
                if node.owner == "tool"
                and node.kind == "tool_bundle"
                and node.owner_ref.get("source_id") == source_id
            ),
            None,
        )
        if bundle_node is not None:
            _expand_context_node_if_present(
                tree_service=tree_service,
                session_key=session_key,
                run_id=run_id,
                node_id=bundle_node.id,
            )

    group_nodes = tree_service.list_tool_nodes_by_kind(
        session_key,
        kinds=("tool_bundle_group",),
    )
    default_schema_ids: list[str] = []
    default_sources: list[str] = []
    default_priorities: dict[str, int] = {}
    default_reasons: dict[str, str] = {}
    matched_groups: list[dict[str, str]] = []
    for group_index, ref in enumerate(group_refs):
        group_node = _find_tool_group_node(group_nodes, ref)
        if group_node is None:
            continue
        _expand_context_node_if_present(
            tree_service=tree_service,
            session_key=session_key,
            run_id=run_id,
            node_id=group_node.id,
        )
        group_schema_ids = metadata_string_list(
            group_node.metadata.get("default_tool_schema_ids"),
        )
        max_count = metadata_positive_int(
            group_node.metadata.get("default_tool_schema_max_count"),
        )
        if max_count is not None:
            group_schema_ids = group_schema_ids[:max_count]
        group_priority = _group_priority(
            ref,
            group_node=group_node,
            fallback=group_index,
        )
        reason = metadata_text(ref.get("reason"))
        for schema_index, schema_id in enumerate(group_schema_ids):
            if schema_id not in default_schema_ids:
                default_schema_ids.append(schema_id)
            default_priorities.setdefault(
                schema_id,
                group_priority + schema_index,
            )
            if reason is not None:
                default_reasons.setdefault(schema_id, reason)
        source = metadata_text(group_node.metadata.get("default_tool_schema_source"))
        if source is not None and source not in default_sources:
            default_sources.append(source)
        matched_groups.append(
            {
                "node_id": group_node.id,
                "source_id": str(group_node.owner_ref.get("source_id") or ""),
                "group_key": str(group_node.owner_ref.get("group_key") or ""),
                "priority": str(group_priority),
                **({"reason": reason} if reason is not None else {}),
            },
        )
    if not default_schema_ids:
        return {}
    return {
        "default_tool_schema_ids": default_schema_ids,
        "default_tool_schema_source": (
            ",".join(default_sources)
            if default_sources
            else group_ref_source
        ),
        "default_tool_schema_group_refs": [dict(ref) for ref in group_refs],
        "default_tool_schema_group_matches": matched_groups,
        "default_tool_schema_priorities": dict(default_priorities),
        "default_tool_schema_reasons": dict(default_reasons),
    }


def default_tool_schema_group_refs_from_source_policy(
    *,
    tree_service: ContextTreeService,
    session_key: str,
    run_id: str,
) -> list[dict[str, str]]:
    _expand_context_node_if_present(
        tree_service=tree_service,
        session_key=session_key,
        run_id=run_id,
        node_id="tools.available",
    )
    bundle_nodes = tree_service.list_tool_nodes_by_kind(
        session_key,
        kinds=("tool_bundle",),
    )
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for bundle_node in bundle_nodes:
        if (
            getattr(bundle_node, "owner", None) != "tool"
            or getattr(bundle_node, "kind", None) != "tool_bundle"
        ):
            continue
        source_id = metadata_text(bundle_node.owner_ref.get("source_id"))
        if source_id is None:
            source_id = metadata_text(bundle_node.metadata.get("source_id"))
        if source_id is None:
            continue
        runtime_request_config = bundle_node.metadata.get("runtime_request")
        if not isinstance(runtime_request_config, dict):
            continue
        source_policy = (
            runtime_request_config.get("default_tool_schema_policy")
            if isinstance(
                runtime_request_config.get("default_tool_schema_policy"),
                dict,
            )
            else {}
        )
        source_priority = metadata_positive_int(source_policy.get("priority"))
        for ref in metadata_tool_schema_group_refs(
            runtime_request_config.get("default_tool_schema_group_refs"),
        ):
            normalized = _with_default_source_id(ref, source_id=source_id)
            if normalized is None:
                continue
            group_key = metadata_text(normalized.get("group_key"))
            if (source_id, group_key or "") not in _CORE_DEFAULT_TOOL_GROUPS:
                continue
            if source_priority is not None and "priority" not in normalized:
                normalized["priority"] = str(source_priority)
            key = (
                normalized.get("node_id", ""),
                normalized.get("source_id", ""),
                normalized.get("group_key", ""),
            )
            if key in seen:
                continue
            seen.add(key)
            refs.append(normalized)
    return refs


def _resolve_default_tool_schema_metadata_from_catalog(
    *,
    runtime_request_catalog: ToolRuntimeRequestCatalog | None,
    draft: RuntimeLlmRequestDraft,
) -> dict[str, object]:
    if runtime_request_catalog is None:
        return {}
    bundles = _runtime_request_bundles_from_catalog(
        runtime_request_catalog,
        function_ids=_draft_tool_schema_names(draft),
    )
    if not bundles:
        return {}
    group_refs = metadata_tool_schema_group_refs(
        draft.flow_hint.get("default_tool_schema_group_refs"),
    )
    group_ref_source = "runtime_request_flow_hint.group_bootstrap"
    if not group_refs:
        group_refs = _default_tool_schema_group_refs_from_catalog_source_policy(
            bundles,
        )
        group_ref_source = "source_runtime_request.default_tool_schema_group_refs"
    if not group_refs:
        return {}
    default_schema_ids: list[str] = []
    default_sources: list[str] = []
    default_priorities: dict[str, int] = {}
    default_reasons: dict[str, str] = {}
    matched_groups: list[dict[str, str]] = []
    for group_index, ref in enumerate(group_refs):
        group_match = _find_catalog_group(bundles, ref)
        if group_match is None:
            continue
        bundle, group = group_match
        group_schema_ids = metadata_string_list(
            group.metadata.get("default_tool_schema_ids"),
        )
        max_count = metadata_positive_int(
            group.metadata.get("default_tool_schema_max_count"),
        )
        if max_count is not None:
            group_schema_ids = group_schema_ids[:max_count]
        group_priority = _catalog_group_priority(
            ref,
            group=group,
            fallback=group_index,
        )
        reason = metadata_text(ref.get("reason"))
        for schema_index, schema_id in enumerate(group_schema_ids):
            if schema_id not in default_schema_ids:
                default_schema_ids.append(schema_id)
            default_priorities.setdefault(
                schema_id,
                group_priority + schema_index,
            )
            if reason is not None:
                default_reasons.setdefault(schema_id, reason)
        source = metadata_text(group.metadata.get("default_tool_schema_source"))
        if source is not None and source not in default_sources:
            default_sources.append(source)
        matched_groups.append(
            {
                "node_id": _tool_bundle_group_node_id(
                    bundle.source_id,
                    group.group_key,
                ),
                "source_id": bundle.source_id,
                "group_key": group.group_key,
                "priority": str(group_priority),
                **({"reason": reason} if reason is not None else {}),
            },
        )
    if not default_schema_ids:
        return {}
    return {
        "default_tool_schema_ids": default_schema_ids,
        "default_tool_schema_source": (
            ",".join(default_sources)
            if default_sources
            else group_ref_source
        ),
        "default_tool_schema_group_refs": [dict(ref) for ref in group_refs],
        "default_tool_schema_group_matches": matched_groups,
        "default_tool_schema_priorities": dict(default_priorities),
        "default_tool_schema_reasons": dict(default_reasons),
    }


def _runtime_request_bundles_from_catalog(
    runtime_request_catalog: ToolRuntimeRequestCatalog,
    *,
    function_ids: tuple[str, ...],
) -> tuple[ToolRuntimeRequestBundle, ...]:
    if not function_ids:
        return ()
    try:
        return runtime_request_catalog.list_runtime_request_bundles(function_ids)
    except Exception:
        return ()


def _draft_tool_schema_names(draft: RuntimeLlmRequestDraft) -> tuple[str, ...]:
    names: list[str] = []
    for schema in draft.tool_schemas:
        name = schema.name.strip()
        if name and name not in names:
            names.append(name)
    return tuple(names)


def _default_tool_schema_group_refs_from_catalog_source_policy(
    bundles: tuple[ToolRuntimeRequestBundle, ...],
) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for bundle in bundles:
        runtime_request_config = bundle.metadata.get("runtime_request")
        if not isinstance(runtime_request_config, dict):
            continue
        source_policy = (
            runtime_request_config.get("default_tool_schema_policy")
            if isinstance(
                runtime_request_config.get("default_tool_schema_policy"),
                dict,
            )
            else {}
        )
        source_priority = metadata_positive_int(source_policy.get("priority"))
        for ref in metadata_tool_schema_group_refs(
            runtime_request_config.get("default_tool_schema_group_refs"),
        ):
            normalized = _with_default_source_id(ref, source_id=bundle.source_id)
            if normalized is None:
                continue
            group_key = metadata_text(normalized.get("group_key"))
            if (bundle.source_id, group_key or "") not in _CORE_DEFAULT_TOOL_GROUPS:
                continue
            if source_priority is not None and "priority" not in normalized:
                normalized["priority"] = str(source_priority)
            key = (
                normalized.get("node_id", ""),
                normalized.get("source_id", ""),
                normalized.get("group_key", ""),
            )
            if key in seen:
                continue
            seen.add(key)
            refs.append(normalized)
    return refs


def _find_catalog_group(
    bundles: tuple[ToolRuntimeRequestBundle, ...],
    ref: dict[str, str],
) -> tuple[ToolRuntimeRequestBundle, ToolRuntimeRequestBundleGroup] | None:
    source_id = ref.get("source_id")
    group_key = ref.get("group_key")
    node_id = ref.get("node_id")
    for bundle in bundles:
        for group in bundle.groups:
            if node_id is not None and _tool_bundle_group_node_id(
                bundle.source_id,
                group.group_key,
            ) == node_id:
                return (bundle, group)
            if (
                source_id is not None
                and group_key is not None
                and bundle.source_id == source_id
                and group.group_key == group_key
            ):
                return (bundle, group)
    return None


def _catalog_group_priority(
    ref: dict[str, str],
    *,
    group: ToolRuntimeRequestBundleGroup,
    fallback: int,
) -> int:
    source_priority = metadata_positive_int(ref.get("priority")) or 100
    group_order = metadata_positive_int(group.metadata.get("order")) or fallback
    return (source_priority * 10_000) + (group_order * 100)


def _expand_tool_bundles_for_default_schema_ids(
    *,
    tree_service: ContextTreeService,
    session_key: str,
    run_id: str,
    schema_ids: tuple[str, ...],
) -> None:
    source_ids = _default_schema_source_ids(schema_ids)
    _expand_context_node_if_present(
        tree_service=tree_service,
        session_key=session_key,
        run_id=run_id,
        node_id="tools.available",
    )
    bundle_nodes = tree_service.list_tool_nodes_by_kind(
        session_key,
        kinds=("tool_bundle",),
    )
    expanded_bundle_ids: set[str] = set()
    for node in bundle_nodes:
        if (
            getattr(node, "owner", None) != "tool"
            or getattr(node, "kind", None) != "tool_bundle"
        ):
            continue
        source_id = metadata_text(node.owner_ref.get("source_id"))
        if source_id is None:
            source_id = metadata_text(node.metadata.get("source_id"))
        if not source_ids or source_id in source_ids:
            _expand_context_node_if_present(
                tree_service=tree_service,
                session_key=session_key,
                run_id=run_id,
                node_id=node.id,
            )
            expanded_bundle_ids.add(str(node.id))
    if not expanded_bundle_ids:
        for node in bundle_nodes:
            if (
                getattr(node, "owner", None) != "tool"
                or getattr(node, "kind", None) != "tool_bundle"
            ):
                continue
            _expand_context_node_if_present(
                tree_service=tree_service,
                session_key=session_key,
                run_id=run_id,
                node_id=node.id,
            )
    group_nodes = tree_service.list_tool_nodes_by_kind(
        session_key,
        kinds=("tool_bundle_group",),
    )
    wanted_schema_ids = set(schema_ids)
    for node in group_nodes:
        if (
            getattr(node, "owner", None) != "tool"
            or getattr(node, "kind", None) != "tool_bundle_group"
        ):
            continue
        function_ids = set(
            metadata_string_list(node.owner_ref.get("function_ids"))
            + metadata_string_list(node.metadata.get("function_ids"))
            + metadata_string_list(node.metadata.get("default_tool_schema_ids"))
        )
        if wanted_schema_ids.isdisjoint(function_ids):
            continue
        _expand_context_node_if_present(
            tree_service=tree_service,
            session_key=session_key,
            run_id=run_id,
            node_id=node.id,
        )


def _default_schema_source_ids(schema_ids: tuple[str, ...]) -> frozenset[str]:
    source_ids: set[str] = set()
    builtin_source_ids = {
        "exec": "bundled.local_package.command",
        "process": "bundled.local_package.command",
    }
    for schema_id in schema_ids:
        builtin_source_id = builtin_source_ids.get(schema_id)
        if builtin_source_id is not None:
            source_ids.add(builtin_source_id)
            continue
        namespace, _, _operation = schema_id.partition(".")
        if not namespace:
            continue
        if namespace == "browser":
            source_ids.add("bundled.local_package.browser")
            continue
        source_ids.add(f"bundled.openapi.{namespace}")
        source_ids.add(f"bundled.local_package.{namespace}")
    return frozenset(source_ids)


def _tool_bundle_group_node_id(source_id: str, group_key: str) -> str:
    return f"{_tool_bundle_node_id(source_id)}.group.{_node_token(group_key)}"


def _tool_bundle_node_id(source_id: str) -> str:
    return f"tools.bundle.{_node_token(source_id)}"


def _node_token(value: str) -> str:
    return quote(value.strip(), safe="")


def metadata_tool_schema_group_refs(value: object) -> list[dict[str, str]]:
    if isinstance(value, dict):
        values: tuple[object, ...] = (value,)
    elif isinstance(value, str):
        values = (value,)
    elif isinstance(value, (list, tuple)):
        values = tuple(value)
    else:
        values = ()
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in values:
        ref = _metadata_tool_schema_group_ref(item)
        if ref is None:
            continue
        key = (
            ref.get("node_id", ""),
            ref.get("source_id", ""),
            ref.get("group_key", ""),
        )
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
    return refs


def _metadata_tool_schema_group_ref(value: object) -> dict[str, str] | None:
    if isinstance(value, dict):
        node_id = metadata_text(value.get("node_id"))
        source_id = metadata_text(value.get("source_id"))
        group_key = metadata_text(value.get("group_key"))
        reason = metadata_text(value.get("reason"))
        priority = metadata_text(value.get("priority"))
        if node_id is not None:
            payload = {"node_id": node_id}
            if source_id is not None:
                payload["source_id"] = source_id
            if group_key is not None:
                payload["group_key"] = group_key
            if reason is not None:
                payload["reason"] = reason
            if priority is not None:
                payload["priority"] = priority
            return payload
        if source_id is not None and group_key is not None:
            payload = {"source_id": source_id, "group_key": group_key}
            if reason is not None:
                payload["reason"] = reason
            if priority is not None:
                payload["priority"] = priority
            return payload
        return None
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip()
    if raw.startswith("tools."):
        return {"node_id": raw}
    for separator in (":", "#", "/"):
        if separator not in raw:
            continue
        source_id, group_key = raw.rsplit(separator, 1)
        source_id = source_id.strip()
        group_key = group_key.strip()
        if source_id and group_key:
            return {"source_id": source_id, "group_key": group_key}
    return None


def _with_default_source_id(
    ref: dict[str, str],
    *,
    source_id: str,
) -> dict[str, str] | None:
    normalized = dict(ref)
    normalized_source_id = metadata_text(normalized.get("source_id")) or source_id
    group_key = metadata_text(normalized.get("group_key"))
    node_id = metadata_text(normalized.get("node_id"))
    if group_key is None and node_id is None:
        return None
    normalized["source_id"] = normalized_source_id
    if group_key is not None:
        normalized["group_key"] = group_key
    if node_id is not None:
        normalized["node_id"] = node_id
    return normalized


def _group_priority(
    ref: dict[str, str],
    *,
    group_node: object,
    fallback: int,
) -> int:
    source_priority = metadata_positive_int(ref.get("priority")) or 100
    raw_group_order = getattr(group_node, "metadata", {}).get("order")
    group_order = metadata_positive_int(raw_group_order) or fallback
    return (source_priority * 10_000) + (group_order * 100)


def _find_tool_group_node(nodes: tuple[object, ...], ref: dict[str, str]):
    node_id = ref.get("node_id")
    if node_id is not None:
        return next(
            (
                node
                for node in nodes
                if getattr(node, "id", None) == node_id
                and getattr(node, "owner", None) == "tool"
                and getattr(node, "kind", None) == "tool_bundle_group"
            ),
            None,
        )
    source_id = ref.get("source_id")
    group_key = ref.get("group_key")
    if source_id is None or group_key is None:
        return None
    return next(
        (
            node
            for node in nodes
            if getattr(node, "owner", None) == "tool"
            and getattr(node, "kind", None) == "tool_bundle_group"
            and node.owner_ref.get("source_id") == source_id
            and node.owner_ref.get("group_key") == group_key
        ),
        None,
    )


def _expand_context_node_if_present(
    *,
    tree_service: ContextTreeService,
    session_key: str,
    run_id: str,
    node_id: str,
) -> None:
    node = tree_service.get_node(session_key, node_id)
    if node is None or not node.state.collapsed:
        return
    tree_service.apply_action(
        ContextActionInput(
            session_key=session_key,
            run_id=run_id,
            node_id=node_id,
            action=ContextAction.EXPAND,
        ),
    )
