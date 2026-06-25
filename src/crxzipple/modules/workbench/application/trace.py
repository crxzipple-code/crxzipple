from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from crxzipple.modules.events.application.read_models import (
    TraceEventView,
    TraceSummaryView,
)
from crxzipple.modules.workbench.application.trace_alias_projection import (
    trace_aliases,
)
from crxzipple.modules.workbench.application.trace_context_filter import (
    WorkbenchContextSliceBuilderPort,
    filter_trace_events_by_context_slice,
)
from crxzipple.modules.workbench.application.trace_summary_projection import (
    trace_summary_from_events,
)


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
        return trace_summary_from_events(trace_id, events)

    def list_trace_events(
        self,
        trace_id: str,
        *,
        focus_id: str | None = None,
        limit: int = 200,
    ) -> tuple[TraceEventView, ...]:
        events = self.trace_query.list_trace_events(
            trace_id,
            aliases=trace_aliases(trace_id, self.run_query.list_runs()),
            focus_id=focus_id,
            limit=limit,
        )
        return filter_trace_events_by_context_slice(
            events,
            context_slice_builder=self.context_slice_builder,
        )
