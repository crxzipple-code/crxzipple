export interface PromptPreviewMessage {
  role: string;
  content: unknown;
  name: string | null;
  tool_call_id: string | null;
  metadata: Record<string, unknown>;
}

export interface PromptPreviewToolSchema {
  name: string;
  description: string;
  input_schema: Record<string, unknown>;
}

export interface RunPromptInputPreview {
  run_id: string;
  llm_id: string;
  mode: string;
  messages: PromptPreviewMessage[];
  tool_schemas: PromptPreviewToolSchema[];
  prompt_report: Record<string, unknown> | null;
  context_render_snapshot_id: string | null;
  context_render: Record<string, unknown> | null;
  context_render_metadata: Record<string, unknown>;
  provider_attachments: Record<string, unknown>;
  provider_request_options: Record<string, unknown>;
}

export function stringifyPromptPreviewJson(value: unknown): string {
  if (value === null || value === undefined) return "null";
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

export function promptPreviewContentText(content: unknown): string {
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
