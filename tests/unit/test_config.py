from __future__ import annotations

import os
import unittest

from crxzipple.core.config import load_settings


class ConfigTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_env = dict(os.environ)

    def tearDown(self) -> None:
        os.environ.clear()
        os.environ.update(self._previous_env)

    def test_load_settings_reads_artifact_llm_budget_overrides(self) -> None:
        os.environ["APP_ARTIFACT_IMAGE_PREVIEW_MAX_DIMENSION"] = "800"
        os.environ["APP_ARTIFACT_IMAGE_LLM_MAX_DIMENSION"] = "1200"
        os.environ["APP_ARTIFACT_IMAGE_LLM_MAX_BYTES"] = "900000"
        os.environ["APP_ARTIFACT_FILE_LLM_MAX_BYTES"] = "123456"
        os.environ["APP_ARTIFACT_TEXT_FILE_LLM_MAX_CHARS"] = "4321"
        os.environ["APP_TOOL_DETAILS_MAX_CHARS"] = "5678"

        settings = load_settings()

        self.assertEqual(settings.artifact_image_preview_max_dimension, 800)
        self.assertEqual(settings.artifact_image_llm_max_dimension, 1200)
        self.assertEqual(settings.artifact_image_llm_max_bytes, 900000)
        self.assertEqual(settings.artifact_file_llm_max_bytes, 123456)
        self.assertEqual(settings.artifact_text_file_llm_max_chars, 4321)
        self.assertEqual(settings.tool_details_max_chars, 5678)
