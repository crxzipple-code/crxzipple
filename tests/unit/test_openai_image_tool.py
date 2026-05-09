from __future__ import annotations

import asyncio
import base64
import json
import os
from typing import Any
from unittest.mock import patch

import httpx

from crxzipple.modules.orchestration.domain import (
    InboundInstruction,
    OrchestrationRun,
)
from crxzipple.modules.orchestration.application.tool_resolver import ToolResolver

from tests.unit.tool_test_support import *  # noqa: F403
from tests.unit.tool_runtime_test_support import process_next_background_tool_run


_PNG_1X1 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII=",
)


class _FakeOpenAIImageResponse:
    def __init__(
        self,
        payload: dict[str, Any],
        *,
        status_code: int = 200,
        content: bytes = b"",
        headers: dict[str, str] | None = None,
    ) -> None:
        self._payload = payload
        self.status_code = status_code
        self.content = content
        self.headers = dict(headers or {})
        self.text = json.dumps(payload, ensure_ascii=False)

    def json(self) -> dict[str, Any]:
        return dict(self._payload)


class _FakeOpenAIImageClient:
    response_payload: dict[str, Any] = {"data": []}
    response_status_code: int = 200
    post_exception: Exception | None = None
    posts: list[dict[str, Any]] = []

    def __init__(self, *, timeout: float) -> None:
        self.timeout = timeout

    async def __aenter__(self) -> "_FakeOpenAIImageClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
    ) -> _FakeOpenAIImageResponse:
        self.__class__.posts.append(
            {
                "url": url,
                "headers": dict(headers),
                "json": dict(json),
                "timeout": self.timeout,
            },
        )
        if self.__class__.post_exception is not None:
            raise self.__class__.post_exception
        return _FakeOpenAIImageResponse(
            dict(self.__class__.response_payload),
            status_code=self.__class__.response_status_code,
        )


