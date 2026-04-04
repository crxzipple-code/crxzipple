import type { TurnRun } from "@/types";

function normalizeRequestedLlmId(run: TurnRun | null | undefined) {
  const raw = run?.metadata.requested_llm_id;
  if (typeof raw !== "string") {
    return null;
  }
  const value = raw.trim();
  return value || null;
}

function truncate(value: string, maxLength = 160) {
  const normalized = value.replace(/\s+/g, " ").trim();
  if (normalized.length <= maxLength) {
    return normalized;
  }
  return `${normalized.slice(0, maxLength - 1).trimEnd()}...`;
}

export function describeRunFailure(run: TurnRun | null | undefined): string | null {
  const message =
    typeof run?.error?.message === "string" ? run.error.message.trim() : "";
  if (!message) {
    return null;
  }

  if (/does not support vision input/i.test(message)) {
    const requestedLlmId = normalizeRequestedLlmId(run);
    const nextStep = requestedLlmId
      ? `Switch ${requestedLlmId} to Auto or another vision-capable model.`
      : "Switch to Auto or another vision-capable model.";
    return `${message} ${nextStep} If this prompt only contains text, the current thread may still include an earlier image attachment.`;
  }

  return message;
}

export function summarizeRunEventDetail(
  run: TurnRun,
  outputText: string | null,
): string {
  const failure = describeRunFailure(run);
  if (failure) {
    return truncate(failure, 120);
  }
  const text = outputText?.trim();
  if (text) {
    return truncate(text, 120);
  }
  return run.status;
}
