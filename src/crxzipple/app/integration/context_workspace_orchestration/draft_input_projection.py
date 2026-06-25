from __future__ import annotations

from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)

from .draft_input_current_inbound import (
    is_current_inbound_input_item,
    mode_allows_session_current_inbound_anchor,
    project_input_item,
    project_message,
)
from .draft_input_merge import merge_projected_input_items


def draft_current_input_projection(
    draft: RuntimeLlmRequestDraft,
) -> tuple[dict[str, object], ...]:
    allow_session_anchor = mode_allows_session_current_inbound_anchor(draft)
    projected = tuple(
        project_input_item(item)
        for item in draft.input_items
        if is_current_inbound_input_item(
            item,
            allow_session_anchor=allow_session_anchor,
        )
    )
    if projected:
        return tuple(item for item in projected if item is not None)
    return tuple(
        item
        for message in draft.messages
        for item in (
            project_message(
                message,
                allow_session_anchor=allow_session_anchor,
            ),
        )
        if item is not None
    )


__all__ = [
    "draft_current_input_projection",
    "merge_projected_input_items",
]
