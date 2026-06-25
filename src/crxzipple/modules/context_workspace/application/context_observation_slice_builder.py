from __future__ import annotations

from time import perf_counter
from uuid import uuid4

from crxzipple.modules.context_workspace.application.context_control_projection import (
    session_item_id_from_protocol_ref,
)
from crxzipple.modules.context_workspace.application.context_slice_item_projection import (
    SessionItemResolver,
    context_slice_item,
    included_session_item_ids,
    protocol_required_slice_items,
)
from crxzipple.modules.context_workspace.application.context_slice_refs import (
    archived_ref,
    collapsed_ref,
    metadata_string_set,
)
from crxzipple.modules.context_workspace.application.context_slice_selection import (
    included_nodes_for_slice,
    visible_nodes_for_slice,
)
from crxzipple.modules.context_workspace.application.context_tool_surface_projection import (
    active_tools_for_slice,
)
from crxzipple.modules.context_workspace.application.models import (
    ContextSlice,
    ContextSliceItem,
    ContextSliceReport,
)
from crxzipple.modules.context_workspace.application.rendering import aggregate_estimate
from crxzipple.modules.context_workspace.domain import ContextNode, ContextWorkspace


def build_context_observation_slice(
    *,
    workspace: ContextWorkspace,
    nodes: tuple[ContextNode, ...],
    run_id: str,
    audience: str,
    provider_profile: str | None,
    request_metadata: dict[str, object],
    read_only: bool,
    session_item_resolver: SessionItemResolver | None,
    builder_timings: dict[str, float] | None = None,
    timings_started_at: float | None = None,
) -> ContextSlice:
    started_at = timings_started_at if timings_started_at is not None else perf_counter()
    phase_started_at = perf_counter()
    collected_timings: dict[str, float] = dict(builder_timings or {})

    def record_timing(label: str) -> None:
        nonlocal phase_started_at
        now = perf_counter()
        collected_timings[f"{label}_ms"] = round((now - phase_started_at) * 1000, 3)
        phase_started_at = now

    visible_nodes = visible_nodes_for_slice(nodes, audience=audience)
    record_timing("select_visible_nodes")
    included_nodes = included_nodes_for_slice(
        nodes=nodes,
        visible_nodes=visible_nodes,
        audience=audience,
        request_metadata=request_metadata,
    )
    record_timing("select_included_nodes")

    resolved_items: list[ContextSliceItem] = []
    unresolved_refs: list[dict[str, object]] = []
    session_item_max_chars = _metadata_positive_int(
        request_metadata.get("session_item_max_chars"),
    )
    slice_session_item_resolver = _prefetch_session_item_resolver(
        session_item_resolver,
        item_ids=_session_item_ids_for_slice(
            included_nodes=tuple(included_nodes),
            protocol_required_refs=request_metadata.get("protocol_required_refs"),
        ),
    )
    record_timing("prefetch_session_items")
    for node in included_nodes:
        item, unresolved_ref = context_slice_item(
            node,
            session_item_resolver=slice_session_item_resolver,
            session_item_max_chars=session_item_max_chars,
        )
        resolved_items.append(item)
        if unresolved_ref is not None:
            unresolved_refs.append(unresolved_ref)
    record_timing("project_included_items")

    protocol_items, protocol_unresolved_refs = protocol_required_slice_items(
        request_metadata.get("protocol_required_refs"),
        existing_session_item_ids=included_session_item_ids(resolved_items),
        session_item_resolver=slice_session_item_resolver,
    )
    resolved_items.extend(protocol_items)
    unresolved_refs.extend(protocol_unresolved_refs)
    record_timing("project_protocol_required_items")

    requested_tool_schema_names = metadata_string_set(
        request_metadata.get("requested_tool_schema_names"),
    )
    included_node_ids = {node.id for node in included_nodes}
    active_tools = active_tools_for_slice(
        nodes=nodes,
        audience=audience,
        requested_tool_schema_names=requested_tool_schema_names,
    )
    record_timing("project_active_tools")
    omitted_node_ids = tuple(node.id for node in nodes if node.id not in included_node_ids)
    collapsed_refs = tuple(
        collapsed_ref(node)
        for node in visible_nodes
        if node.state.collapsed
    )
    archived_refs = tuple(archived_ref(node) for node in nodes if node.state.archived)
    redacted_refs: tuple[dict[str, object], ...] = ()
    record_timing("build_report_refs")
    collected_timings["total_ms"] = round((perf_counter() - started_at) * 1000, 3)

    report = ContextSliceReport(
        included_node_ids=tuple(node.id for node in included_nodes),
        omitted_node_ids=omitted_node_ids,
        archived_refs=archived_refs,
        collapsed_refs=collapsed_refs,
        redacted_refs=redacted_refs,
        unresolved_refs=tuple(unresolved_refs),
        budget=aggregate_estimate(included_nodes).to_payload(),
        loss={
            "omitted_node_count": len(omitted_node_ids),
            "archived_ref_count": len(archived_refs),
            "collapsed_ref_count": len(collapsed_refs),
            "redacted_ref_count": len(redacted_refs),
            "unresolved_ref_count": len(unresolved_refs),
        },
        metadata={
            "audience": audience,
            "provider_profile": provider_profile or "",
            "visible_node_count": len(visible_nodes),
            "active_tool_count": len(active_tools),
            "read_only": read_only,
            "context_slice_builder_timings": dict(collected_timings),
            **request_metadata,
        },
    )
    slice_id = f"ctxslice_{uuid4().hex}"
    return ContextSlice(
        slice_id=slice_id,
        session_key=workspace.session_key,
        run_id=run_id,
        audience=audience,
        tree_revision=workspace.active_revision,
        items=tuple(resolved_items),
        active_tools=active_tools,
        report=report,
        metadata={
            "slice_id": slice_id,
            "audience": audience,
            "provider_profile": provider_profile or "",
            "workspace_id": workspace.id,
            "read_only": read_only,
            "context_slice_builder_timings": dict(collected_timings),
            **request_metadata,
        },
    )


