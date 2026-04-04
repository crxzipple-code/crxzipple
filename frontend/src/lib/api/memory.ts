import { buildApiUrl, requestJson } from "@/lib/api/client";
import type {
  MemoryExcerpt,
  MemoryOverview,
  MemorySearchHit,
} from "@/types";

export function getMemoryOverview(options: {
  agentId: string;
  recentLimit?: number;
}) {
  const url = new URL(buildApiUrl("/memory/overview"), window.location.origin);
  url.searchParams.set("agent_id", options.agentId);
  if (typeof options.recentLimit === "number") {
    url.searchParams.set("recent_limit", String(options.recentLimit));
  }
  return requestJson<MemoryOverview>(url.pathname + (url.search ? url.search : ""));
}

export function searchMemory(options: {
  agentId: string;
  query: string;
  limit?: number;
}) {
  const url = new URL(buildApiUrl("/memory/search"), window.location.origin);
  url.searchParams.set("agent_id", options.agentId);
  url.searchParams.set("query", options.query);
  if (typeof options.limit === "number") {
    url.searchParams.set("limit", String(options.limit));
  }
  return requestJson<MemorySearchHit[]>(url.pathname + (url.search ? url.search : ""));
}

export function getMemoryExcerpt(options: {
  agentId: string;
  path: string;
  startLine?: number | null;
  lineCount?: number | null;
}) {
  const url = new URL(buildApiUrl("/memory/excerpt"), window.location.origin);
  url.searchParams.set("agent_id", options.agentId);
  url.searchParams.set("path", options.path);
  if (typeof options.startLine === "number") {
    url.searchParams.set("start_line", String(options.startLine));
  }
  if (typeof options.lineCount === "number") {
    url.searchParams.set("line_count", String(options.lineCount));
  }
  return requestJson<MemoryExcerpt>(url.pathname + (url.search ? url.search : ""));
}

export function writeDailyMemory(options: {
  agentId: string;
  content: string;
  title?: string | null;
}) {
  return requestJson<{ path: string; line_start: number; line_end: number; kind: string }>(
    "/memory/daily",
    {
      method: "POST",
      body: JSON.stringify({
        agent_id: options.agentId,
        content: options.content,
        title: options.title ?? null,
      }),
    },
  );
}

export function writeLongTermMemory(options: {
  agentId: string;
  content: string;
}) {
  return requestJson<{ path: string; line_start: number; line_end: number; kind: string }>(
    "/memory/long-term",
    {
      method: "POST",
      body: JSON.stringify({
        agent_id: options.agentId,
        content: options.content,
      }),
    },
  );
}
