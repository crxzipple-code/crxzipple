from __future__ import annotations

import asyncio
import tempfile
import threading
from types import SimpleNamespace

from crxzipple.modules.artifacts.application.services import ArtifactApplicationService
from crxzipple.modules.artifacts.infrastructure.filesystem_store import FilesystemArtifactStore
from crxzipple.modules.browser.application import BrowserToolApplicationError
from crxzipple.modules.browser.domain import BrowserValidationError
from crxzipple.modules.browser.interfaces import BrowserControlRequest, BrowserPageActionRequest
from crxzipple.modules.tool.domain import ToolExecutionContext
from tools.browser.local import BrowserToolDeps
from tools.browser.local import create_browser_context_handler
from tools.browser.local import create_browser_control_handler
from tools.browser.local import create_browser_network_handler
from tools.browser.local import create_browser_page_action_handler
from tools.browser.local import create_browser_snapshot_handler
from tests.unit.http_test_support import AppKey, HttpModuleTestCase


class _DefaultBrowserProfileResolver:
    def resolve(self, *, system, profile_name):  # noqa: ANN001, ANN201
        profile = next(
            (
                item
                for item in getattr(system, "profiles", ())
                if getattr(item, "name", None) == profile_name
            ),
            None,
        )
        if profile is None:
            return SimpleNamespace(
                name=profile_name,
                driver="managed",
                cdp_url=None,
                cdp_port=None,
            )
        return SimpleNamespace(
            name=profile.name,
            driver=profile.driver,
            cdp_url=getattr(profile, "cdp_url", None),
            cdp_port=getattr(profile, "cdp_port", None),
        )


class _DefaultBrowserCapabilitiesResolver:
    def resolve(self, *, profile):  # noqa: ANN001, ANN201
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


_DEFAULT_BROWSER_PROFILE_RESOLVER = _DefaultBrowserProfileResolver()
_DEFAULT_BROWSER_CAPABILITIES_RESOLVER = _DefaultBrowserCapabilitiesResolver()


class _BrowserToolApplicationAdapter:
    def __init__(self, *, facade, serializer):  # noqa: ANN001
        self._facade = facade
        self._serializer = serializer

    def execute_control(  # noqa: ANN201
        self,
        *,
        profile_name,
        kind,
        target_id=None,
        payload=None,
        timeout_ms=None,
    ):
        result = self._facade.execute(
            BrowserControlRequest(
                profile_name=profile_name,
                kind=kind,
                target_id=target_id,
                payload=payload or {},
                timeout_ms=timeout_ms,
            ),
        )
        return SimpleNamespace(
            payload=self._serializer.serialize(result),
            runtime_metadata={},
        )

    def execute_page_action(  # noqa: ANN201
        self,
        *,
        profile_name,
        kind,
        target_id=None,
        ref=None,
        selector=None,
        payload=None,
        timeout_ms=None,
    ):
        result = self._facade.execute(
            BrowserPageActionRequest(
                profile_name=profile_name,
                kind=kind,
                target_id=target_id,
                ref=ref,
                selector=selector,
                payload=payload or {},
                timeout_ms=timeout_ms,
            ),
        )
        return SimpleNamespace(
            payload=self._serializer.serialize(result),
            runtime_metadata={},
        )


def _container_value(container, key, attr, default=None):  # noqa: ANN001, ANN202
    require = getattr(container, "require", None)
    if callable(require):
        try:
            return require(key)
        except Exception:
            pass
    return getattr(container, attr, default)


def _tool_deps(container):  # noqa: ANN001, ANN201
    facade = _container_value(
        container,
        AppKey.BROWSER_FACADE,
        "browser_facade",
    )
    serializer = _container_value(
        container,
        AppKey.BROWSER_RESULT_SERIALIZER,
        "browser_result_serializer",
    )
    return BrowserToolDeps(
        browser_tool_application=_container_value(
            container,
            "browser_tool_application",
            "browser_tool_application",
            _BrowserToolApplicationAdapter(facade=facade, serializer=serializer),
        ),
        browser_system_config_store=_container_value(
            container,
            AppKey.BROWSER_SYSTEM_CONFIG_STORE,
            "browser_system_config_store",
        ),
        browser_profile_resolver=_container_value(
            container,
            "browser_profile_resolver",
            "browser_profile_resolver",
            _DEFAULT_BROWSER_PROFILE_RESOLVER,
        ),
        browser_capabilities_resolver=_container_value(
            container,
            "browser_capabilities_resolver",
            "browser_capabilities_resolver",
            _DEFAULT_BROWSER_CAPABILITIES_RESOLVER,
        ),
        settings=getattr(container, "settings", None),
        artifact_service=getattr(container, "artifact_service", None),
        browser_runtime_state_store=getattr(container, "browser_runtime_state_store", None),
        browser_profile_probe_service=getattr(container, "browser_profile_probe_service", None),
        browser_profile_allocator_service=getattr(
            container,
            "browser_profile_allocator_service",
            None,
        ),
    )


