from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from crxzipple.modules.browser.domain import (
    BrowserActionTarget,
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileConfig,
    BrowserProfileCapabilities,
    BrowserProfileRuntimeState,
    BrowserStoredRef,
    BrowserSystemConfig,
    BrowserTab,
    BrowserValidationError,
    ResolvedBrowserProfile,
)
from crxzipple.modules.browser.infrastructure import (
    BrowserDiagnosticsService,
    BrowserPageNetworkFetchService,
    CdpBackedPlaywrightActionEngine,
    InMemoryBrowserRefStore,
)
from crxzipple.modules.daemon import (
    DaemonApplicationService,
    DaemonInstance,
    DaemonServiceSpec,
    FileBackedDaemonInstanceStore,
    FileBackedDaemonLeaseStore,
    FileBackedDaemonServiceSpecStore,
    bootstrap_daemon_state_root,
)
from tests.unit.support import FakePlaywrightCdpSessionPool


class BrowserPlaywrightActionEngineTestCase(unittest.TestCase):
    def _build_daemon_service(self, root_dir: Path) -> DaemonApplicationService:
        state_root = bootstrap_daemon_state_root(str(root_dir))
        spec_store = FileBackedDaemonServiceSpecStore(
            state_root.config_dir,
            bootstrap_specs=(
                DaemonServiceSpec(
                    key="host:browser:crxzipple",
                    role="host",
                    managed_by="internal",
                    transport="process",
                    start_policy="ensure",
                    restart_policy="on-failure",
                ),
            ),
        )
        return DaemonApplicationService(
            service_spec_store=spec_store,
            instance_store=FileBackedDaemonInstanceStore(state_root.instances_dir),
            lease_store=FileBackedDaemonLeaseStore(state_root.leases_dir),
        )

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.daemon_service = self._build_daemon_service(Path(self._tempdir.name))
        self.daemon_service.save_instance(
            DaemonInstance(
                id="browser-host-crxzipple",
                service_key="host:browser:crxzipple",
                status="ready",
                pid=8123,
                endpoint="http://127.0.0.1:9222",
            )
        )
        self.session_pool = FakePlaywrightCdpSessionPool()
        self.ref_store = InMemoryBrowserRefStore()
        self.emitted_browser_events: list[tuple[str, dict[str, object]]] = []
        self.engine = CdpBackedPlaywrightActionEngine(
            session_pool=self.session_pool,
            ref_store=self.ref_store,
            daemon_service=self.daemon_service,
            network_page_fetch_service=BrowserPageNetworkFetchService(
                event_emitter=lambda event_name, payload: self.emitted_browser_events.append(
                    (event_name, payload),
                ),
            ),
            diagnostics_service=BrowserDiagnosticsService(
                event_emitter=lambda event_name, payload: self.emitted_browser_events.append(
                    (event_name, payload),
                ),
            ),
        )
        self.profile = ResolvedBrowserProfile(
            name="crxzipple",
            driver="managed",
            cdp_url="http://127.0.0.1:9222",
            cdp_port=9222,
            user_data_dir=None,
            attach_only=False,
            is_loopback=True,
        )
        self.system = BrowserSystemConfig(
            default_profile="crxzipple",
            profiles=(BrowserProfileConfig(name="crxzipple"),),
        )
        self.capabilities = BrowserProfileCapabilities(
            mode="local-managed",
            is_remote=False,
            control_family="cdp-control",
            action_family="cdp-backed-playwright",
            can_launch=True,
            supports_reset=True,
            supports_per_tab_ws=True,
            supports_json_tab_endpoints=True,
            supports_managed_tab_limit=True,
        )
        self.runtime_state = BrowserProfileRuntimeState(profile_name="crxzipple")
        self.tab = BrowserTab(target_id="tab-1", url="https://example.com")

    def _plan(self, command: BrowserPageActionCommand) -> BrowserExecutionPlan:
        return BrowserExecutionPlan(
            command=command,
            system=self.system,
            profile=self.profile,
            capabilities=self.capabilities,
            control_family="cdp-control",
            action_family="cdp-backed-playwright",
            launch_policy="attach-only",
            tab_selection_policy="sticky-last-target",
        )

    def test_click_and_type_use_locator_actions(self) -> None:
        click_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="click",
            target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
            payload={"button": "left"},
            timeout_ms=1500,
        )
        click_result = self.engine.execute(
            plan=self._plan(click_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=click_command,
        )

        type_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="type",
            target=BrowserActionTarget(target_id="tab-1", selector="#query"),
            payload={"text": "search"},
        )
        type_result = self.engine.execute(
            plan=self._plan(type_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=type_command,
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(click_result.value["engine"], "cdp-backed-playwright")
        self.assertEqual(click_result.value["selector"], "#submit")
        self.assertEqual(type_result.value["result"]["text"], "search")

        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        self.assertEqual(page.operations[0][0], "click")
        self.assertIn("type", [operation[0] for operation in page.operations])
        self.assertEqual(click_result.value["result"]["mode"], "direct")

    def test_click_can_target_viewport_coordinates(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        click_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="click",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "x": 530,
                "y": 636,
                "button": "left",
                "double_click": True,
            },
            timeout_ms=1500,
        )

        click_result = self.engine.execute(
            plan=self._plan(click_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=click_command,
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(click_result.value["result"]["mode"], "coordinate")
        self.assertEqual(click_result.value["result"]["x"], 530.0)
        self.assertEqual(click_result.value["result"]["y"], 636.0)
        self.assertIn(
            ("mouse.click", 530.0, 636.0, {"button": "left", "click_count": 2}),
            page.operations,
        )

    def test_upload_uses_locator_set_input_files(self) -> None:
        upload_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="upload",
            target=BrowserActionTarget(target_id="tab-1", selector="#file-input"),
            payload={"paths": ["/tmp/one.txt", "/tmp/two.txt"]},
            timeout_ms=2500,
        )

        upload_result = self.engine.execute(
            plan=self._plan(upload_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=upload_command,
        )

        self.assertTrue(upload_result.ok)
        self.assertEqual(upload_result.value["engine"], "cdp-backed-playwright")
        self.assertEqual(
            upload_result.value["result"],
            {
                "kind": "upload",
                "paths": ["/tmp/one.txt", "/tmp/two.txt"],
            },
        )

        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        self.assertIn(
            (
                "set_input_files",
                "#file-input",
                ["/tmp/one.txt", "/tmp/two.txt"],
                {"timeout": 2500.0},
                (),
            ),
            page.operations,
        )

    def test_download_clicks_locator_and_serializes_file(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.queue_download(filename="report.csv", data=b"city,price\nkunming,320\n")
        download_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="download",
            target=BrowserActionTarget(target_id="tab-1", selector="#download"),
            payload={"button": "left"},
            timeout_ms=1800,
        )

        download_result = self.engine.execute(
            plan=self._plan(download_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=download_command,
        )

        self.assertTrue(download_result.ok)
        self.assertEqual(download_result.value["result"]["kind"], "download")
        self.assertEqual(download_result.value["result"]["name"], "report.csv")
        self.assertEqual(download_result.value["result"]["content_type"], "text/csv")
        self.assertIn(("expect_download", {"timeout": 1800.0}), page.operations)
        self.assertIn(("click", "#download", {"timeout": 1800.0, "button": "left"}, ()), page.operations)

    def test_wait_download_waits_for_next_download_event(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.queue_download(filename="invoice.pdf", data=b"%PDF-1.4")
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="wait-download",
            target=BrowserActionTarget(target_id="tab-1"),
            timeout_ms=2200,
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.value["result"]["kind"], "download")
        self.assertEqual(result.value["result"]["name"], "invoice.pdf")
        self.assertEqual(result.value["result"]["content_type"], "application/pdf")
        self.assertIn(("wait_for_event", "download", {"timeout": 2200.0}), page.operations)

    def test_dialog_waits_for_next_dialog_and_accepts_prompt(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.queue_dialog(
            dialog_type="prompt",
            message="Enter destination",
            default_value="Kunming",
        )
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="dialog",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"accept": True, "prompt_text": "Shanghai"},
            timeout_ms=1700,
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.value["result"]["kind"], "dialog")
        self.assertEqual(result.value["result"]["type"], "prompt")
        self.assertEqual(result.value["result"]["message"], "Enter destination")
        self.assertEqual(result.value["result"]["default_value"], "Kunming")
        self.assertEqual(result.value["result"]["handled_as"], "accept")
        self.assertEqual(result.value["result"]["prompt_text"], "Shanghai")
        self.assertIn(("wait_for_event", "dialog", {"timeout": 1700.0}), page.operations)
        self.assertIn(("dialog.accept", "Shanghai"), page.operations)

    def test_console_returns_buffered_messages_and_can_clear(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.emit_console(
            text="Network fallback",
            message_type="warning",
            location={"url": "https://example.com/app.js", "lineNumber": 9, "columnNumber": 2},
        )
        page.emit_console(text="Boot complete", message_type="info")

        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="console",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"level": "warn", "clear": True},
            timeout_ms=1600,
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        self.assertTrue(result.ok)
        self.assertEqual(result.value["result"]["kind"], "console")
        self.assertEqual(result.value["result"]["count"], 1)
        self.assertEqual(result.value["result"]["messages"][0]["level"], "warn")
        self.assertEqual(result.value["result"]["messages"][0]["text"], "Network fallback")
        self.assertEqual(
            result.value["result"]["messages"][0]["location"],
            {
                "url": "https://example.com/app.js",
                "line_number": 9,
                "column_number": 2,
            },
        )

        follow_up = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="console",
            target=BrowserActionTarget(target_id="tab-1"),
        )
        follow_up_result = self.engine.execute(
            plan=self._plan(follow_up),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=follow_up,
        )
        self.assertEqual(follow_up_result.value["result"]["count"], 0)

    def test_storage_supports_set_get_and_clear(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")

        set_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="storage",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "storage_kind": "local",
                "storage_operation": "set",
                "storage_key": "theme",
                "storage_value": "dark",
            },
        )
        set_result = self.engine.execute(
            plan=self._plan(set_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=set_command,
        )
        self.assertEqual(set_result.value["result"]["values"], {"theme": "dark"})
        self.assertEqual(page.local_storage, {"theme": "dark"})

        get_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="storage",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "storage_kind": "local",
                "storage_operation": "get",
                "storage_key": "theme",
            },
        )
        get_result = self.engine.execute(
            plan=self._plan(get_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=get_command,
        )
        self.assertEqual(get_result.value["result"]["values"], {"theme": "dark"})

        clear_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="storage",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "storage_kind": "local",
                "storage_operation": "clear",
            },
        )
        clear_result = self.engine.execute(
            plan=self._plan(clear_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=clear_command,
        )
        self.assertEqual(clear_result.value["result"]["values"], {})
        self.assertEqual(page.local_storage, {})

    def test_deep_storage_read_tools_use_cdp_and_page_context(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.indexeddb_databases = {
            "app-db": {
                "version": 2,
                "objectStores": [
                    {
                        "name": "flights",
                        "keyPath": "id",
                        "autoIncrement": False,
                        "indexes": [{"name": "by-city", "keyPath": "city"}],
                    }
                ],
                "entries": {
                    "flights": [
                        {
                            "key": "flight-1",
                            "primaryKey": "flight-1",
                            "value": {
                                "city": "Kunming",
                                "token": "secret-token",
                            },
                        }
                    ]
                },
            }
        }
        page.cache_storage_caches = [
            {
                "cacheId": "cache-1",
                "cacheName": "runtime-cache",
                "securityOrigin": "https://example.com",
            }
        ]
        page.cache_storage_entries = {
            "cache-1": [
                {
                    "requestURL": "https://example.com/api/flights?token=secret",
                    "requestMethod": "GET",
                    "responseStatus": 200,
                    "responseHeaders": [
                        {"name": "content-type", "value": "application/json"},
                        {"name": "set-cookie", "value": "sid=secret"},
                    ],
                }
            ]
        }
        page.cache_storage_responses = {
            ("cache-1", "https://example.com/api/flights?token=secret"): {
                "body": '{"api_key":"secret","ok":true}',
            }
        }
        page.service_worker_registrations = [
            {
                "scope_url": "https://example.com/",
                "active": {
                    "script_url": "https://example.com/sw.js",
                    "state": "activated",
                },
            }
        ]

        indexeddb_list = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="storage-indexeddb-list",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="storage-indexeddb-list",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={},
            ),
        )
        self.assertEqual(indexeddb_list.value["result"]["database_names"], ["app-db"])
        self.assertEqual(
            indexeddb_list.value["result"]["databases"][0]["object_stores"][0]["name"],
            "flights",
        )

        indexeddb_query_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="storage-indexeddb-query",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"database_name": "app-db", "object_store_name": "flights"},
        )
        indexeddb_query = self.engine.execute(
            plan=self._plan(indexeddb_query_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=indexeddb_query_command,
        )
        self.assertEqual(indexeddb_query.value["result"]["entries"][0]["key"], "flight-1")
        self.assertEqual(
            indexeddb_query.value["result"]["entries"][0]["value"]["token"],
            "[redacted]",
        )

        cache_list_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="storage-cache-list",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={},
        )
        cache_list = self.engine.execute(
            plan=self._plan(cache_list_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=cache_list_command,
        )
        self.assertEqual(cache_list.value["result"]["caches"][0]["cache_name"], "runtime-cache")

        cache_get_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="storage-cache-get",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "cache_name": "runtime-cache",
                "request_url": "https://example.com/api/flights?token=secret",
            },
        )
        cache_get = self.engine.execute(
            plan=self._plan(cache_get_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=cache_get_command,
        )
        self.assertIn("%5Bredacted%5D", cache_get.value["result"]["request_url"])
        self.assertEqual(
            cache_get.value["result"]["entries"][0]["response_headers"]["set-cookie"],
            "[redacted]",
        )
        self.assertIn("[redacted]", cache_get.value["result"]["response"]["body"])

        service_worker_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="service-worker-list",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={},
        )
        service_workers = self.engine.execute(
            plan=self._plan(service_worker_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=service_worker_command,
        )
        self.assertEqual(service_workers.value["result"]["count"], 1)
        self.assertEqual(
            service_workers.value["result"]["registrations"][0]["active"]["state"],
            "activated",
        )
        self.assertIn(("cdp.send", "IndexedDB.requestDatabaseNames", {"securityOrigin": "https://example.com"}), page.operations)
        self.assertIn(("cdp.send", "CacheStorage.requestCacheNames", {"securityOrigin": "https://example.com"}), page.operations)

    def test_cookies_supports_set_get_and_clear(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")

        set_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="cookies",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "cookies_operation": "set",
                "cookie": {
                    "name": "session",
                    "value": "abc123",
                    "url": "https://example.com",
                    "httpOnly": True,
                },
            },
        )
        set_result = self.engine.execute(
            plan=self._plan(set_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=set_command,
        )
        self.assertEqual(set_result.value["result"]["count"], 1)
        self.assertEqual(set_result.value["result"]["cookies"][0]["name"], "session")
        self.assertEqual(page.browser_context.cookie_store[0]["value"], "abc123")

        get_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="cookies",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "cookies_operation": "get",
            },
        )
        get_result = self.engine.execute(
            plan=self._plan(get_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=get_command,
        )
        self.assertEqual(get_result.value["result"]["count"], 1)
        self.assertEqual(get_result.value["result"]["cookies"][0]["name"], "session")

        clear_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="cookies",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "cookies_operation": "clear",
            },
        )
        clear_result = self.engine.execute(
            plan=self._plan(clear_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=clear_command,
        )
        self.assertEqual(clear_result.value["result"]["cookies"], [])
        self.assertEqual(page.browser_context.cookie_store, [])

    def test_cdp_raw_sends_command_through_page_cdp_session(self) -> None:
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="cdp-raw",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "method": "Runtime.evaluate",
                "params": {"expression": "1 + 1"},
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        page = self.session_pool.pages["tab-1"]
        self.assertTrue(result.ok)
        self.assertEqual(result.value["result"]["kind"], "cdp-raw")
        self.assertEqual(result.value["result"]["method"], "Runtime.evaluate")
        self.assertEqual(
            result.value["result"]["result"],
            {
                "method": "Runtime.evaluate",
                "params": {"expression": "1 + 1"},
                "targetId": "tab-1",
            },
        )
        self.assertIn(("context.new_cdp_session", "tab-1"), page.operations)
        self.assertIn(
            ("cdp.send", "Runtime.evaluate", {"expression": "1 + 1"}),
            page.operations,
        )
        self.assertIn(("cdp.detach",), page.operations)

    def test_network_inspect_returns_performance_entries_and_cdp_facts(self) -> None:
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-inspect",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"limit": 10},
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        page = self.session_pool.pages["tab-1"]
        self.assertTrue(result.ok)
        payload = result.value["result"]
        self.assertEqual(payload["kind"], "network-inspect")
        self.assertEqual(payload["url"], page.url)
        self.assertEqual(payload["performance"]["entry_count"], 2)
        self.assertEqual(payload["performance"]["entries"][0]["entry_type"], "navigation")
        self.assertEqual(payload["cdp"]["metrics"]["metrics"][0]["name"], "Timestamp")
        self.assertEqual(
            payload["cdp"]["resource_tree"]["frameTree"]["resources"][0]["type"],
            "Script",
        )
        self.assertEqual(payload["errors"], [])
        self.assertIn(
            ("cdp.send", "Performance.getMetrics", {}),
            page.operations,
        )
        self.assertIn(
            ("cdp.send", "Page.getResourceTree", {}),
            page.operations,
        )

    def test_emulation_set_applies_target_scoped_cdp_overrides(self) -> None:
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="emulation-set",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "width": 390,
                "height": 844,
                "device_scale_factor": 3,
                "is_mobile": True,
                "has_touch": True,
                "user_agent": "Test Mobile UA",
                "timezone_id": "Asia/Shanghai",
                "locale": "zh-CN",
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        page = self.session_pool.pages["tab-1"]
        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertEqual(payload["kind"], "emulation-set")
        self.assertEqual(payload["policy"]["runtime_scope"], "target")
        self.assertEqual(
            payload["changed_controls"],
            ["device_metrics", "user_agent", "timezone", "locale"],
        )
        self.assertIn(
            (
                "cdp.send",
                "Emulation.setDeviceMetricsOverride",
                {
                    "width": 390,
                    "height": 844,
                    "deviceScaleFactor": 3.0,
                    "mobile": True,
                    "screenWidth": 390,
                    "screenHeight": 844,
                    "dontSetVisibleSize": False,
                    "screenOrientation": {
                        "type": "portraitPrimary",
                        "angle": 0,
                    },
                    "hasTouch": True,
                },
            ),
            page.operations,
        )
        self.assertIn(
            ("cdp.send", "Emulation.setUserAgentOverride", {"userAgent": "Test Mobile UA"}),
            page.operations,
        )
        self.assertIn(("cdp.detach",), page.operations)

    def test_environment_permissions_geolocation_and_network_conditions(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        grant_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="permissions-grant",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "permissions": ["geolocation", "notifications"],
                "origin": "https://example.com",
            },
        )
        grant_result = self.engine.execute(
            plan=self._plan(grant_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=grant_command,
        )

        geolocation_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="geolocation-set",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"latitude": 25.04, "longitude": 102.71, "accuracy": 10},
        )
        geolocation_result = self.engine.execute(
            plan=self._plan(geolocation_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=geolocation_command,
        )

        network_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-conditions-set",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "offline": False,
                "latency_ms": 120,
                "download_kbps": 512,
                "upload_kbps": 128,
                "connection_type": "cellular3g",
            },
        )
        network_result = self.engine.execute(
            plan=self._plan(network_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=network_command,
        )

        self.assertEqual(grant_result.value["result"]["permission_names"], ["geolocation", "notifications"])
        self.assertIn(
            (
                "context.grant_permissions",
                {
                    "permissions": ["geolocation", "notifications"],
                    "origin": "https://example.com",
                },
            ),
            page.operations,
        )
        self.assertEqual(
            geolocation_result.value["result"]["geolocation"],
            {"latitude": 25.04, "longitude": 102.71, "accuracy": 10.0},
        )
        self.assertIn(
            (
                "cdp.send",
                "Emulation.setGeolocationOverride",
                {"latitude": 25.04, "longitude": 102.71, "accuracy": 10.0},
            ),
            page.operations,
        )
        self.assertEqual(
            network_result.value["result"]["network_conditions"],
            {
                "offline": False,
                "latency_ms": 120.0,
                "download_throughput_bytes_per_second": 65536,
                "upload_throughput_bytes_per_second": 16384,
                "connection_type": "cellular3g",
            },
        )
        self.assertIn(
            (
                "cdp.send",
                "Network.emulateNetworkConditions",
                {
                    "offline": False,
                    "latency": 120.0,
                    "downloadThroughput": 65536,
                    "uploadThroughput": 16384,
                    "connectionType": "cellular3g",
                },
            ),
            page.operations,
        )

    def test_emulation_reset_clears_target_overrides(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="emulation-reset",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={},
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        self.assertTrue(result.ok)
        self.assertIn("device_metrics", result.value["result"]["changed_controls"])
        self.assertIn("permissions", result.value["result"]["changed_controls"])
        self.assertIn(("cdp.send", "Emulation.clearDeviceMetricsOverride", {}), page.operations)
        self.assertIn(("cdp.send", "Emulation.clearGeolocationOverride", {}), page.operations)
        self.assertIn(("context.clear_permissions",), page.operations)

    def test_diagnostics_collects_lifecycle_performance_and_console_errors(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.emit_console(text="Something failed", message_type="error")
        page.emit_page_error(
            message="Unhandled promise rejection",
            name="UnhandledRejection",
            stack="stack line",
        )
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="diagnostics-collect",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"include_entries": True},
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        payload = result.value["result"]
        self.assertTrue(result.ok)
        self.assertEqual(payload["kind"], "diagnostics-collect")
        self.assertEqual(payload["issue_count"], 2)
        self.assertEqual(payload["diagnostics"]["errors"][0]["text"], "Something failed")
        self.assertEqual(payload["diagnostics"]["errors"][1]["source"], "pageerror")
        self.assertEqual(
            payload["diagnostics"]["errors"][1]["text"],
            "Unhandled promise rejection",
        )
        self.assertEqual(payload["diagnostics"]["lifecycle"]["url"], "https://example.com")
        self.assertEqual(
            payload["diagnostics"]["performance"]["metrics"]["metrics"][0]["name"],
            "Timestamp",
        )
        self.assertIn(("cdp.send", "Page.getNavigationHistory", {}), page.operations)
        self.assertEqual(
            self.emitted_browser_events[-1][0],
            "browser.diagnostics.collected",
        )
        self.assertEqual(self.emitted_browser_events[-1][1]["issue_count"], 2)
        self.assertEqual(
            self.emitted_browser_events[-1][1]["diagnostic_kind"],
            "diagnostics-collect",
        )

    def test_trace_start_stop_and_export_returns_zip_payload(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        start_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="trace-start",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"trace_id": "trace-1", "title": "checkout"},
        )
        start_result = self.engine.execute(
            plan=self._plan(start_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=start_command,
        )

        stop_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="trace-stop",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"trace_id": "trace-1"},
        )
        stop_result = self.engine.execute(
            plan=self._plan(stop_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=stop_command,
        )

        export_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="trace-export",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"trace_id": "trace-1"},
        )
        export_result = self.engine.execute(
            plan=self._plan(export_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=export_command,
        )

        self.assertEqual(start_result.value["result"]["status"], "active")
        self.assertEqual(stop_result.value["result"]["content_type"], "application/zip")
        self.assertEqual(stop_result.value["result"]["encoding"], "base64")
        self.assertEqual(export_result.value["result"]["data"], stop_result.value["result"]["data"])
        self.assertIn(
            (
                "tracing.start",
                {"screenshots": True, "snapshots": True, "sources": False, "title": "checkout"},
            ),
            page.operations,
        )
        self.assertTrue(any(operation[0] == "tracing.stop" for operation in page.operations))
        self.assertIn(
            "browser.trace.exported",
            [event_name for event_name, _payload in self.emitted_browser_events],
        )

    def test_network_capture_actions_record_and_list_requests(self) -> None:
        start_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-start-capture",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "capture_id": "cap-1",
                "max_requests": 10,
                "max_body_bytes": 128,
            },
        )

        start_result = self.engine.execute(
            plan=self._plan(start_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=start_command,
        )

        self.assertTrue(start_result.ok)
        self.assertEqual(
            start_result.value["result"]["capture"]["capture_id"],
            "cap-1",
        )
        self.assertEqual(start_result.value["result"]["capture"]["status"], "active")

        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        session = page.browser_context.cdp_sessions[-1]
        assert self.engine.network_capture_controller is not None
        subscription = self.engine.network_capture_controller._subscriptions[
            ("crxzipple", "tab-1", "cap-1")
        ]
        self.assertEqual(subscription.session.mode, "subscription")
        self.assertFalse(subscription.session.detached)
        page.network_response_bodies["req-1"] = {
            "body": '{"ok":true}',
            "base64Encoded": False,
        }
        session.emit(
            "Network.requestWillBeSent",
            {
                "requestId": "req-1",
                "type": "XHR",
                "frameId": "frame-tab-1",
                "loaderId": "loader-1",
                "request": {
                    "url": "https://example.com/api/search?token=secret&city=kunming",
                    "method": "POST",
                    "headers": {
                        "Authorization": "Bearer secret",
                        "Content-Type": "application/json",
                    },
                    "postData": '{"query":"flights","token":"secret"}',
                },
                "initiator": {"type": "script"},
            },
        )
        session.emit(
            "Network.responseReceived",
            {
                "requestId": "req-1",
                "type": "XHR",
                "response": {
                    "status": 200,
                    "headers": {
                        "Content-Type": "application/json",
                        "Set-Cookie": "session=secret",
                    },
                    "mimeType": "application/json",
                    "timing": {"receiveHeadersEnd": 12.0},
                },
            },
        )
        session.emit(
            "Network.loadingFinished",
            {
                "requestId": "req-1",
                "encodedDataLength": 128,
            },
        )

        list_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-list-requests",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"capture_id": "cap-1", "limit": 10},
        )

        list_result = self.engine.execute(
            plan=self._plan(list_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=list_command,
        )

        payload = list_result.value["result"]
        self.assertEqual(payload["kind"], "network-list-requests")
        self.assertEqual(payload["capture"]["capture_id"], "cap-1")
        self.assertEqual(payload["request_count"], 1)
        self.assertEqual(payload["requests"][0]["resource_type"], "xhr")
        self.assertEqual(payload["requests"][0]["status"], 200)
        self.assertEqual(
            payload["requests"][0]["url"],
            "https://example.com/api/search?token=%5Bredacted%5D&city=kunming",
        )
        self.assertEqual(payload["requests"][0]["request_headers"]["Authorization"], "[redacted]")
        self.assertEqual(payload["requests"][0]["response_headers"]["Set-Cookie"], "[redacted]")
        self.assertEqual(payload["requests"][0]["encoded_data_length"], 128)

        request_id = payload["requests"][0]["request_id"]
        get_request_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-get-request",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "capture_id": "cap-1",
                "request_id": request_id,
            },
        )

        get_request_result = self.engine.execute(
            plan=self._plan(get_request_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=get_request_command,
        )

        self.assertEqual(get_request_result.value["result"]["request"]["request_id"], "req-1")
        self.assertEqual(
            get_request_result.value["result"]["request"]["request_post_data_preview"],
            '{"query":"flights","token":"[redacted]"}',
        )

        request_body_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-get-request-body",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "capture_id": "cap-1",
                "request_id": request_id,
            },
        )

        request_body_result = self.engine.execute(
            plan=self._plan(request_body_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=request_body_command,
        )

        self.assertEqual(request_body_result.value["result"]["body_kind"], "request")
        self.assertEqual(
            request_body_result.value["result"]["body"],
            '{"query":"flights","token":"[redacted]"}',
        )

        body_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-get-response-body",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "capture_id": "cap-1",
                "request_id": request_id,
            },
        )

        body_result = self.engine.execute(
            plan=self._plan(body_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=body_command,
        )

        self.assertEqual(body_result.value["result"]["body"], '{"ok":true}')
        self.assertEqual(body_result.value["result"]["body_kind"], "response")

        page.network_fetch_responses["https://example.com/api/details?token=secret"] = {
            "ok": True,
            "url": "https://example.com/api/details?token=secret",
            "status": 200,
            "headers": {"content-type": "application/json"},
            "body": '{"access_token":"secret","ok":true}',
            "size_bytes": 35,
            "stored_size_bytes": 35,
            "truncated": False,
        }
        fetch_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-fetch-as-page",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "url": "/api/details?token=secret",
                "method": "GET",
                "headers": {"Authorization": "Bearer secret", "X-Trace": "trace-1"},
            },
        )

        fetch_result = self.engine.execute(
            plan=self._plan(fetch_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=fetch_command,
        )

        self.assertEqual(fetch_result.value["result"]["status"], 200)
        self.assertEqual(
            fetch_result.value["result"]["url"],
            "https://example.com/api/details?token=%5Bredacted%5D",
        )
        self.assertEqual(fetch_result.value["result"]["request"]["headers"], {"X-Trace": "trace-1"})
        self.assertNotIn("secret", fetch_result.value["result"]["body"])

        page.network_fetch_responses["https://example.com/api/search?city=kunming"] = {
            "ok": True,
            "url": "https://example.com/api/search?city=kunming",
            "status": 201,
            "headers": {"content-type": "application/json"},
            "body": '{"items":[1]}',
            "size_bytes": 13,
            "stored_size_bytes": 13,
            "truncated": False,
        }
        replay_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-replay-request",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "capture_id": "cap-1",
                "request_id": request_id,
                "url": "/api/search?city=kunming",
                "json": {"query": "flights"},
                "allow_mutating": True,
            },
        )

        replay_result = self.engine.execute(
            plan=self._plan(replay_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=replay_command,
        )

        self.assertEqual(replay_result.value["result"]["status"], 201)
        self.assertEqual(replay_result.value["result"]["source_request_id"], "req-1")
        self.assertEqual(
            replay_result.value["result"]["request"]["url"],
            "https://example.com/api/search?city=kunming",
        )
        self.assertEqual(replay_result.value["result"]["body"], '{"items":[1]}')
        self.assertEqual(
            [event_name for event_name, _payload in self.emitted_browser_events],
            [
                "browser.network.fetch.executed",
                "browser.network.replay.executed",
            ],
        )
        fetch_event = self.emitted_browser_events[0][1]
        self.assertEqual(fetch_event["profile_name"], "crxzipple")
        self.assertEqual(fetch_event["target_id"], "tab-1")
        self.assertEqual(fetch_event["status"], "succeeded")
        self.assertEqual(fetch_event["status_code"], 200)
        self.assertNotIn("secret", str(fetch_event))
        replay_event = self.emitted_browser_events[1][1]
        self.assertEqual(replay_event["source_request_id"], "req-1")
        self.assertEqual(replay_event["source_capture_id"], "cap-1")

    def test_network_fetch_failure_emits_display_safe_event(self) -> None:
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="network-fetch-as-page",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "url": "https://api.example.test/search?token=secret",
                "method": "GET",
            },
        )

        with self.assertRaisesRegex(BrowserValidationError, "cross-origin"):
            self.engine.execute(
                plan=self._plan(command),
                runtime_state=self.runtime_state,
                tab=self.tab,
                command=command,
            )

        self.assertEqual(len(self.emitted_browser_events), 1)
        event_name, payload = self.emitted_browser_events[0]
        self.assertEqual(event_name, "browser.network.fetch.failed")
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["level"], "error")
        self.assertEqual(payload["profile_name"], "crxzipple")
        self.assertEqual(payload["target_id"], "tab-1")
        self.assertNotIn("secret", str(payload))

    def test_dom_inspection_actions_return_layout_style_and_clickability(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.interactive_items = [
            {
                "selector": "#submit",
                "label": "Submit",
                "role": "button",
                "text": "Submit",
                "tag": "button",
                "clickable": False,
                "blocked_by": {
                    "tag": "div",
                    "selector_hint": "div.modal-mask",
                    "text": "",
                },
                "computed_style": {
                    "display": "block",
                    "pointer-events": "auto",
                    "z-index": "1",
                },
                "box": {
                    "x": 24,
                    "y": 48,
                    "width": 160,
                    "height": 40,
                    "top": 48,
                    "right": 184,
                    "bottom": 88,
                    "left": 24,
                },
                "mutation_wait": {
                    "changed": True,
                    "reason": "quiet",
                    "mutation_count": 3,
                    "elapsed_ms": 140,
                },
            },
        ]

        inspect_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="dom-inspect",
            target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
            payload={"properties": ["display", "z-index"]},
        )

        inspect_result = self.engine.execute(
            plan=self._plan(inspect_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=inspect_command,
        )

        result = inspect_result.value["result"]
        self.assertEqual(result["kind"], "dom-inspect")
        self.assertEqual(result["selector"], "#submit")
        self.assertFalse(result["clickable"])
        self.assertEqual(result["blocked_by"]["selector_hint"], "div.modal-mask")
        self.assertEqual(result["computed_style"]["z-index"], "1")

        clickability_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="dom-clickability",
            target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
            payload={},
        )
        clickability_result = self.engine.execute(
            plan=self._plan(clickability_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=clickability_command,
        )

        self.assertEqual(clickability_result.value["result"]["kind"], "dom-clickability")
        self.assertEqual(
            clickability_result.value["result"]["reasons"],
            ["blocked_by_overlay"],
        )

        highlight_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="dom-highlight",
            target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
            payload={"duration_ms": 900, "color": "#ff0000", "label": "Submit CTA"},
        )
        highlight_result = self.engine.execute(
            plan=self._plan(highlight_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=highlight_command,
        )

        self.assertEqual(highlight_result.value["result"]["kind"], "dom-highlight")
        self.assertTrue(highlight_result.value["result"]["highlighted"])
        self.assertEqual(highlight_result.value["result"]["duration_ms"], 900)
        self.assertEqual(highlight_result.value["result"]["color"], "#ff0000")

        mutation_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="dom-mutation-wait",
            target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
            payload={"quiet_ms": 50},
            timeout_ms=1800,
        )
        mutation_result = self.engine.execute(
            plan=self._plan(mutation_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=mutation_command,
        )

        self.assertEqual(mutation_result.value["result"]["kind"], "dom-mutation-wait")
        self.assertTrue(mutation_result.value["result"]["changed"])
        self.assertEqual(mutation_result.value["result"]["mutation_count"], 3)
        self.assertEqual(mutation_result.value["result"]["timeout_ms"], 1800)

    def test_action_engine_prefers_runtime_cdp_url_over_profile_url(self) -> None:
        self.runtime_state.metadata["cdp_base_url"] = "http://localhost:18800"
        click_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="click",
            target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
            payload={"button": "left"},
        )

        result = self.engine.execute(
            plan=self._plan(click_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=click_command,
        )

        self.assertTrue(result.ok)
        self.assertEqual(
            self.session_pool.resolve_calls[-1]["cdp_url"],
            "http://localhost:18800",
        )

    def test_execute_acquires_and_releases_host_daemon_lease_for_local_managed_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            daemon_service = self._build_daemon_service(Path(temp_dir))
            daemon_service.save_instance(
                DaemonInstance(
                    id="browser-host-crxzipple",
                    service_key="host:browser:crxzipple",
                    status="ready",
                    pid=8123,
                    endpoint="http://127.0.0.1:9222",
                )
            )
            engine = CdpBackedPlaywrightActionEngine(
                session_pool=self.session_pool,
                ref_store=self.ref_store,
                daemon_service=daemon_service,
            )
            click_command = BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="click",
                target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
                payload={"button": "left"},
            )

            result = engine.execute(
                plan=self._plan(click_command),
                runtime_state=self.runtime_state,
                tab=self.tab,
                command=click_command,
            )

            self.assertTrue(result.ok)
            leases = daemon_service.list_leases(service_key="host:browser:crxzipple")
            self.assertEqual(leases, ())

    def test_execute_uses_runtime_user_data_dir_for_host_daemon_lease_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            daemon_service = self._build_daemon_service(Path(temp_dir))
            daemon_service.save_instance(
                DaemonInstance(
                    id="browser-host-crxzipple",
                    service_key="host:browser:crxzipple",
                    status="ready",
                    pid=8123,
                    endpoint="http://127.0.0.1:9222",
                )
            )
            user_data_dir = str((Path(temp_dir) / "browser" / "profiles" / "crxzipple" / "userdata").resolve())
            owner_id = f"crxzipple:{hashlib.sha1(user_data_dir.encode('utf-8')).hexdigest()[:8]}"
            lease = daemon_service.acquire_lease(
                service_key="host:browser:crxzipple",
                owner_kind="browser_profile",
                owner_id=owner_id,
                ttl_seconds=60,
                metadata={"profile_name": "crxzipple", "user_data_dir": user_data_dir},
            )
            runtime_state = BrowserProfileRuntimeState(
                profile_name="crxzipple",
                metadata={"user_data_dir": user_data_dir},
            )
            engine = CdpBackedPlaywrightActionEngine(
                session_pool=self.session_pool,
                ref_store=self.ref_store,
                daemon_service=daemon_service,
            )
            click_command = BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="click",
                target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
                payload={"button": "left"},
            )

            result = engine.execute(
                plan=self._plan(click_command),
                runtime_state=runtime_state,
                tab=self.tab,
                command=click_command,
            )

            self.assertTrue(result.ok)
            active_leases = daemon_service.list_leases(service_key="host:browser:crxzipple")
            self.assertEqual(len(active_leases), 1)
            self.assertEqual(active_leases[0].id, lease.id)
            daemon_service.release_lease(lease.id)

    def test_click_falls_back_to_force_when_pointer_events_intercept(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.click_failures["#submit"] = [
            RuntimeError("<div class='overlay'>...</div> intercepts pointer events")
        ]

        click_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="click",
            target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
            payload={"button": "left"},
            timeout_ms=120_000,
        )
        click_result = self.engine.execute(
            plan=self._plan(click_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=click_command,
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(click_result.value["result"]["mode"], "force")
        self.assertEqual(page.operations[0], ("click", "#submit", {"timeout": 2000.0, "button": "left"}, ()))
        self.assertEqual(page.operations[1], ("click", "#submit", {"timeout": 120000.0, "button": "left", "force": True}, ()))

    def test_click_retries_once_when_frame_detaches(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.click_failures["#submit"] = [
            RuntimeError("Frame was detached"),
        ]

        click_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="click",
            target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
            payload={"button": "left"},
            timeout_ms=1500,
        )

        click_result = self.engine.execute(
            plan=self._plan(click_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=click_command,
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(
            [operation[0] for operation in page.operations if operation[0] == "click"],
            ["click", "click"],
        )

    def test_stale_ref_rebinds_to_semantic_role_locator(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#archive-primary",
                "resolved_selector": "#archive-primary",
                "label": "Archive",
                "role": "button",
                "text": "Archive",
                "tag": "button",
            },
            {
                "selector": "#archive-secondary",
                "resolved_selector": "#archive-secondary",
                "label": "Archive",
                "role": "button",
                "text": "Archive",
                "tag": "button",
            },
        ]
        self.ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    selector="#archive-secondary-legacy",
                    role="button",
                    label="Archive",
                    nth=1,
                    generation=1,
                    snapshot_format="interactive",
                ),
            ),
        )
        self.runtime_state.remember_page_snapshot(
            target_id="tab-1",
            generation=2,
            snapshot_format="interactive",
            ref_count=1,
            frame_count=1,
        )

        click_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="click",
            target=BrowserActionTarget(target_id="tab-1", ref="r1"),
            payload={},
        )
        click_result = self.engine.execute(
            plan=self._plan(click_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=click_command,
        )

        self.assertTrue(click_result.ok)
        self.assertIn(
            ("click", "#archive-secondary", {"timeout": 2000.0}, ()),
            page.operations,
        )

    def test_click_selector_supports_scope_selector_and_ordinal(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": ".result",
                "resolved_selector": "#left .result:nth-of-type(1)",
                "label": "Open",
                "role": "button",
                "text": "Open",
                "tag": "button",
                "scope_selector": "#left",
            },
            {
                "selector": ".result",
                "resolved_selector": "#right .result:nth-of-type(1)",
                "label": "Open",
                "role": "button",
                "text": "Open",
                "tag": "button",
                "scope_selector": "#right",
            },
            {
                "selector": ".result",
                "resolved_selector": "#right .result:nth-of-type(2)",
                "label": "Open",
                "role": "button",
                "text": "Open",
                "tag": "button",
                "scope_selector": "#right",
            },
        ]

        click_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="click",
            target=BrowserActionTarget(target_id="tab-1", selector=".result"),
            payload={"scope_selector": "#right", "ordinal": 1},
        )
        click_result = self.engine.execute(
            plan=self._plan(click_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=click_command,
        )

        self.assertTrue(click_result.ok)
        self.assertIn(
            ("click", "#right .result:nth-of-type(2)", {"timeout": 2000.0}, ()),
            page.operations,
        )

    def test_fill_selector_prefers_focused_candidate_when_selector_matches_multiple_inputs(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        selector = "input[aria-label*='To'], textarea[aria-label*='To'], input[peoplekit-id]"
        page.interactive_items = [
            {
                "selector": selector,
                "resolved_selector": "#compose-a input.to",
                "label": "To recipients",
                "role": "combobox",
                "tag": "input",
                "visible": True,
            },
            {
                "selector": selector,
                "resolved_selector": "#compose-b input.to",
                "label": "To recipients",
                "role": "combobox",
                "tag": "input",
                "visible": True,
                "focused": True,
            },
        ]

        fill_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="fill",
            target=BrowserActionTarget(target_id="tab-1", selector=selector),
            payload={"text": "657658113@qq.com"},
        )
        fill_result = self.engine.execute(
            plan=self._plan(fill_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=fill_command,
        )

        self.assertTrue(fill_result.ok)
        self.assertIn(
            ("fill", "#compose-b input.to", "657658113@qq.com", {}, ()),
            page.operations,
        )

    def test_wait_selector_prefers_focused_candidate_when_selector_matches_multiple_inputs(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        selector = "input[aria-label*='To'], textarea[aria-label*='To'], input[peoplekit-id]"
        page.interactive_items = [
            {
                "selector": selector,
                "resolved_selector": "#compose-a input.to",
                "label": "To recipients",
                "role": "combobox",
                "tag": "input",
                "visible": True,
            },
            {
                "selector": selector,
                "resolved_selector": "#compose-b input.to",
                "label": "To recipients",
                "role": "combobox",
                "tag": "input",
                "visible": True,
                "focused": True,
            },
        ]

        wait_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="wait",
            target=BrowserActionTarget(target_id="tab-1", selector=selector),
            payload={"state": "visible"},
        )
        wait_result = self.engine.execute(
            plan=self._plan(wait_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=wait_command,
        )

        self.assertTrue(wait_result.ok)
        self.assertIn(
            ("wait", "#compose-b input.to", {"state": "visible"}, ()),
            page.operations,
        )

    def test_fill_ref_rejects_non_editable_link_target_with_clear_error(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#skip-link",
                "resolved_selector": "#skip-link",
                "label": "Skip to content",
                "role": "link",
                "text": "Skip to content",
                "tag": "a",
                "visible": True,
            }
        ]
        self.ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
            refs=(
                BrowserStoredRef(
                    ref="r13",
                    role="link",
                    label="Skip to content",
                    generation=1,
                    snapshot_format="interactive",
                ),
            ),
        )
        self.runtime_state.remember_page_snapshot(
            target_id="tab-1",
            generation=1,
            snapshot_format="interactive",
            ref_count=1,
            frame_count=1,
        )

        fill_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="fill",
            target=BrowserActionTarget(target_id="tab-1", ref="r13"),
            payload={"text": "657658113@qq.com"},
        )

        with self.assertRaises(BrowserValidationError) as exc_info:
            self.engine.execute(
                plan=self._plan(fill_command),
                runtime_state=self.runtime_state,
                tab=self.tab,
                command=fill_command,
            )

        self.assertIn("non-editable element", str(exc_info.exception))
        self.assertIn("role=link", str(exc_info.exception))

    def test_wait_evaluate_snapshot_and_screenshot_return_structured_results(self) -> None:
        wait_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="wait",
            target=BrowserActionTarget(target_id="tab-1", selector="#ready"),
            payload={"state": "visible"},
        )
        wait_result = self.engine.execute(
            plan=self._plan(wait_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=wait_command,
        )

        evaluate_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="evaluate",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"expression": "() => 42"},
        )
        evaluate_result = self.engine.execute(
            plan=self._plan(evaluate_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=evaluate_command,
        )

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "html"},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        screenshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="screenshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"type": "png"},
        )
        screenshot_result = self.engine.execute(
            plan=self._plan(screenshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=screenshot_command,
        )

        self.assertEqual(wait_result.value["result"]["kind"], "wait")
        self.assertEqual(evaluate_result.value["result"]["expression"], "() => 42")
        self.assertEqual(snapshot_result.value["result"]["format"], "html")
        self.assertEqual(screenshot_result.value["result"]["content_type"], "image/png")
        self.assertEqual(screenshot_result.value["result"]["encoding"], "base64")

    def test_evaluate_retries_once_when_execution_context_is_destroyed(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.evaluate_failures = [
            RuntimeError("Execution context was destroyed, most likely because of a navigation."),
        ]

        evaluate_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="evaluate",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"expression": "() => 42"},
        )

        evaluate_result = self.engine.execute(
            plan=self._plan(evaluate_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=evaluate_command,
        )

        self.assertTrue(evaluate_result.ok)
        self.assertEqual(evaluate_result.value["result"]["expression"], "() => 42")
        self.assertEqual(
            [operation[0] for operation in page.operations if operation[0] == "evaluate"],
            ["evaluate", "evaluate"],
        )

    def test_wait_text_supports_scope_exact_and_ordinal(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#pane-a-done",
                "resolved_selector": "#pane-a-done",
                "label": "Done",
                "role": "status",
                "text": "Done",
                "tag": "div",
                "scope_selector": "#pane-a",
            },
            {
                "selector": "#pane-b-done-1",
                "resolved_selector": "#pane-b-done-1",
                "label": "Done",
                "role": "status",
                "text": "Done",
                "tag": "div",
                "scope_selector": "#pane-b",
            },
            {
                "selector": "#pane-b-done-2",
                "resolved_selector": "#pane-b-done-2",
                "label": "Done",
                "role": "status",
                "text": "Done",
                "tag": "div",
                "scope_selector": "#pane-b",
            },
        ]

        wait_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="wait",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "text": "Done",
                "scope_selector": "#pane-b",
                "exact": True,
                "ordinal": 1,
            },
        )
        wait_result = self.engine.execute(
            plan=self._plan(wait_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=wait_command,
        )

        self.assertTrue(wait_result.ok)
        self.assertIn(
            ("wait", "#pane-b-done-2", {}, ()),
            page.operations,
        )

    def test_interactive_snapshot_assigns_nth_for_duplicate_semantic_refs(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#message-star-1",
                "resolved_selector": "#message-star-1",
                "label": "Not starred",
                "role": "button",
                "text": "Not starred",
                "tag": "button",
            },
            {
                "selector": "#message-star-2",
                "resolved_selector": "#message-star-2",
                "label": "Not starred",
                "role": "button",
                "text": "Not starred",
                "tag": "button",
            },
        ]

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "interactive", "mode": "wide"},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        refs = snapshot_result.value["result"]["value"]["refs"]
        self.assertEqual(refs[0]["nth"], 0)
        self.assertEqual(refs[1]["nth"], 1)

    def test_snapshot_can_focus_active_overlay(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.active_overlay_selector = ".city-autocomplete-list"
        page.interactive_items = [
            {
                "selector": "#page-search",
                "resolved_selector": "#page-search",
                "label": "Search",
                "role": "button",
                "text": "Search",
                "tag": "button",
            },
            {
                "selector": ".overlay-option",
                "resolved_selector": ".overlay-option",
                "label": "Hangzhou",
                "role": "option",
                "text": "Hangzhou",
                "tag": "li",
                "scope_selector": ".city-autocomplete-list",
            },
        ]

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "interactive", "active_overlay": True},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        self.assertTrue(snapshot_result.ok)
        self.assertEqual(snapshot_result.value["result"]["root_selector"], ".city-autocomplete-list")
        refs = snapshot_result.value["result"]["value"]["refs"]
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["label"], "Hangzhou")

    def test_interactive_snapshot_retries_once_when_frame_detaches_during_dom_fallback(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.evaluate_failures = [
            RuntimeError("Frame.evaluate: Frame was detached"),
        ]
        page.interactive_items = [
            {
                "selector": "#compose",
                "resolved_selector": "#compose",
                "label": "Compose",
                "role": "button",
                "text": "Compose",
                "tag": "button",
            }
        ]

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "interactive", "mode": "focused"},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        self.assertTrue(snapshot_result.ok)
        refs = snapshot_result.value["result"]["value"]["refs"]
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["label"], "Compose")
        frame_evaluates = [
            op
            for op in page.operations
            if op[0] == "frame.evaluate"
        ]
        self.assertEqual(len(frame_evaluates), 2)




    def test_snapshot_active_overlay_prefers_bound_overlay_context(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.active_overlay_selector = ".depart-overlay"
        self.runtime_state.remember_active_overlay(
            target_id="tab-1",
            overlay_selector=".depart-overlay",
            source_selector="#depart-city",
        )

        self.runtime_state.remember_active_overlay(
            target_id="tab-1",
            overlay_selector=".arrival-overlay",
            source_selector="#arrival-city",
        )
        page.active_overlay_selector = ".arrival-overlay"
        page.interactive_items = [
            {
                "selector": ".depart-option",
                "resolved_selector": ".depart-option",
                "label": "Hangzhou",
                "role": "option",
                "text": "Hangzhou",
                "tag": "li",
                "scope_selector": ".depart-overlay",
            },
            {
                "selector": ".arrival-option",
                "resolved_selector": ".arrival-option",
                "label": "Kunming",
                "role": "option",
                "text": "Kunming",
                "tag": "li",
                "scope_selector": ".arrival-overlay",
            },
        ]

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "format": "interactive",
                "active_overlay": True,
                "overlay_source_selector": "#depart-city",
            },
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        self.assertTrue(snapshot_result.ok)
        self.assertEqual(snapshot_result.value["result"]["root_selector"], ".depart-overlay")
        refs = snapshot_result.value["result"]["value"]["refs"]
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["label"], "Hangzhou")

    def test_interactive_snapshot_uses_dom_for_active_datepicker_overlay(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.active_overlay_selector = ".date-picker-panel"
        page.main_frame.aria_snapshot_text = "\n".join(
            [
                '- button "Previous month"',
                '- button "Next month"',
            ]
        )
        page.interactive_items = [
            {
                "selector": ".date-picker-panel .day:nth-of-type(1)",
                "label": "May 27",
                "role": None,
                "text": "27",
                "tag": "div",
                "scope_selector": ".date-picker-panel",
            },
            {
                "selector": ".date-picker-panel .day:nth-of-type(2)",
                "label": "May 28",
                "role": None,
                "text": "28",
                "tag": "div",
                "scope_selector": ".date-picker-panel",
            },
        ]

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "interactive", "active_overlay": True},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        self.assertTrue(snapshot_result.ok)
        self.assertEqual(snapshot_result.value["result"]["root_selector"], ".date-picker-panel")
        refs = snapshot_result.value["result"]["value"]["refs"]
        self.assertEqual(
            [(item["label"], item["text"], item["tag"]) for item in refs],
            [("May 27", "27", "div"), ("May 28", "28", "div")],
        )
        self.assertEqual(
            [
                operation[0]
                for operation in page.operations
                if operation[0] in {"aria_snapshot", "frame.evaluate"}
            ],
            ["aria_snapshot", "frame.evaluate"],
        )

    def test_interactive_snapshot_dedupes_nested_overlay_refs(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.active_overlay_selector = ".city-autocomplete-list"
        page.main_frame.aria_snapshot_text = ""
        page.interactive_items = [
            {
                "selector": ".city-autocomplete-list > li",
                "label": "昆明(昆明长水)",
                "role": "button",
                "text": "昆明(昆明长水)",
                "tag": "li",
                "scope_selector": ".city-autocomplete-list",
            },
            {
                "selector": ".city-autocomplete-list > li > span",
                "label": "昆明(昆明长水)",
                "role": "button",
                "text": "昆明(昆明长水)",
                "tag": "span",
                "scope_selector": ".city-autocomplete-list",
            },
        ]

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "interactive", "active_overlay": True},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        result = snapshot_result.value["result"]
        refs = result["value"]["refs"]
        self.assertEqual(result["ref_count"], 1)
        self.assertEqual(refs[0]["ref"], "r1")
        self.assertEqual(refs[0]["tag"], "li")
        self.assertIn('- scope ".city-autocomplete-list":', result["value"]["snapshot"])
        self.assertIn('  - button "昆明(昆明长水)" [ref=r1]', result["value"]["snapshot"])
        self.assertNotIn("[ref=r2]", result["value"]["snapshot"])

    def test_interactive_snapshot_dedupes_descendant_overlay_refs(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.active_overlay_selector = ".city-autocomplete-list"
        page.main_frame.aria_snapshot_text = ""
        page.interactive_items = [
            {
                "selector": ".city-autocomplete-list li",
                "label": "上海虹桥",
                "role": "option",
                "text": "上海虹桥",
                "tag": "li",
                "scope_selector": ".city-autocomplete-list",
            },
            {
                "selector": ".city-autocomplete-list li span",
                "label": "上海虹桥",
                "role": "option",
                "text": "上海虹桥",
                "tag": "span",
                "scope_selector": ".city-autocomplete-list",
            },
        ]

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "interactive", "active_overlay": True},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        result = snapshot_result.value["result"]
        self.assertEqual(result["ref_count"], 1)
        refs = result["value"]["refs"]
        self.assertEqual(refs[0]["selector"], ".city-autocomplete-list li")
        self.assertEqual(refs[0]["tag"], "li")

























    def test_evaluate_supports_fn_alias_and_ref_scoped_execution(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        self.ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    selector="#query",
                    generation=1,
                    snapshot_format="interactive",
                    label="Query",
                    role="textbox",
                ),
            ),
        )
        self.runtime_state.remember_page_snapshot(
            target_id="tab-1",
            generation=1,
            snapshot_format="interactive",
            ref_count=1,
            frame_count=1,
        )

        evaluate_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="evaluate",
            target=BrowserActionTarget(target_id="tab-1", ref="r1"),
            payload={"fn": "(el) => el.tagName", "arg": {"debug": True}},
        )
        evaluate_result = self.engine.execute(
            plan=self._plan(evaluate_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=evaluate_command,
        )

        self.assertEqual(evaluate_result.value["result"]["selector"], "#query")
        self.assertEqual(evaluate_result.value["result"]["expression"], "(el) => el.tagName")
        self.assertEqual(evaluate_result.value["result"]["arg"], {"debug": True})
        self.assertIn(
            ("locator.evaluate", "#query", "(el) => el.tagName", {"debug": True}, ()),
            page.operations,
        )

    def test_wait_can_target_text_without_selector(self) -> None:
        wait_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="wait",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"text": "Ready"},
            timeout_ms=2500,
        )

        wait_result = self.engine.execute(
            plan=self._plan(wait_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=wait_command,
        )

        self.assertEqual(wait_result.value["result"]["kind"], "wait")
        self.assertEqual(wait_result.value["result"]["text"], ["Ready"])
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        self.assertIn(("wait", "text=Ready", {"timeout": 2500.0}, ()), page.operations)

    def test_wait_supports_text_gone_load_state_and_fn_alias(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")

        text_gone_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="wait",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"text_gone": "Loading"},
                    timeout_ms=2000,
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="wait",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"text_gone": "Loading"},
                timeout_ms=2000,
            ),
        )
        load_state_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="wait",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"load_state": "domcontentloaded"},
                    timeout_ms=2000,
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="wait",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"load_state": "domcontentloaded"},
                timeout_ms=2000,
            ),
        )
        fn_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="wait",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"fn": "() => window.ready === true"},
                    timeout_ms=2000,
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="wait",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"fn": "() => window.ready === true"},
                timeout_ms=2000,
            ),
        )

        self.assertEqual(text_gone_result.value["result"]["text_gone"], ["Loading"])
        self.assertEqual(load_state_result.value["result"]["load_state"], "domcontentloaded")
        self.assertEqual(fn_result.value["result"]["expression"], "() => window.ready === true")
        self.assertIn(("wait", "text=Loading", {"state": "hidden", "timeout": 2000.0}, ()), page.operations)
        self.assertIn(("wait_for_load_state", "domcontentloaded", {"timeout": 2000.0}), page.operations)
        self.assertIn(("wait_for_function", "() => window.ready === true", None, {"timeout": 2000.0}), page.operations)

    def test_wait_text_prefers_bound_active_overlay_context(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": ".page-option",
                "resolved_selector": ".page-option",
                "label": "Hangzhou",
                "role": "option",
                "text": "Hangzhou",
                "tag": "li",
            },
            {
                "selector": ".overlay-option",
                "resolved_selector": ".overlay-option",
                "label": "Hangzhou",
                "role": "option",
                "text": "Hangzhou",
                "tag": "li",
                "scope_selector": ".city-autocomplete-list",
            },
        ]
        self.runtime_state.remember_active_overlay(
            target_id="tab-1",
            overlay_selector=".city-autocomplete-list",
            source_selector="#depart-city",
        )

        wait_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="wait",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"text": "Hangzhou"},
            timeout_ms=2000,
        )
        wait_result = self.engine.execute(
            plan=self._plan(wait_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=wait_command,
        )

        self.assertTrue(wait_result.ok)
        self.assertIn(
            ("wait", ".overlay-option", {"timeout": 2000.0}, ()),
            page.operations,
        )


    def test_fill_supports_form_fields_by_ref(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#query",
                "label": "Query",
                "role": "textbox",
                "text": "",
                "tag": "input",
            },
            {
                "selector": "#newsletter",
                "label": "Newsletter",
                "role": "checkbox",
                "text": "",
                "tag": "input",
            },
        ]
        self.ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    selector="#query",
                    generation=1,
                    snapshot_format="interactive",
                    label="Query",
                    role="textbox",
                ),
                BrowserStoredRef(
                    ref="r2",
                    selector="#newsletter",
                    generation=1,
                    snapshot_format="interactive",
                    label="Newsletter",
                    role="checkbox",
                ),
            ),
        )
        self.runtime_state.remember_page_snapshot(
            target_id="tab-1",
            generation=1,
            snapshot_format="interactive",
            ref_count=2,
            frame_count=1,
        )

        fill_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="fill",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "fields": [
                    {"ref": "r1", "type": "text", "value": "hello"},
                    {"ref": "r2", "type": "checkbox", "value": True},
                ]
            },
        )

        fill_result = self.engine.execute(
            plan=self._plan(fill_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=fill_command,
        )

        self.assertEqual(fill_result.value["result"]["kind"], "fill")
        self.assertEqual(len(fill_result.value["result"]["fields"]), 2)
        self.assertIn(("fill", "#query", "hello", {}, ()), page.operations)
        self.assertIn(("set_checked", "#newsletter", True, {}, ()), page.operations)

    def test_drag_supports_start_and_end_aliases(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#from",
                "label": "From",
                "role": "button",
                "text": "From",
                "tag": "button",
            },
            {
                "selector": "#to",
                "label": "To",
                "role": "button",
                "text": "To",
                "tag": "button",
            },
        ]
        self.ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    selector="#from",
                    generation=1,
                    snapshot_format="interactive",
                    label="From",
                    role="button",
                ),
                BrowserStoredRef(
                    ref="r2",
                    selector="#to",
                    generation=1,
                    snapshot_format="interactive",
                    label="To",
                    role="button",
                ),
            ),
        )
        self.runtime_state.remember_page_snapshot(
            target_id="tab-1",
            generation=1,
            snapshot_format="interactive",
            ref_count=2,
            frame_count=1,
        )

        drag_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="drag",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"start_ref": "r1", "end_ref": "r2"},
        )

        drag_result = self.engine.execute(
            plan=self._plan(drag_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=drag_command,
        )

        self.assertTrue(drag_result.ok)
        self.assertEqual(drag_result.value["result"]["start_ref"], "r1")
        self.assertEqual(drag_result.value["result"]["end_ref"], "r2")
        self.assertIn(("drag", "#from", "#to", {}, ()), page.operations)

    def test_resize_updates_viewport(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")

        resize_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="resize",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"width": 800, "height": 600},
        )

        resize_result = self.engine.execute(
            plan=self._plan(resize_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=resize_command,
        )

        self.assertTrue(resize_result.ok)
        self.assertEqual(resize_result.value["result"]["width"], 800)
        self.assertEqual(resize_result.value["result"]["height"], 600)
        self.assertEqual(page.viewport, {"width": 800, "height": 600})
        self.assertIn(("set_viewport_size", {"width": 800, "height": 600}), page.operations)

    def test_batch_executes_actions_in_order(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")

        batch_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="batch",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "actions": [
                    {"kind": "resize", "width": 800, "height": 600},
                    {"kind": "evaluate", "fn": "() => document.title"},
                ]
            },
        )

        batch_result = self.engine.execute(
            plan=self._plan(batch_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=batch_command,
        )

        self.assertTrue(batch_result.ok)
        self.assertEqual(batch_result.value["result"]["kind"], "batch")
        self.assertEqual(len(batch_result.value["result"]["results"]), 2)
        self.assertEqual(batch_result.value["result"]["results"][0]["kind"], "resize")
        self.assertEqual(batch_result.value["result"]["results"][1]["kind"], "evaluate")
        self.assertEqual(page.operations[0], ("set_viewport_size", {"width": 800, "height": 600}))
        self.assertEqual(page.operations[1][0], "evaluate")

    def test_batch_stop_on_error_false_continues_after_failure(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.click_failures["#submit"] = [RuntimeError("boom")]

        batch_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="batch",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "actions": [
                    {"kind": "click", "selector": "#submit"},
                    {"kind": "resize", "width": 640, "height": 480},
                ],
                "stop_on_error": False,
            },
        )

        batch_result = self.engine.execute(
            plan=self._plan(batch_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=batch_command,
        )

        self.assertTrue(batch_result.ok)
        results = batch_result.value["result"]["results"]
        self.assertFalse(results[0]["ok"])
        self.assertEqual(results[0]["kind"], "click")
        self.assertTrue(results[1]["ok"])
        self.assertEqual(results[1]["kind"], "resize")
        self.assertIn(("set_viewport_size", {"width": 640, "height": 480}), page.operations)

    def test_aria_snapshot_returns_role_tree_text(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = "\n".join(
            [
                '- banner:',
                '  - button "Menu"',
                '  - link "Deals"',
            ]
        )

        snapshot_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "aria"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "aria"},
            ),
        )

        result = snapshot_result.value["result"]
        self.assertEqual(result["format"], "aria")
        self.assertIn('- button "Menu"', result["value"]["snapshot"])
        self.assertEqual(result["frame_count"], 1)
        self.assertEqual(result["ref_count"], 0)

    def test_snapshot_refs_mode_can_select_aria_and_role_views(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#menu",
                "label": "Menu",
                "role": "button",
                "text": "Menu",
                "tag": "button",
            },
        ]
        page.main_frame.aria_snapshot_text = '- button "Menu"'

        aria_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"refs_mode": "aria"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"refs_mode": "aria"},
            ),
        )
        role_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"refs_mode": "role"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"refs_mode": "role"},
            ),
        )

        self.assertEqual(aria_result.value["result"]["format"], "aria")
        self.assertEqual(aria_result.value["result"]["refs_mode"], "aria")
        self.assertEqual(role_result.value["result"]["format"], "role")
        self.assertEqual(role_result.value["result"]["refs_mode"], "role")
        self.assertEqual(role_result.value["result"]["ref_count"], 1)

    def test_snapshot_refs_mode_rejects_conflicting_format(self) -> None:
        with self.assertRaises(BrowserValidationError):
            self.engine.execute(
                plan=self._plan(
                    BrowserPageActionCommand(
                        profile_name="crxzipple",
                        kind="snapshot",
                        target=BrowserActionTarget(target_id="tab-1"),
                        payload={"format": "role", "refs_mode": "aria"},
                    )
                ),
                runtime_state=self.runtime_state,
                tab=self.tab,
                command=BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "role", "refs_mode": "aria"},
                ),
            )

    def test_role_snapshot_persists_role_refs_and_click_can_use_them(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#menu",
                "label": "Menu",
                "role": "button",
                "text": "Menu",
                "tag": "button",
            },
            {
                "selector": "#deals",
                "label": "Deals",
                "role": "link",
                "text": "Deals",
                "tag": "a",
            },
        ]
        page.main_frame.aria_snapshot_text = "\n".join(
            [
                '- banner:',
                '  - button "Menu"',
                '  - link "Deals"',
            ]
        )

        snapshot_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "role"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "role"},
            ),
        )

        result = snapshot_result.value["result"]
        self.assertEqual(result["format"], "role")
        self.assertIn('[ref=r1]', result["value"]["snapshot"])
        self.assertEqual(result["ref_count"], 2)
        self.assertEqual(result["value"]["stats"]["refs"], 2)
        stored_refs = self.ref_store.get_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
        )
        self.assertEqual(
            stored_refs,
            (
                BrowserStoredRef(
                    ref="r1",
                    nth=None,
                    generation=1,
                    snapshot_format="role",
                    label="Menu",
                    role="button",
                    text="Menu",
                    tag="button",
                ),
                BrowserStoredRef(
                    ref="r2",
                    nth=None,
                    generation=1,
                    snapshot_format="role",
                    label="Deals",
                    role="link",
                    text="Deals",
                    tag="link",
                ),
            ),
        )

        click_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="click",
                    target=BrowserActionTarget(target_id="tab-1", ref="r1"),
                    payload={"button": "left"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="click",
                target=BrowserActionTarget(target_id="tab-1", ref="r1"),
                payload={"button": "left"},
            ),
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(click_result.value["selector"], 'role=button[name="Menu"]')
        self.assertEqual(page.operations[-1][0], "click")
        self.assertEqual(page.operations[-1][1], "#menu")

    def test_interactive_snapshot_persists_refs_and_click_can_use_ref(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#submit",
                "label": "Submit",
                "role": "button",
                "text": "Submit",
                "tag": "button",
            },
            {
                "selector": "#query",
                "label": "Search",
                "role": "textbox",
                "text": "",
                "tag": "input",
            },
        ]
        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "interactive"},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        stored_refs = self.ref_store.get_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
        )
        self.assertEqual(
            stored_refs,
            (
                BrowserStoredRef(
                    ref="r1",
                    nth=None,
                    generation=1,
                    snapshot_format="interactive",
                    label="Submit",
                    role="button",
                    text="Submit",
                    tag="button",
                ),
                BrowserStoredRef(
                    ref="r2",
                    nth=None,
                    generation=1,
                    snapshot_format="interactive",
                    label="Search",
                    role="textbox",
                    text="Search",
                    tag="textbox",
                ),
            ),
        )
        self.assertEqual(snapshot_result.value["result"]["format"], "interactive")
        self.assertEqual(snapshot_result.value["result"]["generation"], 1)
        self.assertEqual(snapshot_result.value["result"]["mode"], "efficient")
        self.assertTrue(snapshot_result.value["result"]["compact"])
        self.assertEqual(snapshot_result.value["result"]["depth"], 6)
        self.assertEqual(snapshot_result.value["result"]["value"]["refs"][0]["ref"], "r1")
        self.assertIsNone(snapshot_result.value["result"]["value"]["refs"][0]["selector"])
        self.assertIsNone(snapshot_result.value["result"]["value"]["refs"][0]["nth"])
        self.assertIn('[ref=r1]', snapshot_result.value["result"]["value"]["snapshot"])
        self.assertEqual(snapshot_result.value["result"]["ref_count"], 2)
        self.assertEqual(snapshot_result.value["result"]["frame_count"], 1)
        self.assertEqual(
            self.runtime_state.page_state(target_id="tab-1"),
            {
                "page_generation": 1,
                "snapshot_generation": 1,
                "current_ref_generation": 1,
                "last_action_kind": "snapshot",
                "last_snapshot_format": "interactive",
                "last_snapshot_ref_count": 2,
                "last_snapshot_frame_count": 1,
                "ref_session_restored": False,
            },
        )

        click_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="click",
            target=BrowserActionTarget(target_id="tab-1", ref="r1"),
            payload={"button": "left"},
        )
        click_result = self.engine.execute(
            plan=self._plan(click_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=click_command,
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(click_result.value["selector"], 'role=button[name="Submit"]')
        self.assertEqual(page.operations[-1][0], "click")
        self.assertEqual(page.operations[-1][1], "#submit")
        self.assertEqual(
            self.runtime_state.page_state(target_id="tab-1"),
            {
                "page_generation": 1,
                "snapshot_generation": 1,
                "current_ref_generation": 1,
                "last_action_kind": "click",
                "last_snapshot_format": "interactive",
                "last_snapshot_ref_count": 2,
                "last_snapshot_frame_count": 1,
                "ref_session_restored": False,
            },
        )

    def test_interactive_snapshot_tracks_frame_path_and_click_uses_child_frame(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
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

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "interactive"},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        stored_refs = self.ref_store.get_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
        )
        self.assertEqual(
            stored_refs,
            (
                BrowserStoredRef(
                    ref="r1",
                    nth=None,
                    generation=1,
                    snapshot_format="interactive",
                    frame_path=(0,),
                    label="Confirm",
                    role="button",
                    text="Confirm",
                    tag="button",
                ),
            ),
        )
        self.assertEqual(snapshot_result.value["result"]["generation"], 1)
        self.assertEqual(snapshot_result.value["result"]["value"]["refs"][0]["frame_path"], [0])
        self.assertIsNone(snapshot_result.value["result"]["value"]["refs"][0]["selector"])
        self.assertEqual(snapshot_result.value["result"]["ref_count"], 1)
        self.assertEqual(snapshot_result.value["result"]["frame_count"], 1)

        click_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="click",
            target=BrowserActionTarget(target_id="tab-1", ref="r1"),
            payload={"button": "left"},
        )
        click_result = self.engine.execute(
            plan=self._plan(click_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=click_command,
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(click_result.value["frame_path"], [0])
        self.assertEqual(click_result.value["selector"], 'role=button[name="Confirm"]')
        self.assertEqual(page.operations[-1][0], "click")
        self.assertEqual(page.operations[-1][1], "#confirm")
        self.assertEqual(page.operations[-1][-1], (0,))

    def test_interactive_snapshot_can_scope_to_frame_selector(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.interactive_items = [
            {
                "selector": "#menu",
                "label": "Menu",
                "role": "button",
                "text": "Menu",
                "tag": "button",
            },
        ]
        page.add_child_frame(
            path=(0,),
            selector="iframe.booking",
            interactive_items=[
                {
                    "selector": "#confirm",
                    "label": "Confirm",
                    "role": "button",
                    "text": "Confirm",
                    "tag": "button",
                }
            ],
            aria_snapshot_text='- button "Confirm"',
        )

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "interactive", "frame_selector": "iframe.booking"},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        stored_refs = self.ref_store.get_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
        )
        self.assertEqual(len(stored_refs), 1)
        self.assertEqual(stored_refs[0].label, "Confirm")
        self.assertEqual(stored_refs[0].frame_path, (0,))
        self.assertEqual(snapshot_result.value["result"]["frame_selector"], "iframe.booking")
        self.assertEqual(snapshot_result.value["result"]["frame_count"], 1)
        self.assertEqual(snapshot_result.value["result"]["value"]["refs"][0]["label"], "Confirm")

    def test_role_snapshot_can_scope_to_frame_selector(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = '- button "Menu"'
        page.add_child_frame(
            path=(0,),
            selector="iframe.booking",
            aria_snapshot_text='\n'.join(
                [
                    '- region "Booking"',
                    '  - button "Search"',
                ]
            ),
        )

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "role", "frame_selector": "iframe.booking"},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        result = snapshot_result.value["result"]
        self.assertEqual(result["frame_selector"], "iframe.booking")
        self.assertEqual(result["frame_count"], 1)
        self.assertIn('button "Search"', result["value"]["snapshot"])
        self.assertNotIn('button "Menu"', result["value"]["snapshot"])

    def test_role_snapshot_can_scope_to_root_selector(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = None
        page.main_frame.interactive_items = [
            {
                "selector": "#menu",
                "label": "Menu",
                "role": "button",
                "text": "Menu",
                "tag": "button",
                "scope_selector": "#nav",
            },
            {
                "selector": "#search",
                "label": "Search",
                "role": "button",
                "text": "Search",
                "tag": "button",
                "scope_selector": "#booking",
            },
        ]

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1", selector="#booking"),
            payload={"format": "role"},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        result = snapshot_result.value["result"]
        self.assertEqual(snapshot_result.value["selector"], "#booking")
        self.assertEqual(result["root_selector"], "#booking")
        self.assertIn('button "Search"', result["value"]["snapshot"])
        self.assertNotIn('button "Menu"', result["value"]["snapshot"])
        self.assertEqual(result["ref_count"], 1)

    def test_interactive_snapshot_can_scope_to_root_selector(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = None
        page.main_frame.interactive_items = [
            {
                "selector": "#menu",
                "label": "Menu",
                "role": "button",
                "text": "Menu",
                "tag": "button",
                "scope_selector": "#nav",
            },
            {
                "selector": "#search",
                "label": "Search",
                "role": "button",
                "text": "Search",
                "tag": "button",
                "scope_selector": "#booking",
            },
        ]

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1", selector="#booking"),
            payload={"format": "interactive"},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        result = snapshot_result.value["result"]
        self.assertEqual(snapshot_result.value["selector"], "#booking")
        self.assertEqual(result["root_selector"], "#booking")
        self.assertEqual(result["ref_count"], 1)
        self.assertEqual(result["value"]["refs"][0]["label"], "Search")

    def test_interactive_snapshot_dom_fallback_groups_refs_by_scope_selector(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = ""
        page.main_frame.interactive_items = [
            {
                "selector": "#depart",
                "label": "Depart",
                "role": "button",
                "text": "Depart",
                "tag": "button",
                "scope_selector": "#search-form",
            },
            {
                "selector": "#arrival",
                "label": "Arrival",
                "role": "textbox",
                "text": "Arrival",
                "tag": "input",
                "scope_selector": "#search-form",
            },
            {
                "selector": "#direct-only",
                "label": "Direct only",
                "role": "checkbox",
                "text": "Direct only",
                "tag": "input",
                "scope_selector": "#filters",
            },
        ]

        snapshot_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive"},
            ),
        )

        snapshot_text = snapshot_result.value["result"]["value"]["snapshot"]
        self.assertIn('- scope "#search-form":', snapshot_text)
        self.assertIn('  - button "Depart" [ref=r1]', snapshot_text)
        self.assertIn('  - textbox "Arrival" [ref=r2]', snapshot_text)
        self.assertIn('- scope "#filters":', snapshot_text)
        self.assertIn('  - checkbox "Direct only" [ref=r3]', snapshot_text)

    def test_interactive_snapshot_uses_role_nth_for_duplicate_accessible_names(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#submit-primary",
                "label": "Submit",
                "role": "button",
                "text": "Submit",
                "tag": "button",
            },
            {
                "selector": "#submit-secondary",
                "label": "Submit",
                "role": "button",
                "text": "Submit",
                "tag": "button",
            },
        ]

        snapshot_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive"},
            ),
        )

        stored_refs = self.ref_store.get_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
        )
        self.assertEqual(stored_refs[0].nth, 0)
        self.assertEqual(stored_refs[1].nth, 1)
        self.assertEqual(snapshot_result.value["result"]["value"]["refs"][0]["nth"], 0)
        self.assertEqual(snapshot_result.value["result"]["value"]["refs"][1]["nth"], 1)

        click_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="click",
                    target=BrowserActionTarget(target_id="tab-1", ref="r2"),
                    payload={"button": "left"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="click",
                target=BrowserActionTarget(target_id="tab-1", ref="r2"),
                payload={"button": "left"},
            ),
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(
            click_result.value["selector"],
            'role=button[name="Submit"][nth=1]',
        )
        self.assertEqual(page.operations[-1][1], "#submit-secondary")

    def test_click_rejects_stale_ref_after_new_snapshot_generation(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#submit",
                "label": "Submit",
                "role": "button",
                "text": "Submit",
                "tag": "button",
            },
        ]
        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "interactive"},
        )
        self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        self.ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    selector="#submit",
                    generation=1,
                    snapshot_format="interactive",
                    label="Submit",
                ),
            ),
        )
        self.runtime_state.remember_page_snapshot(
            target_id="tab-1",
            generation=2,
            snapshot_format="interactive",
            ref_count=1,
            frame_count=1,
        )

        with self.assertRaises(BrowserValidationError):
            self.engine.execute(
                plan=self._plan(
                    BrowserPageActionCommand(
                        profile_name="crxzipple",
                        kind="click",
                        target=BrowserActionTarget(target_id="tab-1", ref="r1"),
                        payload={"button": "left"},
                    )
                ),
                runtime_state=self.runtime_state,
                tab=self.tab,
                command=BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="click",
                    target=BrowserActionTarget(target_id="tab-1", ref="r1"),
                    payload={"button": "left"},
                ),
            )

    def test_click_can_rebind_stale_ref_within_scoped_container(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": ".depart-submit",
                "scope_selector": "#depart-panel",
                "label": "Submit",
                "role": "button",
                "text": "Submit",
                "tag": "button",
            },
            {
                "selector": ".return-submit",
                "scope_selector": "#return-panel",
                "label": "Submit",
                "role": "button",
                "text": "Submit",
                "tag": "button",
            },
        ]
        self.ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    scope_selector="#depart-panel",
                    generation=1,
                    snapshot_format="interactive",
                    label="Submit",
                    role="button",
                    text="Submit",
                ),
            ),
        )
        self.runtime_state.remember_page_snapshot(
            target_id="tab-1",
            generation=2,
            snapshot_format="interactive",
            ref_count=1,
            frame_count=1,
        )

        click_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="click",
                    target=BrowserActionTarget(target_id="tab-1", ref="r1"),
                    payload={"button": "left"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="click",
                target=BrowserActionTarget(target_id="tab-1", ref="r1"),
                payload={"button": "left"},
            ),
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(
            click_result.value["selector"],
            '#depart-panel >> role=button[name="Submit"]',
        )
        self.assertEqual(page.operations[-1][1], ".depart-submit")

    def test_interactive_snapshot_efficient_mode_defaults_to_smaller_ref_budget_than_wide(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": f"#item-{index}",
                "label": f"Item {index}",
                "role": "button",
                "text": f"Item {index}",
                "tag": "button",
                "visible": True,
            }
            for index in range(1, 46)
        ]

        interactive_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive"},
            ),
        )

        wide_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive", "mode": "wide"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive", "mode": "wide"},
            ),
        )

        self.assertEqual(interactive_result.value["result"]["ref_count"], 40)
        self.assertEqual(len(interactive_result.value["result"]["value"]["refs"]), 40)
        self.assertEqual(wide_result.value["result"]["ref_count"], 45)
        self.assertEqual(len(wide_result.value["result"]["value"]["refs"]), 45)

    def test_interactive_snapshot_honors_depth_and_compact_options(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = "\n".join(
            [
                '- banner:',
                '  - button "Menu"',
                '  - button',
                '  - group:',
                '    - link "Deals"',
                '    - textbox',
                '    - button',
            ]
        )

        result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={
                        "format": "interactive",
                        "compact": True,
                        "depth": 1,
                    },
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={
                    "format": "interactive",
                    "compact": True,
                    "depth": 1,
                },
            ),
        )

        value = result.value["result"]["value"]["refs"]
        self.assertEqual(
            [(item["role"], item["label"]) for item in value],
            [("button", "Menu")],
        )
        self.assertTrue(result.value["result"]["compact"])
        self.assertEqual(result.value["result"]["depth"], 1)

    def test_interactive_snapshot_supports_wide_and_focused_modes(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = "\n".join(
            [
                "- main:",
                '  - button "Primary"',
                "  - button",
                "  - textbox",
            ]
        )

        wide_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive", "mode": "wide"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive", "mode": "wide"},
            ),
        )

        default_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive", "mode": "focused"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive", "mode": "focused"},
            ),
        )

        focused_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive", "mode": "focused"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive", "mode": "focused"},
            ),
        )

        self.assertEqual(wide_result.value["result"]["mode"], "wide")
        self.assertEqual(default_result.value["result"]["mode"], "focused")
        self.assertEqual(focused_result.value["result"]["mode"], "focused")
        self.assertEqual(
            [(item["role"], item["label"]) for item in wide_result.value["result"]["value"]["refs"]],
            [("button", "Primary"), ("button", None), ("textbox", None)],
        )
        self.assertEqual(
            [(item["role"], item["label"]) for item in default_result.value["result"]["value"]["refs"]],
            [("button", "Primary"), ("textbox", None)],
        )
        self.assertEqual(
            [(item["role"], item["label"]) for item in focused_result.value["result"]["value"]["refs"]],
            [("button", "Primary"), ("textbox", None)],
        )
        self.assertIn('[ref=r1]', wide_result.value["result"]["value"]["snapshot"])
        self.assertEqual(
            [operation[0] for operation in page.operations if operation[0] in {"aria_snapshot", "frame.evaluate"}],
            ["aria_snapshot", "aria_snapshot", "aria_snapshot"],
        )

    def test_interactive_snapshot_falls_back_to_dom_when_focused_role_snapshot_is_too_sparse(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.active_overlay_selector = "#compose"
        page.main_frame.aria_snapshot_text = "\n".join(
            [
                "- dialog:",
                '  - button "Dismiss"',
            ]
        )
        page.interactive_items = [
            {
                "selector": "input[aria-label='To recipients']",
                "label": "To recipients",
                "role": "textbox",
                "text": "",
                "tag": "input",
                "scope_selector": "#compose",
            },
            {
                "selector": "input[aria-label='Subject']",
                "label": "Subject",
                "role": "textbox",
                "text": "",
                "tag": "input",
                "scope_selector": "#compose",
            },
            {
                "selector": "div[aria-label='Message Body']",
                "label": "Message Body",
                "role": "textbox",
                "text": "",
                "tag": "div",
                "scope_selector": "#compose",
            },
            {
                "selector": "div[aria-label^='Send']",
                "label": "Send",
                "role": "button",
                "text": "Send",
                "tag": "div",
                "scope_selector": "#compose",
            },
        ]

        result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive", "mode": "focused", "active_overlay": True},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive", "mode": "focused", "active_overlay": True},
            ),
        )

        refs = result.value["result"]["value"]["refs"]
        self.assertEqual(
            [(item["role"], item["label"]) for item in refs],
            [
                ("textbox", "To recipients"),
                ("textbox", "Subject"),
                ("button", "Send"),
                ("textbox", "Message Body"),
            ],
        )
        self.assertIn('[ref=r1]', result.value["result"]["value"]["snapshot"])
        self.assertEqual(
            [operation[0] for operation in page.operations if operation[0] in {"aria_snapshot", "frame.evaluate"}],
            ["aria_snapshot", "frame.evaluate"],
        )

    def test_interactive_snapshot_skips_detached_child_frames(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = '- button "Open calendar"'
        page.interactive_items = [
            {
                "selector": "#calendar",
                "label": "Open calendar",
                "role": "button",
                "text": "Open calendar",
                "tag": "button",
            },
        ]
        child_frame = page.add_child_frame(path=(0,), aria_snapshot_text="")
        child_frame.evaluate_failures.append(RuntimeError("Frame was detached"))

        result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive", "mode": "focused"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive", "mode": "focused"},
            ),
        )

        refs = result.value["result"]["value"]["refs"]
        self.assertEqual(
            [(item["role"], item["label"]) for item in refs],
            [("button", "Open calendar")],
        )
        self.assertEqual(
            [
                (operation[0], operation[-1])
                for operation in page.operations
                if operation[0] == "frame.evaluate"
            ],
            [
                ("frame.evaluate", ()),
                ("frame.evaluate", (0,)),
            ],
        )

    def test_interactive_snapshot_focused_excludes_skip_to_content_ref(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = "\n".join(
            [
                "- main:",
                '  - link "Skip to content"',
                '  - textbox "To recipients"',
                '  - textbox "Subject"',
            ]
        )

        result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive", "mode": "focused"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive", "mode": "focused"},
            ),
        )

        refs = result.value["result"]["value"]["refs"]
        self.assertEqual(
            [(item["role"], item["label"]) for item in refs],
            [("textbox", "To recipients"), ("textbox", "Subject")],
        )

    def test_interactive_snapshot_efficient_mode_defaults_compact_and_depth(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = "\n".join(
            [
                '- main:',
                '  - button "Search"',
                '  - group:',
                '    - button',
                '    - textbox',
            ]
        )

        result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive", "mode": "efficient"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive", "mode": "efficient"},
            ),
        )

        self.assertEqual(result.value["result"]["mode"], "efficient")
        self.assertTrue(result.value["result"]["compact"])
        self.assertEqual(result.value["result"]["depth"], 6)
        self.assertEqual(
            [(item["role"], item["label"]) for item in result.value["result"]["value"]["refs"]],
            [("button", "Search"), ("textbox", None)],
        )


if __name__ == "__main__":
    unittest.main()
