"""Tool schema selection for request render snapshots."""

from __future__ import annotations

from crxzipple.modules.context_workspace.application import ContextTreeService
from crxzipple.modules.llm.domain import ToolSchema


def request_render_tool_schemas(
    schemas: tuple[ToolSchema, ...],
    *,
    render_metadata: dict[str, object],
    tree_service: ContextTreeService | None,
    session_key: str,
    surface_contract: str = "default_open",
    active_tool_names: frozenset[str] = frozenset(),
) -> tuple[ToolSchema, ...]:
    if surface_contract == "declared_only":
        return dedupe_tool_schemas(schemas)
    if tree_service is None and not render_metadata:
        return dedupe_tool_schemas(schemas)
    default_schema_ids = metadata_string_set(
        render_metadata.get("default_tool_schema_ids"),
    )
    enabled_schema_names = enabled_tool_schema_names(
        tree_service=tree_service,
        session_key=session_key,
    )
    visible_names = {
        "capability.search",
        *default_schema_ids,
        *enabled_schema_names,
        *active_tool_names,
    }
    selected: list[ToolSchema] = []
    seen: set[str] = set()
    for schema in schemas:
        name = schema.name.strip()
        if not name or name in seen:
            continue
        if name not in visible_names:
            continue
        selected.append(schema)
        seen.add(name)
    return tuple(selected)


def dedupe_tool_schemas(schemas: tuple[ToolSchema, ...]) -> tuple[ToolSchema, ...]:
    selected: list[ToolSchema] = []
    seen: set[str] = set()
    for schema in schemas:
        name = schema.name.strip()
        if not name or name in seen:
            continue
        selected.append(schema)
        seen.add(name)
    return tuple(selected)


def enabled_tool_schema_names(
    *,
    tree_service: ContextTreeService | None,
    session_key: str,
) -> frozenset[str]:
    if tree_service is None:
        return frozenset()
    try:
        return frozenset(tree_service.list_enabled_tool_schema_names(session_key))
    except Exception:
        return frozenset()


def metadata_string_set(value: object) -> frozenset[str]:
    if not isinstance(value, list | tuple | set | frozenset):
        return frozenset()
    return frozenset(
        text
        for item in value
        if isinstance(item, str) and (text := item.strip())
    )
