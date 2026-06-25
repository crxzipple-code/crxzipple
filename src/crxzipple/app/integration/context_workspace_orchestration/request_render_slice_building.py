"""Control/context slice building helpers for request-render snapshots."""

from __future__ import annotations

from crxzipple.modules.context_workspace.application import (
    BuildContextControlSliceInput,
    BuildContextObservationSliceInput,
)
from crxzipple.modules.context_workspace.application.ports import (
    ContextControlSliceBuilder,
    ContextSliceBuilder,
)

from .request_render_input_selection import RequestRenderInputSelection


def build_request_control_slice(
    *,
    builder: ContextControlSliceBuilder | None,
    session_key: str,
    run_id: str,
    provider_profile: str,
    read_only: bool,
    requested_tool_schema_names: tuple[str, ...],
    input_selection: RequestRenderInputSelection,
) -> object | None:
    if builder is None:
        return None
    return builder.build_control_slice(
        data=BuildContextControlSliceInput(
            session_key=session_key,
            run_id=run_id,
            audience="llm_request",
            provider_profile=provider_profile,
            metadata={
                "read_only": read_only,
                "requested_tool_schema_names": list(requested_tool_schema_names),
                "protocol_required_refs": [
                    dict(ref) for ref in input_selection.control_protocol_required_refs
                ],
            },
        ),
    )


def build_request_context_slice(
    *,
    builder: ContextSliceBuilder | None,
    session_key: str,
    run_id: str,
    provider_profile: str,
    read_only: bool,
    requested_tool_schema_names: tuple[str, ...],
    input_selection: RequestRenderInputSelection,
) -> object | None:
    if builder is None:
        return None
    metadata: dict[str, object] = {
        "read_only": read_only,
        "requested_tool_schema_names": list(requested_tool_schema_names),
        "protocol_required_refs": [
            dict(ref) for ref in input_selection.protocol_required_refs
        ],
    }
    if input_selection.request_input_item_refs:
        metadata["input_item_refs"] = [
            dict(ref) for ref in input_selection.request_input_item_refs
        ]
    if input_selection.session_item_max_chars is not None:
        metadata["session_item_max_chars"] = input_selection.session_item_max_chars
    return builder.build_slice(
        data=BuildContextObservationSliceInput(
            session_key=session_key,
            run_id=run_id,
            audience="llm_request",
            provider_profile=provider_profile,
            metadata=metadata,
        ),
    )
