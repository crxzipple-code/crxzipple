from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from crxzipple.modules.context_workspace.application import (
    BuildContextObservationSliceInput,
)
from crxzipple.modules.context_workspace.domain import ContextWorkspaceNotFoundError
from crxzipple.modules.events.application.read_models import (
    TraceEventView,
    TraceSummaryView,
)
from crxzipple.modules.events.application.read_models.trace import TraceLinkedEntity


class WorkbenchRunTraceQueryPort(Protocol):
    def list_runs(self) -> list[object]:
        ...


class WorkbenchEventTraceQueryPort(Protocol):
    def list_trace_events(
        self,
        trace_id: str,
        *,
        aliases: set[str] | None = None,
        focus_id: str | None = None,
        limit: int = 200,
    ) -> tuple[TraceEventView, ...]:
        ...


class WorkbenchContextSliceBuilderPort(Protocol):
    def build_slice(self, *, data: BuildContextObservationSliceInput) -> object:
        ...


@dataclass(frozen=True, slots=True)
class WorkbenchTraceReadModelProvider:
    trace_query: WorkbenchEventTraceQueryPort
    run_query: WorkbenchRunTraceQueryPort
    context_slice_builder: WorkbenchContextSliceBuilderPort | None = None

    def get_trace_summary(
        self,
        trace_id: str,
        *,
        focus_id: str | None = None,
        limit: int = 200,
    ) -> TraceSummaryView:
        events = self.list_trace_events(trace_id, focus_id=focus_id, limit=limit)
        return _trace_summary_from_events(trace_id, events)

    def list_trace_events(
        self,
        trace_id: str,
        *,
        focus_id: str | None = None,
        limit: int = 200,
    ) -> tuple[TraceEventView, ...]:
        aliases = self._trace_aliases(trace_id)
        events = self.trace_query.list_trace_events(
            trace_id,
            aliases=aliases,
            focus_id=focus_id,
            limit=limit,
        )
        return self._filter_trace_events_by_context_slice(events)

    def _filter_trace_events_by_context_slice(
        self,
        events: tuple[TraceEventView, ...],
    ) -> tuple[TraceEventView, ...]:
        session_key, run_id = _trace_slice_context(events)
        if session_key is None or run_id is None:
            return events
        if self.context_slice_builder is None:
            return events
        try:
            context_slice = self.context_slice_builder.build_slice(
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

    def _trace_aliases(self, trace_id: str) -> set[str]:
        normalized = trace_id.strip()
        aliases = {normalized} if normalized else set()
        if not normalized:
            return aliases
        for run in self.run_query.list_runs():
            metadata = getattr(run, "metadata", {}) or {}
            metadata_trace_id = metadata.get("trace_id")
            metadata_correlation_id = metadata.get("correlation_id")
            session_key = getattr(run, "session_key", None)
            run_id = getattr(run, "id", None)
            if normalized in {
                run_id,
                session_key,
                metadata_trace_id if isinstance(metadata_trace_id, str) else None,
                (
                    metadata_correlation_id
                    if isinstance(metadata_correlation_id, str)
                    else None
                ),
            }:
                aliases.add(str(run_id))
                if isinstance(session_key, str) and session_key.strip():
                    aliases.add(session_key.strip())
                if isinstance(metadata_trace_id, str) and metadata_trace_id.strip():
                    aliases.add(metadata_trace_id.strip())
                if (
                    isinstance(metadata_correlation_id, str)
                    and metadata_correlation_id.strip()
                ):
                    aliases.add(metadata_correlation_id.strip())
        return aliases


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
    for key, allowed_values in refs.items():
        value = _optional_str(payload.get(key))
        if value is not None and value in allowed_values:
            return True
    return False


def _trace_summary_from_events(
    trace_id: str,
    events: tuple[TraceEventView, ...],
) -> TraceSummaryView:
    timestamps = [
        datetime.fromisoformat(event.timestamp)
        for event in events
        if event.timestamp
    ]
    started_at = min(timestamps) if timestamps else None
    completed_at = max(timestamps) if timestamps else None
    linked_entities = _unique_trace_entities(
        entity for event in events for entity in event.linked_entities
    )
    return TraceSummaryView(
        trace_id=trace_id,
        status=_trace_status(events),
        started_at=started_at.isoformat() if started_at is not None else None,
        completed_at=completed_at.isoformat() if completed_at is not None else None,
        duration_ms=_trace_span_ms(started_at, completed_at),
        event_count=len(events),
        key_event_count=sum(1 for event in events if event.key_event),
        owners=tuple(sorted({event.owner for event in events if event.owner})),
        linked_entities=linked_entities,
    )


def _unique_trace_entities(items) -> tuple[TraceLinkedEntity, ...]:  # noqa: ANN001
    seen: set[tuple[str, str]] = set()
    unique: list[TraceLinkedEntity] = []
    for item in items:
        key = (item.type, item.id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return tuple(unique)


def _trace_status(events: tuple[TraceEventView, ...]) -> str:
    if any(event.status == "failed" for event in events):
        return "failed"
    if any(event.status in {"running", "queued", "waiting"} for event in events):
        return "running"
    if events:
        return "success"
    return "unknown"


def _trace_span_ms(
    started_at: datetime | None,
    completed_at: datetime | None,
) -> int | None:
    if started_at is None or completed_at is None:
        return None
    return max(int((completed_at - started_at).total_seconds() * 1000), 0)


def _optional_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None
