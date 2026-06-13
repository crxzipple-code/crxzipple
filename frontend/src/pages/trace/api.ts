import {
  traceEvents as fixtureEvents,
  traceGraphEvents as fixtureGraphEvents,
  workbenchRun as fixtureRun,
} from "@/mocks/fixtures/runtime";
import { dataMode, requestJson } from "@/shared/api/client";
import type { RunPromptInputPreview } from "@/shared/runtime/promptPreview";
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

export interface TraceContextRenderSnapshot {
  id: string;
  workspace_id: string;
  session_key: string;
  run_id: string;
  tree_revision: number;
  prompt_body: string;
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
  stepId: string | null = null,
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
  const stepQuery = stepId ? `?step_id=${encodeURIComponent(stepId)}` : "";
  const [summary, events] = await Promise.all([
    requestJson<TraceSummaryView>(`/ui/trace/${encodedTraceId}${stepQuery}`),
    requestJson<TraceEventView[]>(`/ui/trace/${encodedTraceId}/events${stepQuery}`),
  ]);

  return {
    summary,
    events,
    graphEvents: events,
    source: "api",
  };
}

export async function loadTraceContextRenderSnapshot(runId: string): Promise<TraceContextRenderSnapshot | null> {
  if (dataMode !== "api") return null;
  try {
    const payload = await requestJson<{ snapshot: TraceContextRenderSnapshot }>(
      `/context-workspaces/runs/${encodeURIComponent(runId)}/render-snapshot`,
    );
    return payload.snapshot;
  } catch {
    return null;
  }
}

export async function loadTraceContextRenderSnapshotById(snapshotId: string): Promise<TraceContextRenderSnapshot | null> {
  if (dataMode !== "api") return null;
  try {
    const payload = await requestJson<{ snapshot: TraceContextRenderSnapshot }>(
      `/context-workspaces/render-snapshots/${encodeURIComponent(snapshotId)}`,
    );
    return payload.snapshot;
  } catch {
    return null;
  }
}

export async function loadTracePromptPreview(runId: string): Promise<RunPromptInputPreview | null> {
  if (dataMode !== "api") return null;
  try {
    return await requestJson<RunPromptInputPreview>(
      `/turns/${encodeURIComponent(runId)}/prompt-preview`,
    );
  } catch {
    return null;
  }
}

export async function loadTraceInvocationPromptPreview(
  invocationId: string,
  runId: string,
): Promise<RunPromptInputPreview | null> {
  if (dataMode !== "api") return null;
  try {
    const query = new URLSearchParams({ run_id: runId });
    return await requestJson<RunPromptInputPreview>(
      `/llms/calls/${encodeURIComponent(invocationId)}/prompt-preview?${query.toString()}`,
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
