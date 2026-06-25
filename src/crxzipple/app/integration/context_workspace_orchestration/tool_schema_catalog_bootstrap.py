"""Catalog-backed default tool schema bootstrap."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)
from crxzipple.modules.tool.application import (
    ToolRuntimeRequestBundle,
    ToolRuntimeRequestBundleGroup,
)

from ._metadata import metadata_positive_int, metadata_string_list, metadata_text
from .tool_schema_group_refs import (
    CORE_DEFAULT_TOOL_GROUPS,
    metadata_tool_schema_group_refs,
    tool_bundle_group_node_id,
    with_default_source_id,
)


class ToolRuntimeRequestCatalog(Protocol):
    def list_runtime_request_bundles(
        self,
        function_ids: Iterable[str],
    ) -> tuple[ToolRuntimeRequestBundle, ...]:
        ...


def resolve_default_tool_schema_metadata_from_catalog(
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
                "node_id": tool_bundle_group_node_id(
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
            normalized = with_default_source_id(ref, source_id=bundle.source_id)
            if normalized is None:
                continue
            group_key = metadata_text(normalized.get("group_key"))
            if (bundle.source_id, group_key or "") not in CORE_DEFAULT_TOOL_GROUPS:
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
            if node_id is not None and tool_bundle_group_node_id(
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
