from __future__ import annotations

import io
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from PIL import Image

from crxzipple.modules.ocr.application.capacity import OcrCapacityLimiter
from crxzipple.modules.ocr.domain import OcrPoint, OcrResult, OcrTextBlock
from crxzipple.modules.ocr.infrastructure.host_app import create_ocr_host_app


class _FakeHostEngine:
    def health(self) -> dict[str, object]:
        return {"status": "ok", "backend": "fake-ocr-host"}

    def analyze_image(self, **kwargs) -> OcrResult:  # noqa: ANN003
        return OcrResult(
            backend="fake-ocr-host",
            language=str(kwargs["language"]),
            artifact_id=kwargs.get("artifact_id"),
            variant=kwargs.get("variant"),
            image_width=640,
            image_height=360,
            blocks=(
                OcrTextBlock(
                    text="立即购买",
                    confidence=0.97,
                    polygon=(
                        OcrPoint(10, 20),
                        OcrPoint(110, 20),
                        OcrPoint(110, 60),
                        OcrPoint(10, 60),
                    ),
                ),
            ),
        )


class OcrHostHttpTestCase(unittest.TestCase):
    def test_ocr_host_health_reports_capacity(self) -> None:
        client = TestClient(
            create_ocr_host_app(engine=_FakeHostEngine(), max_concurrent_requests=2),
        )
        response = client.get("/health")
        client.close()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["capacity"]["max_concurrent_requests"], 2)
        self.assertEqual(payload["capacity"]["available_requests"], 2)

    def test_ocr_host_app_analyzes_image_path(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            image = Image.new("RGB", (200, 80), color="white")
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            path = Path(tempdir) / "sample.png"
            path.write_bytes(buffer.getvalue())

            client = TestClient(create_ocr_host_app(engine=_FakeHostEngine()))
            response = client.post(
                "/analyze",
                json={
                    "image_path": str(path),
                    "language": "ch",
                    "detect_orientation": True,
                    "artifact_id": "artifact-1",
                    "variant": "original",
                },
            )
            client.close()

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["backend"], "fake-ocr-host")
        self.assertEqual(payload["artifact_id"], "artifact-1")
        self.assertEqual(payload["blocks"][0]["text"], "立即购买")
        self.assertEqual(len(payload["blocks"][0]["polygon"]), 4)

    def test_ocr_host_app_rejects_when_capacity_is_exhausted(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            image = Image.new("RGB", (200, 80), color="white")
            buffer = io.BytesIO()
            image.save(buffer, format="PNG")
            path = Path(tempdir) / "sample.png"
            path.write_bytes(buffer.getvalue())

            limiter = OcrCapacityLimiter(1)
            client = TestClient(
                create_ocr_host_app(
                    engine=_FakeHostEngine(),
                    capacity_limiter=limiter,
                ),
            )
            with limiter.acquire():
                response = client.post(
                    "/analyze",
                    json={
                        "image_path": str(path),
                        "language": "ch",
                        "detect_orientation": True,
                    },
                )
            client.close()

        self.assertEqual(response.status_code, 503)
        self.assertIn("OCR capacity is exhausted", response.json()["detail"])
