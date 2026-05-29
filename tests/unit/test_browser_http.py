from __future__ import annotations

# ruff: noqa: F403,F405

import json as _json

from crxzipple.modules.daemon import DaemonInstance

from tests.unit.http_test_support import *


class BrowserHttpTestCase(HttpModuleTestCase):
    def setUp(self) -> None:
        self._previous_browser_profile_specs = os.environ.get("APP_BROWSER_PROFILE_SPECS")
        self._playwright_pool_patcher = patch(
            "crxzipple.app.assembly.browser.PlaywrightCdpSessionPool",
            FakePlaywrightCdpSessionPool,
        )
        self._playwright_pool_patcher.start()
        self._fake_cdp_server = FakeCdpServer()
        self._fake_cdp_server.start()
        os.environ["APP_BROWSER_PROFILE_SPECS"] = _json.dumps(
            [
                {
                    "name": "crxzipple",
                    "cdp_url": self._fake_cdp_server.base_url,
                },
                {
                    "name": "user",
                    "driver": "existing-session",
                },
            ],
        )
        super().setUp()

    def tearDown(self) -> None:
        super().tearDown()
        self._fake_cdp_server.close()
        self._playwright_pool_patcher.stop()
        if self._previous_browser_profile_specs is None:
            os.environ.pop("APP_BROWSER_PROFILE_SPECS", None)
        else:
            os.environ["APP_BROWSER_PROFILE_SPECS"] = self._previous_browser_profile_specs

    def test_browser_profiles_endpoint_returns_profile_matrix(self) -> None:
        response = self.client.get("/browser/profiles")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["default_profile"], "crxzipple")
        profile_names = [item["name"] for item in payload["profiles"]]
        self.assertIn("crxzipple", profile_names)
        self.assertIn("user", profile_names)
        crxzipple_profile = next(
            item for item in payload["profiles"] if item["name"] == "crxzipple"
        )
        user_profile = next(item for item in payload["profiles"] if item["name"] == "user")
        self.assertTrue(crxzipple_profile["supports_reset"])
        self.assertFalse(user_profile["supports_reset"])
        self.assertTrue(crxzipple_profile["enabled"])
        self.assertTrue(user_profile["enabled"])
        self.assertEqual(crxzipple_profile["diagnostics"]["status"], "ready-to-launch")
        self.assertEqual(user_profile["diagnostics"]["status"], "awaiting-existing-browser")
        self.assertEqual(crxzipple_profile["diagnostics"]["summary"]["code"], "launchable")
        self.assertEqual(user_profile["diagnostics"]["summary"]["code"], "waiting-browser")
        self.assertIn("Launchable:", crxzipple_profile["diagnostics"]["summary_line"])
        self.assertIn("Waiting for browser:", user_profile["diagnostics"]["summary_line"])

    def test_browser_profile_diagnostics_endpoint_returns_actionable_status(self) -> None:
        response = self.client.get("/browser/profiles/user/diagnostics")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["profile"]["name"], "user")
        self.assertEqual(payload["profile"]["diagnostics"]["status"], "awaiting-existing-browser")
        self.assertEqual(
            payload["profile"]["diagnostics"]["recommended_action"],
            "configure-cdp-endpoint",
        )
        self.assertEqual(payload["profile"]["diagnostics"]["summary"]["code"], "waiting-browser")
        self.assertIn("Waiting for browser:", payload["profile"]["diagnostics"]["summary_line"])
        self.assertEqual(
            payload["profile"]["diagnostics"]["probe"]["status"],
            "cdp-not-configured",
        )

    def test_browser_profiles_endpoint_reads_updated_state_root_default_profile(self) -> None:
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
            container = client.app.state.container
            browser_state_root = container.require(AppKey.BROWSER_INFRASTRUCTURE).state_root
            system_path = browser_state_root.config_dir / "system.json"
            payload = json.loads(system_path.read_text(encoding="utf-8"))
            payload["default_profile"] = "user"
            system_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            response = client.get("/browser/profiles")

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()["default_profile"], "user")
        finally:
            client.close()
            client.app.state.container.require(AppKey.DATABASE_ENGINE).dispose()
            harness.close()

    def test_browser_control_and_action_endpoints_share_runtime_state(self) -> None:
        open_response = self.client.post(
            "/browser/control",
            json={
                "kind": "open-tab",
                "payload": {"url": "https://example.com"},
            },
        )

        self.assertEqual(open_response.status_code, 200)
        open_payload = open_response.json()
        target_id = open_payload["target_id"]

        action_response = self.client.post(
            "/browser/actions",
            json={
                "kind": "click",
                "target_id": target_id,
                "selector": "#submit",
            },
        )

        self.assertEqual(action_response.status_code, 200)
        action_payload = action_response.json()
        self.assertTrue(action_payload["ok"])
        self.assertEqual(action_payload["target_id"], target_id)
        self.assertEqual(action_payload["command"]["family"], "page-action")
        self.assertEqual(action_payload["value"]["engine"], "cdp-backed-playwright")
        self.assertEqual(
            open_payload["value"]["ws_url"],
            f"{self._fake_cdp_server.base_url.replace('http://', 'ws://')}/devtools/page/{target_id}",
        )
        self.assertEqual(
            open_payload["value"]["json_endpoints"],
            {
                "version": f"{self._fake_cdp_server.base_url}/json/version",
                "list": f"{self._fake_cdp_server.base_url}/json/list",
                "new": f"{self._fake_cdp_server.base_url}/json/new",
                "activate": f"{self._fake_cdp_server.base_url}/json/activate/{target_id}",
                "close": f"{self._fake_cdp_server.base_url}/json/close/{target_id}",
            },
        )

    def test_browser_action_endpoint_rejects_debug_only_cdp_raw(self) -> None:
        open_response = self.client.post(
            "/browser/control",
            json={
                "kind": "open-tab",
                "payload": {"url": "https://example.com"},
            },
        )
        self.assertEqual(open_response.status_code, 200)
        target_id = open_response.json()["target_id"]

        response = self.client.post(
            "/browser/actions",
            json={
                "kind": "cdp-raw",
                "target_id": target_id,
                "payload": {"method": "Runtime.evaluate"},
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("internal debug/admin", response.json()["detail"])

    def test_browser_snapshot_endpoint_exposes_frame_path(self) -> None:
        open_response = self.client.post(
            "/browser/control",
            json={
                "kind": "open-tab",
                "payload": {"url": "https://example.com"},
            },
        )
        self.assertEqual(open_response.status_code, 200)
        target_id = open_response.json()["target_id"]

        pool = FakePlaywrightCdpSessionPool.last_created
        self.assertIsNotNone(pool)
        assert pool is not None
        page = pool.resolve_page(
            profile=object(),
            target_id=target_id,
        )
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

        snapshot_response = self.client.post(
            "/browser/actions",
            json={
                "kind": "snapshot",
                "target_id": target_id,
                "payload": {"format": "interactive"},
            },
        )

        self.assertEqual(snapshot_response.status_code, 200)
        payload = snapshot_response.json()
        self.assertEqual(payload["value"]["result"]["format"], "interactive")
        self.assertEqual(payload["value"]["result"]["value"]["refs"][0]["frame_path"], [0])

        profiles_response = self.client.get("/browser/profiles")
        self.assertEqual(profiles_response.status_code, 200)
        profiles_payload = profiles_response.json()
        crxzipple_profile = next(
            item for item in profiles_payload["profiles"] if item["name"] == "crxzipple"
        )
        runtime = crxzipple_profile["runtime"]
        self.assertTrue(runtime["host_generation"])
        page_state = runtime["page_state"]
        self.assertEqual(page_state["active_target_id"], target_id)
        self.assertEqual(page_state["page_count"], 1)
        active_page = page_state["active_page"]
        self.assertEqual(active_page["target_id"], target_id)
        self.assertEqual(active_page["page_generation"], 1)
        self.assertEqual(active_page["page_generation_reason"], "open-tab")
        self.assertEqual(active_page["snapshot_generation"], 1)
        self.assertEqual(active_page["current_ref_generation"], 1)
        self.assertEqual(active_page["last_action_kind"], "snapshot")
        self.assertEqual(active_page["last_snapshot_format"], "interactive")
        self.assertEqual(active_page["last_snapshot_ref_count"], 1)
        self.assertEqual(active_page["last_snapshot_frame_count"], 1)
        self.assertNotIn("active_overlay_selector", active_page)

        update_response = self.client.put(
            "/browser/profiles/crxzipple",
            json={"cdp_port": 9333},
        )
        self.assertEqual(update_response.status_code, 200)
        updated_profile = next(
            item for item in update_response.json()["profiles"] if item["name"] == "crxzipple"
        )
        self.assertEqual(updated_profile["diagnostics"]["status"], "restart-needed")
        self.assertEqual(updated_profile["diagnostics"]["recommended_action"], "restart-profile")
        self.assertIn("cdp_port", updated_profile["diagnostics"]["restart_fields"])

    def test_browser_profile_diagnostics_prefers_current_daemon_instance_metadata(self) -> None:
        open_response = self.client.post(
            "/browser/control",
            json={
                "kind": "open-tab",
                "payload": {"url": "https://example.com"},
            },
        )
        self.assertEqual(open_response.status_code, 200)

        daemon_service = self.client.app.state.container.require(AppKey.DAEMON_SERVICE)
        stale = DaemonInstance(
            id="aaa-stale-browser-host",
            service_key="host:browser:crxzipple",
            status="stopped",
            endpoint="http://stale.example:9333",
            started_at=datetime(2026, 5, 26, 10, 0, tzinfo=timezone.utc),
            last_healthcheck_at=datetime(2026, 5, 26, 10, 5, tzinfo=timezone.utc),
            metadata={
                "profile_name": "crxzipple",
                "cdp_url": "http://stale.example:9333",
                "cdp_port": 9333,
            },
        )
        current = DaemonInstance(
            id="bbb-ready-browser-host",
            service_key="host:browser:crxzipple",
            status="ready",
            endpoint=self._fake_cdp_server.base_url,
            started_at=datetime(2026, 5, 26, 10, 1, tzinfo=timezone.utc),
            last_healthcheck_at=datetime(2026, 5, 26, 10, 2, tzinfo=timezone.utc),
            metadata={
                "profile_name": "crxzipple",
                "cdp_url": self._fake_cdp_server.base_url,
                "cdp_port": int(self._fake_cdp_server.base_url.rsplit(":", 1)[1]),
            },
        )
        daemon_service.instance_store.save((stale, current))

        response = self.client.get("/browser/profiles")

        self.assertEqual(response.status_code, 200)
        profile = next(
            item for item in response.json()["profiles"] if item["name"] == "crxzipple"
        )
        self.assertEqual(profile["diagnostics"]["status"], "ready")
        self.assertNotIn("restart_fields", profile["diagnostics"])

    def test_browser_profile_management_endpoints_manage_state_root(self) -> None:
        create_response = self.client.post(
            "/browser/profiles",
            json={
                "name": "work",
                "cdp_url": "http://browser.example:9555",
                "profile_directory": "Profile 1",
                "proxy_mode": "static",
                "proxy_server": "socks5://127.0.0.1:7890",
                "proxy_bypass_list": ["127.0.0.1", "localhost"],
                "close_targets_on_release": False,
                "set_as_default": True,
            },
        )
        self.assertEqual(create_response.status_code, 200)
        create_payload = create_response.json()
        self.assertEqual(create_payload["default_profile"], "work")
        self.assertIn("work", [item["name"] for item in create_payload["profiles"]])
        created_work = next(item for item in create_payload["profiles"] if item["name"] == "work")
        self.assertTrue(created_work["enabled"])
        self.assertFalse(created_work["close_targets_on_release"])
        self.assertTrue(created_work["close_targets_on_expire"])

        update_response = self.client.put(
            "/browser/profiles/work",
            json={
                "user_data_dir": "/tmp/work-profile",
                "attach_only": True,
                "clear_proxy_bypass_list": True,
                "close_targets_on_expire": False,
            },
        )
        self.assertEqual(update_response.status_code, 200)
        updated_work = next(
            item for item in update_response.json()["profiles"] if item["name"] == "work"
        )
        self.assertEqual(updated_work["user_data_dir"], "/tmp/work-profile")
        self.assertEqual(updated_work["profile_directory"], "Profile 1")
        self.assertEqual(updated_work["proxy"]["mode"], "static")
        self.assertEqual(updated_work["proxy"]["server"], "socks5://127.0.0.1:7890")
        self.assertEqual(updated_work["proxy"]["bypass_list"], [])
        self.assertTrue(updated_work["attach_only"])
        self.assertFalse(updated_work["autostart"])
        self.assertFalse(updated_work["close_targets_on_expire"])

        disable_response = self.client.post("/browser/profiles/work/disable")
        self.assertEqual(disable_response.status_code, 200)
        disabled_work = next(
            item for item in disable_response.json()["profiles"] if item["name"] == "work"
        )
        self.assertFalse(disabled_work["enabled"])
        self.assertEqual(disabled_work["diagnostics"]["status"], "disabled")

        disabled_start_response = self.client.post("/browser/profiles/work/start")
        self.assertEqual(disabled_start_response.status_code, 400)
        self.assertIn("disabled", disabled_start_response.json()["detail"])

        enable_response = self.client.post("/browser/profiles/work/enable")
        self.assertEqual(enable_response.status_code, 200)
        enabled_work = next(
            item for item in enable_response.json()["profiles"] if item["name"] == "work"
        )
        self.assertTrue(enabled_work["enabled"])

        cdp_test_response = self.client.post("/browser/profiles/work/test-cdp")
        self.assertEqual(cdp_test_response.status_code, 200)
        self.assertEqual(cdp_test_response.json()["profile"]["name"], "work")

        class _FakeEgressResponse:
            status_code = 200
            text = ""

            def json(self):
                return {"ip": "203.0.113.44"}

            def raise_for_status(self) -> None:
                return None

        class _FakeSession:
            last_request: dict[str, object] = {}

            def __init__(self) -> None:
                self.trust_env = True

            def get(self, url, *, proxies, timeout):  # noqa: ANN001
                self.__class__.last_request = {
                    "url": url,
                    "proxies": proxies,
                    "timeout": timeout,
                    "trust_env": self.trust_env,
                }
                return _FakeEgressResponse()

            def close(self) -> None:
                return None

        with patch("crxzipple.modules.browser.interfaces.http.requests.Session", _FakeSession):
            static_egress_response = self.client.post(
                "/browser/profiles/work/test-egress",
                json={"url": "https://example.com/ip"},
            )
        self.assertEqual(static_egress_response.status_code, 200)
        self.assertEqual(static_egress_response.json()["result"]["ip"], "203.0.113.44")
        self.assertFalse(_FakeSession.last_request["trust_env"])
        self.assertEqual(
            _FakeSession.last_request["proxies"],
            {
                "http": "socks5://127.0.0.1:7890",
                "https": "socks5://127.0.0.1:7890",
            },
        )
        runtime_state = self.client.app.state.container.require(
            AppKey.BROWSER_INFRASTRUCTURE,
        ).runtime_state_store.get(profile_name="work")
        self.assertIsNotNone(runtime_state)
        assert runtime_state is not None
        self.assertEqual(runtime_state.metadata["proxy_egress_ip"], "203.0.113.44")
        self.assertEqual(runtime_state.metadata["proxy_egress_status"], "ready")

        egress_test_response = self.client.post(
            "/browser/profiles/user/test-egress",
            json={"url": "https://example.com/ip"},
        )
        self.assertEqual(egress_test_response.status_code, 200)
        self.assertEqual(egress_test_response.json()["status"], "not_required")

        default_response = self.client.post(
            "/browser/profiles/default",
            json={"profile_name": "user"},
        )
        self.assertEqual(default_response.status_code, 200)
        self.assertEqual(default_response.json()["default_profile"], "user")

        delete_response = self.client.delete("/browser/profiles/work")
        self.assertEqual(delete_response.status_code, 200)
        delete_payload = delete_response.json()
        self.assertNotIn("work", [item["name"] for item in delete_payload["profiles"]])
        browser_state_root = self.client.app.state.container.require(
            AppKey.BROWSER_INFRASTRUCTURE,
        ).state_root
        self.assertFalse(
            (browser_state_root.profiles_dir / "work").exists()
        )

    def test_browser_profile_pool_management_endpoints_manage_pools(self) -> None:
        create_response = self.client.post(
            "/browser/pools",
            json={
                "pool_id": "collection",
                "display_name": "Collection Pool",
                "profile_names": ["crxzipple"],
                "target_hosts": ["ctrip.com"],
                "max_concurrency_per_profile": 2,
                "close_targets_on_release": False,
            },
        )

        self.assertEqual(create_response.status_code, 200)
        create_payload = create_response.json()
        self.assertEqual(create_payload["profile_count"], 2)
        collection_pool = next(
            item for item in create_payload["pools"] if item["pool_id"] == "collection"
        )
        self.assertEqual(collection_pool["display_name"], "Collection Pool")
        self.assertEqual(collection_pool["profile_names"], ["crxzipple"])
        self.assertFalse(collection_pool["close_targets_on_release"])
        self.assertTrue(collection_pool["close_targets_on_expire"])
        self.assertTrue(collection_pool["ready"])

        update_response = self.client.put(
            "/browser/pools/collection",
            json={
                "enabled": False,
                "selection_strategy": "round_robin",
                "max_concurrency_total": 3,
                "close_targets_on_expire": False,
            },
        )
        self.assertEqual(update_response.status_code, 200)
        updated_pool = next(
            item for item in update_response.json()["pools"] if item["pool_id"] == "collection"
        )
        self.assertFalse(updated_pool["enabled"])
        self.assertFalse(updated_pool["ready"])
        self.assertEqual(updated_pool["selection_strategy"], "round_robin")
        self.assertEqual(updated_pool["max_concurrency_total"], 3)
        self.assertFalse(updated_pool["close_targets_on_expire"])

        enable_response = self.client.post("/browser/pools/collection/enable")
        self.assertEqual(enable_response.status_code, 200)
        enabled_pool = next(
            item for item in enable_response.json()["pools"] if item["pool_id"] == "collection"
        )
        self.assertTrue(enabled_pool["enabled"])

        show_response = self.client.get("/browser/pools/collection")
        self.assertEqual(show_response.status_code, 200)
        self.assertEqual(show_response.json()["pool"]["pool_id"], "collection")

        delete_response = self.client.delete("/browser/pools/collection")
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(delete_response.json()["pools"], [])

        reject_response = self.client.post(
            "/browser/pools",
            json={"pool_id": "personal", "profile_names": ["user"]},
        )
        self.assertEqual(reject_response.status_code, 400)
        self.assertIn("attach-only", reject_response.json()["detail"])

    def test_browser_allocation_endpoints_allocate_release_and_drain(self) -> None:
        create_pool_response = self.client.post(
            "/browser/pools",
            json={
                "pool_id": "collection",
                "profile_names": ["crxzipple"],
                "target_hosts": ["example.com"],
            },
        )
        self.assertEqual(create_pool_response.status_code, 200)

        allocate_response = self.client.post(
            "/browser/allocations",
            json={
                "pool_id": "collection",
                "consumer_kind": "tool_run",
                "consumer_id": "tool-1",
                "target_host": "example.com",
            },
        )
        self.assertEqual(allocate_response.status_code, 200)
        allocation = allocate_response.json()["allocation"]
        self.assertEqual(allocation["pool_id"], "collection")
        self.assertEqual(allocation["profile_name"], "crxzipple")
        self.assertEqual(allocation["status"], "active")

        reused_response = self.client.post(
            "/browser/allocations",
            json={
                "pool_id": "collection",
                "consumer_kind": "tool_run",
                "consumer_id": "tool-1",
                "target_host": "example.com",
            },
        )
        self.assertEqual(reused_response.status_code, 200)
        self.assertEqual(
            reused_response.json()["allocation"]["allocation_id"],
            allocation["allocation_id"],
        )

        list_response = self.client.get("/browser/allocations?active_only=true")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_response.json()["total"], 1)

        release_response = self.client.post(
            f"/browser/allocations/{allocation['allocation_id']}/release",
            json={"reason": "done"},
        )
        self.assertEqual(release_response.status_code, 200)
        self.assertEqual(release_response.json()["allocation"]["status"], "released")

        second_allocate_response = self.client.post(
            "/browser/allocations",
            json={
                "pool_id": "collection",
                "consumer_kind": "tool_run",
                "consumer_id": "tool-2",
            },
        )
        self.assertEqual(second_allocate_response.status_code, 200)
        drain_response = self.client.post("/browser/pools/collection/drain")
        self.assertEqual(drain_response.status_code, 200)
        self.assertEqual(drain_response.json()["released"], 1)

    def test_browser_profile_delete_rejects_default_profile(self) -> None:
        response = self.client.delete("/browser/profiles/crxzipple")

        self.assertEqual(response.status_code, 400)
        self.assertIn("default browser profile", response.json()["detail"])

    def test_browser_control_reset_clears_runtime_state_and_userdata(self) -> None:
        open_response = self.client.post(
            "/browser/control",
            json={
                "kind": "open-tab",
                "payload": {"url": "https://example.com"},
            },
        )
        self.assertEqual(open_response.status_code, 200)
        browser_state_root = self.client.app.state.container.require(
            AppKey.BROWSER_INFRASTRUCTURE,
        ).state_root
        runtime_path = browser_state_root.runtime_dir / "crxzipple.json"
        self.assertTrue(runtime_path.exists())

        userdata_dir = browser_state_root.profiles_dir / "crxzipple" / "userdata"
        sentinel = userdata_dir / "sentinel.txt"
        sentinel.write_text("state", encoding="utf-8")

        reset_response = self.client.post(
            "/browser/control",
            json={"kind": "reset"},
        )

        self.assertEqual(reset_response.status_code, 200)
        payload = reset_response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"]["kind"], "reset")
        self.assertEqual(payload["value"]["profile_name"], "crxzipple")
        self.assertFalse(runtime_path.exists())
        self.assertEqual(list(userdata_dir.iterdir()), [])

    def test_browser_control_reset_rejects_existing_session_profiles(self) -> None:
        response = self.client.post(
            "/browser/control",
            json={
                "profile_name": "user",
                "kind": "reset",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("does not support reset", response.json()["detail"])

    def test_browser_control_open_tab_respects_managed_tab_limit(self) -> None:
        browser_state_root = self.client.app.state.container.require(
            AppKey.BROWSER_INFRASTRUCTURE,
        ).state_root
        system_path = browser_state_root.config_dir / "system.json"
        payload = json.loads(system_path.read_text(encoding="utf-8"))
        payload["managed_tab_limit"] = 1
        for profile in payload["profiles"]:
            if profile["name"] == "user":
                profile["cdp_url"] = self._fake_cdp_server.base_url
        system_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        user_profile_path = browser_state_root.profiles_dir / "user" / "profile.json"
        user_profile = json.loads(user_profile_path.read_text(encoding="utf-8"))
        user_profile["cdp_url"] = self._fake_cdp_server.base_url
        user_profile_path.write_text(
            json.dumps(user_profile, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        first_response = self.client.post(
            "/browser/control",
            json={
                "kind": "open-tab",
                "payload": {"url": "https://example.com/one"},
            },
        )
        self.assertEqual(first_response.status_code, 200)

        second_response = self.client.post(
            "/browser/control",
            json={
                "kind": "open-tab",
                "payload": {"url": "https://example.com/two"},
            },
        )
        self.assertEqual(second_response.status_code, 400)
        self.assertIn("managed tab limit", second_response.json()["detail"].lower())

        existing_session_response = self.client.post(
            "/browser/control",
            json={
                "profile_name": "user",
                "kind": "open-tab",
                "payload": {"url": "https://example.com/user"},
            },
        )
        self.assertEqual(existing_session_response.status_code, 200)

    def test_browser_existing_session_tabs_expose_cdp_tab_endpoints(self) -> None:
        browser_state_root = self.client.app.state.container.require(
            AppKey.BROWSER_INFRASTRUCTURE,
        ).state_root
        system_path = browser_state_root.config_dir / "system.json"
        payload = json.loads(system_path.read_text(encoding="utf-8"))
        for profile in payload["profiles"]:
            if profile["name"] == "user":
                profile["cdp_url"] = self._fake_cdp_server.base_url
        system_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        user_profile_path = browser_state_root.profiles_dir / "user" / "profile.json"
        user_profile = json.loads(user_profile_path.read_text(encoding="utf-8"))
        user_profile["cdp_url"] = self._fake_cdp_server.base_url
        user_profile_path.write_text(
            json.dumps(user_profile, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        response = self.client.post(
            "/browser/control",
            json={
                "profile_name": "user",
                "kind": "open-tab",
                "payload": {"url": "https://example.com"},
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNotNone(response.json()["value"]["ws_url"])
        self.assertIsNotNone(response.json()["value"]["json_endpoints"])
