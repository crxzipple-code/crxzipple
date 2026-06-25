"""Value helpers for Context Tree tool schema nodes."""

from __future__ import annotations


def tool_function_nodes_include(
    nodes: tuple[object, ...],
    *,
    schema_names: frozenset[str],
) -> bool:
    return any(tool_node_function_name(node) in schema_names for node in nodes)


def tool_node_function_name(node: object) -> str | None:
    owner_ref = getattr(node, "owner_ref", {})
    metadata = getattr(node, "metadata", {})
    if not isinstance(owner_ref, dict):
        owner_ref = {}
    if not isinstance(metadata, dict):
        metadata = {}
    return metadata_text_value(
        owner_ref.get("tool_id"),
        owner_ref.get("function_id"),
        metadata.get("function_name"),
    )


def schema_source_ids(schema_names: frozenset[str]) -> frozenset[str]:
    source_ids: set[str] = set()
    builtin_source_ids = {
        "exec": "bundled.local_package.command",
        "process": "bundled.local_package.command",
    }
    for schema_name in schema_names:
        builtin_source_id = builtin_source_ids.get(schema_name)
        if builtin_source_id is not None:
            source_ids.add(builtin_source_id)
            continue
        namespace, _, _operation = schema_name.partition("_")
        if not namespace:
            continue
        source_ids.add(f"bundled.local_package.{namespace}")
        source_ids.add(f"bundled.openapi.{namespace}")
    return frozenset(source_ids)


def metadata_text_value(*values: object) -> str | None:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None
