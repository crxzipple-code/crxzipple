from __future__ import annotations

import json
import logging
import os
from unittest.mock import patch
import unittest

from crxzipple.core.config import Settings, load_settings
from crxzipple.core.logger import JsonFormatter, configure_logging


class LoggerTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.root_logger = logging.getLogger()
        self.original_handlers = list(self.root_logger.handlers)
        self.original_level = self.root_logger.level

    def tearDown(self) -> None:
        self.root_logger.handlers.clear()
        for handler in self.original_handlers:
            self.root_logger.addHandler(handler)
        self.root_logger.setLevel(self.original_level)

    def test_load_settings_reads_logging_environment(self) -> None:
        with patch.dict(
            os.environ,
            {"APP_LOG_LEVEL": "debug", "APP_LOG_JSON": "true"},
            clear=False,
        ):
            settings = load_settings()

        self.assertEqual(settings.log_level, "DEBUG")
        self.assertTrue(settings.log_json)

    def test_configure_logging_uses_json_formatter_when_enabled(self) -> None:
        settings = Settings(
            app_name="crxzipple",
            environment="test",
            database_url="sqlite:///./test.db",
            sandbox_base_dir="/tmp/crxzipple-sandboxes",
            sandbox_backend="subprocess",
            sandbox_docker_binary="docker",
            sandbox_docker_image="python:3.11-slim",
            log_level="DEBUG",
            log_json=True,
        )

        configure_logging(settings)

        self.assertEqual(self.root_logger.level, logging.DEBUG)
        self.assertEqual(len(self.root_logger.handlers), 1)
        self.assertIsInstance(self.root_logger.handlers[0].formatter, JsonFormatter)

    def test_json_formatter_serializes_extra_fields(self) -> None:
        formatter = JsonFormatter()
        record = logging.makeLogRecord(
            {
                "name": "crxzipple.test",
                "levelno": logging.INFO,
                "levelname": "INFO",
                "msg": "HTTP request complete",
                "path": "/health",
                "status_code": 200,
            },
        )

        payload = json.loads(formatter.format(record))

        self.assertEqual(payload["message"], "HTTP request complete")
        self.assertEqual(payload["path"], "/health")
        self.assertEqual(payload["status_code"], 200)
        self.assertEqual(payload["level"], "INFO")


if __name__ == "__main__":
    unittest.main()
