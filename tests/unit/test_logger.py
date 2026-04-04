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
            {
                "APP_LOG_LEVEL": "debug",
                "APP_LOG_JSON": "true",
                "APP_MEMORY_RETRIEVAL_BACKEND": "vector",
                "APP_MEMORY_VECTOR_PROVIDER": "openai_compatible",
                "APP_MEMORY_VECTOR_MODEL": "text-embedding-3-small",
                "APP_MEMORY_VECTOR_BASE_URL": "https://api.openai.com/v1",
                "APP_MEMORY_VECTOR_CREDENTIAL_BINDING": "env:OPENAI_API_KEY",
                "OPENAI_API_KEY": "test-openai-key",
            },
            clear=False,
        ):
            settings = load_settings()

        self.assertEqual(settings.log_level, "DEBUG")
        self.assertTrue(settings.log_json)
        self.assertEqual(settings.memory_retrieval_backend, "vector")
        self.assertEqual(settings.memory_vector_provider, "openai_compatible")
        self.assertEqual(settings.memory_vector_model, "text-embedding-3-small")
        self.assertEqual(settings.memory_vector_base_url, "https://api.openai.com/v1")
        self.assertEqual(
            settings.memory_vector_credential_binding,
            "env:OPENAI_API_KEY",
        )

    def test_load_settings_reads_explicit_browser_profile_specs(self) -> None:
        with patch.dict(
            os.environ,
            {
                "APP_BROWSER_PROFILE_SPECS": json.dumps(
                    [
                        {"name": "crxzipple", "runtime_mode": "host"},
                        {"name": "sandbox", "runtime_mode": "sandbox"},
                        {
                            "name": "remote",
                            "runtime_mode": "remote-cdp",
                            "cdp_url": "https://remote.example:9443",
                        },
                        {
                            "name": "attached",
                            "driver": "existing-session",
                            "runtime_mode": "attached",
                            "cdp_url": "http://127.0.0.1:9222",
                        },
                    ],
                ),
            },
            clear=False,
        ):
            settings = load_settings()

        self.assertEqual(
            tuple(spec.name for spec in settings.browser_profile_specs),
            ("crxzipple", "sandbox", "remote", "attached", "user"),
        )
        runtime_by_profile = {
            runtime.profile: runtime for runtime in settings.browser_profile_runtime_settings
        }
        remote = settings.browser_profile_specs[2]
        self.assertEqual(remote.driver, "managed")
        self.assertEqual(remote.cdp_url, "https://remote.example:9443")
        self.assertEqual(remote.cdp_port, 9443)
        self.assertFalse(remote.attach_only)
        self.assertEqual(runtime_by_profile["remote"].runtime_mode, "remote-cdp")
        self.assertEqual(runtime_by_profile["remote"].transport, "cdp")

        attached = settings.browser_profile_specs[-2]
        self.assertEqual(attached.driver, "existing-session")
        self.assertEqual(attached.cdp_url, "http://127.0.0.1:9222")
        self.assertEqual(attached.cdp_port, 9222)
        self.assertTrue(attached.attach_only)
        self.assertEqual(runtime_by_profile["attached"].runtime_mode, "attached")

        user = settings.browser_profile_specs[-1]
        self.assertEqual(user.name, "user")
        self.assertEqual(user.driver, "existing-session")
        self.assertEqual(user.cdp_url, "http://127.0.0.1:9222")
        self.assertTrue(user.attach_only)
        self.assertEqual(runtime_by_profile["user"].runtime_mode, "attached")

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
