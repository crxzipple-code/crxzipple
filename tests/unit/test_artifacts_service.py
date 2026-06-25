from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import io
import tempfile
import unittest

from PIL import Image

from crxzipple.modules.artifacts.application.services import ArtifactApplicationService
from crxzipple.modules.artifacts.domain.entities import ArtifactVariant
from crxzipple.modules.artifacts.domain.exceptions import (
    ArtifactNotFoundError,
    ArtifactValidationError,
)
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

    def test_resolve_variant_reports_missing_underlying_file(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            service = ArtifactApplicationService(FilesystemArtifactStore(tempdir))
            artifact = service.create_artifact(
                data=b"hello",
                mime_type="text/plain",
                name="note.txt",
            )
            resolved = service.resolve_variant(artifact.id)
            resolved.path.unlink()

            with self.assertRaises(ArtifactNotFoundError):
                service.resolve_variant(artifact.id)

    def test_list_artifacts_returns_newest_first(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = FilesystemArtifactStore(tempdir)
            service = ArtifactApplicationService(store)
            older = service.create_artifact(
                data=b"older",
                mime_type="text/plain",
                name="older.txt",
            )
            newer = service.create_artifact(
                data=b"newer",
                mime_type="text/plain",
                name="newer.txt",
            )
            store.save_metadata(
                replace(
                    older,
                    created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                ),
            )
            store.save_metadata(
                replace(
                    newer,
                    created_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
                ),
            )

            artifacts = service.list_artifacts()

            self.assertEqual([artifact.id for artifact in artifacts], [newer.id, older.id])

    def test_storage_usage_counts_present_bytes_and_missing_files(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            service = ArtifactApplicationService(FilesystemArtifactStore(tempdir))
            artifact = service.create_artifact(
                data=b"hello",
                mime_type="text/plain",
                name="note.txt",
            )
            resolved = service.resolve_variant(artifact.id)
            resolved.path.unlink()

            usage = service.storage_usage()

            self.assertEqual(usage.artifact_count, 1)
            self.assertEqual(usage.total_bytes, 0)
            self.assertEqual(usage.missing_file_count, 1)

    def test_cleanup_artifacts_removes_entries_older_than_cutoff(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = FilesystemArtifactStore(tempdir)
            service = ArtifactApplicationService(store)
            old = service.create_artifact(
                data=b"old",
                mime_type="text/plain",
                name="old.txt",
            )
            current = service.create_artifact(
                data=b"current",
                mime_type="text/plain",
                name="current.txt",
            )
            cutoff = datetime.now(timezone.utc) - timedelta(days=1)
            store.save_metadata(replace(old, created_at=cutoff - timedelta(seconds=1)))
            store.save_metadata(replace(current, created_at=cutoff + timedelta(seconds=1)))

            result = service.cleanup_artifacts(created_before=cutoff)

            self.assertEqual(result.pruned_artifact_ids, (old.id,))
            self.assertEqual(result.artifact_count_before, 2)
            self.assertEqual(result.artifact_count_after, 1)
            self.assertEqual(service.get_artifact(current.id).id, current.id)
            with self.assertRaises(ArtifactNotFoundError):
                service.get_artifact(old.id)

    def test_cleanup_artifacts_prunes_oldest_until_within_quota(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = FilesystemArtifactStore(tempdir)
            service = ArtifactApplicationService(store)
            first = service.create_artifact(
                data=b"11111",
                mime_type="text/plain",
                name="first.txt",
            )
            second = service.create_artifact(
                data=b"22222",
                mime_type="text/plain",
                name="second.txt",
            )
            third = service.create_artifact(
                data=b"33333",
                mime_type="text/plain",
                name="third.txt",
            )
            base = datetime(2026, 1, 1, tzinfo=timezone.utc)
            store.save_metadata(replace(first, created_at=base))
            store.save_metadata(replace(second, created_at=base + timedelta(seconds=1)))
            store.save_metadata(replace(third, created_at=base + timedelta(seconds=2)))

            result = service.cleanup_artifacts(max_total_bytes=5)

            self.assertEqual(result.pruned_artifact_ids, (first.id, second.id))
            self.assertEqual(result.total_bytes_before, 15)
            self.assertEqual(result.total_bytes_after, 5)
            self.assertEqual([artifact.id for artifact in service.list_artifacts()], [third.id])

    def test_cleanup_artifacts_rejects_negative_quota(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            service = ArtifactApplicationService(FilesystemArtifactStore(tempdir))

            with self.assertRaises(ArtifactValidationError):
                service.cleanup_artifacts(max_total_bytes=-1)

    def test_filesystem_store_rejects_paths_outside_artifact_root(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            store = FilesystemArtifactStore(tempdir)

            with self.assertRaises(ArtifactValidationError):
                store.save_bytes(storage_key="../escape.txt", data=b"nope")

            with self.assertRaises(ArtifactNotFoundError):
                store.load_metadata("../escape")
