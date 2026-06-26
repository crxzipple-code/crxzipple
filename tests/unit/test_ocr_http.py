from __future__ import annotations

from tests.unit.http_test_support import AppKey, HttpModuleTestCase, patch

from crxzipple.modules.ocr.domain import (
    OcrCapacityExceededError,
    OcrResult,
    OcrTextBlock,
)


class OcrHttpTestCase(HttpModuleTestCase):
    def test_ocr_health_endpoint_returns_service_health(self) -> None:
        container = self.client.app.state.container
        with patch.object(
            type(container.require(AppKey.OCR_SERVICE)),
            "health",
            autospec=True,
            return_value={"status": "ok", "backend": "fake-ocr"},
        ):
            response = self.client.get("/ocr/health")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["backend"], "fake-ocr")

    def test_ocr_analyze_artifact_endpoint_serializes_result(self) -> None:
        captured: list[dict[str, object]] = []
        container = self.client.app.state.container

        def _analyze(*, artifact_id, variant, language, detect_orientation):  # noqa: ANN001, ANN202
            captured.append(
                {
                    "artifact_id": artifact_id,
                    "variant": variant,
                    "language": language,
                    "detect_orientation": detect_orientation,
                }
            )
            return OcrResult(
                backend="fake-ocr",
                language=language or "ch",
                artifact_id=artifact_id,
                variant=variant.value,
                image_width=800,
                image_height=600,
                blocks=(OcrTextBlock(text="欢迎使用", confidence=0.98),),
                layout_blocks=(OcrTextBlock(text="欢迎使用", label="doc_title", confidence=0.98),),
                overall_ocr_blocks=(OcrTextBlock(text="欢迎使用", label="text", confidence=0.98),),
            )

        with patch.object(
            type(container.require(AppKey.OCR_SERVICE)),
            "analyze_artifact",
            autospec=True,
            side_effect=lambda _self, **kwargs: _analyze(**kwargs),
        ):
            response = self.client.post(
                "/ocr/analyze-artifact",
                json={
                    "artifact_id": "artifact-1",
                    "variant": "preview",
                    "language": "ch",
                    "detect_orientation": False,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["backend"], "fake-ocr")
        self.assertEqual(payload["artifact_id"], "artifact-1")
        self.assertEqual(payload["variant"], "preview")
        self.assertEqual(payload["block_count"], 1)
        self.assertEqual(payload["blocks"][0]["text"], "欢迎使用")
        self.assertEqual(payload["layout_block_count"], 1)
        self.assertEqual(payload["layout_blocks"][0]["label"], "doc_title")
        self.assertEqual(payload["overall_ocr_block_count"], 1)
        self.assertEqual(payload["overall_ocr_blocks"][0]["label"], "text")
        self.assertEqual(captured[0]["artifact_id"], "artifact-1")
        self.assertEqual(captured[0]["variant"].value, "preview")

    def test_ocr_analyze_artifact_endpoint_maps_capacity_to_503(self) -> None:
        container = self.client.app.state.container
        with patch.object(
            type(container.require(AppKey.OCR_SERVICE)),
            "analyze_artifact",
            autospec=True,
            side_effect=OcrCapacityExceededError("OCR capacity is exhausted."),
        ):
            response = self.client.post(
                "/ocr/analyze-artifact",
                json={"artifact_id": "artifact-1"},
            )

        self.assertEqual(response.status_code, 503)
        self.assertIn("OCR capacity is exhausted", response.json()["detail"])
