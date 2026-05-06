import { formatLocalTime } from "@/shared/i18n/formatters";

export type LegacyTableRow = Record<string, string | number | null>;

export interface LegacyTableModel {
  columns: Array<{ key: string; label: string }>;
  rows: LegacyTableRow[];
}

export type MetricTone = "success" | "warning" | "danger" | "info" | "neutral";
export type MetricTuple = readonly [string, string, string, MetricTone];

export function asArray<T = Record<string, unknown>>(value: unknown): T[] {
  if (Array.isArray(value)) return value as T[];
  if (typeof value === "string" && value.trim()) {
    const trimmed = value.trim();
    if (trimmed.startsWith("[") && trimmed.endsWith("]")) {
      try {
        const parsed = JSON.parse(trimmed);
        return Array.isArray(parsed) ? parsed as T[] : [];
      } catch {
        return [];
      }
    }
    return trimmed.split(",").map((item) => item.trim()).filter(Boolean) as T[];
  }
  return [];
}

export function asRecord(value: unknown): Record<string, unknown> {
  if (value && typeof value === "object" && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  if (typeof value === "string" && value.trim().startsWith("{")) {
    try {
      const parsed = JSON.parse(value);
      return parsed && typeof parsed === "object" && !Array.isArray(parsed)
        ? parsed as Record<string, unknown>
        : {};
    } catch {
      return {};
    }
  }
  return {};
}

export function asText(value: unknown, fallback = "-"): string {
  if (value === null || value === undefined || value === "") return fallback;
  if (Array.isArray(value)) {
    return value.length ? value.map((item) => asText(item)).join(", ") : fallback;
  }
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

export function asNumber(value: unknown, fallback = 0): number {
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (typeof value === "string" && value.trim()) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }
  return fallback;
}

export function compactId(value: unknown, size = 18): string {
  const text = asText(value);
  if (text === "-" || text.length <= size) return text;
  const head = Math.max(6, Math.floor(size * 0.58));
  const tail = Math.max(4, size - head - 1);
  return `${text.slice(0, head)}...${text.slice(-tail)}`;
}

export function formatTimestamp(value: unknown): string {
  const text = asText(value);
  if (text === "-") return text;
  return /^\d{4}-\d{2}-\d{2}T/.test(text) ? formatLocalTime(text) : text;
}

export function latestTimestamp(values: unknown[]): string {
  const latest = values
    .map((value) => new Date(asText(value)).getTime())
    .filter(Number.isFinite)
    .sort((left, right) => right - left)[0];
  return latest ? formatLocalTime(new Date(latest).toISOString()) : "-";
}

export function countBy<T>(items: T[], keyOf: (item: T) => string): Record<string, number> {
  return items.reduce<Record<string, number>>((counts, item) => {
    const key = keyOf(item) || "unknown";
    counts[key] = (counts[key] ?? 0) + 1;
    return counts;
  }, {});
}

export function percent(part: number, total: number): string {
  if (!total) return "0%";
  return `${Math.round((part / total) * 1000) / 10}%`;
}

export function tableWithRows(
  fallback: LegacyTableModel,
  rows: LegacyTableRow[],
  preferEmpty = false,
): LegacyTableModel {
  if (!rows.length && !preferEmpty) return fallback;
  return {
    columns: fallback.columns,
    rows,
  };
}

export function statusLabel(value: unknown): string {
  const text = asText(value);
  if (text === "-") return text;
  return titleCaseDynamicValue(text);
}

export function staleStatus(lastHeartbeat: unknown, staleAfterMs = 5 * 60 * 1000): string {
  const time = new Date(asText(lastHeartbeat)).getTime();
  if (!Number.isFinite(time)) return "Unknown";
  return Date.now() - time > staleAfterMs ? "Stale" : "Online";
}

export function dynamicValueKeyPart(value: unknown): string {
  return asText(value, "")
    .trim()
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/[.\s-]+/g, "_")
    .replace(/[^a-zA-Z0-9_]+/g, "_")
    .replace(/_+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
}

export function titleCaseDynamicValue(value: unknown, fallback = "-"): string {
  const text = asText(value, fallback);
  if (text === fallback) return fallback;
  return text
    .trim()
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[._-]+/g, " ")
    .replace(/\s+/g, " ")
    .split(" ")
    .filter(Boolean)
    .map((part) => {
      const lower = part.toLowerCase();
      if (["api", "http", "io", "id", "llm", "mcp", "pid", "url"].includes(lower)) {
        return lower.toUpperCase();
      }
      return `${part.slice(0, 1).toUpperCase()}${part.slice(1)}`;
    })
    .join(" ");
}
