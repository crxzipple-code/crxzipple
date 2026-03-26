import { buildApiUrl, requestJson } from "@/lib/api/client";
import type { MemoryCandidate, MemoryEntry } from "@/types";

export function listMemoryCandidates(options?: {
  agentId?: string | null;
  sessionKey?: string | null;
  runId?: string | null;
  status?: string | null;
  limit?: number;
}) {
  const url = new URL(buildApiUrl("/memory/candidates"), window.location.origin);
  if (options?.agentId) {
    url.searchParams.set("agent_id", options.agentId);
  }
  if (options?.sessionKey) {
    url.searchParams.set("session_key", options.sessionKey);
  }
  if (options?.runId) {
    url.searchParams.set("run_id", options.runId);
  }
  if (options?.status) {
    url.searchParams.set("status", options.status);
  }
  if (typeof options?.limit === "number") {
    url.searchParams.set("limit", String(options.limit));
  }
  return requestJson<MemoryCandidate[]>(
    url.pathname + (url.search ? url.search : ""),
  );
}

export function approveMemoryCandidate(candidateId: string) {
  return requestJson<MemoryEntry>(
    `/memory/candidates/${encodeURIComponent(candidateId)}/approve`,
    {
      method: "POST",
    },
  );
}

export function rejectMemoryCandidate(candidateId: string, reason?: string) {
  return requestJson<MemoryCandidate>(
    `/memory/candidates/${encodeURIComponent(candidateId)}/reject`,
    {
      method: "POST",
      body: JSON.stringify({ reason: reason ?? null }),
    },
  );
}

export function listMemoryEntries(options?: {
  agentId?: string | null;
  query?: string | null;
  limit?: number;
}) {
  const url = new URL(buildApiUrl("/memory/entries"), window.location.origin);
  if (options?.agentId) {
    url.searchParams.set("agent_id", options.agentId);
  }
  if (options?.query) {
    url.searchParams.set("query", options.query);
  }
  if (typeof options?.limit === "number") {
    url.searchParams.set("limit", String(options.limit));
  }
  return requestJson<MemoryEntry[]>(
    url.pathname + (url.search ? url.search : ""),
  );
}
