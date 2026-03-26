import { requestJson } from "@/lib/api/client";
import type { AgentHomeSnapshot, AgentProfileSummary } from "@/types";

export function listAgents() {
  return requestJson<AgentProfileSummary[]>("/agents");
}

export function createAgentProfile(payload: {
  id: string;
  name: string;
  description?: string;
  defaultLlmId: string;
  homeDir?: string | null;
  workdir?: string | null;
  systemPrompt?: string;
}) {
  return requestJson<AgentProfileSummary>("/agents", {
    method: "POST",
    body: JSON.stringify({
      id: payload.id,
      name: payload.name,
      description: payload.description ?? "",
      enabled: true,
      identity: {},
      instruction_policy: {
        system_prompt: payload.systemPrompt ?? "You are a concise helpful assistant.",
        response_style: null,
        thinking_default: null,
        stream_by_default: false,
      },
      llm_routing_policy: {
        default_llm_id: payload.defaultLlmId,
        fallback_llm_ids: [],
        image_llm_id: null,
        document_llm_id: null,
      },
      execution_policy: {
        timeout_seconds: 120,
        max_turns: 12,
      },
      runtime_preferences: {
        home_dir: payload.homeDir ?? null,
        workdir: payload.workdir ?? null,
        workspace: null,
        sandbox_mode: null,
        attrs: {},
      },
      tool_preferences: {
        requested_effect_ids: [],
        requested_tool_ids: [],
        preferred_tags: [],
        prefers_background_tools: true,
        prefers_mutating_tools: true,
      },
    }),
  });
}

export function migrateAgentHome(
  agentId: string,
  payload: { homeDir: string; workdir?: string | null },
) {
  return requestJson<{ home_dir: string; workdir: string | null }>(
    `/agents/${encodeURIComponent(agentId)}/migrate-home`,
    {
      method: "POST",
      body: JSON.stringify({
        home_dir: payload.homeDir,
        workdir: payload.workdir ?? null,
      }),
    },
  );
}

export function enableAgentProfile(agentId: string) {
  return requestJson<AgentProfileSummary>(
    `/agents/${encodeURIComponent(agentId)}/enable`,
    {
      method: "POST",
    },
  );
}

export function disableAgentProfile(agentId: string) {
  return requestJson<AgentProfileSummary>(
    `/agents/${encodeURIComponent(agentId)}/disable`,
    {
      method: "POST",
    },
  );
}

export function getAgentHome(agentId: string) {
  return requestJson<AgentHomeSnapshot>(`/agents/${encodeURIComponent(agentId)}/home`);
}

export function updateAgentHome(
  agentId: string,
  files: Array<{ name: string; content: string }>,
) {
  return requestJson<AgentHomeSnapshot>(
    `/agents/${encodeURIComponent(agentId)}/home`,
    {
      method: "PUT",
      body: JSON.stringify({ files }),
    },
  );
}

export function syncAgentHome(agentId: string, payload?: { homeDir?: string | null }) {
  return requestJson<{ home_dir: string; path: string }>(
    `/agents/${encodeURIComponent(agentId)}/sync-home`,
    {
      method: "POST",
      body: JSON.stringify({
        home_dir: payload?.homeDir ?? null,
      }),
    },
  );
}

export function exportAgentHome(agentId: string, payload?: { homeDir?: string | null }) {
  return requestJson<{ home_dir: string; path: string }>(
    `/agents/${encodeURIComponent(agentId)}/export-home`,
    {
      method: "POST",
      body: JSON.stringify({
        home_dir: payload?.homeDir ?? null,
      }),
    },
  );
}
