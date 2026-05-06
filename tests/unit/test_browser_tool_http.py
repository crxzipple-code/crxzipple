from __future__ import annotations

import asyncio
import tempfile
import json as _json
import threading
from types import SimpleNamespace
import unittest

from crxzipple.modules.artifacts.application.services import ArtifactApplicationService
from crxzipple.modules.artifacts.infrastructure.filesystem_store import FilesystemArtifactStore
from crxzipple.modules.browser.domain import BrowserValidationError
from tools.browser.local import browser_action
from tools.browser.local import browser_control
from tools.browser.local import browser_profile
from tools.browser.local import browser_script
from tools.browser.local import browser_snapshot
from tests.unit.http_test_support import *


class BrowserToolHttpTestCase(HttpModuleTestCase):
    def test_browser_profile_handler_lists_profiles_by_default(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(
                    default_profile="user",
                    managed_tab_limit=None,
                    profiles=(
                        SimpleNamespace(
                            name="crxzipple",
                            driver="managed",
                            attach_only=False,
                            cdp_url="http://127.0.0.1:18800",
                            cdp_port=None,
                            user_data_dir="/tmp/browser-crxzipple",
                        ),
                        SimpleNamespace(
                            name="user",
                            driver="existing-session",
                            attach_only=False,
                            cdp_url=None,
                            cdp_port=None,
                            user_data_dir="/tmp/browser-user",
                        ),
                    ),
                )

        class _ProfileResolver:
            def resolve(self, *, system, profile_name):  # noqa: ANN001, ANN201
                profile = next(item for item in system.profiles if item.name == profile_name)
                return SimpleNamespace(
                    name=profile.name,
                    driver=profile.driver,
                    cdp_url=profile.cdp_url,
                    cdp_port=profile.cdp_port,
                )

        class _CapabilitiesResolver:
            def resolve(self, *, profile):  # noqa: ANN001, ANN201
                if profile.driver == "existing-session":
                    return SimpleNamespace(
                        mode="local-existing-session",
                        control_family="mcp-control",
                        action_family="mcp-backed",
                        is_remote=False,
                        supports_reset=False,
                        supports_per_tab_ws=False,
                        supports_json_tab_endpoints=False,
                        supports_managed_tab_limit=False,
                    )
                return SimpleNamespace(
                    mode="local-managed",
                    control_family="cdp-control",
                    action_family="cdp-backed-playwright",
                    is_remote=False,
                    supports_reset=True,
                    supports_per_tab_ws=True,
                    supports_json_tab_endpoints=True,
                    supports_managed_tab_limit=True,
                )

        class _RuntimeStateStore:
            def get(self, *, profile_name):  # noqa: ANN201
                del profile_name
                return None

        container = SimpleNamespace(
            browser_system_config_store=_Store(),
            browser_profile_resolver=_ProfileResolver(),
            browser_capabilities_resolver=_CapabilitiesResolver(),
            browser_runtime_state_store=_RuntimeStateStore(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = browser_profile(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(handler({}))

        self.assertEqual(result.details["default_profile"], "user")
        self.assertEqual(result.details["guidance"]["recommended_profile"], "user")

    def test_browser_profile_handler_routes_diagnose_kind(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(
                    default_profile="crxzipple",
                    managed_tab_limit=None,
                    profiles=(
                        SimpleNamespace(
                            name="crxzipple",
                            driver="managed",
                            attach_only=False,
                            cdp_url="http://127.0.0.1:18800",
                            cdp_port=None,
                            user_data_dir="/tmp/browser-crxzipple",
                        ),
                        SimpleNamespace(
                            name="user",
                            driver="existing-session",
                            attach_only=False,
                            cdp_url=None,
                            cdp_port=None,
                            user_data_dir="/tmp/browser-user",
                        ),
                    ),
                )

        class _ProfileResolver:
            def resolve(self, *, system, profile_name):  # noqa: ANN001, ANN201
                profile = next(item for item in system.profiles if item.name == profile_name)
                return SimpleNamespace(
                    name=profile.name,
                    driver=profile.driver,
                    cdp_url=profile.cdp_url,
                    cdp_port=profile.cdp_port,
                )

        class _CapabilitiesResolver:
            def resolve(self, *, profile):  # noqa: ANN001, ANN201
                if profile.driver == "existing-session":
                    return SimpleNamespace(
                        mode="local-existing-session",
                        control_family="mcp-control",
                        action_family="mcp-backed",
                        is_remote=False,
                        supports_reset=False,
                        supports_per_tab_ws=False,
                        supports_json_tab_endpoints=False,
                        supports_managed_tab_limit=False,
                    )
                return SimpleNamespace(
                    mode="local-managed",
                    control_family="cdp-control",
                    action_family="cdp-backed-playwright",
                    is_remote=False,
                    supports_reset=True,
                    supports_per_tab_ws=True,
                    supports_json_tab_endpoints=True,
                    supports_managed_tab_limit=True,
                )

        class _RuntimeStateStore:
            def get(self, *, profile_name):  # noqa: ANN201
                del profile_name
                return None

        class _ProbeService:
            def probe(self, **kwargs):  # noqa: ANN003, ANN201
                del kwargs
                return {
                    "attempted": True,
                    "ok": False,
                    "status": "mcp-unavailable",
                    "message": "Chrome MCP is not available.",
                }

        container = SimpleNamespace(
            browser_system_config_store=_Store(),
            browser_profile_resolver=_ProfileResolver(),
            browser_capabilities_resolver=_CapabilitiesResolver(),
            browser_runtime_state_store=_RuntimeStateStore(),
            browser_profile_probe_service=_ProbeService(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = browser_profile(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(handler({"kind": "diagnose", "profile": "user"}))

        self.assertEqual(result.details["profile"]["name"], "user")
        self.assertEqual(result.details["guidance"]["fallback_profile"], "crxzipple")

    def test_browser_click_handler_treats_current_target_alias_as_active_tab(self) -> None:
        captured_requests: list[object] = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                return {"ok": True, "target_id": request.target_id, "message": "Clicked."}

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
        handler = browser_action(container)
        assert handler is not None

        asyncio.run(
            handler(
                {
                    "kind": "click",
                    "target_id": "current",
                    "ref": "r1",
                },
            ),
        )

        self.assertEqual(len(captured_requests), 1)
        self.assertIsNone(captured_requests[0].target_id)

    def test_browser_control_list_tabs_includes_target_ids_in_content_blocks(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                return {
                    "ok": True,
                    "message": "Listed 2 tabs.",
                    "command": {"kind": "list-tabs"},
                    "value": [
                        {
                            "target_id": "tab-1",
                            "title": "Example One",
                            "type": "page",
                            "url": "https://one.example",
                        },
                        {
                            "target_id": "tab-2",
                            "title": "Example Two",
                            "type": "page",
                            "url": "https://two.example",
                        },
                    ],
                }

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
        handler = browser_control(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "kind": "list-tabs",
                },
            ),
        )

        self.assertEqual(len(result.blocks), 1)
        self.assertIn("Browser tabs:", result.blocks[0]["text"])
        self.assertIn("[tab-1] (page) Example One", result.blocks[0]["text"])
        self.assertIn("[tab-2] (page) Example Two", result.blocks[0]["text"])

    def test_browser_control_handler_accepts_status_start_and_stop(self) -> None:
        captured_kinds: list[str] = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_kinds.append(request.kind)
                return {"ok": True, "message": f"Ran {request.kind}."}

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
        handler = browser_control(container)
        assert handler is not None

        for kind in ("status", "start", "stop"):
            asyncio.run(handler({"kind": kind}))

        self.assertEqual(captured_kinds, ["status", "start", "stop"])

    def test_browser_script_handler_resolves_current_target_alias_from_open_tab(self) -> None:
        captured_requests: list[object] = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                if request.kind == "open-tab":
                    return {
                        "ok": True,
                        "target_id": "tab-1",
                        "message": "Opened tab.",
                    }
                return {"ok": True, "target_id": request.target_id, "message": f"Ran {request.kind}."}

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
        handler = browser_script(container)
        assert handler is not None

        asyncio.run(
            handler(
                {
                    "steps": [
                        {"kind": "open-tab", "family": "control", "url": "https://example.com"},
                        {"kind": "click", "family": "page-action", "target_id": "current", "ref": "r1"},
                    ],
                },
            ),
        )

        self.assertEqual([request.kind for request in captured_requests], ["open-tab", "click"])
        self.assertEqual(captured_requests[1].target_id, "tab-1")

    def test_browser_script_handler_inherits_target_id_and_final_observe(self) -> None:
        captured_requests: list[object] = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                if request.kind == "open-tab":
                    return {
                        "ok": True,
                        "target_id": "tab-1",
                        "message": "Opened tab.",
                    }
                if request.kind == "snapshot":
                    return {
                        "ok": True,
                        "command": {"kind": "snapshot"},
                        "value": {
                            "result": {
                                "format": "interactive",
                                "value": {"snapshot": '- button "Search" [ref=r1]'},
                            }
                        },
                    }
                return {"ok": True, "target_id": request.target_id, "message": f"Ran {request.kind}."}

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
        handler = browser_script(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "steps": [
                        {"kind": "open-tab", "family": "control", "payload": {"url": "https://example.com"}},
                        {"kind": "click", "selector": "#search"},
                    ],
                    "final_observe": {"format": "interactive", "mode": "focused"},
                },
            ),
        )

        self.assertEqual(len(captured_requests), 3)
        self.assertEqual(captured_requests[0].kind, "open-tab")
        self.assertEqual(captured_requests[1].kind, "click")
        self.assertEqual(captured_requests[1].target_id, "tab-1")
        self.assertEqual(captured_requests[2].kind, "snapshot")
        self.assertEqual(captured_requests[2].target_id, "tab-1")
        self.assertEqual(result.details["step_count"], 2)
        self.assertEqual(result.details["target_id"], "tab-1")
        self.assertIn("Browser script completed 2 steps.", result.blocks[0]["text"])

    def test_browser_script_handler_accepts_stringified_step_objects(self) -> None:
        captured_requests: list[object] = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                if request.kind == "open-tab":
                    return {
                        "ok": True,
                        "target_id": "tab-1",
                        "message": "Opened tab.",
                    }
                return {"ok": True, "target_id": request.target_id, "message": f"Ran {request.kind}."}

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
        handler = browser_script(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "steps": [
                        '{"kind":"open-tab","family":"control","url":"https://example.com"}',
                        '{"kind":"wait","load_state":"domcontentloaded"}',
                    ],
                },
            ),
        )

        self.assertEqual([request.kind for request in captured_requests], ["open-tab", "wait"])
        self.assertEqual(captured_requests[1].payload["load_state"], "domcontentloaded")
        self.assertEqual(result.details["step_count"], 2)

    def test_browser_script_handler_accepts_stringified_steps_array(self) -> None:
        captured_requests: list[object] = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                if request.kind == "open-tab":
                    return {
                        "ok": True,
                        "target_id": "tab-1",
                        "message": "Opened tab.",
                    }
                return {"ok": True, "target_id": request.target_id, "message": f"Ran {request.kind}."}

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
        handler = browser_script(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "steps": '[{"kind":"open-tab","family":"control","url":"https://example.com"},{"kind":"wait","load_state":"domcontentloaded"}]',
                },
            ),
        )

        self.assertEqual([request.kind for request in captured_requests], ["open-tab", "wait"])
        self.assertEqual(captured_requests[1].payload["load_state"], "domcontentloaded")
        self.assertEqual(result.details["step_count"], 2)

    def test_browser_script_handler_applies_step_stabilize_and_observe_after(self) -> None:
        captured_requests: list[object] = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                if request.kind == "open-tab":
                    return {
                        "ok": True,
                        "target_id": "tab-1",
                        "message": "Opened tab.",
                    }
                if request.kind == "snapshot":
                    return {
                        "ok": True,
                        "command": {"kind": "snapshot"},
                        "value": {
                            "result": {
                                "format": "interactive",
                                "value": {"snapshot": '- button "Search" [ref=r1]'},
                            }
                        },
                    }
                return {"ok": True, "target_id": request.target_id, "message": f"Ran {request.kind}."}

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
        handler = browser_script(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "steps": [
                        {
                            "kind": "open-tab",
                            "family": "control",
                            "payload": {"url": "https://example.com"},
                            "stabilize": "navigation",
                            "observe_after": "interactive",
                        }
                    ],
                },
            ),
        )

        self.assertEqual([request.kind for request in captured_requests], ["open-tab", "wait", "snapshot"])
        self.assertEqual(result.details["step_count"], 1)
        self.assertEqual(result.details["steps"][0]["stabilize"], "navigation")
        self.assertEqual(result.details["steps"][0]["observe_after"], "interactive")
        self.assertEqual(result.details["post_state_summary"], "Browser snapshot completed.")
        self.assertIn("Snapshot (interactive):", result.blocks[-1]["text"])

    def test_browser_script_handler_promotes_wait_fields_and_skips_default_observe_for_control_steps(self) -> None:
        captured_requests: list[object] = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                if request.kind == "open-tab":
                    return {
                        "ok": True,
                        "target_id": "tab-1",
                        "message": "Opened tab.",
                    }
                if request.kind == "snapshot":
                    return {
                        "ok": True,
                        "command": {"kind": "snapshot"},
                        "value": {
                            "format": "interactive",
                            "value": {"snapshot": '- textbox "To" [ref=r1]'},
                        },
                    }
                return {"ok": True, "target_id": request.target_id, "message": f"Ran {request.kind}."}

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
        handler = browser_script(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "steps": [
                        {
                            "kind": "open-tab",
                            "family": "control",
                            "url": "https://mail.google.com/",
                        },
                        {
                            "kind": "wait",
                            "load_state": "domcontentloaded",
                        },
                    ],
                    "default_stabilize": "auto",
                    "default_observe_after": "interactive",
                },
            ),
        )

        self.assertEqual([request.kind for request in captured_requests], ["open-tab", "wait", "wait", "snapshot"])
        self.assertEqual(captured_requests[1].payload["load_state"], "load")
        self.assertEqual(captured_requests[2].payload["load_state"], "domcontentloaded")
        self.assertEqual(result.details["steps"][0]["observe_after"], "none")
        self.assertEqual(result.details["steps"][1]["observe_after"], "interactive")

    def test_browser_script_handler_avoids_duplicate_observe_for_single_open_tab_with_final_observe(self) -> None:
        captured_requests: list[object] = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                if request.kind == "open-tab":
                    return {
                        "ok": True,
                        "target_id": "tab-1",
                        "message": "Opened tab.",
                    }
                if request.kind == "snapshot":
                    return {
                        "ok": True,
                        "command": {"kind": "snapshot"},
                        "value": {
                            "format": "interactive",
                            "value": {"snapshot": '- link "Inbox" [ref=r1]'},
                        },
                    }
                return {"ok": True, "target_id": request.target_id, "message": f"Ran {request.kind}."}

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
        handler = browser_script(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "steps": [
                        {
                            "kind": "open-tab",
                            "family": "control",
                            "payload": {"url": "https://mail.google.com/"},
                        },
                    ],
                    "default_stabilize": "auto",
                    "default_observe_after": "interactive",
                    "observe_after": True,
                },
            ),
        )

        self.assertEqual([request.kind for request in captured_requests], ["open-tab", "wait", "snapshot"])
        self.assertEqual(result.details["steps"][0]["observe_after"], "none")
        self.assertEqual(result.details["post_state_summary"], "Browser snapshot completed.")

    def test_browser_click_handler_defaults_to_single_step_action(self) -> None:
        captured_requests: list[object] = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                return {"ok": True, "target_id": request.target_id}

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
        handler = browser_action(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "kind": "click",
                    "target_id": "tab-1",
                    "selector": "#confirm",
                },
            ),
        )

        self.assertEqual([request.kind for request in captured_requests], ["click"])
        self.assertEqual(result.details, {"ok": True, "target_id": "tab-1"})

    def test_browser_click_handler_allows_explicit_stabilize_and_observe_override(self) -> None:
        captured_requests: list[object] = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                return {"ok": True, "target_id": request.target_id}

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
        handler = browser_action(container)
        assert handler is not None

        asyncio.run(
            handler(
                {
                    "kind": "click",
                    "target_id": "tab-1",
                    "selector": "#confirm",
                    "stabilize": "none",
                    "observe_after": "none",
                },
            ),
        )

        self.assertEqual([request.kind for request in captured_requests], ["click"])

    def test_browser_click_handler_offloads_sync_facade_work_to_thread(self) -> None:
        caller_thread_id = threading.get_ident()
        observed_thread_id: int | None = None
        captured_request = None

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                nonlocal observed_thread_id, captured_request
                observed_thread_id = threading.get_ident()
                if captured_request is None:
                    captured_request = request
                if request.kind == "snapshot":
                    return {
                        "ok": True,
                        "command": {"kind": "snapshot"},
                        "value": {
                            "result": {
                                "format": "interactive",
                                "value": {"snapshot": '- button "Confirm" [ref=r1]'},
                            }
                        },
                    }
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
        handler = browser_action(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "kind": "click",
                    "selector": "#confirm",
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.profile_name, "crxzipple")
        self.assertEqual(captured_request.kind, "click")
        self.assertEqual(captured_request.selector, "#confirm")
        self.assertNotEqual(observed_thread_id, caller_thread_id)
        self.assertEqual(result.details, {"ok": True})

    def test_browser_fill_handler_can_request_post_state_snapshot(self) -> None:
        captured_requests: list[object] = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                if request.kind == "snapshot":
                    return {
                        "ok": True,
                        "command": {"kind": "snapshot"},
                        "value": {
                            "result": {
                                "format": "interactive",
                                "value": {"snapshot": '- textbox "Query" [ref=r3]: frog'},
                            }
                        },
                    }
                return {"ok": True, "target_id": request.target_id}

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
        handler = browser_action(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "kind": "fill",
                    "target_id": "tab-1",
                    "selector": "#query",
                    "text": "frog",
                    "observe_after": "interactive",
                },
            ),
        )

        self.assertEqual([request.kind for request in captured_requests], ["fill", "snapshot"])
        self.assertIn("Snapshot (interactive):", result.blocks[-1]["text"])

    def test_browser_wait_handler_promotes_top_level_text_argument(self) -> None:
        captured_request = None

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                nonlocal captured_request
                if captured_request is None:
                    captured_request = request
                if request.kind == "snapshot":
                    return {
                        "ok": True,
                        "command": {"kind": "snapshot"},
                        "value": {
                            "result": {
                                "format": "interactive",
                                "value": {"snapshot": '- text "Ready to search" [ref=r2]'},
                            }
                        },
                    }
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
        handler = browser_action(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "kind": "wait",
                    "text": "Ready to search",
                    "timeout_ms": 3000,
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.profile_name, "crxzipple")
        self.assertEqual(captured_request.kind, "wait")
        self.assertEqual(captured_request.payload["text"], "Ready to search")
        self.assertEqual(result.details, {"ok": True})

    def test_browser_wait_handler_allows_explicit_observe_override(self) -> None:
        captured_requests: list[object] = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                return {"ok": True, "target_id": request.target_id}

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
        handler = browser_action(container)
        assert handler is not None

        asyncio.run(
            handler(
                {
                    "kind": "wait",
                    "target_id": "tab-1",
                    "load_state": "load",
                    "observe_after": "none",
                },
            ),
        )

        self.assertEqual([request.kind for request in captured_requests], ["wait"])

    def test_browser_profile_diagnose_handler_returns_profile_status(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(
                    default_profile="crxzipple",
                    managed_tab_limit=None,
                    profiles=(
                        SimpleNamespace(
                            name="crxzipple",
                            driver="managed",
                            attach_only=False,
                            cdp_url="http://127.0.0.1:18800",
                            cdp_port=None,
                            user_data_dir="/tmp/browser-crxzipple",
                        ),
                        SimpleNamespace(
                            name="user",
                            driver="existing-session",
                            attach_only=False,
                            cdp_url=None,
                            cdp_port=None,
                            user_data_dir="/tmp/browser-user",
                        ),
                    ),
                )

        class _ProfileResolver:
            def resolve(self, *, system, profile_name):  # noqa: ANN001, ANN201
                profile = next(item for item in system.profiles if item.name == profile_name)
                return SimpleNamespace(
                    name=profile.name,
                    driver=profile.driver,
                    cdp_url=profile.cdp_url,
                    cdp_port=profile.cdp_port,
                )

        class _CapabilitiesResolver:
            def resolve(self, *, profile):  # noqa: ANN001, ANN201
                if profile.driver == "existing-session":
                    return SimpleNamespace(
                        mode="local-existing-session",
                        control_family="mcp-control",
                        action_family="mcp-backed",
                        is_remote=False,
                        supports_reset=False,
                        supports_per_tab_ws=False,
                        supports_json_tab_endpoints=False,
                        supports_managed_tab_limit=False,
                    )
                return SimpleNamespace(
                    mode="local-managed",
                    control_family="cdp-control",
                    action_family="cdp-backed-playwright",
                    is_remote=False,
                    supports_reset=True,
                    supports_per_tab_ws=True,
                    supports_json_tab_endpoints=True,
                    supports_managed_tab_limit=True,
                )

        class _RuntimeStateStore:
            def get(self, *, profile_name):  # noqa: ANN201
                del profile_name
                return None

        class _ProbeService:
            def probe(self, **kwargs):  # noqa: ANN003, ANN201
                del kwargs
                return {
                    "attempted": True,
                    "ok": False,
                    "status": "mcp-unavailable",
                    "message": "Chrome MCP is not available.",
                }

        container = SimpleNamespace(
            browser_system_config_store=_Store(),
            browser_profile_resolver=_ProfileResolver(),
            browser_capabilities_resolver=_CapabilitiesResolver(),
            browser_runtime_state_store=_RuntimeStateStore(),
            browser_profile_probe_service=_ProbeService(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = browser_profile(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(handler({"kind": "diagnose", "profile": "user"}))

        self.assertEqual(result.details["profile"]["name"], "user")
        self.assertEqual(
            result.details["profile"]["diagnostics"]["status"],
            "error",
        )
        self.assertEqual(
            result.details["profile"]["diagnostics"]["summary"]["code"],
            "error",
        )
        self.assertIn(
            "Error:",
            result.details["profile"]["diagnostics"]["summary_line"],
        )
        self.assertEqual(
            result.details["profile"]["diagnostics"]["probe"]["status"],
            "mcp-unavailable",
        )
        self.assertEqual(
            result.details["guidance"]["fallback_profile"],
            "crxzipple",
        )
        self.assertEqual(
            result.metadata["guidance"]["next_action"],
            "retry-or-check-mcp",
        )

    def test_browser_profiles_handler_returns_default_profile_guidance(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(
                    default_profile="user",
                    managed_tab_limit=None,
                    profiles=(
                        SimpleNamespace(
                            name="crxzipple",
                            driver="managed",
                            attach_only=False,
                            cdp_url="http://127.0.0.1:18800",
                            cdp_port=None,
                            user_data_dir="/tmp/browser-crxzipple",
                        ),
                        SimpleNamespace(
                            name="user",
                            driver="existing-session",
                            attach_only=False,
                            cdp_url=None,
                            cdp_port=None,
                            user_data_dir="/tmp/browser-user",
                        ),
                    ),
                )

        class _ProfileResolver:
            def resolve(self, *, system, profile_name):  # noqa: ANN001, ANN201
                profile = next(item for item in system.profiles if item.name == profile_name)
                return SimpleNamespace(
                    name=profile.name,
                    driver=profile.driver,
                    cdp_url=profile.cdp_url,
                    cdp_port=profile.cdp_port,
                )

        class _CapabilitiesResolver:
            def resolve(self, *, profile):  # noqa: ANN001, ANN201
                if profile.driver == "existing-session":
                    return SimpleNamespace(
                        mode="local-existing-session",
                        control_family="mcp-control",
                        action_family="mcp-backed",
                        is_remote=False,
                        supports_reset=False,
                        supports_per_tab_ws=False,
                        supports_json_tab_endpoints=False,
                        supports_managed_tab_limit=False,
                    )
                return SimpleNamespace(
                    mode="local-managed",
                    control_family="cdp-control",
                    action_family="cdp-backed-playwright",
                    is_remote=False,
                    supports_reset=True,
                    supports_per_tab_ws=True,
                    supports_json_tab_endpoints=True,
                    supports_managed_tab_limit=True,
                )

        class _RuntimeStateStore:
            def get(self, *, profile_name):  # noqa: ANN201
                del profile_name
                return None

        container = SimpleNamespace(
            browser_system_config_store=_Store(),
            browser_profile_resolver=_ProfileResolver(),
            browser_capabilities_resolver=_CapabilitiesResolver(),
            browser_runtime_state_store=_RuntimeStateStore(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = browser_profile(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(handler({}))

        self.assertEqual(result.details["guidance"]["recommended_profile"], "user")
        self.assertEqual(
            result.details["guidance"]["fallback_profile"],
            "crxzipple",
        )
        self.assertEqual(
            result.details["guidance"]["next_action"],
            "open-signed-in-browser-and-retry",
        )
        self.assertEqual(result.metadata["guidance"]["applies_to"], "default-profile")

    def test_browser_click_failure_includes_profile_guidance(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(
                    default_profile="user",
                    managed_tab_limit=None,
                    profiles=(
                        SimpleNamespace(
                            name="crxzipple",
                            driver="managed",
                            attach_only=False,
                            cdp_url="http://127.0.0.1:18800",
                            cdp_port=None,
                            user_data_dir="/tmp/browser-crxzipple",
                        ),
                        SimpleNamespace(
                            name="user",
                            driver="existing-session",
                            attach_only=False,
                            cdp_url=None,
                            cdp_port=None,
                            user_data_dir="/tmp/browser-user",
                        ),
                    ),
                )

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                del request
                raise BrowserValidationError("Could not click element because the session is unavailable.")

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return result

        class _ProfileResolver:
            def resolve(self, *, system, profile_name):  # noqa: ANN001, ANN201
                profile = next(item for item in system.profiles if item.name == profile_name)
                return SimpleNamespace(
                    name=profile.name,
                    driver=profile.driver,
                    cdp_url=profile.cdp_url,
                    cdp_port=profile.cdp_port,
                )

        class _CapabilitiesResolver:
            def resolve(self, *, profile):  # noqa: ANN001, ANN201
                if profile.driver == "existing-session":
                    return SimpleNamespace(
                        mode="local-existing-session",
                        control_family="mcp-control",
                        action_family="mcp-backed",
                        is_remote=False,
                        supports_reset=False,
                        supports_per_tab_ws=False,
                        supports_json_tab_endpoints=False,
                        supports_managed_tab_limit=False,
                    )
                return SimpleNamespace(
                    mode="local-managed",
                    control_family="cdp-control",
                    action_family="cdp-backed-playwright",
                    is_remote=False,
                    supports_reset=True,
                    supports_per_tab_ws=True,
                    supports_json_tab_endpoints=True,
                    supports_managed_tab_limit=True,
                )

        class _RuntimeStateStore:
            def get(self, *, profile_name):  # noqa: ANN201
                del profile_name
                return None

        container = SimpleNamespace(
            browser_facade=_Facade(),
            browser_result_serializer=_Serializer(),
            browser_system_config_store=_Store(),
            browser_profile_resolver=_ProfileResolver(),
            browser_capabilities_resolver=_CapabilitiesResolver(),
            browser_runtime_state_store=_RuntimeStateStore(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = browser_action(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        with self.assertRaises(BrowserValidationError) as exc_info:
            asyncio.run(handler({"kind": "click", "profile": "user", "ref": "r1"}))

        message = str(exc_info.exception)
        self.assertIn("Next: open-signed-in-browser-and-retry with profile 'user'.", message)
        self.assertIn("Fallback: use profile 'crxzipple' and run-open-tab.", message)

    def test_browser_action_targeting_error_does_not_append_profile_launch_guidance(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(
                    default_profile="crxzipple",
                    profiles=(
                        SimpleNamespace(
                            name="crxzipple",
                            driver="managed",
                            attach_only=False,
                            cdp_url="http://127.0.0.1:9222",
                            cdp_port=9222,
                            user_data_dir=None,
                        ),
                    ),
                )

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                raise BrowserValidationError(
                    f"Browser action '{request.kind}' requires ref or selector targeting.",
                )

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return result

        class _ProfileResolver:
            def resolve(self, *, system, profile_name):  # noqa: ANN001, ANN201
                profile = next(item for item in system.profiles if item.name == profile_name)
                return SimpleNamespace(
                    name=profile.name,
                    driver=profile.driver,
                    cdp_url=profile.cdp_url,
                    cdp_port=profile.cdp_port,
                )

        class _CapabilitiesResolver:
            def resolve(self, *, profile):  # noqa: ANN001, ANN201
                del profile
                return SimpleNamespace(
                    mode="local-managed",
                    control_family="cdp-control",
                    action_family="cdp-backed-playwright",
                    is_remote=False,
                    supports_reset=True,
                    supports_per_tab_ws=True,
                    supports_json_tab_endpoints=True,
                    supports_managed_tab_limit=True,
                )

        class _RuntimeStateStore:
            def get(self, *, profile_name):  # noqa: ANN201
                del profile_name
                return None

        container = SimpleNamespace(
            browser_facade=_Facade(),
            browser_result_serializer=_Serializer(),
            browser_system_config_store=_Store(),
            browser_profile_resolver=_ProfileResolver(),
            browser_capabilities_resolver=_CapabilitiesResolver(),
            browser_runtime_state_store=_RuntimeStateStore(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = browser_action(container)
        assert handler is not None

        with self.assertRaises(BrowserValidationError) as exc_info:
            asyncio.run(handler({"kind": "press"}))

        message = str(exc_info.exception)
        self.assertEqual(
            message,
            "Browser action 'press' requires ref or selector targeting.",
        )

    def test_browser_action_websocket_403_error_surfaces_remote_allow_origins_guidance(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(
                    default_profile="crxzipple",
                    profiles=(
                        SimpleNamespace(
                            name="crxzipple",
                            driver="managed",
                            attach_only=False,
                            cdp_url="http://127.0.0.1:18800",
                            cdp_port=18800,
                            user_data_dir=None,
                        ),
                    ),
                )

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                del request
                raise BrowserValidationError(
                    "Browser CDP websocket ws://localhost:18800/devtools/page/demo could not be opened: "
                    "Handshake status 403 Forbidden -+-+- {'content-length': '241', 'content-type': 'text/html'} "
                    "-+-+- b'Rejected an incoming WebSocket connection from the http://localhost:18800 origin. "
                    "Use the command line flag --remote-allow-origins=http://localhost:18800 to allow connections "
                    "from this origin or --remote-allow-origins=* to allow all origins.'"
                )

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return result

        class _ProfileResolver:
            def resolve(self, *, system, profile_name):  # noqa: ANN001, ANN201
                profile = next(item for item in system.profiles if item.name == profile_name)
                return SimpleNamespace(
                    name=profile.name,
                    driver=profile.driver,
                    cdp_url=profile.cdp_url,
                    cdp_port=profile.cdp_port,
                )

        class _CapabilitiesResolver:
            def resolve(self, *, profile):  # noqa: ANN001, ANN201
                del profile
                return SimpleNamespace(
                    mode="local-managed",
                    control_family="cdp-control",
                    action_family="cdp-backed-playwright",
                    is_remote=False,
                    supports_reset=True,
                    supports_per_tab_ws=True,
                    supports_json_tab_endpoints=True,
                    supports_managed_tab_limit=True,
                )

        class _RuntimeStateStore:
            def get(self, *, profile_name):  # noqa: ANN201
                del profile_name
                return None

        container = SimpleNamespace(
            browser_facade=_Facade(),
            browser_result_serializer=_Serializer(),
            browser_system_config_store=_Store(),
            browser_profile_resolver=_ProfileResolver(),
            browser_capabilities_resolver=_CapabilitiesResolver(),
            browser_runtime_state_store=_RuntimeStateStore(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = browser_snapshot(container)
        assert handler is not None

        with self.assertRaises(BrowserValidationError) as exc_info:
            asyncio.run(handler({"profile": "crxzipple"}))

        message = str(exc_info.exception)
        self.assertIn(
            "Next: reset the managed browser for profile 'crxzipple' and run-open-tab again.",
            message,
        )
        self.assertIn("mismatched remote-allow-origins policy", message)

    def test_browser_wait_handler_promotes_extended_wait_arguments(self) -> None:
        captured_request = None

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                nonlocal captured_request
                if captured_request is None:
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
        handler = browser_action(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "kind": "wait",
                    "text_gone": "Loading",
                    "load_state": "domcontentloaded",
                    "fn": "() => window.ready === true",
                    "time_ms": 250,
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.payload["text_gone"], "Loading")
        self.assertEqual(captured_request.payload["load_state"], "domcontentloaded")
        self.assertEqual(captured_request.payload["fn"], "() => window.ready === true")
        self.assertEqual(captured_request.payload["time_ms"], 250)
        self.assertEqual(result.details, {"ok": True})

    def test_browser_wait_handler_promotes_scope_exact_and_ordinal(self) -> None:
        captured_request = None

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                nonlocal captured_request
                if captured_request is None:
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
        handler = browser_action(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "kind": "wait",
                    "text": "Done",
                    "scope_selector": "#results",
                    "exact": True,
                    "ordinal": 1,
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.payload["scope_selector"], "#results")
        self.assertTrue(captured_request.payload["exact"])
        self.assertEqual(captured_request.payload["ordinal"], 1)
        self.assertEqual(result.details, {"ok": True})

    def test_browser_wait_handler_promotes_overlay_source_selector(self) -> None:
        captured_request = None

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                nonlocal captured_request
                if captured_request is None:
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
        handler = browser_action(container)
        assert handler is not None

        asyncio.run(
            handler(
                {
                    "kind": "wait",
                    "text": "Done",
                    "overlay_source_selector": "#depart-city",
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.payload["overlay_source_selector"], "#depart-city")

    def test_browser_click_handler_promotes_scope_and_ordinal(self) -> None:
        captured_request = None

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                nonlocal captured_request
                if captured_request is None:
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
        handler = browser_action(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "kind": "click",
                    "selector": ".result",
                    "scope_ref": "r9",
                    "ordinal": 2,
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.payload["scope_ref"], "r9")
        self.assertEqual(captured_request.payload["ordinal"], 2)
        self.assertEqual(result.details, {"ok": True})

    def test_browser_action_handler_promotes_drag_alias_arguments(self) -> None:
        captured_request = None

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                nonlocal captured_request
                if captured_request is None:
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
        handler = browser_action(container)
        self.assertIsNotNone(handler)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "kind": "drag",
                    "start_ref": "r1",
                    "end_ref": "r2",
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.kind, "drag")
        self.assertEqual(captured_request.payload["start_ref"], "r1")
        self.assertEqual(captured_request.payload["end_ref"], "r2")
        self.assertEqual(result.details, {"ok": True})

    def test_browser_action_handler_promotes_fill_fields_payload(self) -> None:
        captured_request = None

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                nonlocal captured_request
                if captured_request is None:
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
        handler = browser_action(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "kind": "fill",
                    "fields": [
                        {"ref": "r1", "type": "text", "value": "昆明"},
                        {"ref": "r2", "type": "checkbox", "value": True},
                    ],
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.kind, "fill")
        self.assertEqual(
            captured_request.payload["fields"],
            [
                {"ref": "r1", "type": "text", "value": "昆明"},
                {"ref": "r2", "type": "checkbox", "value": True},
            ],
        )

    def test_browser_action_handler_promotes_upload_paths_payload(self) -> None:
        captured_request = None

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                nonlocal captured_request
                captured_request = request
                return {"ok": True, "message": "Uploaded."}

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
        handler = browser_action(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "kind": "upload",
                    "ref": "r7",
                    "paths": ["/tmp/a.txt", "/tmp/b.txt"],
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        assert captured_request is not None
        self.assertEqual(captured_request.kind, "upload")
        self.assertEqual(captured_request.ref, "r7")
        self.assertEqual(captured_request.payload["paths"], ["/tmp/a.txt", "/tmp/b.txt"])
        self.assertEqual(result.details, {"ok": True, "message": "Uploaded."})

    def test_browser_action_handler_persists_download_as_artifact_ref(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                del request
                return {
                    "ok": True,
                    "value": {
                        "kind": "download",
                        "content_type": "text/csv",
                        "name": "report.csv",
                        "data": "Y2l0eSxwcmljZQpra3VubWluZywzMjAK",
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
            handler = browser_action(container)
            assert handler is not None

            result = asyncio.run(handler({"kind": "wait-download"}))

            self.assertEqual(result.content[0], {"type": "text", "text": "Browser download captured."})
            attachment_block = result.content[1]
            self.assertEqual(attachment_block["type"], "file_ref")
            artifact = artifact_service.get_artifact(attachment_block["artifact_id"])
            self.assertEqual(artifact.mime_type, "text/csv")
            self.assertEqual(artifact.name, "report.csv")
            self.assertEqual(
                result.details,
                {
                    "ok": True,
                    "value": {
                        "kind": "download",
                        "content_type": "text/csv",
                        "name": "report.csv",
                        "attachment_in_content": True,
                    },
                },
            )

    def test_browser_action_handler_accepts_single_step_observe_controls(self) -> None:
        captured_requests: list[object] = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                return {"ok": True, "target_id": request.target_id}

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
        handler = browser_action(container)
        assert handler is not None

        asyncio.run(
            handler(
                {
                    "kind": "press",
                    "target_id": "tab-1",
                    "key": "Enter",
                    "stabilize": "none",
                    "observe_after": "none",
                },
            ),
        )

        self.assertEqual([request.kind for request in captured_requests], ["press"])

    def test_browser_action_handler_promotes_dialog_arguments(self) -> None:
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
        handler = browser_action(container)
        assert handler is not None

        asyncio.run(
            handler(
                {
                    "kind": "dialog",
                    "accept": False,
                    "prompt_text": "ignored",
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.kind, "dialog")
        self.assertEqual(
            dict(captured_request.payload),
            {
                "accept": False,
                "prompt_text": "ignored",
            },
        )

    def test_browser_action_handler_promotes_console_arguments(self) -> None:
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
        handler = browser_action(container)
        assert handler is not None

        asyncio.run(
            handler(
                {
                    "kind": "console",
                    "level": "error",
                    "clear": True,
                    "limit": 5,
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.kind, "console")
        self.assertEqual(
            dict(captured_request.payload),
            {
                "level": "error",
                "clear": True,
                "limit": 5,
            },
        )

    def test_browser_action_handler_promotes_storage_arguments(self) -> None:
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
        handler = browser_action(container)
        assert handler is not None

        asyncio.run(
            handler(
                {
                    "kind": "storage",
                    "storage_kind": "session",
                    "storage_operation": "set",
                    "storage_key": "theme",
                    "storage_value": "dark",
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.kind, "storage")
        self.assertEqual(
            dict(captured_request.payload),
            {
                "storage_kind": "session",
                "storage_operation": "set",
                "storage_key": "theme",
                "storage_value": "dark",
            },
        )

    def test_browser_action_handler_promotes_cookies_arguments(self) -> None:
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
        handler = browser_action(container)
        assert handler is not None

        asyncio.run(
            handler(
                {
                    "kind": "cookies",
                    "cookies_operation": "set",
                    "cookie": {
                        "name": "session",
                        "value": "abc123",
                        "url": "https://example.com",
                    },
                },
            ),
        )

        self.assertIsNotNone(captured_request)
        self.assertEqual(captured_request.kind, "cookies")
        self.assertEqual(
            dict(captured_request.payload),
            {
                "cookies_operation": "set",
                "cookie": {
                    "name": "session",
                    "value": "abc123",
                    "url": "https://example.com",
                },
            },
        )

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
        handler = browser_action(container)
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
        handler = browser_action(container)
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
                },
            ],
        )

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
        handler = browser_snapshot(container)
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
        handler = browser_snapshot(container)
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
        handler = browser_snapshot(container)
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
        handler = browser_snapshot(container)
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
        handler = browser_snapshot(container)
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
        handler = browser_snapshot(container)
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
        handler = browser_snapshot(container)
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
        handler = browser_action(container)
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
        handler = browser_action(container)
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
        handler = browser_action(container)
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
            handler = browser_action(container)
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
            handler = browser_action(container)
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

    def test_browser_tool_is_listed_and_can_open_tab(self) -> None:
        previous_specs = os.environ.get("APP_BROWSER_PROFILE_SPECS")
        fake_cdp_server = FakeCdpServer()
        fake_cdp_server.start()
        os.environ["APP_BROWSER_PROFILE_SPECS"] = _json.dumps(
            [
                {
                    "name": "crxzipple",
                    "cdp_url": fake_cdp_server.base_url,
                },
                {
                    "name": "user",
                    "driver": "existing-session",
                },
            ],
        )
        harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            database_url=harness.database_url,
            authorization_enabled=False,
            browser_state_dir=str(Path(harness._tempdir.name) / "browser"),
        )

        harness.initialize_schema(settings=settings)
        with patch(
            "crxzipple.bootstrap.container.ChromeMcpClientPool",
            FakeChromeMcpClientPool,
        ):
            client = TestClient(
                create_app(
                    settings=settings,
                    database_url=harness.database_url,
                ),
            )

        try:
            list_response = client.get("/tools")

            self.assertEqual(list_response.status_code, 200)
            tool_ids = [item["id"] for item in list_response.json()]
            self.assertIn("browser_profile", tool_ids)
            self.assertIn("browser_control", tool_ids)
            self.assertIn("browser_script", tool_ids)
            self.assertIn("browser_snapshot", tool_ids)
            self.assertIn("browser_action", tool_ids)

            run_response = client.post(
                "/tools/browser_control/runs",
                json={
                    "arguments": {
                        "kind": "open-tab",
                        "url": "https://example.com",
                    },
                },
            )

            self.assertEqual(run_response.status_code, 201)
            payload = run_response.json()
            self.assertEqual(payload["tool_id"], "browser_control")
            self.assertEqual(payload["status"], "succeeded")
            self.assertEqual(payload["output_payload"]["command"]["kind"], "open-tab")
            self.assertTrue(
                payload["output_payload"]["value"]["url"].startswith("https://example.com")
            )
            self.assertEqual(
                payload["output_payload"]["value"]["ws_url"],
                f"{fake_cdp_server.base_url.replace('http://', 'ws://')}/devtools/page/{payload['output_payload']['target_id']}",
            )
            self.assertEqual(
                payload["output_payload"]["value"]["json_endpoints"],
                {
                    "version": f"{fake_cdp_server.base_url}/json/version",
                    "list": f"{fake_cdp_server.base_url}/json/list",
                    "new": f"{fake_cdp_server.base_url}/json/new",
                    "activate": f"{fake_cdp_server.base_url}/json/activate/{payload['output_payload']['target_id']}",
                    "close": f"{fake_cdp_server.base_url}/json/close/{payload['output_payload']['target_id']}",
                },
            )
        finally:
            client.close()
            client.app.state.container.engine.dispose()
            harness.close()
            fake_cdp_server.close()
            if previous_specs is None:
                os.environ.pop("APP_BROWSER_PROFILE_SPECS", None)
            else:
                os.environ["APP_BROWSER_PROFILE_SPECS"] = previous_specs

    def test_browser_tool_snapshot_exposes_frame_path(self) -> None:
        previous_specs = os.environ.get("APP_BROWSER_PROFILE_SPECS")
        fake_cdp_server = FakeCdpServer()
        fake_cdp_server.start()
        os.environ["APP_BROWSER_PROFILE_SPECS"] = _json.dumps(
            [
                {
                    "name": "crxzipple",
                    "cdp_url": fake_cdp_server.base_url,
                },
                {
                    "name": "user",
                    "driver": "existing-session",
                },
            ],
        )
        harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            database_url=harness.database_url,
            authorization_enabled=False,
            browser_state_dir=str(Path(harness._tempdir.name) / "browser"),
        )

        harness.initialize_schema(settings=settings)
        with patch(
            "crxzipple.bootstrap.container.PlaywrightCdpSessionPool",
            FakePlaywrightCdpSessionPool,
        ):
            client = TestClient(
                create_app(
                    settings=settings,
                    database_url=harness.database_url,
                ),
            )

        try:
            open_response = client.post(
                "/tools/browser_control/runs",
                json={
                    "arguments": {
                        "kind": "open-tab",
                        "url": "https://example.com",
                    },
                },
            )
            self.assertEqual(open_response.status_code, 201)
            target_id = open_response.json()["output_payload"]["target_id"]

            pool = FakePlaywrightCdpSessionPool.last_created
            self.assertIsNotNone(pool)
            assert pool is not None
            page = pool.resolve_page(profile=object(), target_id=target_id)
            page.main_frame.interactive_items = []
            page.add_child_frame(
                path=(0,),
                interactive_items=[
                    {
                        "selector": "#confirm",
                        "label": "Confirm",
                        "role": "button",
                        "text": "Confirm",
                        "tag": "button",
                    }
                ],
            )

            snapshot_response = client.post(
                "/tools/browser_snapshot/runs",
                json={
                    "arguments": {
                        "target_id": target_id,
                        "format": "interactive",
                    },
                },
            )

            self.assertEqual(snapshot_response.status_code, 201)
            output_payload = snapshot_response.json()["output_payload"]
            self.assertEqual(output_payload["value"]["result"]["value"]["refs"][0]["frame_path"], [0])
        finally:
            client.close()
            client.app.state.container.engine.dispose()
            harness.close()
            fake_cdp_server.close()
            if previous_specs is None:
                os.environ.pop("APP_BROWSER_PROFILE_SPECS", None)
            else:
                os.environ["APP_BROWSER_PROFILE_SPECS"] = previous_specs

    def test_browser_tool_uses_updated_default_profile_from_state_root(self) -> None:
        previous_specs = os.environ.get("APP_BROWSER_PROFILE_SPECS")
        fake_cdp_server = FakeCdpServer()
        fake_cdp_server.start()
        os.environ["APP_BROWSER_PROFILE_SPECS"] = _json.dumps(
            [
                {
                    "name": "crxzipple",
                    "cdp_url": fake_cdp_server.base_url,
                },
                {
                    "name": "user",
                    "driver": "existing-session",
                },
            ],
        )
        harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            database_url=harness.database_url,
            authorization_enabled=False,
            browser_state_dir=str(Path(harness._tempdir.name) / "browser"),
        )

        harness.initialize_schema(settings=settings)
        with patch(
            "crxzipple.bootstrap.container.ChromeMcpClientPool",
            FakeChromeMcpClientPool,
        ):
            client = TestClient(
                create_app(
                    settings=settings,
                    database_url=harness.database_url,
                ),
            )

        try:
            container = client.app.state.container
            system_path = container.browser_state_root.config_dir / "system.json"
            payload = json.loads(system_path.read_text(encoding="utf-8"))
            payload["default_profile"] = "user"
            system_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            run_response = client.post(
                "/tools/browser_control/runs",
                json={
                    "arguments": {
                        "kind": "open-tab",
                        "url": "https://example.com",
                    },
                },
            )

            self.assertEqual(run_response.status_code, 201)
            output_payload = run_response.json()["output_payload"]
            self.assertEqual(output_payload["command"]["profile_name"], "user")
        finally:
            client.close()
            client.app.state.container.engine.dispose()
            harness.close()
            fake_cdp_server.close()
            if previous_specs is None:
                os.environ.pop("APP_BROWSER_PROFILE_SPECS", None)
            else:
                os.environ["APP_BROWSER_PROFILE_SPECS"] = previous_specs

    def test_browser_tool_can_reset_local_managed_profile(self) -> None:
        previous_specs = os.environ.get("APP_BROWSER_PROFILE_SPECS")
        fake_cdp_server = FakeCdpServer()
        fake_cdp_server.start()
        os.environ["APP_BROWSER_PROFILE_SPECS"] = _json.dumps(
            [
                {
                    "name": "crxzipple",
                    "cdp_url": fake_cdp_server.base_url,
                },
                {
                    "name": "user",
                    "driver": "existing-session",
                },
            ],
        )
        harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            database_url=harness.database_url,
            authorization_enabled=False,
            browser_state_dir=str(Path(harness._tempdir.name) / "browser"),
        )

        harness.initialize_schema(settings=settings)
        client = TestClient(
            create_app(
                settings=settings,
                database_url=harness.database_url,
            ),
        )

        try:
            open_response = client.post(
                "/tools/browser_control/runs",
                json={
                    "arguments": {
                        "kind": "open-tab",
                        "url": "https://example.com",
                    },
                },
            )
            self.assertEqual(open_response.status_code, 201)

            container = client.app.state.container
            runtime_path = container.browser_state_root.runtime_dir / "crxzipple.json"
            self.assertTrue(runtime_path.exists())
            userdata_dir = (
                container.browser_state_root.profiles_dir / "crxzipple" / "userdata"
            )
            sentinel = userdata_dir / "sentinel.txt"
            sentinel.write_text("state", encoding="utf-8")

            reset_response = client.post(
                "/tools/browser_control/runs",
                json={
                    "arguments": {
                        "kind": "reset",
                    },
                },
            )

            self.assertEqual(reset_response.status_code, 201)
            payload = reset_response.json()["output_payload"]
            self.assertTrue(payload["ok"])
            self.assertEqual(payload["command"]["kind"], "reset")
            self.assertEqual(payload["value"]["profile_name"], "crxzipple")
            self.assertFalse(runtime_path.exists())
            self.assertEqual(list(userdata_dir.iterdir()), [])
        finally:
            client.close()
            client.app.state.container.engine.dispose()
            harness.close()
            fake_cdp_server.close()
            if previous_specs is None:
                os.environ.pop("APP_BROWSER_PROFILE_SPECS", None)
            else:
                os.environ["APP_BROWSER_PROFILE_SPECS"] = previous_specs
