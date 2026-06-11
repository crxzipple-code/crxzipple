from __future__ import annotations

import unittest
from types import SimpleNamespace

from crxzipple.modules.browser.application import (
    BrowserObservationService,
    BrowserToolApplicationError,
    BrowserToolExecutionError,
    BrowserToolExecutionResult,
)
from tools.browser.local import BrowserToolDeps, create_browser_observe_handler


class _ToolApplication:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, object]]] = []
        self.snapshot_refs: list[dict[str, object]] = [
            {
                "ref": "r1",
                "selector": "#search",
                "role": "button",
                "label": "Search",
                "text": "Search",
                "tag": "button",
                "evidence": ["native-control", "hit-test"],
            }
        ]
        self.snapshot_root_selector: str | None = None
        self.snapshot_active_overlay = False

    def execute_control(self, **kwargs) -> BrowserToolExecutionResult:  # noqa: ANN003
        self.calls.append(("control", dict(kwargs)))
        return BrowserToolExecutionResult(
            payload={
                "ok": True,
                "value": [
                    {
                        "target_id": "tab-1",
                        "title": "Flights",
                        "url": "https://example.test/flights",
                        "type": "page",
                    }
                ],
            },
            runtime_metadata={"browser_target_id": "tab-1"},
        )

    def execute_page_action(self, **kwargs) -> BrowserToolExecutionResult:  # noqa: ANN003
        self.calls.append(("page-action", dict(kwargs)))
        kind = str(kwargs.get("kind") or "")
        if kind == "snapshot":
            return BrowserToolExecutionResult(
                payload={
                    "ok": True,
                    "target_id": "tab-1",
                    "value": {
                        "tab": {
                            "target_id": "tab-1",
                            "title": "Flights",
                            "url": "https://example.test/flights",
                            "type": "page",
                        },
                        "result": {
                            "kind": "snapshot",
                            "format": "interactive",
                            "ref_count": len(self.snapshot_refs),
                            "frame_count": 1,
                            "value": {
                                "snapshot": "- button \"Search\" [ref=r1]",
                                "refs": list(self.snapshot_refs),
                            },
                            "root_selector": self.snapshot_root_selector,
                            "active_overlay": self.snapshot_active_overlay,
                        },
                    },
                },
                runtime_metadata={"browser_target_id": "tab-1"},
            )
        if kind == "network-inspect":
            return BrowserToolExecutionResult(
                payload={
                    "ok": True,
                    "target_id": "tab-1",
                    "value": {
                        "result": {
                            "kind": "network-inspect",
                            "url": "https://example.test/flights",
                            "performance": {
                                "navigation": [{"name": "nav"}],
                                "resources": [{"name": "app.js"}],
                            },
                            "cdp": {
                                "metrics": {
                                    "metrics": [
                                        {"name": "Timestamp", "value": 1.0},
                                        {"name": "TaskDuration", "value": 0.5},
                                    ]
                                },
                                "resource_tree": {
                                    "frameTree": {
                                        "frame": {"id": "frame-tab-1"},
                                        "resources": [
                                            {"url": "https://example.test/app.js", "type": "Script"}
                                        ],
                                    }
                                },
                            },
                            "errors": [],
                        }
                    },
                },
                runtime_metadata={"browser_target_id": "tab-1"},
            )
        if kind == "runtime-inspect":
            return BrowserToolExecutionResult(
                payload={
                    "ok": True,
                    "target_id": "tab-1",
                    "value": {
                        "result": {
                            "kind": "runtime-inspect",
                            "url": "https://example.test/flights",
                            "page_state": {
                                "ready_state": "complete",
                                "visibility_state": "visible",
                                "focused": True,
                            },
                            "frameworks": {
                                "detected": ["next"],
                                "items": [
                                    {
                                        "key": "next",
                                        "label": "Next.js",
                                        "detected": True,
                                    }
                                ],
                            },
                            "route_hints": [
                                {
                                    "source": "location",
                                    "path": "/flights",
                                    "search": "?from=KMG",
                                    "hash": "",
                                }
                            ],
                            "globals": [
                                {
                                    "name": "__NEXT_DATA__",
                                    "exists": True,
                                    "type": "object",
                                    "constructor_name": "Object",
                                    "keys": ["page", "query"],
                                }
                            ],
                        }
                    },
                },
                runtime_metadata={"browser_target_id": "tab-1"},
            )
        if kind == "network-list-requests":
            return BrowserToolExecutionResult(
                payload={
                    "ok": True,
                    "target_id": "tab-1",
                    "value": {
                        "result": {
                            "kind": "network-list-requests",
                            "request_count": 1,
                            "total_count": 1,
                            "requests": [
                                {
                                    "request_id": "req-1",
                                    "method": "GET",
                                    "url": "https://example.test/api/flights",
                                    "resource_type": "xhr",
                                    "status": 200,
                                }
                            ],
                        }
                    },
                },
                runtime_metadata={"browser_target_id": "tab-1"},
            )
        if kind == "script-list":
            return BrowserToolExecutionResult(
                payload={
                    "ok": True,
                    "target_id": "tab-1",
                    "value": {
                        "result": {
                            "kind": "script-list",
                            "scripts_count": 2,
                            "matched_scripts": 2,
                            "returned_scripts": 2,
                            "scripts": [
                                {
                                    "script_id": "script-1",
                                    "url": "https://example.test/app.js",
                                    "line_count": 120,
                                    "execution_context_id": 1,
                                    "is_module": True,
                                    "source_map_url": "app.js.map",
                                },
                                {
                                    "script_id": "script-2",
                                    "url": "https://example.test/vendor.js",
                                    "line_count": 400,
                                    "execution_context_id": 1,
                                },
                            ],
                            "errors": [],
                        }
                    },
                },
                runtime_metadata={"browser_target_id": "tab-1"},
            )
        if kind == "code-search":
            payload = kwargs.get("payload")
            payload = payload if isinstance(payload, dict) else {}
            return BrowserToolExecutionResult(
                payload={
                    "ok": True,
                    "target_id": "tab-1",
                    "value": {
                        "result": {
                            "kind": "code-search",
                            "query": payload.get("query"),
                            "regex": False,
                            "case_sensitive": False,
                            "scripts_count": 2,
                            "searched_scripts": 2,
                            "matched_scripts": 1,
                            "match_count": 1,
                            "matches": [
                                {
                                    "script_id": "script-1",
                                    "url": "https://example.test/app.js",
                                    "script": {
                                        "script_id": "script-1",
                                        "url": "https://example.test/app.js",
                                        "line_count": 120,
                                    },
                                    "source_available": True,
                                    "source_chars": 4096,
                                    "matches": [
                                        {
                                            "field": "source",
                                            "term": payload.get("query"),
                                            "line_number": 42,
                                            "column": 8,
                                            "snippet": "fetchFlights()",
                                        }
                                    ],
                                }
                            ],
                            "errors": [],
                        }
                    },
                },
                runtime_metadata={"browser_target_id": "tab-1"},
            )
        if kind == "script-find-request":
            payload = kwargs.get("payload")
            payload = payload if isinstance(payload, dict) else {}
            return BrowserToolExecutionResult(
                payload={
                    "ok": True,
                    "target_id": "tab-1",
                    "value": {
                        "result": {
                            "kind": "script-find-request",
                            "request": {
                                "url": payload.get("request_url"),
                                "search_terms": [payload.get("query") or payload.get("path")],
                            },
                            "case_sensitive": False,
                            "scripts_count": 2,
                            "searched_scripts": 2,
                            "candidate_count": 1,
                            "match_count": 1,
                            "candidates": [
                                {
                                    "script_id": "script-1",
                                    "url": "https://example.test/app.js",
                                    "script": {
                                        "script_id": "script-1",
                                        "url": "https://example.test/app.js",
                                        "line_count": 120,
                                    },
                                    "source_available": True,
                                    "source_chars": 4096,
                                    "score": 11,
                                    "matched_terms": [payload.get("query") or payload.get("path")],
                                    "matches": [
                                        {
                                            "field": "source",
                                            "term": payload.get("query") or payload.get("path"),
                                            "line_number": 54,
                                            "column": 12,
                                            "snippet": "/api/flights",
                                        }
                                    ],
                                }
                            ],
                            "errors": [],
                        }
                    },
                },
                runtime_metadata={"browser_target_id": "tab-1"},
            )
        return BrowserToolExecutionResult(
            payload={
                "ok": True,
                "target_id": "tab-1",
                "value": {
                    "result": {
                        "kind": "console",
                        "count": 1,
                        "messages": [
                            {
                                "level": "info",
                                "text": "ready",
                            }
                        ],
                    }
                },
            },
            runtime_metadata={"browser_target_id": "tab-1"},
        )


