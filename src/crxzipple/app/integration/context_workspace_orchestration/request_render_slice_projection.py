"""Projection bundle for request-render control/context slices."""

from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.orchestration.application.runtime_llm_request_draft import (
    RuntimeLlmRequestDraft,
)

from .context_slice_projection import (
    context_slice_collapsed_refs,
    context_slice_included_node_ids,
    context_slice_loss,
    context_slice_omitted_node_ids,
    context_slice_projected_input_items,
    context_slice_report_refs,
    context_slice_session_refs,
    control_slice_selected_node_ids,
)
from .draft_input_projection import (
    draft_current_input_projection,
    merge_projected_input_items,
)


@dataclass(frozen=True)
class RequestRenderSliceProjection:
    control_selected_node_ids: tuple[str, ...]
    context_slice_refs: tuple[dict[str, object], ...]
    context_slice_node_ids: tuple[str, ...]
    context_slice_omitted_node_ids: tuple[str, ...]
    context_slice_report_refs: dict[str, tuple[dict[str, object], ...]]
    context_slice_loss: dict[str, object]
    projected_input_items: tuple[dict[str, object], ...]
    included_refs: tuple[dict[str, object], ...]
    included_node_ids: tuple[str, ...]
    collapsed_refs: tuple[dict[str, object], ...]


def project_request_render_slices(
    *,
    draft: RuntimeLlmRequestDraft,
    control_slice: object | None,
    context_slice: object | None,
) -> RequestRenderSliceProjection:
    context_refs = context_slice_session_refs(context_slice)
    node_ids = context_slice_included_node_ids(context_slice)
    projected_input_items = merge_projected_input_items(
        context_slice_projected_input_items(context_slice),
        draft_current_input_projection(draft),
    )
    return RequestRenderSliceProjection(
        control_selected_node_ids=control_slice_selected_node_ids(control_slice),
        context_slice_refs=context_refs,
        context_slice_node_ids=node_ids,
        context_slice_omitted_node_ids=context_slice_omitted_node_ids(context_slice),
        context_slice_report_refs=context_slice_report_refs(context_slice),
        context_slice_loss=context_slice_loss(context_slice),
        projected_input_items=projected_input_items,
        included_refs=context_refs if context_slice is not None else (),
        included_node_ids=node_ids if context_slice is not None else (),
        collapsed_refs=context_slice_collapsed_refs(context_slice),
    )
