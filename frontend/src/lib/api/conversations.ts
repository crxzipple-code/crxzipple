import { buildApiUrl, requestJson } from "@/lib/api/client";
import type { ConversationSummary, SessionMessage } from "@/types";

export function listConversations() {
  return requestJson<ConversationSummary[]>("/conversations");
}

export function getConversation(bulkKey: string) {
  return requestJson<ConversationSummary>(
    `/conversations/${encodeURIComponent(bulkKey)}`,
  );
}

export function getConversationMessages(
  bulkKey: string,
  options?: {
    includeArchived?: boolean;
  },
) {
  const url = new URL(
    buildApiUrl(`/conversations/${encodeURIComponent(bulkKey)}/messages`),
    window.location.origin,
  );
  if (options?.includeArchived) {
    url.searchParams.set("include_archived", "true");
  }
  return requestJson<SessionMessage[]>(
    url.pathname + (url.search ? url.search : ""),
  );
}