class BrowserObservationServiceTestCase(unittest.TestCase):
    def test_observe_builds_page_interaction_and_console_payload(self) -> None:
        tool_application = _ToolApplication()
        service = BrowserObservationService(
            tool_application_service=tool_application,
        )

        result = service.observe(
            profile_name="crxzipple",
            target_id="tab-1",
            payload={"limit": 12},
            timeout_ms=1500,
        )

        self.assertEqual(
            [call[0] for call in tool_application.calls],
            [
                "control",
                "page-action",
                "page-action",
                "page-action",
                "page-action",
                "page-action",
            ],
        )
        self.assertEqual(tool_application.calls[0][1]["kind"], "list-tabs")
        self.assertEqual(tool_application.calls[1][1]["kind"], "snapshot")
        self.assertEqual(tool_application.calls[1][1]["payload"]["limit"], 12)
        self.assertEqual(tool_application.calls[2][1]["kind"], "console")
        self.assertEqual(tool_application.calls[3][1]["kind"], "runtime-inspect")
        self.assertEqual(tool_application.calls[4][1]["kind"], "network-inspect")
        self.assertEqual(tool_application.calls[5][1]["kind"], "script-list")
        self.assertEqual(result.payload["kind"], "observe")
        self.assertEqual(result.payload["page"]["title"], "Flights")
        self.assertEqual(result.payload["frames"]["count"], 0)
        self.assertEqual(result.payload["interaction"]["ref_count"], 1)
        self.assertEqual(result.payload["interaction"]["refs"][0]["ref"], "r1")
        self.assertEqual(
            result.payload["interaction"]["evidence"],
            {"hit-test": 1, "native-control": 1},
        )
        self.assertEqual(result.payload["console"]["count"], 1)
        self.assertEqual(result.payload["runtime"]["page_state"]["ready_state"], "complete")
        self.assertEqual(result.payload["runtime"]["frameworks"]["detected"], ["next"])
        self.assertEqual(result.payload["runtime"]["route_hints"][0]["path"], "/flights")
        self.assertEqual(result.payload["runtime"]["globals"][0]["name"], "__NEXT_DATA__")
        self.assertEqual(result.payload["runtime"]["resources"]["resource_count"], 1)
        self.assertEqual(result.payload["runtime"]["performance"]["metric_count"], 2)
        self.assertEqual(
            result.payload["network"]["performance"],
            {"navigation_count": 1, "resource_count": 1},
        )
        self.assertFalse(result.payload["network"]["capture"]["enabled"])
        self.assertEqual(result.payload["code"]["scripts"]["returned_scripts"], 2)
        self.assertEqual(
            result.payload["code"]["scripts"]["scripts"][0]["script_id"],
            "script-1",
        )
        self.assertIsNone(result.payload["code"]["search"])
        self.assertEqual(
            result.payload["guidance"]["next_action"],
            "inspect-runtime-or-scripts",
        )
        self.assertEqual(
            result.payload["guidance"]["evidence_path_key"],
            "runtime_and_code",
        )
        self.assertIn(
            "browser.runtime.inspect",
            result.payload["guidance"]["suggested_tools"],
        )
        self.assertEqual(
            result.payload["guidance"]["primary_evidence_path"]["key"],
            "runtime_and_code",
        )
        alternative_keys = {
            item["key"]
            for item in result.payload["guidance"]["alternative_evidence_paths"]
        }
        self.assertIn("stateful_interaction", alternative_keys)
        self.assertIn("network_truth", alternative_keys)
        evidence_path_keys = {
            item["key"] for item in result.payload["guidance"]["evidence_paths"]
        }
        self.assertIn("diagnose_blockers", evidence_path_keys)
        self.assertEqual(
            result.runtime_metadata["browser_observation_target_id"],
            "tab-1",
        )

    def test_observe_keeps_optional_page_action_errors_as_partial_errors(self) -> None:
        class _FailingScriptsToolApplication(_ToolApplication):
            def execute_page_action(self, **kwargs) -> BrowserToolExecutionResult:  # noqa: ANN003
                if kwargs.get("kind") == "script-list":
                    raise BrowserToolApplicationError(
                        BrowserToolExecutionError(
                            code="browser_execution_failed",
                            message="Browser CDP script-list failed: non-JSON response.",
                            details={
                                "profile": kwargs.get("profile_name"),
                                "family": "page-action",
                                "kind": "script-list",
                                "target_id": kwargs.get("target_id"),
                            },
                        )
                    )
                return super().execute_page_action(**kwargs)

        tool_application = _FailingScriptsToolApplication()
        service = BrowserObservationService(
            tool_application_service=tool_application,
        )

        result = service.observe(
            profile_name="crxzipple",
            target_id="tab-1",
            payload={"limit": 12},
            timeout_ms=1500,
        )

        self.assertEqual(result.payload["kind"], "observe")
        self.assertEqual(result.payload["page"]["title"], "Flights")
        self.assertIsNone(result.payload["code"]["scripts"])
        self.assertEqual(len(result.payload["errors"]), 1)
        self.assertEqual(result.payload["errors"][0]["kind"], "script-list")
        self.assertEqual(
            result.payload["errors"][0]["code"],
            "browser_execution_failed",
        )

    def test_observe_derives_form_and_overlay_workbench_payload(self) -> None:
        tool_application = _ToolApplication()
        tool_application.snapshot_root_selector = ".city-overlay"
        tool_application.snapshot_active_overlay = True
        tool_application.snapshot_refs = [
            {
                "ref": "r1",
                "selector": "#depart-city",
                "role": "combobox",
                "label": "Departure city",
                "text": "",
                "tag": "input",
                "evidence": ["native-control", "editable", "hit-test"],
            },
            {
                "ref": "r2",
                "selector": "#search",
                "role": "button",
                "label": "Search",
                "text": "Search",
                "tag": "button",
                "evidence": ["native-control", "hit-test"],
            },
            {
                "ref": "r3",
                "selector": ".city-overlay .option:first-child",
                "scope_selector": ".city-overlay",
                "role": "option",
                "label": "Kunming",
                "text": "Kunming",
                "tag": "li",
                "evidence": ["picker-choice", "visible-text"],
            },
        ]
        service = BrowserObservationService(
            tool_application_service=tool_application,
        )

        result = service.observe(
            profile_name="crxzipple",
            target_id="tab-1",
            payload={"active_overlay": True, "limit": 20},
            timeout_ms=1500,
        )

        self.assertEqual(result.payload["form"]["field_count"], 1)
        self.assertEqual(result.payload["form"]["action_count"], 1)
        self.assertEqual(result.payload["form"]["candidate_count"], 1)
        self.assertEqual(result.payload["form"]["fields"][0]["ref"], "r1")
        self.assertEqual(result.payload["form"]["actions"][0]["ref"], "r2")
        self.assertEqual(result.payload["form"]["candidates"][0]["ref"], "r3")
        self.assertTrue(result.payload["overlay"]["active"])
        self.assertEqual(result.payload["overlay"]["selector"], ".city-overlay")
        self.assertEqual(result.payload["overlay"]["candidate_count"], 1)
        self.assertEqual(
            result.payload["guidance"]["next_action"],
            "select-overlay-candidate",
        )

    def test_observe_can_include_bounded_code_search(self) -> None:
        tool_application = _ToolApplication()
        service = BrowserObservationService(
            tool_application_service=tool_application,
        )

        result = service.observe(
            profile_name="crxzipple",
            target_id="tab-1",
            payload={
                "code_search_query": "fetchFlights",
                "code_search_limit": 3,
            },
            timeout_ms=1500,
        )

        self.assertEqual(tool_application.calls[-1][1]["kind"], "code-search")
        self.assertEqual(
            tool_application.calls[-1][1]["payload"]["query"],
            "fetchFlights",
        )
        self.assertEqual(tool_application.calls[-1][1]["payload"]["limit"], 3)
        self.assertEqual(result.payload["code"]["search"]["match_count"], 1)
        self.assertEqual(
            result.payload["code"]["search"]["matches"][0]["matches"][0]["line_number"],
            42,
        )

    def test_observe_can_include_script_request_matches(self) -> None:
        tool_application = _ToolApplication()
        service = BrowserObservationService(
            tool_application_service=tool_application,
        )

        result = service.observe(
            profile_name="crxzipple",
            target_id="tab-1",
            payload={
                "script_request_query": "/api/flights",
                "script_request_limit": 2,
            },
            timeout_ms=1500,
        )

        self.assertEqual(tool_application.calls[-1][1]["kind"], "script-find-request")
        self.assertEqual(
            tool_application.calls[-1][1]["payload"]["query"],
            "/api/flights",
        )
        self.assertEqual(tool_application.calls[-1][1]["payload"]["limit"], 2)
        self.assertEqual(result.payload["code"]["request_matches"]["match_count"], 1)
        self.assertEqual(
            result.payload["code"]["request_matches"]["candidates"][0]["matches"][0][
                "line_number"
            ],
            54,
        )

    def test_observe_can_include_existing_network_capture_summary(self) -> None:
        tool_application = _ToolApplication()
        service = BrowserObservationService(
            tool_application_service=tool_application,
        )

        result = service.observe(
            profile_name="crxzipple",
            target_id="tab-1",
            payload={
                "include_network_capture": True,
                "capture_id": "cap-1",
                "network_limit": 5,
            },
            timeout_ms=1500,
        )

        network_calls = [
            call
            for call in tool_application.calls
            if call[1].get("kind") == "network-list-requests"
        ]
        self.assertEqual(len(network_calls), 1)
        self.assertEqual(network_calls[0][1]["payload"]["capture_id"], "cap-1")
        self.assertEqual(network_calls[0][1]["payload"]["limit"], 5)
        self.assertTrue(result.payload["network"]["capture"]["enabled"])
        self.assertEqual(result.payload["network"]["capture"]["request_count"], 1)
        self.assertEqual(
            result.payload["network"]["capture"]["requests"][0]["request_id"],
            "req-1",
        )

    def test_browser_observe_handler_returns_observation_content_block(self) -> None:
        class _Store:
            @staticmethod
            def load() -> SimpleNamespace:
                return SimpleNamespace(default_profile="crxzipple")

        class _ObservationService:
            @staticmethod
            def observe(**_kwargs) -> BrowserToolExecutionResult:  # noqa: ANN003
                return BrowserToolExecutionResult(
                    payload={
                        "ok": True,
                        "kind": "observe",
                        "message": "Observed Flights with 1 interactive ref(s).",
                        "page": {
                            "target_id": "tab-1",
                            "title": "Flights",
                            "url": "https://example.test/flights",
                        },
                        "tabs": {"count": 1, "items": []},
                        "interaction": {
                            "ref_count": 1,
                            "frame_count": 1,
                            "refs": [],
                            "evidence": {"hit-test": 1},
                        },
                        "snapshot": {
                            "format": "interactive",
                            "value": {"snapshot": "- button \"Search\" [ref=r1]"},
                        },
                        "console": None,
                        "runtime": {
                            "resources": {"resource_count": 2, "frame_count": 1},
                            "performance": {"metric_count": 3},
                            "errors": [],
                        },
                        "network": {
                            "performance": {
                                "navigation_count": 1,
                                "resource_count": 2,
                            },
                            "capture": {
                                "enabled": True,
                                "request_count": 2,
                                "total_count": 5,
                                "requests": [],
                            },
                        },
                        "code": {
                            "scripts": {
                                "scripts_count": 2,
                                "returned_scripts": 2,
                                "scripts": [
                                    {
                                        "script_id": "script-1",
                                        "url": "https://example.test/app.js",
                                    }
                                ],
                            },
                            "search": {
                                "query": "fetchFlights",
                                "match_count": 1,
                            },
                            "request_matches": None,
                        },
                        "form": {
                            "field_count": 1,
                            "action_count": 1,
                            "candidate_count": 1,
                            "fields": [
                                {
                                    "ref": "r1",
                                    "role": "combobox",
                                    "label": "Departure city",
                                    "selector": "#depart-city",
                                }
                            ],
                            "actions": [
                                {
                                    "ref": "r2",
                                    "role": "button",
                                    "label": "Search",
                                    "selector": "#search",
                                }
                            ],
                            "candidates": [
                                {
                                    "ref": "r3",
                                    "role": "option",
                                    "label": "Kunming",
                                    "selector": ".city-overlay .option",
                                }
                            ],
                            "guidance": {
                                "next_action": "select-overlay-candidate",
                            },
                        },
                        "overlay": {
                            "active": True,
                            "selector": ".city-overlay",
                            "candidate_count": 1,
                            "candidates": [
                                {
                                    "ref": "r3",
                                    "role": "option",
                                    "label": "Kunming",
                                    "selector": ".city-overlay .option",
                                }
                            ],
                            "guidance": {
                                "next_action": "select-overlay-candidate",
                            },
                        },
                        "guidance": {
                            "next_action": "inspect-runtime-or-scripts",
                            "reason": (
                                "Runtime or script facts are available; inspect "
                                "them before choosing state-changing page actions."
                            ),
                            "suggested_tools": [
                                "browser.runtime.inspect",
                                "browser.script.find_request",
                                "browser.code.search",
                                "browser.network.inspect",
                            ],
                            "evidence_path_key": "runtime_and_code",
                            "primary_evidence_path": {
                                "key": "runtime_and_code",
                                "title": "Inspect Runtime And Frontend Code",
                                "tool_ids": [
                                    "browser.runtime.inspect",
                                    "browser.script.find_request",
                                ],
                            },
                            "alternative_evidence_paths": [
                                {
                                    "key": "network_truth",
                                    "title": "Trace Network Truth",
                                    "tool_ids": [
                                        "browser.network.inspect",
                                        "browser.network.replay_request",
                                    ],
                                },
                                {
                                    "key": "stateful_interaction",
                                    "title": "Act With Evidence",
                                    "tool_ids": [
                                        "browser.action.trace",
                                        "browser.form.inspect",
                                    ],
                                },
                            ],
                        },
                        "errors": [],
                    },
                    runtime_metadata={"browser_target_id": "tab-1"},
                )

        deps = BrowserToolDeps(
            browser_tool_application=object(),
            browser_system_config_store=_Store(),
            browser_profile_resolver=object(),
            browser_capabilities_resolver=object(),
            browser_observation_service=_ObservationService(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = create_browser_observe_handler(deps)
        assert handler is not None

        import asyncio

        result = asyncio.run(handler({"target_id": "tab-1"}))

        self.assertEqual(result.metadata["tool"], "browser.observe")
        self.assertEqual(result.metadata["kind"], "observe")
        self.assertIn("Observed Flights", result.content[0]["text"])
        self.assertIn("Runtime: 2 resource(s)", result.content[0]["text"])
        self.assertIn("Network: 1 navigation entry", result.content[0]["text"])
        self.assertIn("Code: 2/2 script(s)", result.content[0]["text"])
        self.assertIn("search fetchFlights: 1 match(es)", result.content[0]["text"])
        self.assertIn("Form:", result.content[0]["text"])
        self.assertIn("r1: combobox \"Departure city\"", result.content[0]["text"])
        self.assertIn("Overlay:", result.content[0]["text"])
        self.assertIn("r3: option \"Kunming\"", result.content[0]["text"])
        self.assertIn("Next: inspect-runtime-or-scripts", result.content[0]["text"])
        self.assertIn("Suggested tools: browser.runtime.inspect", result.content[0]["text"])
        self.assertIn(
            "Evidence path: runtime_and_code",
            result.content[0]["text"],
        )
        self.assertIn(
            "Alternative paths: network_truth",
            result.content[0]["text"],
        )
        self.assertIn(
            "network_truth",
            result.content[0]["text"],
        )
        self.assertIn("Snapshot (interactive)", result.content[0]["text"])

    def test_browser_observe_handler_omits_raw_large_payloads_from_content(self) -> None:
        raw_resource_secret = "RAW_RESOURCE_TREE_SECRET" * 200
        raw_body_secret = "RAW_RESPONSE_BODY_SECRET" * 200
        raw_snapshot_secret = "RAW_SNAPSHOT_SECRET" * 200

        class _Store:
            @staticmethod
            def load() -> SimpleNamespace:
                return SimpleNamespace(default_profile="crxzipple")

        class _ObservationService:
            @staticmethod
            def observe(**_kwargs) -> BrowserToolExecutionResult:  # noqa: ANN003
                return BrowserToolExecutionResult(
                    payload={
                        "ok": True,
                        "kind": "observe",
                        "message": "Observed page with bounded summaries.",
                        "page": {
                            "target_id": "tab-raw",
                            "title": "Raw Payload Test",
                            "url": "https://example.test/raw",
                        },
                        "interaction": {
                            "ref_count": 0,
                            "frame_count": 1,
                            "refs": [],
                        },
                        "runtime": {
                            "resources": {
                                "resource_count": 200,
                                "frame_count": 8,
                                "raw_resource_tree": raw_resource_secret,
                            },
                            "performance": {
                                "metric_count": 12,
                                "raw_metrics": raw_resource_secret,
                            },
                            "errors": [],
                        },
                        "network": {
                            "performance": {
                                "navigation_count": 1,
                                "resource_count": 200,
                                "raw_entries": raw_body_secret,
                            },
                            "capture": {
                                "enabled": True,
                                "request_count": 10,
                                "total_count": 200,
                                "requests": [
                                    {
                                        "url": "https://example.test/api",
                                        "response_body": raw_body_secret,
                                    },
                                ],
                            },
                        },
                        "snapshot": {
                            "format": "interactive",
                            "value": {
                                "snapshot": "- text \"Ready\"",
                                "raw_dom": raw_snapshot_secret,
                            },
                        },
                        "guidance": {
                            "next_action": "inspect-network-truth",
                            "primary_evidence_path": {
                                "key": "network_truth",
                                "title": "Trace Network Truth",
                                "tool_ids": ["browser.network.list_requests"],
                            },
                        },
                        "errors": [],
                    },
                    runtime_metadata={"browser_target_id": "tab-raw"},
                )

        deps = BrowserToolDeps(
            browser_tool_application=object(),
            browser_system_config_store=_Store(),
            browser_profile_resolver=object(),
            browser_capabilities_resolver=object(),
            browser_observation_service=_ObservationService(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = create_browser_observe_handler(deps)
        assert handler is not None

        import asyncio

        result = asyncio.run(handler({"target_id": "tab-raw"}))
        text = "\n".join(
            block["text"] for block in result.content if block.get("type") == "text"
        )

        self.assertIn("Observed page with bounded summaries.", text)
        self.assertIn("Runtime: 200 resource(s), 8 runtime frame(s)", text)
        self.assertIn("Network: 1 navigation entry, 200 resource entry", text)
        self.assertIn("Evidence path: network_truth", text)
        self.assertNotIn(raw_resource_secret, text)
        self.assertNotIn(raw_body_secret, text)
        self.assertNotIn(raw_snapshot_secret, text)
        self.assertLess(len(text), 3000)


if __name__ == "__main__":
    unittest.main()
