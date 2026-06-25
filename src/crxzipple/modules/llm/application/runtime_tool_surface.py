from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from uuid import uuid4

from crxzipple.modules.llm.domain import ToolSchema


@dataclass(frozen=True, slots=True)
class RuntimeToolSurfaceRef:
    tool_id: str
    name: str
    schema: ToolSchema
    target: str
    source_id: str | None = None
    group_key: str | None = None
    always_visible: bool = True
    enabled: bool = True
    metadata: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "tool_id": self.tool_id,
            "name": self.name,
            "schema": self.schema.to_payload(),
            "target": self.target,
            "always_visible": self.always_visible,
            "enabled": self.enabled,
        }
        if self.source_id is not None:
            payload["source_id"] = self.source_id
        if self.group_key is not None:
            payload["group_key"] = self.group_key
        if self.metadata:
            payload["metadata"] = dict(self.metadata)
        return payload


@dataclass(frozen=True, slots=True)
class RuntimeToolSurface:
    id: str
    functions: tuple[RuntimeToolSurfaceRef, ...] = ()
    mirrored_schema_names: tuple[str, ...] = ()
    blocked_access_count: int = 0
    metadata: dict[str, object] = field(default_factory=dict)

    def to_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "id": self.id,
            "functions": [item.to_payload() for item in self.functions],
            "mirrored_schema_names": list(self.mirrored_schema_names),
            "blocked_access_count": self.blocked_access_count,
            "metadata": dict(self.metadata),
        }
        return {
            key: value
            for key, value in payload.items()
            if value not in (None, "", {}, [])
        }


def tool_schemas_from_projected_refs(
    tool_schema_refs: tuple[Mapping[str, object], ...],
) -> tuple[ToolSchema, ...]:
    """Build canonical tool schemas from Context Slice tool schema refs."""

    schemas: list[ToolSchema] = []
    for raw_ref in tool_schema_refs:
        schema_payload = raw_ref.get("schema")
        if not isinstance(schema_payload, Mapping):
            continue
        try:
            schemas.append(ToolSchema.from_payload(schema_payload))
        except Exception:
            continue
    return dedupe_tool_schemas(tuple(schemas))


def tool_surface_request_metadata(
    tool_surface: RuntimeToolSurface,
) -> dict[str, object]:
    function_refs = _tool_surface_function_refs(tool_surface.functions)
    metadata: dict[str, object] = {
        "tool_surface_mirrored_schema_names": list(
            tool_surface.mirrored_schema_names,
        ),
        "tool_surface_mirrored_schema_count": len(
            tool_surface.mirrored_schema_names,
        ),
        "tool_surface_always_visible_count": sum(
            1 for function in tool_surface.functions if function.always_visible
        ),
        "tool_surface_context_selected_count": sum(
            1 for function in tool_surface.functions if not function.always_visible
        ),
        "tool_surface_function_refs": function_refs,
        "tool_surface_source_refs": _dedupe_surface_refs(
            function_refs,
            key_fields=("source_id",),
        ),
        "tool_surface_group_refs": _dedupe_surface_refs(
            function_refs,
            key_fields=("source_id", "group_key"),
        ),
    }
    return {
        key: value
        for key, value in metadata.items()
        if value not in (None, "", {}, [])
    }


def request_time_tool_surface(tool_surface: RuntimeToolSurface) -> RuntimeToolSurface:
    return RuntimeToolSurface(
        id=f"{tool_surface.id}:{uuid4().hex}",
        functions=tool_surface.functions,
        mirrored_schema_names=tool_surface.mirrored_schema_names,
        blocked_access_count=tool_surface.blocked_access_count,
        metadata={
            **tool_surface.metadata,
            "base_tool_surface_id": tool_surface.id,
            "request_time_unique": True,
        },
    )


def dedupe_tool_schemas(tool_schemas: tuple[ToolSchema, ...] | None) -> tuple[ToolSchema, ...]:
    if not tool_schemas:
        return ()
    schemas: list[ToolSchema] = []
    seen: set[str] = set()
    for schema in tool_schemas:
        name = schema.name.strip()
        if not name or name in seen:
            continue
        schemas.append(schema)
        seen.add(name)
    return tuple(schemas)


def _tool_surface_function_refs(
    functions: tuple[RuntimeToolSurfaceRef, ...],
) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    for function in functions:
        ref: dict[str, object] = {
            "tool_id": function.tool_id,
            "name": function.name,
            "enabled": function.enabled,
            "always_visible": function.always_visible,
        }
        if function.source_id is not None:
            ref["source_id"] = function.source_id
        if function.group_key is not None:
            ref["group_key"] = function.group_key
        for key in ("source", "node_id", "tool_ref_id", "function_name"):
            value = function.metadata.get(key)
            if value not in (None, "", {}, []):
                ref[key] = value
        refs.append(ref)
    return refs


def _dedupe_surface_refs(
    refs: list[dict[str, object]],
    *,
    key_fields: tuple[str, ...],
) -> list[dict[str, object]]:
    seen: set[tuple[object, ...]] = set()
    result: list[dict[str, object]] = []
    for ref in refs:
        key = tuple(ref.get(field) for field in key_fields)
        if any(value is None for value in key) or key in seen:
            continue
        seen.add(key)
        result.append({field: ref[field] for field in key_fields})
    return result


__all__ = [
    "RuntimeToolSurface",
    "RuntimeToolSurfaceRef",
    "dedupe_tool_schemas",
    "request_time_tool_surface",
    "tool_schemas_from_projected_refs",
    "tool_surface_request_metadata",
]
