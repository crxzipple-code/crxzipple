export function formatLocalTime(value: string | null | undefined) {
  if (!value) {
    return "-";
  }
  return new Intl.DateTimeFormat(runtimeLocale(), {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  }).format(new Date(value));
}

export function formatDuration(ms: number | null | undefined) {
  if (ms === null || ms === undefined) {
    return "-";
  }
  const locale = runtimeLocale();
  if (ms < 1000) {
    const value = Math.max(0, Math.round(ms));
    return locale === "zh-CN" ? `${value}毫秒` : `${value}ms`;
  }
  const totalSeconds = Math.round(ms / 1000);
  const minutes = Math.floor(totalSeconds / 60);
  const seconds = totalSeconds % 60;
  if (minutes === 0) {
    return locale === "zh-CN" ? `${seconds}秒` : `${seconds}s`;
  }
  return locale === "zh-CN" ? `${minutes}分 ${seconds}秒` : `${minutes}m ${seconds}s`;
}

export function formatNumber(value: number) {
  return new Intl.NumberFormat(runtimeLocale()).format(value);
}

export function formatPercent(value: number) {
  return new Intl.NumberFormat(runtimeLocale(), {
    style: "percent",
    maximumFractionDigits: 1,
  }).format(value);
}

export function formatBytes(value: number) {
  return new Intl.NumberFormat(runtimeLocale(), {
    style: "unit",
    unit: "megabyte",
    maximumFractionDigits: 1,
  }).format(value / 1024 / 1024);
}

export function looksLikeRawKey(value: string | null | undefined): boolean {
  if (!value) return false;
  const text = value.trim();
  if (!text || text === "-" || text.length > 120) return false;
  if (/^https?:\/\//i.test(text) || text.startsWith("/")) return false;
  if (/\s/.test(text)) return false;
  if (!/[._:/-]/.test(text)) return false;
  if (/^[A-Z0-9_-]+$/.test(text)) return false;
  if (/^[a-z]{2,10}_[0-9a-z]+$/i.test(text)) return false;
  return /^[a-z][a-z0-9]*(?:[._:/-][a-z0-9]+)+$/i.test(text);
}

export function formatRawKeyLabel(value: string | null | undefined): string {
  if (!value) return "";
  const text = value.trim();
  if (!looksLikeRawKey(text)) return value;
  return text
    .replace(/^events\.named\./, "")
    .split(/[._:/-]+/)
    .filter(Boolean)
    .map((part) => {
      const lower = part.toLowerCase();
      if (["api", "cli", "db", "http", "id", "io", "json", "llm", "mcp", "pid", "ttl", "ui", "url"].includes(lower)) {
        return lower.toUpperCase();
      }
      return `${part.slice(0, 1).toUpperCase()}${part.slice(1).toLowerCase()}`;
    })
    .join(" / ");
}

function runtimeLocale(): "zh-CN" | "en-US" {
  if (typeof document === "undefined") return "zh-CN";
  return document.documentElement.lang === "en-US" ? "en-US" : "zh-CN";
}
