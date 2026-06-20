from __future__ import annotations


REQUEST_RENDER_BUDGET_METADATA_FIELDS = (
    "draft_input_estimated_tokens",
    "mirrored_tool_schema_estimated_tokens",
    "artifact_content_estimated_tokens",
    "estimated_provider_input_tokens",
    "tool_schema_mirror_budget_status",
    "artifact_content_budget",
)


def request_render_budget_metadata(metadata: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for field_name in REQUEST_RENDER_BUDGET_METADATA_FIELDS:
        value = metadata.get(field_name)
        payload[field_name] = value
    return payload


__all__ = [
    "REQUEST_RENDER_BUDGET_METADATA_FIELDS",
    "request_render_budget_metadata",
]
