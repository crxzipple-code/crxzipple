import {
  traceEvents as fixtureEvents,
  traceGraphEvents as fixtureGraphEvents,
  workbenchRun as fixtureRun,
} from "@/mocks/fixtures/runtime";
import { dataMode, requestJson } from "@/shared/api/client";
import type { TraceEventView, TraceLinkedEntity, TraceSummaryView } from "@/shared/runtime/types";

export interface TraceData {
  summary: TraceSummaryView;
  events: TraceEventView[];
  graphEvents: TraceEventView[];
  source: "fixture" | "api";
}

export async function loadTraceData(traceId: string | null): Promise<TraceData> {
  if (dataMode !== "api" || !traceId) {
    return {
      summary: fixtureSummary(),
      events: fixtureEvents,
      graphEvents: fixtureGraphEvents,
      source: "fixture",
    };
  }

  const encodedTraceId = encodeURIComponent(traceId);
  const [summary, events] = await Promise.all([
    requestJson<TraceSummaryView>(`/ui/trace/${encodedTraceId}`),
    requestJson<TraceEventView[]>(`/ui/trace/${encodedTraceId}/events`),
  ]);

  return {
    summary,
    events,
    graphEvents: events,
    source: "api",
  };
}

function fixtureSummary(): TraceSummaryView {
  const startedAt = fixtureEvents[0]?.timestamp ?? fixtureRun.started_at;
  const completedAt = fixtureEvents[fixtureEvents.length - 1]?.timestamp ?? fixtureRun.completed_at;
  return {
    trace_id: fixtureRun.trace.trace_id,
    status: "success",
    started_at: startedAt,
    completed_at: completedAt,
    duration_ms: fixtureRun.duration_ms,
    event_count: 28,
    key_event_count: fixtureEvents.filter((event) => event.key_event).length,
    owners: [...new Set(fixtureEvents.map((event) => event.owner))],
    linked_entities: uniqueEntities(
      fixtureEvents.flatMap((event) => event.linked_entities),
    ),
  };
}

function uniqueEntities(items: TraceLinkedEntity[]): TraceLinkedEntity[] {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = `${item.type}:${item.id}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}