class OpenAIImageToolTestCase(ToolTestCaseBase):
    def setUp(self) -> None:
        super().setUp()
        self.previous_openai_api_key = os.environ.get("OPENAI_API_KEY")
        self.previous_openai_image_model = os.environ.get("OPENAI_IMAGE_MODEL")
        os.environ["OPENAI_API_KEY"] = "test-openai-key"
        os.environ.pop("OPENAI_IMAGE_MODEL", None)
        _FakeOpenAIImageClient.posts = []
        _FakeOpenAIImageClient.response_status_code = 200
        _FakeOpenAIImageClient.post_exception = None

    def _execute_background_image_tool(
        self,
        *,
        tool_id: str,
        arguments: dict[str, Any],
    ):
        queued_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id=tool_id,
                    arguments=arguments,
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )
        self.assertEqual(queued_run.status, ToolRunStatus.QUEUED)
        processed_run = queued_run
        for attempt_index in range(queued_run.max_attempts):
            next_run = process_next_background_tool_run(
                self.container,
                worker_id=f"openai-image-worker-{attempt_index + 1}",
            )
            self.assertIsNotNone(next_run)
            assert next_run is not None
            processed_run = next_run
            if processed_run.is_terminal():
                break
        return processed_run

    def tearDown(self) -> None:
        if self.previous_openai_api_key is None:
            os.environ.pop("OPENAI_API_KEY", None)
        else:
            os.environ["OPENAI_API_KEY"] = self.previous_openai_api_key
        if self.previous_openai_image_model is None:
            os.environ.pop("OPENAI_IMAGE_MODEL", None)
        else:
            os.environ["OPENAI_IMAGE_MODEL"] = self.previous_openai_image_model
        super().tearDown()

    def test_generate_registers_as_openai_api_tool_and_externalizes_image(self) -> None:
        _FakeOpenAIImageClient.response_payload = {
            "data": [
                {
                    "b64_json": base64.b64encode(b"fake-openai-png").decode("ascii"),
                    "revised_prompt": "A compact runtime dashboard.",
                },
            ],
        }
        register_scanned_tool_packages(self.container, include_openapi=False)
        self.container.tool_service.discover_local_tools()

        tool = self.container.tool_service.get_tool("openai_image_generate")
        self.assertEqual(tool.access_requirement_sets, (("env:OPENAI_API_KEY",),))
        self.assertEqual(tool.required_effect_ids, ("remote_tool_execution",))
        self.assertEqual(tool.execution_support.supported_modes, (ToolMode.BACKGROUND,))
        self.assertIn("surface:interactive", tool.tags)

        with patch("tools.openai_image.local.httpx.AsyncClient", _FakeOpenAIImageClient):
            tool_run = self._execute_background_image_tool(
                tool_id="openai_image_generate",
                arguments={
                    "prompt": "Design a clean agent runtime dashboard.",
                    "size": "1024x1024",
                },
            )

        assert tool_run.result is not None
        self.assertEqual(
            _FakeOpenAIImageClient.posts[0]["url"],
            "https://api.openai.com/v1/images/generations",
        )
        self.assertEqual(
            _FakeOpenAIImageClient.posts[0]["headers"]["Authorization"],
            "Bearer test-openai-key",
        )
        self.assertEqual(_FakeOpenAIImageClient.posts[0]["json"]["model"], "gpt-image-2")
        self.assertEqual(
            _FakeOpenAIImageClient.posts[0]["json"]["prompt"],
            "Design a clean agent runtime dashboard.",
        )
        self.assertEqual(tool_run.result.blocks[0]["type"], "text")
        self.assertEqual(tool_run.result.blocks[1]["type"], "image_ref")
        artifact = self.container.artifact_service.get_artifact(
            tool_run.result.blocks[1]["artifact_id"],
        )
        self.assertEqual(artifact.mime_type, "image/png")
        self.assertEqual(artifact.name, "openai-gpt-image-2-generate-1.png")
        self.assertNotIn("fake-openai-png", json.dumps(tool_run.result.details))

    def test_generate_uses_openai_image_model_env_override(self) -> None:
        os.environ["OPENAI_IMAGE_MODEL"] = "dall-e-3"
        _FakeOpenAIImageClient.response_payload = {
            "data": [
                {
                    "b64_json": base64.b64encode(b"fake-openai-png").decode("ascii"),
                },
            ],
        }
        register_scanned_tool_packages(self.container, include_openapi=False)
        self.container.tool_service.discover_local_tools()

        with patch("tools.openai_image.local.httpx.AsyncClient", _FakeOpenAIImageClient):
            self._execute_background_image_tool(
                tool_id="openai_image_generate",
                arguments={"prompt": "A small blue folder icon."},
            )

        self.assertEqual(_FakeOpenAIImageClient.posts[0]["json"]["model"], "dall-e-3")

    def test_generate_reports_openai_org_verification_errors_clearly(self) -> None:
        _FakeOpenAIImageClient.response_status_code = 403
        _FakeOpenAIImageClient.response_payload = {
            "error": {
                "message": (
                    "Your organization must be verified to use the model `gpt-image-2`. "
                    "Please go to: https://platform.openai.com/settings/organization/general "
                    "and click on Verify Organization. If you just verified, it can take "
                    "up to 15 minutes for access to propagate."
                ),
            },
        }
        register_scanned_tool_packages(self.container, include_openapi=False)
        self.container.tool_service.discover_local_tools()

        with patch("tools.openai_image.local.httpx.AsyncClient", _FakeOpenAIImageClient):
            tool_run = self._execute_background_image_tool(
                tool_id="openai_image_generate",
                arguments={"prompt": "A small blue folder icon."},
            )

        self.assertEqual(tool_run.status, ToolRunStatus.FAILED)
        assert tool_run.error_message is not None
        self.assertIn("organization verification is required", tool_run.error_message)
        self.assertIn("OPENAI_IMAGE_MODEL", tool_run.error_message)

    def test_generate_reports_openai_timeout_with_retry_guidance(self) -> None:
        _FakeOpenAIImageClient.post_exception = httpx.ReadTimeout(" ")
        register_scanned_tool_packages(self.container, include_openapi=False)
        self.container.tool_service.discover_local_tools()

        with patch("tools.openai_image.local.httpx.AsyncClient", _FakeOpenAIImageClient):
            tool_run = self._execute_background_image_tool(
                tool_id="openai_image_generate",
                arguments={"prompt": "A slow cinematic poster."},
            )

        self.assertEqual(tool_run.status, ToolRunStatus.FAILED)
        assert tool_run.error_message is not None
        self.assertIn("timed out after 300s", tool_run.error_message)
        self.assertIn("OPENAI_IMAGE_TIMEOUT_SECONDS", tool_run.error_message)

    def test_edit_sends_artifact_as_data_url_and_externalizes_result_image(self) -> None:
        source = self.container.artifact_service.create_artifact(
            data=_PNG_1X1,
            mime_type="image/png",
            name="source.png",
        )
        _FakeOpenAIImageClient.response_payload = {
            "data": [
                {
                    "b64_json": base64.b64encode(b"edited-openai-png").decode("ascii"),
                },
            ],
        }
        register_scanned_tool_packages(self.container, include_openapi=False)
        self.container.tool_service.discover_local_tools()

        tool = self.container.tool_service.get_tool("openai_image_edit")
        self.assertEqual(tool.access_requirement_sets, (("env:OPENAI_API_KEY",),))
        self.assertEqual(
            tool.required_effect_ids,
            ("remote_tool_execution", "sensitive_operation_confirmation"),
        )
        self.assertEqual(tool.execution_support.supported_modes, (ToolMode.BACKGROUND,))
        self.assertIn("surface:interactive", tool.tags)

        with patch("tools.openai_image.local.httpx.AsyncClient", _FakeOpenAIImageClient):
            tool_run = self._execute_background_image_tool(
                tool_id="openai_image_edit",
                arguments={
                    "prompt": "Add a soft blue glow.",
                    "image_artifact_id": source.id,
                    "output_format": "webp",
                },
            )

        assert tool_run.result is not None
        request_payload = _FakeOpenAIImageClient.posts[0]["json"]
        self.assertEqual(
            _FakeOpenAIImageClient.posts[0]["url"],
            "https://api.openai.com/v1/images/edits",
        )
        self.assertEqual(request_payload["model"], "gpt-image-2")
        self.assertEqual(request_payload["images"][0]["type"], "input_image")
        self.assertTrue(
            request_payload["images"][0]["image_url"].startswith(
                "data:image/png;base64,",
            ),
        )
        self.assertEqual(tool_run.result.blocks[1]["type"], "image_ref")
        artifact = self.container.artifact_service.get_artifact(
            tool_run.result.blocks[1]["artifact_id"],
        )
        self.assertEqual(artifact.mime_type, "image/webp")
        self.assertEqual(artifact.name, "openai-gpt-image-2-edit-1.webp")
        self.assertNotIn("data:image/png", json.dumps(tool_run.result.details))

    def test_image_tools_declare_the_same_openai_access_requirement(self) -> None:
        register_scanned_tool_packages(self.container, include_openapi=False)
        self.container.tool_service.discover_local_tools()

        generate = self.container.tool_service.get_tool("openai_image_generate")
        edit = self.container.tool_service.get_tool("openai_image_edit")

        self.assertEqual(
            generate.access_requirement_sets,
            (("env:OPENAI_API_KEY",),),
        )
        self.assertEqual(
            edit.access_requirement_sets,
            generate.access_requirement_sets,
        )

    def test_image_tools_are_visible_to_interactive_orchestration_runs(self) -> None:
        register_scanned_tool_packages(self.container, include_openapi=False)
        self.container.tool_service.discover_local_tools()

        run = OrchestrationRun.accept(
            run_id="run-openai-image-tools",
            inbound_instruction=InboundInstruction(
                source="web",
                content="generate an image",
            ),
        )
        resolver = ToolResolver(
            tool_catalog=self.container.tool_service,
            authorization_port=self.container.authorization_service,
            access_port=self.container.access_service,
        )

        with patch.dict("os.environ", {"OPENAI_API_KEY": "test-openai-key"}):
            resolved = resolver.resolve(run)

        tool_ids = {item.tool.id for item in resolved.tools}
        self.assertIn("openai_image_generate", tool_ids)
        self.assertIn("openai_image_edit", tool_ids)
        assert resolved.by_name("openai_image_generate") is not None
        assert resolved.by_name("openai_image_edit") is not None
        self.assertEqual(
            resolved.by_name("openai_image_generate").target.mode,
            ToolMode.BACKGROUND,
        )
        self.assertEqual(
            resolved.by_name("openai_image_edit").target.mode,
            ToolMode.BACKGROUND,
        )
        self.assertIsNone(resolved.blocked_access_by_name("openai_image_generate"))
        self.assertIsNone(resolved.blocked_access_by_name("openai_image_edit"))
