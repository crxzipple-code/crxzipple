from __future__ import annotations

import base64
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image

from crxzipple.modules.ocr.domain import OcrExecutionError, OcrValidationError
from crxzipple.modules.ocr.infrastructure.ppstructure_client import PPStructureV3Client


class _FakeResponse:
    def __init__(self, payload: object, *, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> object:
        return self._payload

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"status={self.status_code}")


class PPStructureV3ClientTestCase(unittest.TestCase):
    def _create_image(self) -> Path:
        tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(tempdir.cleanup)
        path = Path(tempdir.name) / "sample.png"
        image = Image.new("RGB", (200, 100), color="white")
        buffer = io.BytesIO()
        image.save(buffer, format="PNG")
        path.write_bytes(buffer.getvalue())
        return path

    def test_analyze_image_uses_base64_payload_and_parses_layout_blocks(self) -> None:
        image_path = self._create_image()
        captured: list[dict[str, object]] = []
        client = PPStructureV3Client(base_url="http://ocr.example.com", timeout_seconds=12)

        payload = {
            "logId": "log-1",
            "result": {
                "layoutParsingResults": [
                    {
                        "prunedResult": {
                            "parsing_res_list": [
                                {
                                    "block_label": "doc_title",
                                    "block_content": "欢迎使用",
                                    "block_bbox": [10, 20, 110, 70],
                                }
                            ]
                        },
                        "markdown": {"text": "# 欢迎使用", "isStart": True, "isEnd": True},
                    }
                ],
                "dataInfo": {"width": 200, "height": 100, "type": "image"},
            },
            "errorCode": 0,
            "errorMsg": "Success",
        }

        def _fake_request(method: str, url: str, **kwargs):  # noqa: ANN001, ANN202
            captured.append(
                {
                    "method": method,
                    "url": url,
                    "json": kwargs.get("json"),
                    "timeout": kwargs.get("timeout"),
                }
            )
            return _FakeResponse(payload)

        with patch(
            "crxzipple.modules.ocr.infrastructure.ppstructure_client.request_url",
            side_effect=_fake_request,
        ):
            result = client.analyze_image(
                image_path=image_path,
                language="ch",
                detect_orientation=True,
                artifact_id="artifact-1",
                variant="preview",
            )

        self.assertEqual(result.backend, "ppstructurev3")
        self.assertEqual(result.language, "ch")
        self.assertEqual(result.artifact_id, "artifact-1")
        self.assertEqual(result.variant, "preview")
        self.assertEqual(result.image_width, 200)
        self.assertEqual(result.image_height, 100)
        self.assertEqual(len(result.blocks), 1)
        self.assertEqual(result.blocks[0].text, "欢迎使用")
        self.assertEqual(result.blocks[0].label, "doc_title")
        self.assertEqual(len(result.blocks[0].polygon), 4)
        self.assertEqual(len(result.layout_blocks), 1)
        self.assertEqual(result.layout_blocks[0].label, "doc_title")
        self.assertEqual(len(result.overall_ocr_blocks), 0)
        self.assertEqual(result.metadata["provider"], "ppstructurev3")
        self.assertEqual(result.metadata["block_source"], "layout")
        self.assertEqual(result.metadata["layout_block_count"], 1)
        self.assertEqual(result.metadata["overall_ocr_block_count"], 0)
        request_payload = captured[0]["json"]
        self.assertIsInstance(request_payload, dict)
        assert isinstance(request_payload, dict)
        self.assertEqual(request_payload["fileType"], 1)
        self.assertEqual(request_payload["logId"], "artifact-1")
        self.assertIs(request_payload["useDocUnwarping"], False)
        self.assertNotIn("data:image", str(request_payload["file"]))
        self.assertEqual(
            base64.b64decode(str(request_payload["file"])),
            image_path.read_bytes(),
        )

    def test_analyze_image_falls_back_to_overall_ocr_blocks(self) -> None:
        image_path = self._create_image()
        client = PPStructureV3Client(base_url="http://ocr.example.com")
        payload = {
            "logId": "log-1",
            "result": {
                "layoutParsingResults": [
                    {
                        "prunedResult": {
                            "parsing_res_list": [],
                            "overall_ocr_res": {
                                "rec_texts": ["Hello OCR"],
                                "rec_boxes": [[1, 2, 101, 42]],
                                "rec_scores": [0.98],
                            },
                        },
                        "markdown": {"text": "Hello OCR", "isStart": True, "isEnd": True},
                    }
                ],
                "dataInfo": {"width": 200, "height": 100, "type": "image"},
            },
            "errorCode": 0,
            "errorMsg": "Success",
        }

        with patch(
            "crxzipple.modules.ocr.infrastructure.ppstructure_client.request_url",
            return_value=_FakeResponse(payload),
        ):
            result = client.analyze_image(
                image_path=image_path,
                language="en",
                detect_orientation=False,
            )

        self.assertEqual(len(result.blocks), 1)
        self.assertEqual(result.blocks[0].text, "Hello OCR")
        self.assertEqual(result.blocks[0].label, "text")
        self.assertEqual(result.blocks[0].confidence, 0.98)
        self.assertEqual(len(result.layout_blocks), 0)
        self.assertEqual(len(result.overall_ocr_blocks), 1)
        self.assertEqual(result.metadata["block_source"], "overall_ocr")

    def test_analyze_image_prefers_overall_ocr_when_layout_is_single_image_block(self) -> None:
        image_path = self._create_image()
        client = PPStructureV3Client(base_url="http://ocr.example.com")
        payload = {
            "logId": "log-1",
            "result": {
                "layoutParsingResults": [
                    {
                        "prunedResult": {
                            "parsing_res_list": [
                                {
                                    "block_label": "image",
                                    "block_content": "泰海通证\n\n泰海通证",
                                    "block_bbox": [0, 0, 200, 100],
                                }
                            ],
                            "overall_ocr_res": {
                                "rec_texts": ["泰海通证", "小红书"],
                                "rec_boxes": [[10, 20, 80, 50], [110, 20, 180, 50]],
                                "rec_scores": [0.99, 0.98],
                            },
                        },
                        "markdown": {
                            "text": '<div><img alt="Image" /></div>',
                            "isStart": True,
                            "isEnd": True,
                        },
                    }
                ],
                "dataInfo": {"width": 200, "height": 100, "type": "image"},
            },
            "errorCode": 0,
            "errorMsg": "Success",
        }

        with patch(
            "crxzipple.modules.ocr.infrastructure.ppstructure_client.request_url",
            return_value=_FakeResponse(payload),
        ):
            result = client.analyze_image(
                image_path=image_path,
                language="ch",
                detect_orientation=False,
            )

        self.assertEqual(result.metadata["block_source"], "overall_ocr")
        self.assertEqual(result.metadata["layout_block_count"], 1)
        self.assertEqual(result.metadata["overall_ocr_block_count"], 2)
        self.assertEqual([block.text for block in result.blocks], ["泰海通证", "小红书"])
        self.assertEqual([block.label for block in result.layout_blocks], ["image"])
        self.assertEqual([block.label for block in result.overall_ocr_blocks], ["text", "text"])

    def test_analyze_image_rotates_ocr_boxes_back_to_original_when_preprocessor_angle_is_180(self) -> None:
        image_path = self._create_image()
        client = PPStructureV3Client(base_url="http://ocr.example.com")
        payload = {
            "logId": "log-1",
            "result": {
                "layoutParsingResults": [
                    {
                        "prunedResult": {
                            "width": 200,
                            "height": 100,
                            "doc_preprocessor_res": {"angle": 180},
                            "parsing_res_list": [],
                            "overall_ocr_res": {
                                "rec_texts": ["Hello OCR"],
                                "rec_boxes": [[10, 20, 50, 40]],
                                "rec_scores": [0.98],
                            },
                        },
                    }
                ],
            },
            "errorCode": 0,
            "errorMsg": "Success",
        }

        with patch(
            "crxzipple.modules.ocr.infrastructure.ppstructure_client.request_url",
            return_value=_FakeResponse(payload),
        ):
            result = client.analyze_image(
                image_path=image_path,
                language="en",
                detect_orientation=True,
            )

        self.assertEqual(result.metadata["preprocessor_angle"], 180)
        self.assertEqual(len(result.blocks), 1)
        polygon = result.blocks[0].polygon
        self.assertEqual(len(polygon), 4)
        self.assertEqual(result.overall_ocr_blocks[0].label, "text")
        self.assertEqual((polygon[0].x, polygon[0].y), (150.0, 60.0))
        self.assertEqual((polygon[2].x, polygon[2].y), (190.0, 80.0))

    def test_analyze_image_raises_validation_error_for_4xx(self) -> None:
        image_path = self._create_image()
        client = PPStructureV3Client(base_url="http://ocr.example.com")
        with patch(
            "crxzipple.modules.ocr.infrastructure.ppstructure_client.request_url",
            return_value=_FakeResponse(
                {"errorMsg": "Invalid input file"},
                status_code=422,
            ),
        ):
            with self.assertRaisesRegex(OcrValidationError, "Invalid input file"):
                client.analyze_image(
                    image_path=image_path,
                    language="ch",
                    detect_orientation=True,
                )

    def test_health_raises_execution_error_for_invalid_payload(self) -> None:
        client = PPStructureV3Client(base_url="http://ocr.example.com")
        with patch(
            "crxzipple.modules.ocr.infrastructure.ppstructure_client.request_url",
            return_value=_FakeResponse(["invalid"]),
        ):
            with self.assertRaises(OcrExecutionError):
                client.health()
