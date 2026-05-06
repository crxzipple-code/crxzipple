import { buildApiUrl } from "./client";

export interface EventConsoleRecord {
  cursor: string;
  event_id: string;
  event_name: string;
  topic: string;
  kind: string;
  source_event_name?: string | null;
  source_event_owner?: string | null;
  source_topic?: string | null;
  source_payload?: Record<string, unknown>;
  created_at?: string;
}

export interface EventStreamSnapshot {
  records?: EventConsoleRecord[];
}

export interface EventStreamOptions {
  topicPrefix: string;
  snapshotLimit?: number;
  timeoutSeconds?: number;
}

export interface EventStreamHandlers {
  event?: (record: EventConsoleRecord) => void;
  snapshot?: (snapshot: EventStreamSnapshot) => void;
  error?: (event: Event) => void;
}

export function openEventStream(
  options: EventStreamOptions,
  handlers: EventStreamHandlers,
): () => void {
  const query = new URLSearchParams({
    topic_prefix: options.topicPrefix,
    snapshot_limit: String(options.snapshotLimit ?? 0),
    timeout_seconds: String(options.timeoutSeconds ?? 300),
  });
  const source = new EventSource(buildApiUrl(`/events/stream?${query.toString()}`));

  source.addEventListener("event", (event) => {
    const record = parseEventData<EventConsoleRecord>(event);
    if (record) handlers.event?.(record);
  });
  source.addEventListener("snapshot", (event) => {
    const snapshot = parseEventData<EventStreamSnapshot>(event);
    if (snapshot) handlers.snapshot?.(snapshot);
  });
  source.addEventListener("error", (event) => {
    handlers.error?.(event);
  });

  return () => source.close();
}

function parseEventData<T>(event: MessageEvent): T | null {
  try {
    return JSON.parse(event.data) as T;
  } catch {
    return null;
  }
}
