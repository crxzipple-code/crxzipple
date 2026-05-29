from __future__ import annotations

from types import SimpleNamespace

from crxzipple.interfaces.runtime_container import AppKey
from crxzipple.modules.ocr.domain import OcrResult, OcrTextBlock
from crxzipple.modules.ocr.interfaces.serializers import OcrResultSerializer

from tests.unit.cli_test_support import *


class OcrCliTestCase(CliModuleTestCase):
    def test_ocr_analyze_artifact_command_uses_service(self) -> None:
        values = {
            AppKey.OCR_SERVICE: SimpleNamespace(
                analyze_artifact=lambda **_: OcrResult(
                    backend="fake-ocr",
                    language="ch",
                    artifact_id="artifact-1",
                    variant="preview",
                    blocks=(OcrTextBlock(text="示例", confidence=0.9),),
                    layout_blocks=(
                        OcrTextBlock(text="示例", label="doc_title", confidence=0.9),
                    ),
                    overall_ocr_blocks=(
                        OcrTextBlock(text="示例", label="text", confidence=0.9),
                    ),
                )
            ),
            AppKey.OCR_RESULT_SERIALIZER: OcrResultSerializer(),
        }
        container = SimpleNamespace(
            require=lambda key: values[key],
        )

        with patch(
            "crxzipple.modules.ocr.interfaces.cli.ensure_container",
            return_value=container,
        ):
            result = self.runner.invoke(
                app,
                [
                    "ocr",
                    "analyze-artifact",
                    "artifact-1",
                    "--variant",
                    "preview",
                    "--language",
                    "ch",
                ],
                env=self.env,
            )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["artifact_id"], "artifact-1")
        self.assertEqual(payload["block_count"], 1)
        self.assertEqual(payload["blocks"][0]["text"], "示例")
        self.assertEqual(payload["layout_block_count"], 1)
        self.assertEqual(payload["layout_blocks"][0]["label"], "doc_title")
        self.assertEqual(payload["overall_ocr_block_count"], 1)
        self.assertEqual(payload["overall_ocr_blocks"][0]["label"], "text")

    def test_ocr_host_run_uses_uvicorn(self) -> None:
        settings = SimpleNamespace(
            ocr_host="127.0.0.1",
            ocr_port=18900,
            ocr_language="ch",
            ocr_use_gpu=False,
        )
        container = SimpleNamespace(
            require=lambda key: {AppKey.CORE_SETTINGS: settings}[key],
        )

        with patch(
            "crxzipple.modules.ocr.interfaces.cli.ensure_container",
            return_value=container,
        ), patch("uvicorn.run") as run_mock:
            result = self.runner.invoke(
                app,
                ["ocr", "host", "run"],
                env=self.env,
            )

        self.assertEqual(result.exit_code, 0)
        run_mock.assert_called_once()
        _, kwargs = run_mock.call_args
        self.assertEqual(kwargs["host"], "127.0.0.1")
        self.assertEqual(kwargs["port"], 18900)
