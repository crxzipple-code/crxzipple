import {
  traceEvents as fixtureEvents,
  traceGraphEvents as fixtureGraphEvents,
  workbenchRun as fixtureRun,
} from "@/mocks/fixtures/runtime";
import { dataMode, requestJson } from "@/shared/api/client";
import type { RuntimeLlmRequestPreview } from "@/shared/runtime/runtimeRequestPreview";
import type {
  TraceEventView,
  TraceLinkedEntity,
  TraceSummaryView,
  WorkbenchLinkedEntityDetail,
} from "@/shared/runtime/types";

export interface TraceData {
  summary: TraceSummaryView;
  events: TraceEventView[];
  graphEvents: TraceEventView[];
  source: "fixture" | "api";
}

export interface TraceContextEstimate {
  text_chars: number;
  text_tokens: number;
  tool_schema_tokens: number;
  image_count: number;
  file_count: number;
  file_tokens: number;
  provider_attachment_count: number;
}

export interface TraceContextSnapshot {
  id: string;
  workspace_id: string;
  session_key: string;
  run_id: string;
  tree_revision: number;
  debug_body?: string;
  provider_attachments: Record<string, unknown>;
  estimate: TraceContextEstimate;
  included_node_ids: string[];
  mirrored_node_ids: string[];
  included_refs: Array<Record<string, unknown>>;
  collapsed_refs: Array<Record<string, unknown>>;
  protocol_required_refs: Array<Record<string, unknown>>;
  metadata: Record<string, unknown>;
  created_at: string;
}

export async function loadTraceData(
  traceId: string | null,
  focusId: string | null = null,
): Promise<TraceData> {
  if (dataMode !== "api" || !traceId) {
    return {
      summary: fixtureSummary(),
      events: fixtureEvents,
      graphEvents: fixtureGraphEvents,
      source: "fixture",
    };
  }

  const encodedTraceId = encodeURIComponent(traceId);
  const focusQuery = focusId ? `?focus_id=${encodeURIComponent(focusId)}` : "";
  const [summary, events] = await Promise.all([
    requestJson<TraceSummaryView>(`/ui/trace/${encodedTraceId}${focusQuery}`),
    requestJson<TraceEventView[]>(`/ui/trace/${encodedTraceId}/events${focusQuery}`),
  ]);

  return {
    summary,
    events,
    graphEvents: events,
    source: "api",
  };
}

export async function loadTraceContextSnapshot(
  runId: string,
  options: { includeDebugBody?: boolean } = {},
): Promise<TraceContextSnapshot | null> {
  if (dataMode !== "api") return null;
  try {
    const query = options.includeDebugBody ? "?include_debug_body=true" : "";
    const payload = await requestJson<{ snapshot: TraceContextSnapshot }>(
      `/ui/workbench/context-snapshots/runs/${encodeURIComponent(runId)}${query}`,
    );
    return payload.snapshot;
  } catch {
    return null;
  }
}

export async function loadTraceContextSnapshotById(
  snapshotId: string,
  options: { includeDebugBody?: boolean } = {},
): Promise<TraceContextSnapshot | null> {
  if (dataMode !== "api") return null;
  try {
    const query = options.includeDebugBody ? "?include_debug_body=true" : "";
    const payload = await requestJson<{ snapshot: TraceContextSnapshot }>(
      `/ui/workbench/context-snapshots/${encodeURIComponent(snapshotId)}${query}`,
    );
    return payload.snapshot;
  } catch {
    return null;
  }
}

export async function loadTraceRuntimeRequestPreview(runId: string): Promise<RuntimeLlmRequestPreview | null> {
  if (dataMode !== "api") return null;
  try {
    return await requestJson<RuntimeLlmRequestPreview>(
      `/ui/workbench/runs/${encodeURIComponent(runId)}/llm-request-preview`,
    );
  } catch {
    return null;
  }
}

export async function loadTraceInvocationRuntimeRequestPreview(
  invocationId: string,
  runId: string,
): Promise<RuntimeLlmRequestPreview | null> {
  if (dataMode !== "api") return null;
  try {
    const query = new URLSearchParams({ run_id: runId });
    return await requestJson<RuntimeLlmRequestPreview>(
      `/ui/workbench/llm-invocations/${encodeURIComponent(invocationId)}/llm-request-preview?${query.toString()}`,
    );
  } catch {
    return null;
  }
}

export function loadTraceLinkedEntityDetail(
  entityType: string,
  entityId: string,
): Promise<WorkbenchLinkedEntityDetail> {
  return requestJson<WorkbenchLinkedEntityDetail>(
    `/ui/workbench/linked-entities/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`,
  );
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
