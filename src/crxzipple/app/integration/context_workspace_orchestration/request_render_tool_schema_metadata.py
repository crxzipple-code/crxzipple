"""Tool schema metadata for request-render snapshots."""

from __future__ import annotations

from crxzipple.modules.llm.domain import ToolSchema


def request_render_tool_schema_metadata(
    *,
    render_metadata: dict[str, object],
    visible_tool_schemas: tuple[ToolSchema, ...],
    available_tool_schemas: tuple[ToolSchema, ...],
) -> dict[str, object]:
    return {
        "mirrored_tool_schema_count": len(visible_tool_schemas),
        "provider_tool_schema_names": [schema.name for schema in visible_tool_schemas],
        "tool_schema_mirror_budget": {
            "status": "ok",
            "default_schema_source": render_metadata.get(
                "default_tool_schema_source",
            ),
            "default_requested_count": len(
                _sequence_value(render_metadata.get("default_tool_schema_ids")),
            ),
            "default_mirrored_count": len(visible_tool_schemas),
            "available_count": len(available_tool_schemas),
            "enabled_candidate_count": len(visible_tool_schemas),
            "group_count": len(
                _sequence_value(render_metadata.get("default_tool_schema_group_refs")),
            ),
        },
        "tool_schema_mirror_default_schema_source": render_metadata.get(
            "default_tool_schema_source",
        ),
    }


def _sequence_value(value: object) -> tuple[object, ...]:
    if not isinstance(value, list | tuple):
        return ()
    return tuple(value)
