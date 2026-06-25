"""Tool schema projection from Context Workspace observation slices."""

from __future__ import annotations

from crxzipple.modules.llm.domain import ToolSchema


def context_slice_tool_schemas(
    context_slice: object | None,
    *,
    available_schemas: tuple[ToolSchema, ...] = (),
    requested_schema_names: tuple[str, ...] = (),
) -> tuple[ToolSchema, ...]:
    active_names = (
        context_slice_active_tool_names(context_slice)
        if context_slice is not None
        else frozenset()
    )
    requested_names = frozenset(
        name.strip()
        for name in requested_schema_names
        if isinstance(name, str) and name.strip()
    )
    visible_names = active_names | requested_names
    if not active_names:
        visible_names = requested_names
    if not visible_names:
        return ()
    schemas: list[ToolSchema] = []
    seen: set[str] = set()
    for schema in available_schemas:
        if schema.name not in visible_names:
            continue
        if schema.name in seen:
            continue
        schemas.append(schema)
        seen.add(schema.name)
    return tuple(schemas)


def context_slice_tool_schema_refs(
    context_slice: object | None,
    *,
    schemas: tuple[ToolSchema, ...] = (),
) -> tuple[dict[str, object], ...]:
    tool_ref_by_name: dict[str, object] = {}
    active_tools = getattr(context_slice, "active_tools", ()) if context_slice else ()
    for tool_ref in active_tools or ():
        raw_name = getattr(tool_ref, "function_name", None)
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        if name and name not in tool_ref_by_name:
            tool_ref_by_name[name] = tool_ref
    refs: list[dict[str, object]] = []
    seen: set[str] = set()
    for schema in schemas:
        if schema.name in seen:
            continue
        tool_ref = tool_ref_by_name.get(schema.name)
        owner_ref = getattr(tool_ref, "owner_ref", None) if tool_ref is not None else None
        refs.append(
            {
                key: value
                for key, value in {
                    "name": schema.name,
                    "source": (
                        "context_slice"
                        if tool_ref is not None
                        else "runtime_request_draft"
                    ),
                    "schema": schema.to_payload(),
                    "node_id": (
                        getattr(tool_ref, "node_id", None)
                        if tool_ref is not None
                        else None
                    ),
                    "tool_ref_id": (
                        getattr(tool_ref, "tool_ref_id", None)
                        if tool_ref is not None
                        else None
                    ),
                    "source_id": (
                        getattr(tool_ref, "source_id", None)
                        if tool_ref is not None
                        else None
                    ),
                    "function_name": (
                        getattr(tool_ref, "function_name", None)
                        if tool_ref is not None
                        else schema.name
                    ),
                    "owner_ref": (
                        dict(owner_ref) if isinstance(owner_ref, dict) else None
                    ),
                }.items()
                if value not in (None, "", {}, [])
            },
        )
        seen.add(schema.name)
    return tuple(refs)


def context_slice_active_tool_names(
    context_slice: object | None,
) -> frozenset[str]:
    if context_slice is None:
        return frozenset()
    names: set[str] = set()
    for tool_ref in getattr(context_slice, "active_tools", ()) or ():
        name = getattr(tool_ref, "function_name", None)
        if isinstance(name, str) and name.strip():
            names.add(name.strip())
    return frozenset(names)
