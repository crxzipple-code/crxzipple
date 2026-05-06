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

function runtimeLocale(): "zh-CN" | "en-US" {
  if (typeof document === "undefined") return "zh-CN";
  return document.documentElement.lang === "en-US" ? "en-US" : "zh-CN";
}
