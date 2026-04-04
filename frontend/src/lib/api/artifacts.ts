import { buildApiUrl } from "@/lib/api/client";

export type ArtifactResponse = {
  id: string;
  kind: string;
  mime_type: string;
  name: string | null;
  size_bytes: number;
  width: number | null;
  height: number | null;
  preview_url: string;
  original_url: string;
  download_url: string;
  created_at: string;
};

export async function uploadArtifact(file: File): Promise<ArtifactResponse> {
  const query = new URLSearchParams({
    name: file.name,
    mime_type: file.type || "application/octet-stream",
  }).toString();
  const url = `${buildApiUrl("/artifacts")}?${query}`;

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": file.type || "application/octet-stream",
    },
    body: file,
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed with status ${response.status}`);
  }

  return (await response.json()) as ArtifactResponse;
}
