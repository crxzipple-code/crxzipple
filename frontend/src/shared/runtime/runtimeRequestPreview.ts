export interface RuntimeRequestPreviewMessage {
  role: string;
  content: unknown;
  name: string | null;
  tool_call_id: string | null;
  metadata: Record<string, unknown>;
}

export interface RuntimeRequestPreviewToolSchema {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface RuntimeLlmRequestPreview {
  run_id: string;
  llm_id: string;
  mode: string;
  messages: RuntimeRequestPreviewMessage[];
  input_items: Record<string, unknown>[];
  tool_schemas: RuntimeRequestPreviewToolSchema[];
  runtime_request_report: Record<string, unknown> | null;
  request_render_snapshot_id: string | null;
  request_render_snapshot: Record<string, unknown> | null;
  request_render_snapshot_metadata: Record<string, unknown>;
  runtime_context: Record<string, unknown>;
  provider_request_options: Record<string, unknown>;
}

export function stringifyRuntimeRequestPreviewJson(value: unknown): string {
  if (value === null || value === undefined) return "null";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function runtimeRequestPreviewContentText(content: unknown): string {
  if (typeof content === "string") return content;
  if (!Array.isArray(content)) return "";
  return content
    .map((block) => {
      if (!block || typeof block !== "object" || Array.isArray(block)) return "";
      const record = block as Record<string, unknown>;
      if (typeof record.text === "string") return record.text;
      if (typeof record.content === "string") return record.content;
      return "";
    })
    .filter(Boolean)
    .join("\n");
}
