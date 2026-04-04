import { afterEach, describe, expect, it, vi } from "vitest";

async function loadArtifactsModule() {
  return await import("@/lib/api/artifacts");
}

describe("api/artifacts", () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.unstubAllGlobals();
    vi.resetModules();
  });

  it("uploads artifacts as raw request bodies", async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        id: "img_123",
        kind: "image",
        mime_type: "image/png",
        name: "duck.png",
        size_bytes: 5,
        width: 10,
        height: 10,
        preview_url: "/artifacts/img_123/preview",
        original_url: "/artifacts/img_123/original",
        download_url: "/artifacts/img_123/download",
        created_at: "2026-04-03T00:00:00Z",
      }),
      text: async () => "",
    });
    vi.stubGlobal("fetch", fetchMock);
    vi.stubEnv("VITE_API_BASE", "");

    const file = new File(["hello"], "duck.png", { type: "image/png" });
    const { uploadArtifact } = await loadArtifactsModule();
    const result = await uploadArtifact(file);

    expect(result.id).toBe("img_123");
    expect(fetchMock).toHaveBeenCalledWith(
      expect.stringContaining("/artifacts?name=duck.png&mime_type=image%2Fpng"),
      {
        method: "POST",
        headers: {
          "Content-Type": "image/png",
        },
        body: file,
      },
    );
  });
});
