from __future__ import annotations


CONTEXT_RENDER_BUDGET_METADATA_FIELDS = (
    "rendered_prompt_estimated_tokens",
    "direct_transcript_estimated_tokens",
    "mirrored_tool_schema_estimated_tokens",
    "artifact_content_estimated_tokens",
    "estimated_provider_prompt_tokens",
    "tool_schema_mirror_budget_status",
    "artifact_content_budget",
    "top_rendered_nodes",
)


def context_render_budget_metadata(metadata: dict[str, object]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for field_name in CONTEXT_RENDER_BUDGET_METADATA_FIELDS:
        value = metadata.get(field_name)
        if value is None and field_name == "top_rendered_nodes":
            value = _top_rendered_nodes_from_breakdown(metadata)
        payload[field_name] = value
    return payload


def _top_rendered_nodes_from_breakdown(metadata: dict[str, object]) -> object:
    breakdown = metadata.get("node_estimate_breakdown")
    if not isinstance(breakdown, dict):
        return None
    top_rendered_nodes = breakdown.get("top_rendered_nodes")
    if isinstance(top_rendered_nodes, list):
        return list(top_rendered_nodes)
    return None


__all__ = [
    "CONTEXT_RENDER_BUDGET_METADATA_FIELDS",
    "context_render_budget_metadata",
]
