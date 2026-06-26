from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crxzipple.modules.ocr.domain import (
    OcrCapacityExceededError,
    OcrExecutionError,
    OcrValidationError,
)
from crxzipple.modules.ocr.infrastructure.http_client import OcrHostClient
from crxzipple.modules.ocr.infrastructure.ppstructure_client import PPStructureV3Client


class _FakeResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        payload: object | None = None,
        json_error: Exception | None = None,
    ) -> None:
        self.status_code = status_code
        self.payload = payload if payload is not None else {}
        self.json_error = json_error

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self) -> object:
        if self.json_error is not None:
            raise self.json_error
        return self.payload


class OcrInfrastructureTestCase(unittest.TestCase):
    def test_host_client_health_uses_normalized_timeout(self) -> None:
        with patch(
            "crxzipple.modules.ocr.infrastructure.http_client.request_url",
            return_value=_FakeResponse(payload={"status": "ok"}),
        ) as request_url:
            payload = OcrHostClient(
                base_url="http://ocr-host/",
                timeout_seconds=0,
            ).health()

        self.assertEqual(payload["status"], "ok")
        request_url.assert_called_once_with(
            "GET",
            "http://ocr-host/health",
            timeout=0.1,
        )

    def test_host_client_maps_request_and_invalid_json_errors(self) -> None:
        with patch(
            "crxzipple.modules.ocr.infrastructure.http_client.request_url",
            side_effect=TimeoutError("timed out"),
        ):
            with self.assertRaisesRegex(OcrExecutionError, "healthcheck failed"):
                OcrHostClient(base_url="http://ocr-host").health()

        with patch(
            "crxzipple.modules.ocr.infrastructure.http_client.request_url",
            return_value=_FakeResponse(json_error=ValueError("bad json")),
        ):
            with self.assertRaisesRegex(OcrExecutionError, "invalid OCR payload"):
                OcrHostClient(base_url="http://ocr-host").analyze_image(
                    image_path=Path("sample.png"),
                    language="ch",
                    detect_orientation=True,
                )

    def test_host_client_maps_http_errors_to_domain_errors(self) -> None:
        with patch(
            "crxzipple.modules.ocr.infrastructure.http_client.request_url",
            return_value=_FakeResponse(status_code=400, payload={"detail": "bad input"}),
        ):
            with self.assertRaisesRegex(OcrValidationError, "bad input"):
                OcrHostClient(base_url="http://ocr-host").analyze_image(
                    image_path=Path("sample.png"),
                    language="ch",
                    detect_orientation=True,
                )

        with patch(
            "crxzipple.modules.ocr.infrastructure.http_client.request_url",
            return_value=_FakeResponse(
                status_code=503,
                json_error=ValueError("bad json"),
            ),
        ):
            with self.assertRaisesRegex(
                OcrCapacityExceededError,
                "OCR host request failed",
            ):
                OcrHostClient(base_url="http://ocr-host").analyze_image(
                    image_path=Path("sample.png"),
                    language="ch",
                    detect_orientation=True,
                )

    def test_ppstructure_client_maps_http_and_provider_errors(self) -> None:
        with tempfile.NamedTemporaryFile(suffix=".png") as image_file:
            image_path = Path(image_file.name)
            image_path.write_bytes(b"image")

            with patch(
                "crxzipple.modules.ocr.infrastructure.ppstructure_client.request_url",
                return_value=_FakeResponse(
                    status_code=503,
                    json_error=ValueError("bad json"),
                ),
            ):
                with self.assertRaisesRegex(
                    OcrExecutionError,
                    "PP-StructureV3 request failed",
                ):
                    PPStructureV3Client(base_url="http://ocr-host").analyze_image(
                        image_path=image_path,
                        language="ch",
                        detect_orientation=True,
                    )

            with patch(
                "crxzipple.modules.ocr.infrastructure.ppstructure_client.request_url",
                return_value=_FakeResponse(
                    payload={"errorCode": 1001, "errorMsg": "engine unavailable"},
                ),
            ):
                with self.assertRaisesRegex(OcrExecutionError, "engine unavailable"):
                    PPStructureV3Client(base_url="http://ocr-host").analyze_image(
                        image_path=image_path,
                        language="ch",
                        detect_orientation=True,
                    )


if __name__ == "__main__":
    unittest.main()
