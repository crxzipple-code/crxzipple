import { describe, expect, it } from "vitest";

import {
  artifactToComposerAttachment,
  blockDownloadUrl,
  blockPreviewUrl,
  extractTextContent,
  fileToComposerAttachment,
  formatAttachmentSize,
  normalizeContentBlocks,
  summarizeContentBlocks,
} from "@/lib/contentBlocks";

describe("contentBlocks helpers", () => {
  it("normalizes nested blocks payloads", () => {
    expect(
      normalizeContentBlocks({
        blocks: [
          { type: "text", text: "hello" },
          { type: "image", data: "aGVsbG8=", mime_type: "image/png" },
        ],
      }),
    ).toEqual([
      { type: "text", text: "hello" },
      { type: "image", data: "aGVsbG8=", mime_type: "image/png" },
    ]);
  });

  it("normalizes tool-style content payloads", () => {
    expect(
      normalizeContentBlocks({
        content: [
          { type: "text", text: "Browser wait completed." },
          {
            type: "image_ref",
            artifact_id: "img_123",
            mime_type: "image/png",
            name: "frog.png",
          },
        ],
      }),
    ).toEqual([
      { type: "text", text: "Browser wait completed." },
      {
        type: "image_ref",
        artifact_id: "img_123",
        mime_type: "image/png",
        name: "frog.png",
      },
    ]);
  });

  it("extracts text content and summarizes attachments", () => {
    const payload = {
      blocks: [
        { type: "text", text: "hello" },
        { type: "file", data: "aGVsbG8=", mime_type: "application/pdf", name: "brief.pdf" },
      ],
    };
    expect(extractTextContent(payload)).toBe("hello");
    expect(summarizeContentBlocks(payload)).toBe("hello\n[file:brief.pdf]");
  });

  it("normalizes referenced attachment blocks and derives URLs", () => {
    const payload = {
      blocks: [
        {
          type: "image_ref",
          artifact_id: "img_123",
          mime_type: "image/png",
          name: "duck.png",
        },
        {
          type: "file_ref",
          artifact_id: "file_123",
          mime_type: "application/pdf",
          name: "brief.pdf",
        },
      ],
    };
    const blocks = normalizeContentBlocks(payload);
    expect(blocks).toEqual([
      {
        type: "image_ref",
        artifact_id: "img_123",
        mime_type: "image/png",
        name: "duck.png",
      },
      {
        type: "file_ref",
        artifact_id: "file_123",
        mime_type: "application/pdf",
        name: "brief.pdf",
      },
    ]);
    expect(blockPreviewUrl(blocks[0] as never)).toBe("/artifacts/img_123/preview");
    expect(blockDownloadUrl(blocks[0] as never)).toBe("/artifacts/img_123/original");
    expect(blockDownloadUrl(blocks[1] as never)).toBe("/artifacts/file_123/download");
    expect(summarizeContentBlocks(payload)).toBe("[image:duck.png]\n[file:brief.pdf]");
  });

  it("formats attachment sizes for display", () => {
    expect(formatAttachmentSize(0)).toBe("0 B");
    expect(formatAttachmentSize(900)).toBe("900 B");
    expect(formatAttachmentSize(1536)).toBe("1.5 KB");
    expect(formatAttachmentSize(1024 * 1024 * 3)).toBe("3.0 MB");
  });

  it("converts files into composer attachments", async () => {
    const file = new File(["hello"], "note.txt", { type: "text/plain" });
    const attachment = await fileToComposerAttachment(file);

    expect(attachment.name).toBe("note.txt");
    expect(attachment.mimeType).toBe("text/plain");
    expect(attachment.block).toEqual({
      type: "file",
      data: "aGVsbG8=",
      mime_type: "text/plain",
      name: "note.txt",
    });
    expect(attachment.previewUrl).toBeNull();
  });

  it("converts artifact metadata into composer attachments", () => {
    const attachment = artifactToComposerAttachment({
      id: "img_123",
      kind: "image",
      mime_type: "image/png",
      name: "duck.png",
      size_bytes: 2048,
      width: 100,
      height: 80,
      preview_url: "/artifacts/img_123/preview",
      original_url: "/artifacts/img_123/original",
      download_url: "/artifacts/img_123/download",
    });

    expect(attachment).toEqual({
      id: "img_123",
      name: "duck.png",
      mimeType: "image/png",
      size: 2048,
      previewUrl: "/artifacts/img_123/preview",
      block: {
        type: "image_ref",
        artifact_id: "img_123",
        mime_type: "image/png",
        name: "duck.png",
        width: 100,
        height: 80,
        preview_url: "/artifacts/img_123/preview",
        original_url: "/artifacts/img_123/original",
      },
    });
  });
});
