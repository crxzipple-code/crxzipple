import { afterEach, describe, expect, it, vi } from "vitest";

async function loadClientModule() {
  return await import("@/lib/api/client");
}

describe("api/client", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("returns the original path when no api base is configured", async () => {
    vi.stubEnv("VITE_API_BASE", "");
    const { buildApiUrl } = await loadClientModule();

    expect(buildApiUrl("/turns")).toBe("/turns");
  });

  it("prefixes relative api bases and normalizes trailing slashes", async () => {
    vi.stubEnv("VITE_API_BASE", "/backend/");
    const { buildApiUrl } = await loadClientModule();

    expect(buildApiUrl("/turns")).toBe("/backend/turns");
  });

  it("builds absolute api urls when the base is a full origin", async () => {
    vi.stubEnv("VITE_API_BASE", "https://api.example.com");
    const { buildApiUrl } = await loadClientModule();

    expect(buildApiUrl("/turns")).toBe("https://api.example.com/turns");
  });

  it("requests json with the default content-type header", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ ok: true }),
      text: async () => "",
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("VITE_API_BASE", "");

    const { requestJson } = await loadClientModule();
    const payload = await requestJson<{ ok: boolean }>("/turns", {
      method: "POST",
      headers: {
        Authorization: "Bearer token",
      },
      body: JSON.stringify({ hello: "world" }),
    });

    expect(payload).toEqual({ ok: true });
    expect(fetchMock).toHaveBeenCalledWith("/turns", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer token",
      },
      body: JSON.stringify({ hello: "world" }),
    });
  });

  it("throws the response body when the request fails", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 403,
      text: async () => "forbidden",
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("VITE_API_BASE", "");

    const { requestJson } = await loadClientModule();

    await expect(requestJson("/turns")).rejects.toThrow("forbidden");
  });

  it("falls back to the status code when the response body is empty", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: false,
      status: 503,
      text: async () => "",
      json: async () => ({}),
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("VITE_API_BASE", "");

    const { requestJson } = await loadClientModule();

    await expect(requestJson("/turns")).rejects.toThrow(
      "Request failed with status 503",
    );
  });
});
