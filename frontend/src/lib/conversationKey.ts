import type { ConversationSummary, TurnRun } from "@/types";

export function conversationKey(conversation: Pick<ConversationSummary, "session_key">) {
  const sessionKey = conversation.session_key?.trim();
  if (sessionKey) {
    return sessionKey;
  }
  throw new Error("Conversation is missing a stable key.");
}

export function turnConversationKey(run: Pick<TurnRun, "session_key">) {
  const sessionKey = run.session_key?.trim();
  if (sessionKey) {
    return sessionKey;
  }
  return null;
}
