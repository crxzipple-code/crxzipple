from __future__ import annotations

import unittest

from crxzipple.app.assembly.daemon import build_runtime_daemon_specs
from crxzipple.app.assembly.runtime_defaults import RuntimeSettingsBootstrapConfig
from crxzipple.core.config import Settings
from crxzipple.modules.browser.domain import BrowserSystemConfig


class OcrRuntimeConfigTestCase(unittest.TestCase):
    def test_local_ocr_backend_registers_ocr_daemon_spec(self) -> None:
        settings = Settings(
            app_name="crxzipple",
            environment="test",
            database_url="sqlite:///test.db",
            sandbox_base_dir="/tmp",
            sandbox_backend="process",
            sandbox_docker_binary="docker",
            sandbox_docker_image="python:3.11-slim",
            log_level="INFO",
            log_json=False,
            ocr_enabled=True,
            ocr_backend="local",
            ocr_provider="host",
            ocr_base_url="http://127.0.0.1:18900",
        )

        specs = build_runtime_daemon_specs(
            settings=settings,
            browser_system_config=BrowserSystemConfig(
                default_profile="crxzipple",
            ),
            runtime_bootstrap_config=RuntimeSettingsBootstrapConfig(),
        )

        self.assertIn(
            "capability:ocr:default",
            tuple(spec.key for spec in specs),
        )

    def test_remote_ocr_backend_skips_local_ocr_daemon_spec(self) -> None:
        settings = Settings(
            app_name="crxzipple",
            environment="test",
            database_url="sqlite:///test.db",
            sandbox_base_dir="/tmp",
            sandbox_backend="process",
            sandbox_docker_binary="docker",
            sandbox_docker_image="python:3.11-slim",
            log_level="INFO",
            log_json=False,
            ocr_enabled=True,
            ocr_backend="remote",
            ocr_provider="host",
            ocr_base_url="https://ocr.example.com",
        )

        specs = build_runtime_daemon_specs(
            settings=settings,
            browser_system_config=BrowserSystemConfig(
                default_profile="crxzipple",
            ),
            runtime_bootstrap_config=RuntimeSettingsBootstrapConfig(),
        )

        self.assertNotIn(
            "capability:ocr:default",
            tuple(spec.key for spec in specs),
        )

    def test_remote_ppstructure_provider_skips_local_ocr_daemon_spec(self) -> None:
        settings = Settings(
            app_name="crxzipple",
            environment="test",
            database_url="sqlite:///test.db",
            sandbox_base_dir="/tmp",
            sandbox_backend="process",
            sandbox_docker_binary="docker",
            sandbox_docker_image="python:3.11-slim",
            log_level="INFO",
            log_json=False,
            ocr_enabled=True,
            ocr_backend="remote",
            ocr_provider="ppstructurev3",
            ocr_base_url="https://ocr.example.com",
        )

        specs = build_runtime_daemon_specs(
            settings=settings,
            browser_system_config=BrowserSystemConfig(
                default_profile="crxzipple",
            ),
            runtime_bootstrap_config=RuntimeSettingsBootstrapConfig(),
        )

        self.assertNotIn(
            "capability:ocr:default",
            tuple(spec.key for spec in specs),
        )
