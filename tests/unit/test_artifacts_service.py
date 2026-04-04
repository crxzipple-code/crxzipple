from __future__ import annotations

import io
import tempfile
import unittest

from PIL import Image

from crxzipple.modules.artifacts.application.services import ArtifactApplicationService
from crxzipple.modules.artifacts.domain.entities import ArtifactVariant
from crxzipple.modules.artifacts.infrastructure.filesystem_store import (
    FilesystemArtifactStore,
)


class ArtifactApplicationServiceTestCase(unittest.TestCase):
    def test_create_image_artifact_generates_preview_and_llm_variants(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            service = ArtifactApplicationService(FilesystemArtifactStore(tempdir))
            original = Image.effect_noise((2400, 1600), 100).convert("RGB")
            buffer = io.BytesIO()
            original.save(buffer, format="PNG")

            artifact = service.create_artifact(
                data=buffer.getvalue(),
                mime_type="image/png",
                name="landscape.png",
            )

            self.assertEqual(artifact.width, 2400)
            self.assertEqual(artifact.height, 1600)
            self.assertIsNotNone(artifact.preview_storage_key)
            self.assertIsNotNone(artifact.llm_storage_key)

            preview = service.resolve_variant(artifact.id, variant=ArtifactVariant.PREVIEW)
            llm = service.resolve_variant(artifact.id, variant=ArtifactVariant.LLM)

            with Image.open(preview.path) as preview_image:
                self.assertLessEqual(
                    max(preview_image.size),
                    ArtifactApplicationService.DEFAULT_PREVIEW_MAX_DIMENSION,
                )
            with Image.open(llm.path) as llm_image:
                self.assertLessEqual(
                    max(llm_image.size),
                    ArtifactApplicationService.DEFAULT_LLM_MAX_DIMENSION,
                )
            self.assertLessEqual(
                len(llm.path.read_bytes()),
                ArtifactApplicationService.DEFAULT_LLM_IMAGE_MAX_BYTES,
            )

    def test_create_non_image_artifact_keeps_original_only(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            service = ArtifactApplicationService(FilesystemArtifactStore(tempdir))

            artifact = service.create_artifact(
                data=b"%PDF-1.4\nfake",
                mime_type="application/pdf",
                name="brief.pdf",
            )

            self.assertIsNone(artifact.preview_storage_key)
            self.assertIsNone(artifact.llm_storage_key)
            resolved = service.resolve_variant(artifact.id, variant=ArtifactVariant.LLM)
            self.assertEqual(resolved.path.read_bytes(), b"%PDF-1.4\nfake")
