import { requestJson } from "@/lib/api/client";
import type { LlmProfileSummary } from "@/types";

export function listLlms() {
  return requestJson<LlmProfileSummary[]>("/llms");
}
