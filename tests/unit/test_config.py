from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from crxzipple.core.config import (
    RuntimeDatabaseGuardError,
    RuntimeEventsBackendGuardError,
    RuntimeMemoryIndexGuardError,
    load_settings,
    require_production_memory_index_acknowledgement,
    require_shared_events_backend,
    require_runtime_database,
)


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

    def test_load_settings_reads_remote_tool_concurrency_limits(self) -> None:
        os.environ["APP_TOOL_REMOTE_DEFAULT_MAX_CONCURRENCY"] = "32"
        os.environ["APP_TOOL_MCP_PROVIDERS"] = """
        [
          {
            "name": "sample_mcp",
            "command": ["node", "server.js"],
            "max_concurrency": 3
          }
        ]
        """
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "sample.yaml"
            config_path.write_text(
                """
name: sample_api
spec_location: sample_openapi.json
base_url: https://api.example.test
max_concurrency: 7
""".strip(),
                encoding="utf-8",
            )
            os.environ["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = str(config_path)

            settings = load_settings()

        self.assertEqual(settings.tool_remote_default_max_concurrency, 32)
        self.assertEqual(settings.tool_mcp_providers[0].max_concurrency, 3)
        self.assertEqual(settings.tool_openapi_providers[0].max_concurrency, 7)

    def test_load_settings_reads_llm_profile_concurrency_limits(self) -> None:
        os.environ["APP_LLM_PROFILES"] = """
        [
          {
            "id": "local-vllm",
            "provider": "openai_compatible",
            "api_family": "openai_chat_compatible",
            "model_name": "qwen3.5",
            "max_concurrency": 2,
            "concurrency_key": "vllm:qwen3.5"
          }
        ]
        """

        settings = load_settings()

        profile = next(item for item in settings.llm_profiles if item.id == "local-vllm")
        self.assertEqual(profile.max_concurrency, 2)
        self.assertEqual(profile.concurrency_key, "vllm:qwen3.5")

    def test_load_settings_defaults_executor_concurrency_to_four(self) -> None:
        os.environ.pop("APP_ORCHESTRATION_EXECUTOR_MAX_CONCURRENT_ASSIGNMENTS", None)

        settings = load_settings()

        self.assertEqual(settings.orchestration_executor_max_concurrent_assignments, 4)

    def test_load_settings_reads_tool_worker_inflight_capacity(self) -> None:
        os.environ["APP_TOOL_WORKER_MAX_IN_FLIGHT"] = "6"

        settings = load_settings()

        self.assertEqual(settings.tool_worker_max_in_flight, 6)

    def test_load_settings_reads_browser_profile_fields(self) -> None:
        os.environ["APP_BROWSER_PROFILE_SPECS"] = """
        [
          {
            "name": "work",
            "cdp_port": 18800,
            "user_data_dir": "/tmp/crx-browser-work",
            "profile_directory": "Profile 1",
            "autostart": false,
            "proxy_mode": "static",
            "proxy_server": "socks5://127.0.0.1:7890",
            "proxy_bypass_list": ["127.0.0.1", "localhost"],
            "proxy_credential_kind": "bearer"
          }
        ]
        """

        settings = load_settings()

        work = next(profile for profile in settings.browser_profiles if profile.name == "work")
        self.assertEqual(work.profile_directory, "Profile 1")
        self.assertFalse(work.autostart)
        self.assertEqual(work.proxy_mode, "static")
        self.assertEqual(work.proxy_server, "socks5://127.0.0.1:7890")
        self.assertEqual(work.proxy_bypass_list, ("127.0.0.1", "localhost"))
        self.assertEqual(work.proxy_credential_kind, "bearer_token")

    def test_load_settings_rejects_removed_browser_profile_runtime_fields(self) -> None:
        for removed_field in ("runtime_mode", "transport", "executable_path", "headless"):
            with self.subTest(removed_field=removed_field):
                value = "false" if removed_field == "headless" else '"legacy"'
                os.environ["APP_BROWSER_PROFILE_SPECS"] = (
                    f'[{{"name":"work","{removed_field}":{value}}}]'
                )

                with self.assertRaisesRegex(ValueError, f"{removed_field} has been removed"):
                    load_settings()

    def test_load_settings_rejects_static_browser_proxy_credentials(self) -> None:
        os.environ["APP_BROWSER_PROFILE_SPECS"] = """
        [
          {
            "name": "work",
            "proxy_mode": "static",
            "proxy_server": "http://user:secret@proxy.example:8080"
          }
        ]
        """

        with self.assertRaisesRegex(ValueError, "must not contain credentials"):
            load_settings()

    def test_load_settings_reads_http_mcp_provider(self) -> None:
        os.environ["APP_TOOL_MCP_PROVIDERS"] = """
        [
          {
            "name": "sample_mcp",
            "transport": "http",
            "endpoint_url": "http://127.0.0.1:19800/mcp"
          }
        ]
        """

        settings = load_settings()

        provider = settings.tool_mcp_providers[0]
        self.assertEqual(provider.transport, "http")
        self.assertEqual(provider.endpoint_url, "http://127.0.0.1:19800/mcp")
        self.assertEqual(provider.command, ())

    def test_load_settings_defaults_tool_worker_inflight_capacity_to_four(self) -> None:
        os.environ.pop("APP_TOOL_WORKER_MAX_IN_FLIGHT", None)

        settings = load_settings()

        self.assertEqual(settings.tool_worker_max_in_flight, 4)

    def test_load_settings_reads_tool_worker_capability_concurrency(self) -> None:
        os.environ["APP_TOOL_WORKER_MAX_IN_FLIGHT"] = "6"
        os.environ["APP_TOOL_WORKER_DEFAULT_RUN_CONCURRENCY"] = "5"
        os.environ["APP_TOOL_WORKER_IMAGE_RUN_CONCURRENCY"] = "4"
        os.environ["APP_TOOL_WORKER_SHARED_STATE_RUN_CONCURRENCY"] = "2"

        settings = load_settings()

        self.assertEqual(settings.tool_worker_default_run_concurrency, 5)
        self.assertEqual(settings.tool_worker_image_run_concurrency, 4)
        self.assertEqual(settings.tool_worker_shared_state_run_concurrency, 2)

    def test_load_settings_defaults_capability_concurrency_from_worker_capacity(self) -> None:
        os.environ["APP_TOOL_WORKER_MAX_IN_FLIGHT"] = "3"
        os.environ.pop("APP_TOOL_WORKER_DEFAULT_RUN_CONCURRENCY", None)
        os.environ.pop("APP_TOOL_WORKER_IMAGE_RUN_CONCURRENCY", None)
        os.environ.pop("APP_TOOL_WORKER_SHARED_STATE_RUN_CONCURRENCY", None)

        settings = load_settings()

        self.assertEqual(settings.tool_worker_default_run_concurrency, 3)
        self.assertEqual(settings.tool_worker_image_run_concurrency, 3)
        self.assertEqual(settings.tool_worker_shared_state_run_concurrency, 1)

    def test_load_settings_reads_detailed_engine_metrics_flag(self) -> None:
        os.environ["APP_ORCHESTRATION_DETAILED_ENGINE_METRICS_ENABLED"] = "true"

        settings = load_settings()

        self.assertTrue(settings.orchestration_detailed_engine_metrics_enabled)

    def test_load_settings_reads_mobile_device_specs(self) -> None:
        os.environ["APP_DAEMON_STATE_DIR"] = "/tmp/crxzipple-daemon-state"
        os.environ["APP_MOBILE_DEVICE_SPECS"] = """
        [
          {
            "name": "pixel",
            "platform": "android",
            "udid": "emulator-5554",
            "app_package": "com.google.android.gm",
            "app_activity": "com.google.android.gm.ConversationListActivityGmail"
          }
        ]
        """

        settings = load_settings()

        self.assertEqual(settings.daemon_state_dir, "/tmp/crxzipple-daemon-state")
        self.assertEqual(len(settings.mobile_devices), 1)
        self.assertEqual(settings.mobile_devices[0].name, "pixel")
        self.assertEqual(settings.mobile_devices[0].udid, "emulator-5554")
        self.assertEqual(settings.mobile_devices[0].app_package, "com.google.android.gm")
        self.assertEqual(
            settings.mobile_devices[0].app_activity,
            "com.google.android.gm.ConversationListActivityGmail",
        )

    def test_load_settings_reads_ocr_overrides(self) -> None:
        os.environ.pop("APP_OCR_BASE_URL", None)
        os.environ["APP_OCR_ENABLED"] = "true"
        os.environ["APP_OCR_BACKEND"] = "local"
        os.environ["APP_OCR_PROVIDER"] = "host"
        os.environ["APP_OCR_HOST"] = "127.0.0.1"
        os.environ["APP_OCR_PORT"] = "19999"
        os.environ["APP_OCR_LANGUAGE"] = "en"
        os.environ["APP_OCR_USE_GPU"] = "true"
        os.environ["APP_OCR_REQUEST_TIMEOUT_SECONDS"] = "12.5"
        os.environ["APP_OCR_MAX_CONCURRENT_REQUESTS"] = "3"

        settings = load_settings()

        self.assertTrue(settings.ocr_enabled)
        self.assertEqual(settings.ocr_backend, "local")
        self.assertEqual(settings.ocr_provider, "host")
        self.assertEqual(settings.ocr_host, "127.0.0.1")
        self.assertEqual(settings.ocr_port, 19999)
        self.assertEqual(settings.ocr_base_url, "http://127.0.0.1:19999")
        self.assertEqual(settings.ocr_language, "en")
        self.assertTrue(settings.ocr_use_gpu)
        self.assertEqual(settings.ocr_request_timeout_seconds, 12.5)
        self.assertEqual(settings.ocr_max_concurrent_requests, 3)

    def test_load_settings_reads_redis_events_overrides(self) -> None:
        os.environ["APP_EVENTS_BACKEND"] = "redis"
        os.environ["APP_EVENTS_FILE_SYNC_WRITES"] = "true"
        os.environ["APP_EVENTS_REDIS_URL"] = "redis://127.0.0.1:6379/9"
        os.environ["APP_EVENTS_REDIS_KEY_PREFIX"] = "crx:test:events"
        os.environ["APP_EVENTS_REDIS_BLOCK_MS"] = "250"
        os.environ["APP_EVENTS_REDIS_DEDUPE_TTL_SECONDS"] = "45"

        settings = load_settings()

        self.assertEqual(settings.events_backend, "redis")
        self.assertTrue(settings.events_file_sync_writes)
        self.assertEqual(settings.events_redis_url, "redis://127.0.0.1:6379/9")
        self.assertEqual(settings.events_redis_key_prefix, "crx:test:events")
        self.assertEqual(settings.events_redis_block_ms, 250)
        self.assertEqual(settings.events_redis_dedupe_ttl_seconds, 45)

    def test_load_settings_defaults_to_redis_events_for_local_dev(self) -> None:
        os.environ.pop("APP_EVENTS_BACKEND", None)
        os.environ.pop("APP_EVENTS_REDIS_URL", None)

        settings = load_settings()

        self.assertEqual(settings.events_backend, "redis")
        self.assertEqual(settings.events_redis_url, "redis://127.0.0.1:6379/0")

    def test_shared_events_backend_guard_allows_redis_backend(self) -> None:
        os.environ["APP_EVENTS_BACKEND"] = "redis"

        settings = load_settings()

        require_shared_events_backend(settings, runtime_name="test runtime")

    def test_shared_events_backend_guard_rejects_file_without_explicit_fallback(
        self,
    ) -> None:
        os.environ["APP_EVENTS_BACKEND"] = "file"
        os.environ.pop("APP_ALLOW_FILE_EVENTS_RUNTIME_FALLBACK", None)

        settings = load_settings()

        with self.assertRaises(RuntimeEventsBackendGuardError):
            require_shared_events_backend(settings, runtime_name="test runtime")

    def test_shared_events_backend_guard_requires_fallback_value_one(self) -> None:
        os.environ["APP_EVENTS_BACKEND"] = "file"
        os.environ["APP_ALLOW_FILE_EVENTS_RUNTIME_FALLBACK"] = "true"

        settings = load_settings()

        self.assertFalse(settings.allow_file_events_runtime_fallback)
        with self.assertRaises(RuntimeEventsBackendGuardError):
            require_shared_events_backend(settings, runtime_name="test runtime")

    def test_shared_events_backend_guard_allows_file_with_explicit_fallback(
        self,
    ) -> None:
        os.environ["APP_EVENTS_BACKEND"] = "file"
        os.environ["APP_ALLOW_FILE_EVENTS_RUNTIME_FALLBACK"] = "1"

        settings = load_settings()

        require_shared_events_backend(settings, runtime_name="test runtime")
        self.assertTrue(settings.allow_file_events_runtime_fallback)

    def test_production_memory_index_guard_allows_local_environment(self) -> None:
        os.environ["APP_ENV"] = "local"

        settings = load_settings()

        require_production_memory_index_acknowledgement(
            settings,
            runtime_name="test runtime",
        )

    def test_production_memory_index_guard_rejects_without_explicit_ack(
        self,
    ) -> None:
        os.environ["APP_ENV"] = "production"
        os.environ.pop("APP_ALLOW_SQLITE_MEMORY_INDEX_RUNTIME", None)

        settings = load_settings()

        with self.assertRaises(RuntimeMemoryIndexGuardError):
            require_production_memory_index_acknowledgement(
                settings,
                runtime_name="test runtime",
            )

    def test_production_memory_index_guard_requires_ack_value_one(self) -> None:
        os.environ["APP_ENV"] = "production"
        os.environ["APP_ALLOW_SQLITE_MEMORY_INDEX_RUNTIME"] = "true"

        settings = load_settings()

        self.assertFalse(settings.allow_sqlite_memory_index_runtime)
        with self.assertRaises(RuntimeMemoryIndexGuardError):
            require_production_memory_index_acknowledgement(
                settings,
                runtime_name="test runtime",
            )

    def test_production_memory_index_guard_allows_explicit_ack(self) -> None:
        os.environ["APP_ENV"] = "production"
        os.environ["APP_ALLOW_SQLITE_MEMORY_INDEX_RUNTIME"] = "1"

        settings = load_settings()

        require_production_memory_index_acknowledgement(
            settings,
            runtime_name="test runtime",
        )
        self.assertTrue(settings.allow_sqlite_memory_index_runtime)

    def test_runtime_database_guard_rejects_sqlite_without_explicit_fallback(self) -> None:
        os.environ["APP_DATABASE_URL"] = "sqlite:///tmp/crxzipple-test.db"
        os.environ.pop("APP_ALLOW_SQLITE_RUNTIME_FALLBACK", None)

        settings = load_settings()

        with self.assertRaises(RuntimeDatabaseGuardError):
            require_runtime_database(settings, runtime_name="test runtime")

    def test_runtime_database_guard_ignores_legacy_serve_fallback_env(self) -> None:
        os.environ["APP_DATABASE_URL"] = "sqlite:///tmp/crxzipple-test.db"
        os.environ["APP_ALLOW_SQLITE_SERVE"] = "1"
        os.environ.pop("APP_ALLOW_SQLITE_RUNTIME_FALLBACK", None)

        settings = load_settings()

        self.assertFalse(settings.allow_sqlite_runtime_fallback)
        with self.assertRaises(RuntimeDatabaseGuardError):
            require_runtime_database(settings, runtime_name="test runtime")

    def test_runtime_database_guard_requires_runtime_fallback_value_one(self) -> None:
        os.environ["APP_DATABASE_URL"] = "sqlite:///tmp/crxzipple-test.db"
        os.environ["APP_ALLOW_SQLITE_RUNTIME_FALLBACK"] = "true"

        settings = load_settings()

        self.assertFalse(settings.allow_sqlite_runtime_fallback)
        with self.assertRaises(RuntimeDatabaseGuardError):
            require_runtime_database(settings, runtime_name="test runtime")

    def test_runtime_database_guard_allows_sqlite_with_explicit_fallback(self) -> None:
        os.environ["APP_DATABASE_URL"] = "sqlite:///tmp/crxzipple-test.db"
        os.environ["APP_ALLOW_SQLITE_RUNTIME_FALLBACK"] = "1"

        settings = load_settings()

        require_runtime_database(settings, runtime_name="test runtime")
        self.assertTrue(settings.allow_sqlite_runtime_fallback)

    def test_load_settings_reads_channel_profiles_from_config_files(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            config_path = Path(tempdir) / "lark.yaml"
            config_path.write_text(
                """
channel_type: lark
enabled: true
accounts:
  - account_id: default
    transport_mode: webhook
    metadata:
      agent_id: assistant-lark
      lark_app_id: cli_test
      lark_app_secret: secret_test
""".strip(),
                encoding="utf-8",
            )
            os.environ["APP_CHANNEL_PROFILE_PATHS"] = str(config_path)

            settings = load_settings()

            self.assertEqual(len(settings.channel_profiles), 1)
            profile = settings.channel_profiles[0]
            self.assertEqual(profile.channel_type, "lark")
            self.assertEqual(profile.accounts[0].account_id, "default")
            self.assertEqual(
                profile.accounts[0].metadata["lark_app_id"],
                "cli_test",
            )

    def test_load_settings_supports_remote_ocr_host(self) -> None:
        os.environ["APP_OCR_BACKEND"] = "remote"
        os.environ["APP_OCR_PROVIDER"] = "ppstructurev3"
        os.environ["APP_OCR_BASE_URL"] = "https://ocr.example.com"
        os.environ["APP_OCR_REQUEST_TIMEOUT_SECONDS"] = "33"

        settings = load_settings()

        self.assertEqual(settings.ocr_backend, "remote")
        self.assertEqual(settings.ocr_provider, "ppstructurev3")
        self.assertEqual(settings.ocr_base_url, "https://ocr.example.com")
        self.assertEqual(settings.ocr_request_timeout_seconds, 33.0)

    def test_load_settings_rejects_local_non_host_ocr_provider(self) -> None:
        os.environ["APP_OCR_BACKEND"] = "local"
        os.environ["APP_OCR_PROVIDER"] = "ppstructurev3"

        with self.assertRaisesRegex(
            ValueError,
            "APP_OCR_PROVIDER must be 'host' when APP_OCR_BACKEND=local.",
        ):
            load_settings()
