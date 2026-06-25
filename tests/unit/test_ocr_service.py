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
from crxzipple.modules.ocr.application import OcrApplicationService
from crxzipple.modules.ocr.domain import (
    OcrExecutionError,
    OcrResult,
    OcrTextBlock,
    OcrValidationError,
)


class _FakeOcrEngine:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def health(self) -> dict[str, object]:
        return {"status": "ok", "backend": "fake-ocr"}

    def analyze_image(self, **kwargs) -> OcrResult:  # noqa: ANN003
        self.calls.append(dict(kwargs))
        return OcrResult(
            backend="fake-ocr",
            language=str(kwargs["language"]),
            blocks=(OcrTextBlock(text="Hello", confidence=0.99),),
        )


class _StaticOcrEngine:
    def __init__(self, result: OcrResult) -> None:
        self.result = result

    def health(self) -> dict[str, object]:
        return {"status": "ok", "backend": "static-ocr"}

    def analyze_image(self, **kwargs) -> OcrResult:  # noqa: ANN003
        return self.result


class _CapabilityOcrEngine(_FakeOcrEngine):
    def health(self) -> dict[str, object]:
        return {
            "status": "ok",
            "backend": "capability-ocr",
            "capabilities": {
                "languages": ("ch", "en"),
                "features": ("layout", "orientation"),
            },
        }


class OcrApplicationServiceTestCase(unittest.TestCase):
    def test_analyze_artifact_resolves_image_variant_and_calls_engine(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            artifact_service = ArtifactApplicationService(FilesystemArtifactStore(tempdir))
            image = Image.new("RGB", (320, 120), color="white")
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            artifact = artifact_service.create_artifact(
                data=buffer.getvalue(),
                mime_type="image/png",
                name="sample.png",
            )
            engine = _FakeOcrEngine()
            service = OcrApplicationService(
                engine=engine,
                artifact_service=artifact_service,
                default_language="ch",
            )

            result = service.analyze_artifact(
                artifact_id=artifact.id,
                variant=ArtifactVariant.PREVIEW,
                language="en",
                detect_orientation=False,
            )

        self.assertEqual(result.backend, "fake-ocr")
        self.assertEqual(result.language, "en")
        self.assertEqual(result.artifact_id, artifact.id)
        self.assertEqual(result.variant, ArtifactVariant.PREVIEW.value)
        self.assertEqual(len(result.blocks), 1)
        self.assertEqual(engine.calls[0]["language"], "en")
        self.assertFalse(engine.calls[0]["detect_orientation"])
        self.assertTrue(str(engine.calls[0]["image_path"]).endswith("preview.png"))

    def test_capability_metadata_reports_engine_features_and_service_budgets(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            service = OcrApplicationService(
                engine=_CapabilityOcrEngine(),
                artifact_service=ArtifactApplicationService(FilesystemArtifactStore(tempdir)),
                default_language="ch",
                max_result_blocks=9,
                max_result_text_chars=99,
            )

            metadata = service.capability_metadata()

        self.assertEqual(metadata["backend"], "capability-ocr")
        self.assertEqual(metadata["languages"], ("ch", "en"))
        self.assertEqual(metadata["features"], ("layout", "orientation"))
        self.assertEqual(metadata["limits"]["max_result_blocks"], 9)
        self.assertEqual(metadata["limits"]["max_result_text_chars"], 99)
        self.assertEqual(
            metadata["large_output_policy"]["mode"],
            "reject_until_artifact_externalization",
        )

    def test_analyze_artifact_rejects_non_image_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            artifact_service = ArtifactApplicationService(FilesystemArtifactStore(tempdir))
            artifact = artifact_service.create_artifact(
                data=b"plain-text",
                mime_type="text/plain",
                name="sample.txt",
            )
            service = OcrApplicationService(
                engine=_FakeOcrEngine(),
                artifact_service=artifact_service,
            )

            with self.assertRaises(OcrValidationError):
                service.analyze_artifact(artifact_id=artifact.id)

    def test_analyze_artifact_rejects_results_that_exceed_block_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            artifact_service = ArtifactApplicationService(FilesystemArtifactStore(tempdir))
            artifact = self._create_image_artifact(artifact_service)
            service = OcrApplicationService(
                engine=_StaticOcrEngine(
                    OcrResult(
                        backend="static-ocr",
                        language="ch",
                        blocks=(
                            OcrTextBlock(text="one"),
                            OcrTextBlock(text="two"),
                        ),
                    ),
                ),
                artifact_service=artifact_service,
                max_result_blocks=1,
            )

            with self.assertRaisesRegex(OcrExecutionError, "block budget"):
                service.analyze_artifact(artifact_id=artifact.id)

    def test_analyze_artifact_rejects_results_that_exceed_text_budget(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            artifact_service = ArtifactApplicationService(FilesystemArtifactStore(tempdir))
            artifact = self._create_image_artifact(artifact_service)
            service = OcrApplicationService(
                engine=_StaticOcrEngine(
                    OcrResult(
                        backend="static-ocr",
                        language="ch",
                        blocks=(OcrTextBlock(text="abcdef"),),
                    ),
                ),
                artifact_service=artifact_service,
                max_result_text_chars=5,
            )

            with self.assertRaisesRegex(OcrExecutionError, "text budget"):
                service.analyze_artifact(artifact_id=artifact.id)

    def _create_image_artifact(self, artifact_service: ArtifactApplicationService):
        image = Image.new("RGB", (32, 32), color="white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        return artifact_service.create_artifact(
            data=buffer.getvalue(),
            mime_type="image/png",
            name="sample.png",
        )