class _CachedSessionItemResolver:
    def __init__(
        self,
        delegate: SessionItemResolver,
        cache: dict[str, object],
    ) -> None:
        self._delegate = delegate
        self._cache = cache

    def get_item(self, item_id: str) -> object:
        cached = self._cache.get(item_id)
        if cached is not None:
            return cached
        return self._delegate.get_item(item_id)


def _prefetch_session_item_resolver(
    resolver: SessionItemResolver | None,
    *,
    item_ids: tuple[str, ...],
) -> SessionItemResolver | None:
    if resolver is None or not item_ids:
        return resolver
    get_items = getattr(resolver, "get_items", None)
    if not callable(get_items):
        return resolver
    try:
        result = get_items(item_ids)
    except Exception:
        return resolver
    cache: dict[str, object] = {}
    if isinstance(result, dict):
        for key, item in result.items():
            item_id = _metadata_text(key) or _metadata_text(getattr(item, "id", None))
            if item_id is not None:
                cache[item_id] = item
    elif isinstance(result, (list, tuple)):
        for item in result:
            item_id = _metadata_text(getattr(item, "id", None))
            if item_id is not None:
                cache[item_id] = item
    if not cache:
        return resolver
    return _CachedSessionItemResolver(resolver, cache)


def _session_item_ids_for_slice(
    *,
    included_nodes: tuple[ContextNode, ...],
    protocol_required_refs: object,
) -> tuple[str, ...]:
    ids: list[str] = []
    seen: set[str] = set()

    def add(value: object) -> None:
        text = _metadata_text(value)
        if text is not None and text not in seen:
            seen.add(text)
            ids.append(text)

    for node in included_nodes:
        if node.owner == "session":
            add(node.owner_ref.get("session_item_id"))
    if isinstance(protocol_required_refs, (list, tuple)):
        for ref in protocol_required_refs:
            if isinstance(ref, dict):
                add(session_item_id_from_protocol_ref(ref))
    return tuple(ids)


def _metadata_positive_int(value: object) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _metadata_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


__all__ = ["build_context_observation_slice"]
