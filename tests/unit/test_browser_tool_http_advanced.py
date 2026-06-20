from __future__ import annotations

import asyncio
import json
import tempfile
from types import SimpleNamespace

from crxzipple.modules.artifacts.application.services import ArtifactApplicationService
from crxzipple.modules.artifacts.infrastructure.filesystem_store import FilesystemArtifactStore
from tests.unit.http_test_support import HttpModuleTestCase
from tests.unit.test_browser_tool_http import (
    network_handler,
    page_action_handler,
    snapshot_handler,
)


class BrowserToolHttpAdvancedTestCase(HttpModuleTestCase):
    def test_browser_network_inspect_uses_compact_sanitized_summary(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _ToolApplication:
            def execute_page_action(self, **kwargs):  # noqa: ANN003, ANN201
                assert kwargs["kind"] == "network-inspect"
                return SimpleNamespace(
                    payload={
                        "ok": True,
                        "command": {"kind": "network-inspect"},
                        "value": {
                            "result": {
                                "kind": "network-inspect",
                                "url": "https://example.com/app?token=secret",
                                "performance": {
                                    "entries": [
                                        {
                                            "name": "https://api.example.com/v1/search?token=secret",
                                            "entry_type": "resource",
                                            "duration": 42,
                                        },
                                    ],
                                },
                                "cdp": {
                                    "metrics": {"metrics": [{"name": "TaskDuration"}]},
                                    "resource_tree": {
                                        "frame_count": 1,
                                        "resource_count": 2,
                                        "types": {"Image": 1, "Script": 1},
                                        "resources": [
                                            {
                                                "url": "https://api.example.com/v1/search?token=secret",
                                                "type": "Script",
                                            },
                                            {
                                                "url": "data:image/png;base64,[omitted 2488 chars]",
                                                "type": "Image",
                                            },
                                        ],
                                        "truncated": True,
                                        "raw_omitted": True,
                                    },
                                },
                            },
                        },
                    },
                    runtime_metadata={},
                )

        container = SimpleNamespace(
            browser_tool_application=_ToolApplication(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = network_handler(container, tool_id="browser.network.inspect")
        assert handler is not None

        result = asyncio.run(handler({"target_id": "tab-1"}))

        summary = result.content[0]["text"]
        self.assertIn("Network inspection:", summary)
        self.assertIn("api.example.com/v1/search", summary)
        self.assertIn("data:image/png;base64,[omitted 2488 chars]", summary)
        self.assertNotIn("[omitted 20 chars]", summary)
        self.assertNotIn("token=secret", summary)
        self.assertEqual(
            result.details["value"]["result"]["performance"]["entries"][0]["name"],
            "https://api.example.com/v1/search?token=secret",
        )

    def test_browser_network_list_requests_uses_compact_top_level_summary(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _ToolApplication:
            def execute_page_action(self, **kwargs):  # noqa: ANN003, ANN201
                assert kwargs["kind"] == "network-list-requests"
                return SimpleNamespace(
                    payload={
                        "ok": True,
                        "command": {"kind": "network-list-requests"},
                        "value": {
                            "result": {
                                "capture_id": "cap-1",
                                "total": 2,
                                "requests": [
                                    {
                                        "request_id": "req-1",
                                        "method": "POST",
                                        "url": "https://api.example.com/v1/search?token=secret",
                                        "status": 200,
                                        "resource_type": "xhr",
                                        "mime_type": "application/json",
                                        "duration_ms": 123.4,
                                        "response_body": {"large": ["detail-only"] * 200},
                                    },
                                    {
                                        "request_id": "req-2",
                                        "method": "GET",
                                        "url": "https://static.example.com/app.js",
                                        "status": 304,
                                        "resource_type": "script",
                                    },
                                ],
                            },
                        },
                    },
                    runtime_metadata={},
                )

        container = SimpleNamespace(
            browser_tool_application=_ToolApplication(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = network_handler(container, tool_id="browser.network.list_requests")
        assert handler is not None

        result = asyncio.run(handler({"capture_id": "cap-1", "limit": 10}))

        summary = result.content[0]["text"]
        self.assertIn("Network requests (cap-1): 2 shown of 2", summary)
        self.assertIn("200 POST xhr api.example.com/v1/search", summary)
        self.assertNotIn("token=secret", summary)
        self.assertNotIn("detail-only", summary)
        self.assertEqual(
            result.details["value"]["result"]["requests"][0]["response_body"]["large"][0],
            "detail-only",
        )

    def test_browser_network_start_capture_surfaces_capture_id_next_step(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _ToolApplication:
            def execute_page_action(self, **kwargs):  # noqa: ANN003, ANN201
                assert kwargs["kind"] == "network-start-capture"
                return SimpleNamespace(
                    payload={
                        "ok": True,
                        "command": {"kind": "network-start-capture"},
                        "value": {
                            "result": {
                                "kind": "network-start-capture",
                                "capture": {
                                    "capture_id": "cap-generated",
                                    "target_id": "tab-1",
                                    "status": "active",
                                },
                                "request_count": 0,
                            },
                        },
                    },
                    runtime_metadata={},
                )

        container = SimpleNamespace(
            browser_tool_application=_ToolApplication(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = network_handler(container, tool_id="browser.network.start_capture")
        assert handler is not None

        result = asyncio.run(handler({"target_id": "tab-1"}))

        summary = result.content[0]["text"]
        self.assertIn("Network capture started:", summary)
        self.assertIn("- Capture: cap-generated", summary)
        self.assertIn("- Use capture_id: cap-generated", summary)
        self.assertIn("trigger the page action or runtime probe", summary)
        self.assertIn("browser.network.list_requests", summary)

    def test_browser_code_search_omits_large_snippets_from_top_level_content(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _ToolApplication:
            def execute_page_action(self, **kwargs):  # noqa: ANN003, ANN201
                assert kwargs["kind"] == "code-search"
                long_snippet = "1: " + ("const x = 'flight';" * 140)
                return SimpleNamespace(
                    payload={
                        "ok": True,
                        "command": {"kind": "code-search"},
                        "value": {
                            "result": {
                                "kind": "code-search",
                                "query": "flight",
                                "match_count": 3,
                                "matched_scripts": 1,
                                "matches": [
                                    {
                                        "script_id": "script-big",
                                        "url": "https://example.test/app.js",
                                        "source_chars": 2_000_000,
                                        "matches": [
                                            {
                                                "field": "source",
                                                "line_number": 1,
                                                "column": 9,
                                                "snippet": long_snippet,
                                            },
                                            {
                                                "field": "source",
                                                "line_number": 1,
                                                "column": 40,
                                                "snippet": long_snippet,
                                            },
                                            {
                                                "field": "source",
                                                "line_number": 1,
                                                "column": 80,
                                                "snippet": long_snippet,
                                            },
                                        ],
                                    },
                                ],
                            },
                        },
                    },
                    runtime_metadata={},
                )

        container = SimpleNamespace(
            browser_tool_application=_ToolApplication(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = page_action_handler(container, tool_id="browser.code.search")
        assert handler is not None

        result = asyncio.run(handler({"kind": "code-search", "query": "flight"}))

        summary = result.content[0]["text"]
        self.assertIn("Browser code search:", summary)
        self.assertIn("script-big", summary)
        self.assertIn("script_id=script-big", summary)
        self.assertIn("line 1, column 9", summary)
        self.assertIn("browser.evaluate", summary)
        self.assertIn("stop broad searching", summary)
        self.assertIn("more matches in details", summary)
        self.assertLess(len(summary), 1200)
        self.assertNotIn("const x = 'flight';" * 20, summary)
        self.assertIn(
            "const x = 'flight';" * 20,
            result.details["value"]["result"]["matches"][0]["matches"][0]["snippet"],
        )

    def test_browser_network_response_body_omits_large_body_from_top_level_content(self) -> None:
        large_body = "{\"items\":[" + ",".join('"detail-only"' for _ in range(300)) + "]}"

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _ToolApplication:
            def execute_page_action(self, **kwargs):  # noqa: ANN003, ANN201
                assert kwargs["kind"] == "network-get-response-body"
                return SimpleNamespace(
                    payload={
                        "ok": True,
                        "command": {"kind": "network-get-response-body"},
                        "value": {
                            "result": {
                                "capture_id": "cap-1",
                                "request_id": "req-1",
                                "url": "https://api.example.com/v1/search?token=secret",
                                "status": 200,
                                "mime_type": "application/json",
                                "size_bytes": len(large_body),
                                "body": large_body,
                            },
                        },
                    },
                    runtime_metadata={},
                )

        container = SimpleNamespace(
            browser_tool_application=_ToolApplication(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = network_handler(container, tool_id="browser.network.get_response_body")
        assert handler is not None

        result = asyncio.run(handler({"capture_id": "cap-1", "request_id": "req-1"}))

        summary = result.content[0]["text"]
        self.assertIn("Network response body:", summary)
        self.assertIn("Body: omitted from top-level content; see details.", summary)
        self.assertNotIn("detail-only", summary)
        self.assertNotIn("token=secret", summary)
        self.assertEqual(result.details["value"]["result"]["body"], large_body)

    def test_browser_network_fetch_large_body_is_written_as_artifact(self) -> None:
        large_body = "{\"items\":[" + ",".join('"detail-only"' for _ in range(300)) + "]}"

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _ToolApplication:
            def execute_page_action(self, **kwargs):  # noqa: ANN003, ANN201
                assert kwargs["kind"] == "network-fetch-as-page"
                return SimpleNamespace(
                    payload={
                        "ok": True,
                        "command": {"kind": "network-fetch-as-page"},
                        "value": {
                            "result": {
                                "kind": "network-fetch-as-page",
                                "url": "https://api.example.com/v1/search?token=secret",
                                "status": 200,
                                "mime_type": "application/json",
                                "size_bytes": len(large_body),
                                "body": large_body,
                                "body_preview": "{\"items\":",
                                "body_omitted": False,
                                "response_summary": {
                                    "ok": True,
                                    "status": 200,
                                    "mime_type": "application/json",
                                    "size_bytes": len(large_body),
                                },
                            },
                        },
                    },
                    runtime_metadata={},
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_service = ArtifactApplicationService(
                FilesystemArtifactStore(temp_dir),
            )
            container = SimpleNamespace(
                browser_tool_application=_ToolApplication(),
                browser_system_config_store=_Store(),
                artifact_service=artifact_service,
                settings=SimpleNamespace(browser_enabled=True),
            )
            handler = network_handler(container, tool_id="browser.network.fetch_as_page")
            assert handler is not None

            result = asyncio.run(handler({"url": "/v1/search"}))

            summary = result.content[0]["text"]
            self.assertIn("Network response body:", summary)
            self.assertNotIn("detail-only", summary)
            file_block = result.content[1]
            self.assertEqual(file_block["type"], "file_ref")
            artifact = artifact_service.get_artifact(file_block["artifact_id"])
            self.assertEqual(artifact.mime_type, "application/json")
            self.assertTrue(artifact.name.endswith(".json"))
            binary = artifact_service.resolve_variant(artifact.id)
            self.assertIn("detail-only", binary.path.read_text(encoding="utf-8"))
            result_payload = result.details["value"]["result"]
            self.assertNotIn("body", result_payload)
            self.assertTrue(result_payload["body_removed_from_details"])
            self.assertEqual(result.metadata["browser_artifact_ids"], [artifact.id])
            self.assertEqual(result.metadata["artifact_ids"], [artifact.id])

    def test_browser_script_inspect_large_preview_is_written_as_artifact(self) -> None:
        large_preview = "\n".join(f"{line}: const value_{line} = 'detail-only';" for line in range(1, 260))

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _ToolApplication:
            def execute_page_action(self, **kwargs):  # noqa: ANN003, ANN201
                assert kwargs["kind"] == "script-inspect"
                return SimpleNamespace(
                    payload={
                        "ok": True,
                        "command": {"kind": "script-inspect"},
                        "value": {
                            "result": {
                                "kind": "script-inspect",
                                "script_id": "script-1",
                                "script": {
                                    "script_id": "script-1",
                                    "url": "https://example.com/assets/app.js",
                                },
                                "source_chars": len(large_preview),
                                "start_line": 1,
                                "end_line": 259,
                                "source_preview": large_preview,
                                "truncated": True,
                            },
                        },
                    },
                    runtime_metadata={},
                )

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_service = ArtifactApplicationService(
                FilesystemArtifactStore(temp_dir),
            )
            container = SimpleNamespace(
                browser_tool_application=_ToolApplication(),
                browser_system_config_store=_Store(),
                artifact_service=artifact_service,
                settings=SimpleNamespace(browser_enabled=True),
            )
            handler = page_action_handler(container)
            assert handler is not None

            result = asyncio.run(handler({"kind": "script-inspect", "script_id": "script-1"}))

            summary = result.content[0]["text"]
            self.assertIn("Browser script inspect:", summary)
            self.assertIn("Source preview: omitted from top-level content", summary)
            self.assertNotIn("detail-only", summary)
            file_block = result.content[1]
            self.assertEqual(file_block["type"], "file_ref")
            artifact = artifact_service.get_artifact(file_block["artifact_id"])
            self.assertEqual(artifact.mime_type, "application/javascript")
            binary = artifact_service.resolve_variant(artifact.id)
            self.assertIn("detail-only", binary.path.read_text(encoding="utf-8"))
            result_payload = result.details["value"]["result"]
            self.assertNotIn("source_preview", result_payload)
            self.assertTrue(result_payload["source_preview_removed_from_details"])
            self.assertEqual(result.metadata["browser_artifact_ids"], [artifact.id])
            self.assertEqual(result.metadata["artifact_ids"], [artifact.id])

    def test_browser_script_extract_request_formats_endpoint_candidates(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _ToolApplication:
            def execute_page_action(self, **kwargs):  # noqa: ANN003, ANN201
                assert kwargs["kind"] == "script-extract-request"
                return SimpleNamespace(
                    payload={
                        "ok": True,
                        "command": {"kind": "script-extract-request"},
                        "value": {
                            "result": {
                                "kind": "script-extract-request",
                                "script_id": "script-1",
                                "script": {
                                    "script_id": "script-1",
                                    "url": "https://example.com/assets/app.js",
                                },
                                "source_chars": 2048,
                                "start_line": 12,
                                "end_line": 12,
                                "start_column": 120,
                                "end_column": 960,
                                "focus_terms": ["getShopping"],
                                "candidate_count": 1,
                                "candidates": [
                                    {
                                        "endpoint": "/portal/v3/shopping/briefInfo",
                                        "endpoint_kind": "absolute_path",
                                        "line_number": 12,
                                        "column": 320,
                                        "method_candidates": ["POST"],
                                        "client_method_candidates": ["http.post"],
                                        "payload_key_candidates": ["depCityCode", "arrCityCode"],
                                        "confidence": "high",
                                        "evidence_preview": "return http.post('/portal/v3/shopping/briefInfo', {depCityCode: payload.depCityCode});",
                                    },
                                ],
                            },
                        },
                    },
                    runtime_metadata={},
                )

        container = SimpleNamespace(
            browser_tool_application=_ToolApplication(),
            browser_system_config_store=_Store(),
            artifact_service=None,
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = page_action_handler(container)
        assert handler is not None

        result = asyncio.run(handler({"kind": "script-extract-request", "script_id": "script-1"}))

        summary = result.content[0]["text"]
        self.assertIn("Browser script request extract:", summary)
        self.assertIn("/portal/v3/shopping/briefInfo", summary)
        self.assertIn("Method hints: POST", summary)
        self.assertIn("Payload keys: depCityCode, arrCityCode", summary)
        self.assertIn("one JSON object argument", summary)

    def test_browser_action_handler_promotes_evaluate_fn_alias(self) -> None:
        captured_request = None

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                nonlocal captured_request
                captured_request = request
                return {"ok": True}

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return result

        container = SimpleNamespace(
            browser_facade=_Facade(),
            browser_result_serializer=_Serializer(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = page_action_handler(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "kind": "evaluate",
                    "ref": "r1",
                    "fn": "(el) => el.textContent",
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.kind, "evaluate")
        self.assertEqual(captured_request.ref, "r1")
        self.assertEqual(captured_request.payload["fn"], "(el) => el.textContent")
        self.assertEqual(result.details, {"ok": True})

    def test_browser_action_handler_promotes_evaluate_script_alias(self) -> None:
        captured_request = None

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                nonlocal captured_request
                captured_request = request
                return {"ok": True}

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return result

        container = SimpleNamespace(
            browser_facade=_Facade(),
            browser_result_serializer=_Serializer(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = page_action_handler(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "kind": "evaluate",
                    "script": "() => document.body.innerText",
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.kind, "evaluate")
        self.assertEqual(captured_request.payload["expression"], "() => document.body.innerText")
        self.assertEqual(result.details, {"ok": True})

    def test_browser_action_handler_surfaces_evaluate_result_in_content(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                return {"ok": True}

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return {
                    "ok": True,
                    "message": "Executed evaluate via cdp-backed-playwright.",
                    "command": {
                        "kind": "evaluate",
                    },
                    "value": {
                        "result": {
                            "value": {
                                "title": "frog 图片 - Google Search",
                                "count": 12,
                            },
                        },
                    },
                }

        container = SimpleNamespace(
            browser_facade=_Facade(),
            browser_result_serializer=_Serializer(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = page_action_handler(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "kind": "evaluate",
                    "fn": "() => ({ title: document.title, count: 12 })",
                },
            ),
        )

        self.assertEqual(
            list(result.blocks),
            [
                {
                    "type": "text",
                    "text": 'Evaluate result:\n```json\n{\n  "count": 12,\n  "title": "frog 图片 - Google Search"\n}\n```',
                }
            ],
        )
        self.assertNotIn("evidence_path_key", result.metadata["browser_evidence"])

    def test_browser_action_handler_surfaces_evaluate_envelope_result_in_content(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                return {"ok": True}

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return {
                    "ok": True,
                    "message": "Executed evaluate via cdp-backed-playwright.",
                    "command": {
                        "kind": "evaluate",
                    },
                    "value": {
                        "action_envelope": {
                            "kind": "evaluate",
                            "tool_ok": True,
                            "page_effect_ok": False,
                            "page_effect_status": "no_observable_change",
                            "before": {"url": "https://example.test"},
                            "after": {"url": "https://example.test"},
                            "changes": {},
                            "result": {
                                "nuxt": True,
                                "shopping_keys": ["getShopping", "getFareDetail"],
                            },
                            "next_action": "use-action-trace-or-observe",
                            "errors": [],
                        },
                    },
                }

        container = SimpleNamespace(
            browser_facade=_Facade(),
            browser_result_serializer=_Serializer(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = page_action_handler(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "kind": "evaluate",
                    "script": "() => ({ nuxt: true })",
                },
            ),
        )

        text = result.blocks[0]["text"]
        self.assertIn("Browser evaluate completed.", text)
        self.assertIn("Evaluate result:", text)
        self.assertIn('"getShopping"', text)
        self.assertIn('"nuxt": true', text)

    def test_browser_snapshot_handler_promotes_mode_compact_and_depth(self) -> None:
        captured_request = None

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                nonlocal captured_request
                captured_request = request
                return {"ok": True}

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return result

        container = SimpleNamespace(
            browser_facade=_Facade(),
            browser_result_serializer=_Serializer(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = snapshot_handler(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "format": "interactive",
                    "mode": "efficient",
                    "compact": True,
                    "depth": 4,
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.kind, "snapshot")
        self.assertEqual(captured_request.payload["format"], "interactive")
        self.assertEqual(captured_request.payload["mode"], "efficient")
        self.assertTrue(captured_request.payload["compact"])
        self.assertEqual(captured_request.payload["depth"], 4)
        self.assertEqual(result.details, {"ok": True})

    def test_browser_snapshot_handler_surfaces_snapshot_body_in_content(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                return {"ok": True}

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return {
                    "ok": True,
                    "message": "Executed snapshot via cdp-backed-playwright.",
                    "command": {
                        "kind": "snapshot",
                    },
                    "value": {
                        "result": {
                            "kind": "snapshot",
                            "format": "text",
                            "value": "Search results for frog 图片",
                        },
                    },
                }

        container = SimpleNamespace(
            browser_facade=_Facade(),
            browser_result_serializer=_Serializer(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = snapshot_handler(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "format": "text",
                },
            ),
        )

        self.assertEqual(
            list(result.blocks),
            [
                {
                    "type": "text",
                    "text": "Snapshot (text):\nSearch results for frog 图片",
                },
            ],
        )

    def test_browser_snapshot_handler_promotes_refs_mode(self) -> None:
        captured_request = None

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                nonlocal captured_request
                captured_request = request
                return {"ok": True}

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return result

        container = SimpleNamespace(
            browser_facade=_Facade(),
            browser_result_serializer=_Serializer(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = snapshot_handler(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "refs_mode": "role",
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.kind, "snapshot")
        self.assertEqual(captured_request.payload["refs_mode"], "role")
        self.assertEqual(result.details, {"ok": True})

    def test_browser_snapshot_handler_promotes_frame_selector(self) -> None:
        captured_request = None

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                nonlocal captured_request
                captured_request = request
                return {"ok": True}

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return result

        container = SimpleNamespace(
            browser_facade=_Facade(),
            browser_result_serializer=_Serializer(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = snapshot_handler(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "frame_selector": "iframe.booking",
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.kind, "snapshot")
        self.assertEqual(captured_request.payload["frame_selector"], "iframe.booking")
        self.assertEqual(result.details, {"ok": True})

    def test_browser_snapshot_handler_promotes_active_overlay(self) -> None:
        captured_request = None

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                nonlocal captured_request
                captured_request = request
                return {"ok": True}

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return result

        container = SimpleNamespace(
            browser_facade=_Facade(),
            browser_result_serializer=_Serializer(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = snapshot_handler(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "active_overlay": True,
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.payload["active_overlay"], True)
        self.assertEqual(result.details, {"ok": True})

    def test_browser_snapshot_handler_promotes_overlay_source_selector(self) -> None:
        captured_request = None

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                nonlocal captured_request
                captured_request = request
                return {"ok": True}

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return result

        container = SimpleNamespace(
            browser_facade=_Facade(),
            browser_result_serializer=_Serializer(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = snapshot_handler(container)
        assert handler is not None

        asyncio.run(
            handler(
                {
                    "active_overlay": True,
                    "overlay_source_selector": "#depart-city",
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.payload["overlay_source_selector"], "#depart-city")

    def test_browser_snapshot_handler_passes_selector_root(self) -> None:
        captured_request = None

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                nonlocal captured_request
                captured_request = request
                return {"ok": True}

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return result

        container = SimpleNamespace(
            browser_facade=_Facade(),
            browser_result_serializer=_Serializer(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = snapshot_handler(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "selector": "#booking",
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.kind, "snapshot")
        self.assertEqual(captured_request.selector, "#booking")
        self.assertEqual(result.details, {"ok": True})

    def test_browser_action_handler_promotes_advanced_top_level_arguments(self) -> None:
        captured_request = None

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                nonlocal captured_request
                captured_request = request
                return {"ok": True}

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return result

        container = SimpleNamespace(
            browser_facade=_Facade(),
            browser_result_serializer=_Serializer(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = page_action_handler(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "kind": "evaluate",
                    "expression": "() => document.title",
                    "arg": {"debug": True},
                    "timeout_ms": 3000,
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.profile_name, "crxzipple")
        self.assertEqual(captured_request.kind, "evaluate")
        self.assertEqual(captured_request.payload["expression"], "() => document.title")
        self.assertEqual(captured_request.payload["arg"], {"debug": True})
        self.assertEqual(result.details, {"ok": True})

    def test_browser_action_handler_promotes_resize_dimensions(self) -> None:
        captured_request = None

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                nonlocal captured_request
                captured_request = request
                return {"ok": True}

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return result

        container = SimpleNamespace(
            browser_facade=_Facade(),
            browser_result_serializer=_Serializer(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = page_action_handler(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "kind": "resize",
                    "width": 1280,
                    "height": 720,
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.kind, "resize")
        self.assertEqual(captured_request.payload["width"], 1280)
        self.assertEqual(captured_request.payload["height"], 720)
        self.assertEqual(result.details, {"ok": True})

    def test_browser_action_handler_promotes_batch_arguments(self) -> None:
        captured_request = None

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                nonlocal captured_request
                captured_request = request
                return {"ok": True}

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return result

        container = SimpleNamespace(
            browser_facade=_Facade(),
            browser_result_serializer=_Serializer(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = page_action_handler(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "kind": "batch",
                    "actions": [
                        {"kind": "resize", "width": 800, "height": 600},
                        {"kind": "evaluate", "fn": "() => document.title"},
                    ],
                    "stop_on_error": False,
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.kind, "batch")
        self.assertEqual(len(captured_request.payload["actions"]), 2)
        self.assertFalse(captured_request.payload["stop_on_error"])
        self.assertEqual(result.details, {"ok": True})

    def test_browser_action_handler_persists_screenshot_as_artifact_ref(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                del request
                return {
                    "ok": True,
                    "value": {
                        "kind": "screenshot",
                        "content_type": "image/png",
                        "data": "ZmFrZS1wbmc=",
                    },
                }

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return dict(result)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_service = ArtifactApplicationService(
                FilesystemArtifactStore(temp_dir),
            )
            container = SimpleNamespace(
                browser_facade=_Facade(),
                browser_result_serializer=_Serializer(),
                browser_system_config_store=_Store(),
                artifact_service=artifact_service,
                settings=SimpleNamespace(browser_enabled=True),
            )
            handler = page_action_handler(container)
            self.assertIsNotNone(handler)
            assert handler is not None

            result = asyncio.run(
                handler(
                    {
                        "kind": "screenshot",
                    },
                ),
            )

            self.assertEqual(result.content[0], {"type": "text", "text": "Browser screenshot captured."})
            attachment_block = result.content[1]
            self.assertEqual(attachment_block["type"], "image_ref")
            artifact_id = attachment_block["artifact_id"]
            artifact = artifact_service.get_artifact(artifact_id)
            self.assertEqual(artifact.mime_type, "image/png")
            self.assertEqual(result.metadata["browser_artifact_ids"], [artifact_id])
            self.assertEqual(result.metadata["artifact_ids"], [artifact_id])
            self.assertEqual(
                result.details,
                {
                    "ok": True,
                    "value": {
                        "kind": "screenshot",
                        "content_type": "image/png",
                        "attachment_in_content": True,
                    },
                },
            )

    def test_browser_action_handler_strips_nested_screenshot_data_from_details(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                del request
                return {
                    "ok": True,
                    "value": {
                        "engine": "cdp-backed-playwright",
                        "result": {
                            "kind": "screenshot",
                            "content_type": "image/png",
                            "data": "ZmFrZS1wbmc=",
                        },
                    },
                }

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return dict(result)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_service = ArtifactApplicationService(
                FilesystemArtifactStore(temp_dir),
            )
            container = SimpleNamespace(
                browser_facade=_Facade(),
                browser_result_serializer=_Serializer(),
                browser_system_config_store=_Store(),
                artifact_service=artifact_service,
                settings=SimpleNamespace(browser_enabled=True),
            )
            handler = page_action_handler(container)
            self.assertIsNotNone(handler)
            assert handler is not None

            result = asyncio.run(
                handler(
                    {
                        "kind": "screenshot",
                    },
                ),
            )

            self.assertEqual(result.content[0], {"type": "text", "text": "Browser screenshot captured."})
            self.assertEqual(result.content[1]["type"], "image_ref")
            self.assertEqual(
                result.details,
                {
                    "ok": True,
                    "value": {
                        "engine": "cdp-backed-playwright",
                        "result": {
                            "kind": "screenshot",
                            "content_type": "image/png",
                            "attachment_in_content": True,
                        },
                    },
                },
            )

    def test_browser_action_handler_persists_action_trace_json_artifact(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                self.request = request
                return {
                    "ok": True,
                    "value": {
                        "engine": "cdp-backed-playwright",
                        "result": {
                            "kind": "action-trace",
                            "trace_id": "trace/action:1",
                            "profile_name": "crxzipple",
                            "target_id": "tab-1",
                            "action": {"kind": "click", "ok": True},
                            "diff": {"snapshot_changed": True},
                            "before": {
                                "frame_count": 1,
                                "value": {
                                    "snapshot": "BEFORE_SECRET_SNAPSHOT" * 200,
                                    "refs": [{"ref": "r1"}],
                                },
                            },
                            "after": {
                                "frame_count": 1,
                                "value": {
                                    "snapshot": "AFTER_SECRET_SNAPSHOT" * 200,
                                    "refs": [{"ref": "r2"}, {"ref": "r3"}],
                                },
                            },
                            "network": {"request_count": 0, "requests": []},
                            "storage": {
                                "changed": True,
                                "local": {
                                    "added_keys": ["flight_search"],
                                    "removed_keys": [],
                                    "count_delta": 1,
                                },
                                "session": {
                                    "added_keys": [],
                                    "removed_keys": [],
                                    "count_delta": 0,
                                },
                            },
                            "lifecycle": {
                                "changed": False,
                                "changed_fields": {},
                            },
                            "recommendation": {
                                "next_action": "continue-from-after-snapshot",
                            },
                        },
                    },
                }

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return dict(result)

        with tempfile.TemporaryDirectory() as temp_dir:
            artifact_service = ArtifactApplicationService(
                FilesystemArtifactStore(temp_dir),
            )
            container = SimpleNamespace(
                browser_facade=_Facade(),
                browser_result_serializer=_Serializer(),
                browser_system_config_store=_Store(),
                artifact_service=artifact_service,
                settings=SimpleNamespace(browser_enabled=True),
            )
            handler = page_action_handler(container)
            self.assertIsNotNone(handler)
            assert handler is not None

            result = asyncio.run(handler({"kind": "action-trace", "action": "click"}))

            self.assertEqual(result.content[0]["type"], "text")
            self.assertIn("Before snapshot: ", result.content[0]["text"])
            self.assertIn("After snapshot: ", result.content[0]["text"])
            self.assertIn("chars omitted from text result", result.content[0]["text"])
            self.assertNotIn("BEFORE_SECRET_SNAPSHOT", result.content[0]["text"])
            self.assertNotIn("AFTER_SECRET_SNAPSHOT", result.content[0]["text"])
            trace_block = result.content[1]
            self.assertEqual(trace_block["type"], "file_ref")
            artifact_id = trace_block["artifact_id"]
            artifact = artifact_service.get_artifact(artifact_id)
            self.assertEqual(artifact.mime_type, "application/json")
            self.assertEqual(artifact.name, "trace-action-1.json")
            self.assertEqual(artifact.metadata["attachment_kind"], "action-trace")
            self.assertEqual(artifact.metadata["trace_id"], "trace/action:1")
            binary = artifact_service.resolve_variant(artifact_id)
            payload = json.loads(binary.path.read_text(encoding="utf-8"))
            self.assertEqual(payload["kind"], "action-trace")
            self.assertEqual(payload["trace_id"], "trace/action:1")
            self.assertEqual(payload["storage"]["local"]["added_keys"], ["flight_search"])
            self.assertEqual(result.metadata["browser_artifact_ids"], [artifact_id])
            self.assertEqual(result.metadata["artifact_ids"], [artifact_id])
