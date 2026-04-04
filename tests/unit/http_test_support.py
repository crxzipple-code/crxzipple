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
from crxzipple.modules.agent.infrastructure import derive_agent_home_root
from crxzipple.modules.llm.application import LlmStreamEvent
from crxzipple.modules.llm.application.adapters import LlmAdapterResponse
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmMessageRole,
    LlmProviderKind,
    LlmResult,
    ToolCallIntent,
)
from crxzipple.modules.session.application import ListSessionMessagesInput
from crxzipple.modules.tool.application import RegisterToolInput
from crxzipple.modules.tool.domain import ToolEnvironment, ToolMode
from tests.unit.skill_test_support import write_skill_package as _write_skill_package
from tests.unit.support import (
    FakeCdpServer,
    FakeChromeMcpClientPool,
    FakePlaywrightCdpSessionPool,
    SampleApiServer,
    SampleLlmApiServer,
    SqliteTestHarness,
    fixture_path,
    openapi_fixture_path,
)


class _FakeStreamResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        events: tuple[tuple[str, dict[str, object]], ...] = (),
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._events = events
        self.text = text

    def iter_lines(self, decode_unicode: bool = False):  # noqa: ANN001
        del decode_unicode
        for event_name, payload in self._events:
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
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-echo-1",
                            name="echo",
                            arguments={"message": "hello from tool"},
                        ),
                    ),
                ),
            )
        return LlmAdapterResponse(result=LlmResult(text="tool loop complete"))


class _FakeEffectApprovalAdapter:
    def invoke(self, _profile, request):  # noqa: ANN001
        tool_messages = [
            message for message in request.messages if message.role is LlmMessageRole.TOOL
        ]
        echo_messages = [message for message in tool_messages if message.name == "echo"]
        if not tool_messages:
            return LlmAdapterResponse(
                result=LlmResult(
                    tool_calls=(
                        ToolCallIntent(
                            id="call-echo-1",
                            name="echo",
                            arguments={"message": "hello after approval"},
                        ),
                    ),
                ),
            )
        if not echo_messages:
            raise AssertionError("approval replay should provide an echo tool result")
        return LlmAdapterResponse(result=LlmResult(text="approval flow complete"))


class _SequentialTextAdapter:
    def __init__(self, *texts: str) -> None:
        self._texts = list(texts)
        self.requests: list[object] = []

    def invoke(self, _profile, request):  # noqa: ANN001
        self.requests.append(request)
        text = self._texts.pop(0) if self._texts else ""
        return LlmAdapterResponse(result=LlmResult(text=text))


class _SequentialResultAdapter:
    def __init__(self, *results: str | LlmResult) -> None:
        self._results = list(results)
        self.requests: list[object] = []

    def invoke(self, _profile, request):  # noqa: ANN001
        self.requests.append(request)
        item = self._results.pop(0) if self._results else ""
        result = item if isinstance(item, LlmResult) else LlmResult(text=item)
        return LlmAdapterResponse(result=result)


class HttpModuleTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_browser_state_dir = os.environ.get("APP_BROWSER_STATE_DIR")
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
        self._global_skills_patcher.start()
        self._system_skills_patcher.start()
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
        self.client = TestClient(create_app(database_url=self.harness.database_url))

    def tearDown(self) -> None:
        self.client.close()
        self.client.app.state.container.engine.dispose()
        self.harness.close()
        self._system_skills_patcher.stop()
        self._global_skills_patcher.stop()
        self._skills_tempdir.cleanup()
        if self.previous_browser_state_dir is None:
            os.environ.pop("APP_BROWSER_STATE_DIR", None)
        else:
            os.environ["APP_BROWSER_STATE_DIR"] = self.previous_browser_state_dir
        if self.previous_openapi_provider_paths is None:
            os.environ.pop("APP_TOOL_OPENAPI_PROVIDER_PATHS", None)
        else:
            os.environ["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = (
                self.previous_openapi_provider_paths
            )


__all__ = [
    "AgentProfileSettings",
    "FakeCdpServer",
    "FakeChromeMcpClientPool",
    "FakePlaywrightCdpSessionPool",
    "HttpModuleTestCase",
    "ListSessionMessagesInput",
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
    "RegisterToolInput",
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
