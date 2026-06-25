"""Tool schema group reference parsing helpers."""

from __future__ import annotations

from urllib.parse import quote

from ._metadata import metadata_text

CORE_DEFAULT_TOOL_GROUPS: frozenset[tuple[str, str]] = frozenset(
    {
        ("bundled.local_package.command", "run_and_verify"),
        ("bundled.local_package.command", "background_processes"),
        ("bundled.local_package.context_tree", "capability_discovery"),
    },
)


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


def with_default_source_id(
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


def default_schema_source_ids(schema_ids: tuple[str, ...]) -> frozenset[str]:
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


def tool_bundle_group_node_id(source_id: str, group_key: str) -> str:
    return f"{tool_bundle_node_id(source_id)}.group.{_node_token(group_key)}"


def tool_bundle_node_id(source_id: str) -> str:
    return f"tools.bundle.{_node_token(source_id)}"


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


def _node_token(value: str) -> str:
    return quote(value.strip(), safe="")
