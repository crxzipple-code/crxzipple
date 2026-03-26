import { requestJson } from "@/lib/api/client";

export function getHealth() {
  return requestJson<{ status: string }>("/health");
}
