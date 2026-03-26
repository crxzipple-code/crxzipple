const API_BASE = (import.meta.env.VITE_API_BASE ?? "").replace(/\/$/, "");

export function buildApiUrl(path: string): string {
  if (!API_BASE) {
    return path;
  }
  if (/^https?:\/\//.test(API_BASE)) {
    return new URL(path, `${API_BASE}/`).toString();
  }
  return `${API_BASE}${path}`;
}

export async function requestJson<T>(path: string, init?: RequestInit): Promise<T> {
  const headers = {
    "Content-Type": "application/json",
    ...(init?.headers ?? {}),
  };

  const response = await fetch(buildApiUrl(path), {
    ...init,
    headers,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as T;
}
