from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from crxzipple.core.config import (
    AgentProfileSettings,
    LlmProfileSettings,
    McpProviderSettings,
    OpenApiCredentialBinding,
    OpenApiProviderSettings,
    load_settings,
)
from crxzipple.interfaces.http.app import create_app
from crxzipple.interfaces.http.conversations import _normalize_preview_text
from crxzipple.interfaces.runtime_container import AppKey
from crxzipple.modules.agent.infrastructure import derive_agent_home_root
from crxzipple.modules.browser.infrastructure.engines import CdpControlEngine
from crxzipple.modules.llm.application import LlmStreamEvent
from crxzipple.modules.llm.application.adapters import LlmAdapterResponse
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmMessageRole,
    LlmProviderKind,
    LlmResult,
    ToolCallIntent,
)
from crxzipple.modules.tool.domain import ToolEnvironment, ToolMode
from tests.unit.skill_test_support import write_skill_package as _write_skill_package
from tests.unit.support import (
    FakeCdpServer,
    FakePlaywrightCdpSessionPool,
    SampleApiServer,
    SampleLlmApiServer,
    SqliteTestHarness,
    fixture_path,
    openapi_fixture_path,
)
from tests.unit.orchestration_test_support import (
    _adapter_response_from_result,
    _enable_tool_schema_call,
    _expand_tool_bundle_call,
    _has_tool_call_message,
    _has_tool_message,
    assign_next_orchestration_assignment,
    execution_tool_run_ids_for_run,
    process_next_orchestration_assignment,
)
from tests.unit.tool_catalog_seed import seed_catalog_tool


class _FakeStreamResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        events: tuple[tuple[str | None, dict[str, object]], ...] = (),
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._events = events
        self.text = text
        self.iter_lines_chunk_size: int | None = None

    def iter_lines(
        self,
        chunk_size: int | None = None,
        decode_unicode: bool = False,
    ):  # noqa: ANN001
        self.iter_lines_chunk_size = chunk_size
        del decode_unicode
        for event_name, payload in self._events:
            if event_name is not None:
                yield f"event: {event_name}".encode("utf-8")
            yield f"data: {json.dumps(payload)}".encode("utf-8")
            yield b""

    def close(self) -> None:
        return None


class _FakeStreamingAdapter:
    def stream_invoke(self, profile, request):  # noqa: ANN001
        del profile, request
        yield LlmStreamEvent(
            type="text_delta",
            sequence=1,
            data={"text": "hello "},
        )
        yield LlmStreamEvent(
            type="text_delta",
            sequence=2,
            data={"text": "from stream"},
        )
        yield LlmStreamEvent(
            type="completed",
            sequence=3,
            data={
                "result": LlmResult(
                    text="hello from stream",
                    finish_reason="completed",
                ).to_payload(),
                "provider_request_id": "stream-http-request",
            },
        )


class _FakeInlineToolAdapter:
    def __init__(self) -> None:
        self.requests: list[object] = []

    def invoke(self, _profile, request):  # noqa: ANN001
        self.requests.append(request)
        tool_messages = [
            message for message in request.messages if message.role is LlmMessageRole.TOOL
        ]
        if not tool_messages:
            return _adapter_response_from_result(
                request,
                LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-echo-1",
                            name="echo",
                            arguments={"message": "hello from tool"},
                        ),
                    ),
                ),
            )
        return _adapter_response_from_result(
            request,
            LlmResult(text="tool loop complete"),
        )


class _FakeCdpSocket:
    def send(self, _payload: str) -> None:
        return None

    def recv(self) -> str:
        return '{"id": 1, "result": {}}'

    def close(self) -> None:
        return None


def _fake_ws_connect(_ws_url: str, *, timeout: float | None = None):  # noqa: ANN202
    del timeout
    return _FakeCdpSocket()


def _fake_cdp_control_engine(*args, **kwargs):  # noqa: ANN002, ANN003, ANN202
    kwargs.setdefault("ws_connect", _fake_ws_connect)
    return CdpControlEngine(*args, **kwargs)


class _FakeEffectApprovalAdapter:
    def __init__(self) -> None:
        self._expanded = False
        self._schema_enabled = False
        self._echo_requested = False

    def invoke(self, _profile, request):  # noqa: ANN001
        if not self._expanded:
            self._expanded = True
            return _adapter_response_from_result(
                request,
                LlmResult(
                    tool_calls=(
                        _expand_tool_bundle_call(
                            call_id="call-expand-echo",
                            source_id="test.local_package.echo",
                        ),
                    ),
                ),
            )
        if not self._schema_enabled:
            self._schema_enabled = True
            return _adapter_response_from_result(
                request,
                LlmResult(
                    tool_calls=(
                        _enable_tool_schema_call(
                            call_id="call-enable-echo",
                            tool_id="echo",
                        ),
                    ),
                ),
            )
        if not self._echo_requested:
            self._echo_requested = True
            return _adapter_response_from_result(
                request,
                LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-echo-1",
                            name="echo",
                            arguments={"message": "hello after approval"},
                        ),
                    ),
                ),
            )
        if not _has_tool_message(request, "echo"):
            raise AssertionError("approval replay should provide an echo tool result")
        return _adapter_response_from_result(
            request,
            LlmResult(text="approval flow complete"),
        )


