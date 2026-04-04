from __future__ import annotations

import unittest

from crxzipple.shared.content_blocks import (
    content_blocks_from_payload,
    describe_content_for_text_fallback,
    normalize_content_blocks,
)


class ContentBlocksTestCase(unittest.TestCase):
    def test_normalizes_referenced_blocks(self) -> None:
        payload = {
            "blocks": [
                {
                    "type": "image_ref",
                    "artifact_id": "img_123",
                    "mime_type": "image/png",
                    "name": "duck.png",
                },
                {
                    "type": "file_ref",
                    "artifactId": "file_123",
                    "mimeType": "application/pdf",
                    "name": "brief.pdf",
                },
            ],
        }

        self.assertEqual(
            normalize_content_blocks(payload),
            [
                {
                    "type": "image_ref",
                    "artifact_id": "img_123",
                    "mime_type": "image/png",
                    "name": "duck.png",
                },
                {
                    "type": "file_ref",
                    "artifact_id": "file_123",
                    "mime_type": "application/pdf",
                    "name": "brief.pdf",
                },
            ],
        )
        self.assertEqual(
            content_blocks_from_payload(payload),
            normalize_content_blocks(payload),
        )

    def test_normalizes_image_blocks_with_optional_name(self) -> None:
        self.assertEqual(
            normalize_content_blocks(
                {
                    "blocks": [
                        {
                            "type": "image",
                            "data": "aGVsbG8=",
                            "mime_type": "image/png",
                            "name": "duck.png",
                        },
                    ],
                },
            ),
            [
                {
                    "type": "image",
                    "data": "aGVsbG8=",
                    "mime_type": "image/png",
                    "name": "duck.png",
                },
            ],
        )

    def test_text_fallback_describes_referenced_attachments(self) -> None:
        payload = {
            "blocks": [
                {"type": "text", "text": "hello"},
                {
                    "type": "image_ref",
                    "artifact_id": "img_123",
                    "mime_type": "image/png",
                    "name": "duck.png",
                },
                {
                    "type": "file_ref",
                    "artifact_id": "file_123",
                    "mime_type": "application/pdf",
                    "name": "brief.pdf",
                },
            ],
        }

        self.assertEqual(
            describe_content_for_text_fallback(payload),
            "hello\n[image:duck.png]\n[file:brief.pdf]",
        )
