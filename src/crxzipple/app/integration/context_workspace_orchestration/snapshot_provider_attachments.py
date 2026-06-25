"""Provider attachment helpers for request snapshot metadata."""

from __future__ import annotations

from crxzipple.modules.llm.domain import ToolSchema

from ._metadata import estimate_text_tokens_from_chars


def build_snapshot_provider_attachments(
    rendered_attachments: dict[str, object],
    *,
    draft: object,
) -> dict[str, object]:
    return dict(rendered_attachments)


def mirrored_schema_estimated_tokens(provider_attachments: dict[str, object]) -> int:
    raw_schemas = provider_attachments.get("tool_schemas")
    if not isinstance(raw_schemas, list):
        return 0
    total_chars = 0
    for schema in raw_schemas:
        if not isinstance(schema, dict):
            continue
        total_chars += len(str(schema.get("name") or ""))
        total_chars += len(str(schema.get("description") or ""))
        total_chars += len(str(schema.get("input_schema") or ""))
    return estimate_text_tokens_from_chars(total_chars)


def mirrored_tool_schemas(
    provider_attachments: dict[str, object],
    *,
    mirror_available: bool,
) -> tuple[ToolSchema, ...] | None:
    if not mirror_available:
        return None
    raw_schemas = provider_attachments.get("tool_schemas")
    if not isinstance(raw_schemas, list):
        return ()
    schemas: list[ToolSchema] = []
    for raw_schema in raw_schemas:
        if not isinstance(raw_schema, dict):
            continue
        name = raw_schema.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        input_schema = raw_schema.get("input_schema")
        schemas.append(
            ToolSchema(
                name=name,
                description=(
                    str(raw_schema.get("description"))
                    if raw_schema.get("description") is not None
                    else ""
                ),
                input_schema=(
                    dict(input_schema) if isinstance(input_schema, dict) else {}
                ),
            ),
        )
    return tuple(schemas)