def control_handler(container):  # noqa: ANN001, ANN201
    return create_browser_control_handler(_tool_deps(container))


def snapshot_handler(container):  # noqa: ANN001, ANN201
    return create_browser_snapshot_handler(_tool_deps(container))


def page_action_handler(container):  # noqa: ANN001, ANN201
    return create_browser_page_action_handler(_tool_deps(container))


def network_handler(container, *, tool_id="browser.network"):  # noqa: ANN001, ANN201
    return create_browser_network_handler(_tool_deps(container), tool_id=tool_id)


class BrowserToolHttpTestCase(HttpModuleTestCase):
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
        handler = page_action_handler(container)
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

    def test_browser_click_handler_passes_viewport_coordinates(self) -> None:
        captured_requests: list[object] = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                return {
                    "ok": True,
                    "target_id": request.target_id,
                    "payload": dict(request.payload),
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
        handler = page_action_handler(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "kind": "click",
                    "target_id": "tab-1",
                    "x": 530,
                    "y": 636,
                },
            ),
        )

        self.assertEqual(len(captured_requests), 1)
        self.assertEqual(captured_requests[0].payload["x"], 530.0)
        self.assertEqual(captured_requests[0].payload["y"], 636.0)
        self.assertEqual(result.details["payload"]["x"], 530.0)
        self.assertEqual(result.details["payload"]["y"], 636.0)

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
        handler = control_handler(container)
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
        handler = control_handler(container)
        assert handler is not None

        for kind in ("status", "start", "stop"):
            asyncio.run(handler({"kind": kind}))

        self.assertEqual(captured_kinds, ["status", "start", "stop"])

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
        handler = page_action_handler(container)
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
        handler = page_action_handler(container)
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
        handler = page_action_handler(container)
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
        handler = page_action_handler(container)
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
        handler = page_action_handler(container)
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

    def test_browser_profile_resolution_prefers_input_context_then_default(self) -> None:
        captured_profiles: list[str] = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_profiles.append(request.profile_name)
                return {"ok": True, "profile_name": request.profile_name}

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

        context_result = asyncio.run(
            handler(
                {"kind": "wait"},
                ToolExecutionContext(
                    attrs={
                        "browser_profile": "user",
                        "agent_id": "assistant",
                        "active_session_id": "session-1",
                        "run_id": "run-1",
                        "trace_id": "trace-1",
                    },
                ),
            ),
        )
        explicit_result = asyncio.run(
            handler(
                {"kind": "wait", "profile": "crxzipple"},
                ToolExecutionContext(attrs={"browser_profile": "user"}),
            ),
        )
        default_context_result = asyncio.run(
            handler(
                {"kind": "wait"},
                ToolExecutionContext(attrs={"default_browser_profile": "user"}),
            ),
        )
        default_result = asyncio.run(handler({"kind": "wait"}))

        self.assertEqual(captured_profiles, ["user", "crxzipple", "user", "crxzipple"])
        self.assertEqual(context_result.metadata["profile_source"], "context.browser_profile")
        self.assertEqual(context_result.metadata["browser_context_agent_id"], "assistant")
        self.assertEqual(context_result.metadata["browser_context_session_id"], "session-1")
        self.assertEqual(context_result.metadata["browser_context_run_id"], "run-1")
        self.assertEqual(context_result.metadata["browser_context_trace_id"], "trace-1")
        self.assertEqual(context_result.metadata["browser_context_profile"], "user")
        self.assertEqual(
            context_result.metadata["browser_context_profile_source"],
            "context.browser_profile",
        )
        self.assertEqual(explicit_result.metadata["profile_source"], "input.profile")
        self.assertEqual(
            default_context_result.metadata["profile_source"],
            "context.default_browser_profile",
        )
        self.assertEqual(default_result.metadata["profile_source"], "browser.default_profile")

    def test_browser_profile_pool_allocates_profile_and_records_metadata(self) -> None:
        captured_profiles: list[str] = []
        allocation_calls: list[dict[str, object]] = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _ToolApplication:
            def execute_control(  # noqa: ANN201
                self,
                *,
                profile_name,
                kind,
                target_id=None,
                payload=None,
                timeout_ms=None,
            ):
                del kind, target_id, timeout_ms
                captured_profiles.append(profile_name)
                return SimpleNamespace(
                    payload={
                        "ok": True,
                        "target_id": "tab-1",
                        "message": "Opened browser tab.",
                        "value": {
                            "target_id": "tab-1",
                            "url": payload["url"],
                        },
                    },
                    runtime_metadata={"browser_target_id": "tab-1"},
                )

        class _Allocator:
            remembered_targets: list[tuple[str, str]] = []

            def allocate(self, **kwargs):  # noqa: ANN003, ANN201
                allocation_calls.append(dict(kwargs))
                return SimpleNamespace(
                    allocation_id="browser_alloc_1",
                    pool_id=kwargs["pool_id"],
                    profile_name="crawler-a",
                    consumer_kind=kwargs["consumer_kind"],
                    consumer_id=kwargs["consumer_id"],
                    target_host=kwargs["target_host"],
                    status="active",
                    metadata={
                        "selection_reason": "least_busy",
                        "profile_source": "pool_allocation",
                        "host_service_key": "host:browser:crawler-a",
                    },
                )

            def remember_allocation_target(self, *, allocation_id, target_id):  # noqa: ANN001, ANN201
                self.remembered_targets.append((allocation_id, target_id))

        container = SimpleNamespace(
            browser_tool_application=_ToolApplication(),
            browser_system_config_store=_Store(),
            browser_profile_allocator_service=_Allocator(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = control_handler(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {
                    "kind": "open-tab",
                    "url": "https://flights.ctrip.com/online/channel/domestic",
                    "profile_pool": "collection",
                },
                ToolExecutionContext(attrs={"tool_run_id": "tool-run-1", "run_id": "run-1"}),
            ),
        )

        self.assertEqual(captured_profiles, ["crawler-a"])
        self.assertEqual(allocation_calls[0]["pool_id"], "collection")
        self.assertEqual(allocation_calls[0]["consumer_kind"], "orchestration_run")
        self.assertEqual(allocation_calls[0]["consumer_id"], "run-1")
        self.assertEqual(allocation_calls[0]["target_host"], "flights.ctrip.com")
        self.assertEqual(result.metadata["profile_name"], "crawler-a")
        self.assertEqual(result.metadata["profile_source"], "input.profile_pool")
        self.assertEqual(result.metadata["browser_profile"], "crawler-a")
        self.assertEqual(result.metadata["browser_profile_pool"], "collection")
        self.assertEqual(result.metadata["browser_profile_pool_source"], "input.profile_pool")
        self.assertEqual(result.metadata["browser_allocation_id"], "browser_alloc_1")
        self.assertEqual(result.metadata["browser_profile_selection_reason"], "least_busy")
        self.assertEqual(result.metadata["browser_profile_allocation_source"], "pool_allocation")
        self.assertEqual(result.metadata["browser_host_service_key"], "host:browser:crawler-a")
        self.assertEqual(container.browser_profile_allocator_service.remembered_targets, [("browser_alloc_1", "tab-1")])

    def test_browser_context_allocation_reuses_allocated_profile(self) -> None:
        captured_profiles: list[str] = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _ToolApplication:
            def execute_page_action(  # noqa: ANN201
                self,
                *,
                profile_name,
                kind,
                target_id=None,
                ref=None,
                selector=None,
                payload=None,
                timeout_ms=None,
            ):
                del kind, target_id, ref, selector, payload, timeout_ms
                captured_profiles.append(profile_name)
                return SimpleNamespace(payload={"ok": True}, runtime_metadata={})

        class _Allocator:
            def get_allocation(self, *, allocation_id):  # noqa: ANN001, ANN201
                assert allocation_id == "browser_alloc_2"
                return SimpleNamespace(
                    allocation_id=allocation_id,
                    pool_id="collection",
                    profile_name="crawler-b",
                    consumer_kind="tool_run",
                    consumer_id="tool-run-2",
                    target_host="example.com",
                    status="active",
                    metadata={
                        "selection_reason": "reuse_context_allocation",
                        "profile_source": "pool_allocation",
                        "host_service_key": "host:browser:crawler-b",
                    },
                )

            def allocate(self, **_kwargs):  # noqa: ANN003, ANN201
                raise AssertionError("context allocation should be reused")

        container = SimpleNamespace(
            browser_tool_application=_ToolApplication(),
            browser_system_config_store=_Store(),
            browser_profile_allocator_service=_Allocator(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = page_action_handler(container)
        assert handler is not None

        result = asyncio.run(
            handler(
                {"kind": "wait"},
                ToolExecutionContext(attrs={"browser_allocation_id": "browser_alloc_2"}),
            ),
        )

        self.assertEqual(captured_profiles, ["crawler-b"])
        self.assertEqual(result.metadata["profile_source"], "context.browser_allocation_id")
        self.assertEqual(result.metadata["browser_profile"], "crawler-b")
        self.assertEqual(result.metadata["browser_profile_pool"], "collection")
        self.assertEqual(result.metadata["browser_allocation_id"], "browser_alloc_2")

    def test_browser_context_tools_acquire_heartbeat_and_release_lease(self) -> None:
        calls: list[tuple[str, dict[str, object]]] = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _ToolApplication:
            def execute_control(self, **kwargs):  # noqa: ANN003, ANN201
                calls.append(("control", dict(kwargs)))
                return SimpleNamespace(
                    payload={
                        "ok": True,
                        "target_id": "tab-9",
                        "value": {"target_id": "tab-9"},
                    },
                    runtime_metadata={"browser_target_id": "tab-9"},
                )

        class _Allocator:
            def __init__(self) -> None:
                self.allocation = SimpleNamespace(
                    allocation_id="browser_alloc_context",
                    pool_id="profile:crxzipple",
                    profile_name="crxzipple",
                    consumer_kind="orchestration_run",
                    consumer_id="run-1",
                    target_host="example.com",
                    status="active",
                    acquired_at=None,
                    expires_at=None,
                    last_heartbeat_at=None,
                    released_at=None,
                    release_reason=None,
                    owned_target_ids=(),
                    metadata={
                        "selection_reason": "explicit_profile",
                        "profile_source": "explicit_profile",
                    },
                )

            def allocate(self, **kwargs):  # noqa: ANN003, ANN201
                calls.append(("allocate", dict(kwargs)))
                return self.allocation

            def remember_allocation_target(self, *, allocation_id, target_id):  # noqa: ANN001, ANN201
                assert allocation_id == self.allocation.allocation_id
                self.allocation.owned_target_ids = (target_id,)
                return self.allocation

            def get_allocation(self, *, allocation_id):  # noqa: ANN001, ANN201
                assert allocation_id == self.allocation.allocation_id
                return self.allocation

            def heartbeat_allocation(self, *, allocation_id, ttl_seconds=None):  # noqa: ANN001, ANN201
                del ttl_seconds
                assert allocation_id == self.allocation.allocation_id
                self.allocation.metadata = {
                    **dict(self.allocation.metadata),
                    "last_heartbeat_at": "2026-05-29T00:00:00+00:00",
                }
                return self.allocation

            def release_allocation(self, *, allocation_id, reason, recycle_targets=True):  # noqa: ANN001, ANN201
                del recycle_targets
                assert allocation_id == self.allocation.allocation_id
                self.allocation.status = "released"
                self.allocation.release_reason = reason
                return self.allocation

        allocator = _Allocator()
        deps = BrowserToolDeps(
            browser_tool_application=_ToolApplication(),
            browser_system_config_store=_Store(),
            browser_profile_resolver=object(),
            browser_capabilities_resolver=object(),
            browser_profile_allocator_service=allocator,
            settings=SimpleNamespace(browser_enabled=True),
        )
        acquire = create_browser_context_handler(
            deps,
            tool_id="browser.context.acquire",
            action="acquire",
        )
        heartbeat = create_browser_context_handler(
            deps,
            tool_id="browser.context.heartbeat",
            action="heartbeat",
        )
        release = create_browser_context_handler(
            deps,
            tool_id="browser.context.release",
            action="release",
        )
        assert acquire is not None
        assert heartbeat is not None
        assert release is not None
        context = ToolExecutionContext(attrs={"run_id": "run-1"})

        acquired = asyncio.run(acquire({"url": "https://example.com"}, context))
        heartbeated = asyncio.run(
            heartbeat({"lease_id": "browser_alloc_context", "ttl_seconds": 60}, context),
        )
        released = asyncio.run(
            release({"lease_id": "browser_alloc_context", "reason": "done"}, context),
        )

        self.assertEqual(acquired.metadata["browser_context_lease_id"], "browser_alloc_context")
        self.assertEqual(acquired.metadata["browser_profile"], "crxzipple")
        self.assertEqual(heartbeated.metadata["tool"], "browser.context.heartbeat")
        self.assertEqual(released.metadata["browser_context_lease_status"], "released")
        self.assertEqual(calls[0][0], "allocate")
        self.assertEqual(calls[1][1]["kind"], "open-tab")

    def test_browser_profile_pool_selection_error_is_structured(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _ToolApplication:
            def execute_control(self, **_kwargs):  # noqa: ANN003, ANN201
                raise AssertionError("allocation should fail before browser execution")

        class _Allocator:
            def allocate(self, **_kwargs):  # noqa: ANN003, ANN201
                raise BrowserValidationError(
                    "Browser profile pool 'collection' reached max concurrency.",
                )

        container = SimpleNamespace(
            browser_tool_application=_ToolApplication(),
            browser_system_config_store=_Store(),
            browser_profile_allocator_service=_Allocator(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = control_handler(container)
        assert handler is not None

        with self.assertRaises(BrowserToolApplicationError) as raised:
            asyncio.run(
                handler(
                    {
                        "kind": "open-tab",
                        "url": "https://example.com",
                        "profile_pool": "collection",
                    },
                ),
            )

        payload = raised.exception.to_payload()
        self.assertEqual(payload["code"], "browser_profile_pool_concurrency_exceeded")
        self.assertTrue(payload["retryable"])
        self.assertEqual(payload["profile_pool"], "collection")

    def test_browser_tool_missing_profile_fails_without_profile_source_fallback(self) -> None:
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
                            user_data_dir="/tmp/browser-crxzipple",
                        ),
                    ),
                )

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                raise BrowserValidationError(
                    f"Browser profile '{request.profile_name}' is not configured.",
                )

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return result

        class _ProfileResolver:
            def resolve(self, *, system, profile_name):  # noqa: ANN001, ANN201
                for profile in system.profiles:
                    if profile.name == profile_name:
                        return SimpleNamespace(
                            name=profile.name,
                            driver=profile.driver,
                            cdp_url=profile.cdp_url,
                            cdp_port=profile.cdp_port,
                        )
                raise BrowserValidationError(
                    f"Browser profile '{profile_name}' is not configured.",
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

        container = SimpleNamespace(
            browser_facade=_Facade(),
            browser_result_serializer=_Serializer(),
            browser_system_config_store=_Store(),
            browser_profile_resolver=_ProfileResolver(),
            browser_capabilities_resolver=_CapabilitiesResolver(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = page_action_handler(container)
        assert handler is not None

        with self.assertRaises(BrowserValidationError) as exc_info:
            asyncio.run(handler({"kind": "wait", "profile": "ghost"}))

        self.assertEqual(
            str(exc_info.exception),
            "Browser profile 'ghost' is not configured.",
        )

    def test_browser_tool_result_metadata_includes_runtime_generation(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _ToolApplication:
            def execute_page_action(  # noqa: ANN201
                self,
                *,
                profile_name,
                kind,
                target_id=None,
                ref=None,
                selector=None,
                payload=None,
                timeout_ms=None,
            ):
                del kind, target_id, ref, selector, payload, timeout_ms
                assert profile_name == "crxzipple"
                return SimpleNamespace(
                    payload={
                        "ok": True,
                        "target_id": "tab-1",
                        "profile_name": profile_name,
                        "value": {
                            "url": "https://example.com/path?token=secret#private",
                        },
                    },
                    runtime_metadata={
                        "browser_host_service_key": "host:browser:crxzipple",
                        "browser_host_generation": "host-gen-1",
                        "browser_target_id": "tab-1",
                        "browser_page_generation": 3,
                        "browser_page_generation_reason": "navigate",
                        "browser_snapshot_generation": 5,
                        "browser_current_ref_generation": 5,
                    },
                )

        container = SimpleNamespace(
            browser_tool_application=_ToolApplication(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = page_action_handler(container)
        assert handler is not None

        result = asyncio.run(handler({"kind": "wait"}))

        self.assertEqual(
            result.metadata["browser_host_service_key"],
            "host:browser:crxzipple",
        )
        self.assertEqual(result.metadata["browser_host_generation"], "host-gen-1")
        self.assertEqual(result.metadata["browser_target_id"], "tab-1")
        self.assertEqual(result.metadata["browser_page_generation"], 3)
        self.assertEqual(result.metadata["browser_page_generation_reason"], "navigate")
        self.assertEqual(result.metadata["browser_snapshot_generation"], 5)
        self.assertEqual(result.metadata["browser_current_ref_generation"], 5)
        self.assertEqual(
            result.metadata["browser_target_origin"],
            "https://example.com",
        )
        self.assertEqual(
            result.metadata["browser_target_url"],
            "https://example.com/path",
        )

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
        handler = page_action_handler(container)
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
                        control_family="cdp-control",
                        action_family="cdp-backed-playwright",
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
        handler = page_action_handler(container)
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
        handler = page_action_handler(container)
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
        handler = snapshot_handler(container)
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
        handler = page_action_handler(container)
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
        handler = page_action_handler(container)
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
        handler = page_action_handler(container)
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
        handler = page_action_handler(container)
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
        handler = page_action_handler(container)
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
        handler = page_action_handler(container)
        assert handler is not None

        asyncio.run(
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
        handler = page_action_handler(container)
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
            handler = page_action_handler(container)
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
        handler = page_action_handler(container)
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
        handler = page_action_handler(container)
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
        handler = page_action_handler(container)
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
        handler = page_action_handler(container)
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
        handler = page_action_handler(container)
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

    def test_browser_page_action_handler_routes_supported_action_kinds(self) -> None:
        captured_requests = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Facade:
            def execute(self, request):  # noqa: ANN001, ANN201
                captured_requests.append(request)
                return {"ok": True, "command": {"kind": request.kind}}

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
        assert handler is not None

        cases = [
            (
                {"kind": "pdf", "print_background": False},
                "pdf",
                {"print_background": False},
            ),
            (
                {"kind": "wait-download"},
                "wait-download",
                {},
            ),
            (
                {"kind": "cookies", "operation": "get"},
                "cookies",
                {"cookies_operation": "get"},
            ),
            (
                {"kind": "storage", "storage_kind": "local", "operation": "get", "key": "theme"},
                "storage",
                {
                    "storage_kind": "local",
                    "storage_operation": "get",
                    "storage_key": "theme",
                },
            ),
            (
                {"kind": "console", "level": "error", "limit": 5},
                "console",
                {"level": "error", "limit": 5},
            ),
        ]

        for arguments, expected_kind, expected_payload in cases:
            result = asyncio.run(handler(arguments))
            self.assertEqual(result.metadata["tool"], "browser.action")
            self.assertEqual(result.metadata["kind"], expected_kind)

        self.assertEqual([request.kind for request in captured_requests], [item[1] for item in cases])
        self.assertEqual(
            [dict(request.payload) for request in captured_requests],
            [item[2] for item in cases],
        )

    def test_browser_action_rejects_curated_diagnostic_escape_hatches(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _Serializer:
            @staticmethod
            def serialize(result):  # noqa: ANN001, ANN201
                return result

        container = SimpleNamespace(
            browser_facade=object(),
            browser_result_serializer=_Serializer(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = page_action_handler(container)
        assert handler is not None

        for arguments in (
            {"kind": "cdp-raw", "method": "Runtime.evaluate"},
            {"kind": "network-inspect"},
        ):
            with self.subTest(arguments=arguments):
                with self.assertRaises(BrowserValidationError):
                    asyncio.run(handler(arguments))

    def test_browser_network_handler_maps_stable_tools_to_kebab_action_kinds(self) -> None:
        captured_requests: list[dict[str, object]] = []

        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        class _ToolApplication:
            def execute_page_action(  # noqa: ANN201
                self,
                *,
                profile_name,
                kind,
                target_id=None,
                ref=None,
                selector=None,
                payload=None,
                timeout_ms=None,
            ):
                del profile_name, ref, selector, timeout_ms
                captured_requests.append(
                    {
                        "kind": kind,
                        "target_id": target_id,
                        "payload": dict(payload or {}),
                    },
                )
                return SimpleNamespace(
                    payload={
                        "ok": True,
                        "command": {"kind": kind},
                        "value": {"result": {"capture_id": (payload or {}).get("capture_id")}},
                    },
                    runtime_metadata={},
                )

        container = SimpleNamespace(
            browser_tool_application=_ToolApplication(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )

        cases = [
            (
                "browser.network.start_capture",
                {"target_id": "tab-1", "capture_id": "cap-1", "max_requests": 250, "include_headers": True},
                "network-start-capture",
                {"capture_id": "cap-1", "max_requests": 250, "include_headers": True},
            ),
            (
                "browser.network.stop_capture",
                {"capture_id": "cap-1"},
                "network-stop-capture",
                {"capture_id": "cap-1"},
            ),
            (
                "browser.network.list_requests",
                {
                    "capture_id": "cap-1",
                    "method": "POST",
                    "status": 200,
                    "domain": "api.example.com",
                    "limit": 5,
                },
                "network-list-requests",
                {
                    "capture_id": "cap-1",
                    "limit": 5,
                    "filters": {
                        "domain": "api.example.com",
                        "method": "POST",
                        "status": 200,
                    },
                },
            ),
            (
                "browser.network.get_request",
                {"capture_id": "cap-1", "request_id": "req-1"},
                "network-get-request",
                {"capture_id": "cap-1", "request_id": "req-1"},
            ),
            (
                "browser.network.get_response_body",
                {"capture_id": "cap-1", "request_id": "req-1", "max_body_bytes": 4096},
                "network-get-response-body",
                {"capture_id": "cap-1", "request_id": "req-1", "max_body_bytes": 4096},
            ),
            (
                "browser.network.get_request_body",
                {"capture_id": "cap-1", "request_id": "req-1"},
                "network-get-request-body",
                {"capture_id": "cap-1", "request_id": "req-1"},
            ),
            (
                "browser.network.fetch_as_page",
                {
                    "target_id": "tab-1",
                    "url": "/api/details",
                    "method": "GET",
                    "headers": {"X-Trace": "trace-1"},
                },
                "network-fetch-as-page",
                {
                    "url": "/api/details",
                    "method": "GET",
                    "headers": {"X-Trace": "trace-1"},
                },
            ),
            (
                "browser.network.replay_request",
                {
                    "capture_id": "cap-1",
                    "request_id": "req-1",
                    "allow_mutating": True,
                    "json": {"query": "flight"},
                },
                "network-replay-request",
                {
                    "capture_id": "cap-1",
                    "request_id": "req-1",
                    "allow_mutating": True,
                    "json": {"query": "flight"},
                },
            ),
            (
                "browser.network.clear_capture",
                {"capture_id": "cap-1"},
                "network-clear-capture",
                {"capture_id": "cap-1"},
            ),
        ]

        for tool_id, arguments, expected_kind, _expected_payload in cases:
            handler = network_handler(container, tool_id=tool_id)
            assert handler is not None
            result = asyncio.run(handler(arguments))
            self.assertEqual(result.metadata["tool"], tool_id)
            self.assertEqual(result.metadata["kind"], expected_kind)

        self.assertEqual([item["kind"] for item in captured_requests], [item[2] for item in cases])
        self.assertEqual([item["payload"] for item in captured_requests], [item[3] for item in cases])
        self.assertEqual(captured_requests[0]["target_id"], "tab-1")

    def test_browser_network_handler_rejects_cdp_raw_as_regular_path(self) -> None:
        class _Store:
            def load(self):  # noqa: ANN201
                return SimpleNamespace(default_profile="crxzipple")

        container = SimpleNamespace(
            browser_tool_application=object(),
            browser_system_config_store=_Store(),
            settings=SimpleNamespace(browser_enabled=True),
        )
        handler = network_handler(container)
        assert handler is not None

        with self.assertRaises(BrowserValidationError):
            asyncio.run(handler({"kind": "cdp-raw", "method": "Network.enable"}))

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