class _SequentialTextAdapter:
    def __init__(self, *texts: str) -> None:
        self._texts = list(texts)
        self.requests: list[object] = []

    def invoke(self, _profile, request):  # noqa: ANN001
        self.requests.append(request)
        text = self._texts.pop(0) if self._texts else ""
        return _adapter_response_from_result(request, LlmResult(text=text))


class _SequentialResultAdapter:
    def __init__(self, *results: str | LlmResult) -> None:
        self._results = list(results)
        self.requests: list[object] = []

    def invoke(self, _profile, request):  # noqa: ANN001
        self.requests.append(request)
        item = self._results.pop(0) if self._results else ""
        result = item if isinstance(item, LlmResult) else LlmResult(text=item)
        return _adapter_response_from_result(request, result)


class HttpModuleTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_browser_state_dir = os.environ.get("APP_BROWSER_STATE_DIR")
        self.previous_channels_state_dir = os.environ.get("APP_CHANNELS_STATE_DIR")
        self.previous_channel_profile_paths = os.environ.get(
            "APP_CHANNEL_PROFILE_PATHS",
        )
        self.previous_daemon_state_dir = os.environ.get("APP_DAEMON_STATE_DIR")
        self.previous_events_state_dir = os.environ.get("APP_EVENTS_STATE_DIR")
        self.previous_memory_storage_root = os.environ.get("APP_MEMORY_STORAGE_ROOT")
        self.previous_operations_state_dir = os.environ.get("APP_OPERATIONS_STATE_DIR")
        self.previous_events_backend = os.environ.get("APP_EVENTS_BACKEND")
        self.previous_events_redis_url = os.environ.get("APP_EVENTS_REDIS_URL")
        self.previous_openapi_provider_paths = os.environ.get(
            "APP_TOOL_OPENAPI_PROVIDER_PATHS",
        )
        os.environ["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = os.pathsep
        self._skills_tempdir = tempfile.TemporaryDirectory()
        skills_root = Path(self._skills_tempdir.name)
        self._global_skills_patcher = patch(
            "crxzipple.modules.skills.infrastructure.filesystem.repository.DEFAULT_GLOBAL_SKILLS_DIR",
            skills_root / "global",
        )
        self._system_skills_patcher = patch(
            "crxzipple.modules.skills.infrastructure.filesystem.repository.DEFAULT_SYSTEM_SKILLS_DIR",
            skills_root / "system",
        )
        self._browser_playwright_patcher = patch(
            "crxzipple.app.assembly.browser.PlaywrightCdpSessionPool",
            FakePlaywrightCdpSessionPool,
        )
        self._browser_cdp_control_patcher = patch(
            "crxzipple.app.assembly.browser.CdpControlEngine",
            _fake_cdp_control_engine,
        )
        self._global_skills_patcher.start()
        self._system_skills_patcher.start()
        self._browser_playwright_patcher.start()
        self._browser_cdp_control_patcher.start()
        system_skill_dir = skills_root / "system" / "memory-recall"
        _write_skill_package(
            system_skill_dir,
            name="memory-recall",
            description=(
                "Use this skill when earlier decisions, preferences, commitments, "
                "or durable workspace context may affect the current answer."
            ),
            instructions=(
                "# Memory Recall\n\n"
                "Use this skill when earlier decisions, preferences, commitments, "
                "or durable workspace context may affect the current answer.\n"
            ),
            allowed_tools=("memory_search", "memory_read", "memory_write_daily"),
        )
        self.harness = SqliteTestHarness()
        self.harness.initialize_schema()
        os.environ["APP_BROWSER_STATE_DIR"] = str(
            Path(self.harness._tempdir.name) / "browser",
        )
        os.environ["APP_CHANNELS_STATE_DIR"] = str(
            Path(self.harness._tempdir.name) / "channels",
        )
        os.environ["APP_CHANNEL_PROFILE_PATHS"] = os.pathsep
        os.environ["APP_DAEMON_STATE_DIR"] = str(
            Path(self.harness._tempdir.name) / "daemon",
        )
        os.environ["APP_EVENTS_BACKEND"] = "file"
        os.environ.pop("APP_EVENTS_REDIS_URL", None)
        os.environ["APP_EVENTS_STATE_DIR"] = str(
            Path(self.harness._tempdir.name) / "events",
        )
        os.environ["APP_MEMORY_STORAGE_ROOT"] = str(
            Path(self.harness._tempdir.name) / "memory",
        )
        os.environ["APP_OPERATIONS_STATE_DIR"] = str(
            Path(self.harness._tempdir.name) / "operations",
        )
        self._client_context = TestClient(
            create_app(
                database_url=self.harness.database_url,
                enable_memory_watchers=False,
            ),
        )
        self.client = self._client_context.__enter__()

    def tearDown(self) -> None:
        self._client_context.__exit__(None, None, None)
        self.harness.close()
        self._browser_cdp_control_patcher.stop()
        self._browser_playwright_patcher.stop()
        self._system_skills_patcher.stop()
        self._global_skills_patcher.stop()
        self._skills_tempdir.cleanup()
        if self.previous_browser_state_dir is None:
            os.environ.pop("APP_BROWSER_STATE_DIR", None)
        else:
            os.environ["APP_BROWSER_STATE_DIR"] = self.previous_browser_state_dir
        if self.previous_channels_state_dir is None:
            os.environ.pop("APP_CHANNELS_STATE_DIR", None)
        else:
            os.environ["APP_CHANNELS_STATE_DIR"] = self.previous_channels_state_dir
        if self.previous_channel_profile_paths is None:
            os.environ.pop("APP_CHANNEL_PROFILE_PATHS", None)
        else:
            os.environ["APP_CHANNEL_PROFILE_PATHS"] = (
                self.previous_channel_profile_paths
            )
        if self.previous_daemon_state_dir is None:
            os.environ.pop("APP_DAEMON_STATE_DIR", None)
        else:
            os.environ["APP_DAEMON_STATE_DIR"] = self.previous_daemon_state_dir
        if self.previous_events_state_dir is None:
            os.environ.pop("APP_EVENTS_STATE_DIR", None)
        else:
            os.environ["APP_EVENTS_STATE_DIR"] = self.previous_events_state_dir
        if self.previous_operations_state_dir is None:
            os.environ.pop("APP_OPERATIONS_STATE_DIR", None)
        else:
            os.environ["APP_OPERATIONS_STATE_DIR"] = (
                self.previous_operations_state_dir
            )
        if self.previous_memory_storage_root is None:
            os.environ.pop("APP_MEMORY_STORAGE_ROOT", None)
        else:
            os.environ["APP_MEMORY_STORAGE_ROOT"] = (
                self.previous_memory_storage_root
            )
        if self.previous_events_backend is None:
            os.environ.pop("APP_EVENTS_BACKEND", None)
        else:
            os.environ["APP_EVENTS_BACKEND"] = self.previous_events_backend
        if self.previous_events_redis_url is None:
            os.environ.pop("APP_EVENTS_REDIS_URL", None)
        else:
            os.environ["APP_EVENTS_REDIS_URL"] = self.previous_events_redis_url
        if self.previous_openapi_provider_paths is None:
            os.environ.pop("APP_TOOL_OPENAPI_PROVIDER_PATHS", None)
        else:
            os.environ["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = (
                self.previous_openapi_provider_paths
            )


__all__ = [
    "AgentProfileSettings",
    "AppKey",
    "assign_next_orchestration_assignment",
    "execution_tool_run_ids_for_run",
    "FakeCdpServer",
    "FakePlaywrightCdpSessionPool",
    "HttpModuleTestCase",
    "LlmAdapterResponse",
    "LlmApiFamily",
    "LlmMessageRole",
    "LlmProviderKind",
    "LlmResult",
    "LlmProfileSettings",
    "LlmStreamEvent",
    "McpProviderSettings",
    "OpenApiCredentialBinding",
    "OpenApiProviderSettings",
    "Path",
    "seed_catalog_tool",
    "SampleApiServer",
    "SampleLlmApiServer",
    "SqliteTestHarness",
    "TestClient",
    "ToolCallIntent",
    "ToolEnvironment",
    "ToolMode",
    "_FakeEffectApprovalAdapter",
    "_FakeInlineToolAdapter",
    "_FakeStreamResponse",
    "_FakeStreamingAdapter",
    "_SequentialResultAdapter",
    "_SequentialTextAdapter",
    "_normalize_preview_text",
    "_write_skill_package",
    "create_app",
    "datetime",
    "derive_agent_home_root",
    "fixture_path",
    "json",
    "load_settings",
    "openapi_fixture_path",
    "os",
    "patch",
    "process_next_orchestration_assignment",
    "replace",
    "shutil",
    "sys",
    "tempfile",
    "threading",
    "time",
    "timedelta",
    "timezone",
    "unittest",
]
