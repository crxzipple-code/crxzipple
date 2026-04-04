export type TextContentBlock = {
  type: "text";
  text: string;
};

export type ImageContentBlock = {
  type: "image";
  data: string;
  mime_type: string;
  name?: string;
};

export type ImageRefContentBlock = {
  type: "image_ref";
  artifact_id: string;
  mime_type: string;
  name?: string;
  width?: number;
  height?: number;
  preview_url?: string;
  original_url?: string;
};

export type FileContentBlock = {
  type: "file";
  data: string;
  mime_type: string;
  name?: string;
};

export type FileRefContentBlock = {
  type: "file_ref";
  artifact_id: string;
  mime_type: string;
  name?: string;
  download_url?: string;
};

export type ContentBlock =
  | TextContentBlock
  | ImageContentBlock
  | ImageRefContentBlock
  | FileContentBlock
  | FileRefContentBlock;

export type ComposerAttachment = {
  id: string;
  name: string;
  mimeType: string;
  size: number;
  block: ImageContentBlock | ImageRefContentBlock | FileContentBlock | FileRefContentBlock;
  previewUrl: string | null;
};

export type ArtifactUploadDescriptor = {
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
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

export function normalizeContentBlocks(value: unknown): ContentBlock[] {
  if (value === null || value === undefined) {
    return [];
  }
  if (typeof value === "string") {
    return value.trim() ? [{ type: "text", text: value }] : [];
  }
  if (Array.isArray(value)) {
    return value.flatMap((item) => normalizeSingleBlock(item));
  }
  if (isRecord(value)) {
    if (typeof value.type === "string") {
      return normalizeSingleBlock(value);
    }
    const blocks = normalizeContentBlocks(value.blocks);
    if (blocks.length > 0) {
      return blocks;
    }
    const content = normalizeContentBlocks(value.content);
    if (content.length > 0) {
      return content;
    }
    if (typeof value.text === "string" && value.text.trim()) {
      return [{ type: "text", text: value.text }];
    }
    return [];
  }
  return [];
}

function normalizeSingleBlock(value: unknown): ContentBlock[] {
  if (!isRecord(value) || typeof value.type !== "string") {
    return [];
  }
  if (value.type === "text" && typeof value.text === "string" && value.text.trim()) {
    return [{ type: "text", text: value.text }];
  }
  if (
    value.type === "image" &&
    typeof value.data === "string" &&
    value.data.trim() &&
    typeof value.mime_type === "string" &&
    value.mime_type.trim()
  ) {
    return [
      {
        type: "image",
        data: value.data,
        mime_type: value.mime_type,
        name: typeof value.name === "string" && value.name.trim() ? value.name.trim() : undefined,
      },
    ];
  }
  if (
    value.type === "image_ref" &&
    typeof value.artifact_id === "string" &&
    value.artifact_id.trim() &&
    typeof value.mime_type === "string" &&
    value.mime_type.trim()
  ) {
    return [
      {
        type: "image_ref",
        artifact_id: value.artifact_id.trim(),
        mime_type: value.mime_type,
        name: typeof value.name === "string" && value.name.trim() ? value.name.trim() : undefined,
        width: typeof value.width === "number" && value.width > 0 ? value.width : undefined,
        height: typeof value.height === "number" && value.height > 0 ? value.height : undefined,
        preview_url:
          typeof value.preview_url === "string" && value.preview_url.trim()
            ? value.preview_url.trim()
            : (typeof value.previewUrl === "string" && value.previewUrl.trim()
                ? value.previewUrl.trim()
                : undefined),
        original_url:
          typeof value.original_url === "string" && value.original_url.trim()
            ? value.original_url.trim()
            : (typeof value.originalUrl === "string" && value.originalUrl.trim()
                ? value.originalUrl.trim()
                : undefined),
      },
    ];
  }
  if (
    value.type === "file" &&
    typeof value.data === "string" &&
    value.data.trim() &&
    typeof value.mime_type === "string" &&
    value.mime_type.trim()
  ) {
    return [
      {
        type: "file",
        data: value.data,
        mime_type: value.mime_type,
        name: typeof value.name === "string" && value.name.trim() ? value.name.trim() : undefined,
      },
    ];
  }
  if (
    value.type === "file_ref" &&
    typeof value.artifact_id === "string" &&
    value.artifact_id.trim() &&
    typeof value.mime_type === "string" &&
    value.mime_type.trim()
  ) {
    return [
      {
        type: "file_ref",
        artifact_id: value.artifact_id.trim(),
        mime_type: value.mime_type,
        name: typeof value.name === "string" && value.name.trim() ? value.name.trim() : undefined,
        download_url:
          typeof value.download_url === "string" && value.download_url.trim()
            ? value.download_url.trim()
            : (typeof value.downloadUrl === "string" && value.downloadUrl.trim()
                ? value.downloadUrl.trim()
                : undefined),
      },
    ];
  }
  return [];
}

export function extractTextContent(value: unknown): string | null {
  const fragments = normalizeContentBlocks(value)
    .filter((block): block is TextContentBlock => block.type === "text")
    .map((block) => block.text.trim())
    .filter(Boolean);
  if (fragments.length === 0) {
    return null;
  }
  return fragments.join("\n");
}

export function blockDataUrl(block: ImageContentBlock | FileContentBlock): string {
  return `data:${block.mime_type};base64,${block.data}`;
}

function artifactBasePath(artifactId: string): string {
  return `/artifacts/${encodeURIComponent(artifactId)}`;
}

export function blockPreviewUrl(block: ContentBlock): string {
  if (block.type === "image") {
    return blockDataUrl(block);
  }
  if (block.type === "image_ref") {
    return block.preview_url ?? `${artifactBasePath(block.artifact_id)}/preview`;
  }
  return "";
}

export function blockDownloadUrl(
  block: ContentBlock,
): string {
  if (block.type === "image" || block.type === "file") {
    return blockDataUrl(block);
  }
  if (block.type === "image_ref") {
    return block.original_url ?? `${artifactBasePath(block.artifact_id)}/original`;
  }
  if (block.type === "file_ref") {
    return block.download_url ?? `${artifactBasePath(block.artifact_id)}/download`;
  }
  return "";
}

export function summarizeContentBlocks(value: unknown): string {
  const blocks = normalizeContentBlocks(value);
  if (blocks.length === 0) {
    return "";
  }
  const parts = blocks.map((block) => {
    if (block.type === "text") {
      return block.text;
    }
    if (block.type === "image") {
      return `[image${block.name ? `:${block.name}` : ""}]`;
    }
    if (block.type === "image_ref") {
      return `[image${block.name ? `:${block.name}` : ""}]`;
    }
    if (block.type === "file_ref") {
      return `[file${block.name ? `:${block.name}` : ""}]`;
    }
    return `[file${block.name ? `:${block.name}` : ""}]`;
  });
  return parts.join("\n");
}

export function formatAttachmentSize(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes <= 0) {
    return "0 B";
  }
  if (bytes < 1024) {
    return `${bytes} B`;
  }
  if (bytes < 1024 * 1024) {
    return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`;
  }
  return `${(bytes / (1024 * 1024)).toFixed(bytes < 10 * 1024 * 1024 ? 1 : 0)} MB`;
}

function bytesToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (let index = 0; index < bytes.length; index += 1) {
    binary += String.fromCharCode(bytes[index] ?? 0);
  }
  return btoa(binary);
}

export async function fileToComposerAttachment(file: File): Promise<ComposerAttachment> {
  const arrayBuffer = await file.arrayBuffer();
  const data = bytesToBase64(new Uint8Array(arrayBuffer));
  const mimeType = file.type || "application/octet-stream";
  const isImage = mimeType.startsWith("image/");
  const block = isImage
    ? ({ type: "image", data, mime_type: mimeType, name: file.name } satisfies ImageContentBlock)
    : ({ type: "file", data, mime_type: mimeType, name: file.name } satisfies FileContentBlock);
  return {
    id: `${file.name}:${file.size}:${file.lastModified}:${mimeType}`,
    name: file.name,
    mimeType,
    size: file.size,
    block,
    previewUrl: isImage ? blockDataUrl(block) : null,
  };
}

export function artifactToComposerAttachment(
  artifact: ArtifactUploadDescriptor,
): ComposerAttachment {
  const resolvedName = artifact.name?.trim() || "attachment";
  const isImage = artifact.kind === "image" || artifact.mime_type.startsWith("image/");
  const block = isImage
    ? ({
        type: "image_ref",
        artifact_id: artifact.id,
        mime_type: artifact.mime_type,
        name: resolvedName,
        width: artifact.width ?? undefined,
        height: artifact.height ?? undefined,
        preview_url: artifact.preview_url,
        original_url: artifact.original_url,
      } satisfies ImageRefContentBlock)
    : ({
        type: "file_ref",
        artifact_id: artifact.id,
        mime_type: artifact.mime_type,
        name: resolvedName,
        download_url: artifact.download_url,
      } satisfies FileRefContentBlock);
  return {
    id: artifact.id,
    name: resolvedName,
    mimeType: artifact.mime_type,
    size: artifact.size_bytes,
    block,
    previewUrl: isImage ? artifact.preview_url : null,
  };
}
