from __future__ import annotations

from typing import Protocol

from crxzipple.modules.context_workspace.application import (
    BuildContextObservationSliceInput,
)
from crxzipple.modules.context_workspace.domain import ContextWorkspaceNotFoundError
from crxzipple.modules.events.application.read_models import TraceEventView


class WorkbenchContextSliceBuilderPort(Protocol):
    def build_slice(self, *, data: BuildContextObservationSliceInput) -> object:
        ...


def filter_trace_events_by_context_slice(
    events: tuple[TraceEventView, ...],
    *,
    context_slice_builder: WorkbenchContextSliceBuilderPort | None,
) -> tuple[TraceEventView, ...]:
    session_key, run_id = _trace_slice_context(events)
    if session_key is None or run_id is None:
        return events
    if context_slice_builder is None:
        return events
    try:
        context_slice = context_slice_builder.build_slice(
            data=BuildContextObservationSliceInput(
                session_key=session_key,
                run_id=run_id,
                audience="trace_timeline",
                metadata={"surface": "trace", "read_only": True},
            ),
        )
    except ContextWorkspaceNotFoundError:
        return events
    payload = context_slice.to_payload()
    refs = _context_slice_trace_refs(payload.get("items"))
    if not refs:
        return events
    return tuple(
        event for event in events if _trace_event_matches_context_slice(event, refs)
    )


def _trace_slice_context(
    events: tuple[TraceEventView, ...],
) -> tuple[str | None, str | None]:
    session_key: str | None = None
    run_id: str | None = None
    for event in events:
        if session_key is None:
            session_key = _optional_str(event.trace.session_key)
        if run_id is None:
            run_id = _optional_str(event.trace.run_id)
        if session_key is not None and run_id is not None:
            return session_key, run_id
    return session_key, run_id


_TRACE_CONTEXT_REF_KEYS = (
    "session_item_id",
    "message_id",
    "step_id",
    "llm_response_item_id",
    "llm_invocation_id",
    "invocation_id",
    "tool_run_id",
    "execution_step_id",
    "execution_item_id",
    "request_render_snapshot_id",
    "provider_item_id",
    "call_id",
    "tool_call_id",
    "artifact_id",
    "approval_request_id",
)

_FILTERABLE_TRACE_CONTEXT_REF_KEYS = frozenset(
    {
        "session_item_id",
        "session_item_ids",
        "llm_response_item_id",
        "tool_run_id",
        "execution_step_id",
        "execution_item_id",
        "request_render_snapshot_id",
        "provider_item_id",
        "call_id",
        "tool_call_id",
        "artifact_id",
        "approval_request_id",
    },
)


def _context_slice_trace_refs(items: object) -> dict[str, frozenset[str]]:
    if not isinstance(items, (list, tuple)):
        return {}
    refs: dict[str, set[str]] = {}
    for item in items:
        if not isinstance(item, dict):
            continue
        owner_ref = item.get("owner_ref")
        if not isinstance(owner_ref, dict):
            owner_ref = {}
        for key in _TRACE_CONTEXT_REF_KEYS:
            for candidate in (item, owner_ref):
                value = _optional_str(candidate.get(key))
                if value is not None:
                    refs.setdefault(key, set()).add(value)
    return {key: frozenset(values) for key, values in refs.items() if values}


def _trace_event_matches_context_slice(
    event: TraceEventView,
    refs: dict[str, frozenset[str]],
) -> bool:
    payload = event.trace.to_payload()
    payload.update(event.payload)
    for entity in event.linked_entities:
        payload.setdefault(entity.type, entity.id)
    has_filterable_ref = any(
        _payload_has_trace_ref(payload.get(key))
        for key in _FILTERABLE_TRACE_CONTEXT_REF_KEYS
    )
    for key, allowed_values in refs.items():
        if _payload_trace_ref_matches(payload.get(key), allowed_values):
            return True
    return not has_filterable_ref


def _payload_trace_ref_matches(
    value: object,
    allowed_values: frozenset[str],
) -> bool:
    return bool(_payload_trace_ref_values(value).intersection(allowed_values))


def _payload_has_trace_ref(value: object) -> bool:
    return bool(_payload_trace_ref_values(value))


def _payload_trace_ref_values(value: object) -> frozenset[str]:
    if isinstance(value, str):
        normalized = value.strip()
        return frozenset({normalized}) if normalized else frozenset()
    if isinstance(value, (list, tuple, set, frozenset)):
        return frozenset(
            normalized
            for item in value
            if isinstance(item, str) and (normalized := item.strip())
        )
    return frozenset()


def _optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
