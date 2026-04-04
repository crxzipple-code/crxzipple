from __future__ import annotations

import json as _json

from tests.unit.http_test_support import *


class BrowserHttpTestCase(HttpModuleTestCase):
    def setUp(self) -> None:
        self._previous_browser_profile_specs = os.environ.get("APP_BROWSER_PROFILE_SPECS")
        self._playwright_pool_patcher = patch(
            "crxzipple.bootstrap.container.PlaywrightCdpSessionPool",
            FakePlaywrightCdpSessionPool,
        )
        self._mcp_pool_patcher = patch(
            "crxzipple.bootstrap.container.ChromeMcpClientPool",
            FakeChromeMcpClientPool,
        )
        self._playwright_pool_patcher.start()
        self._mcp_pool_patcher.start()
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
        self._mcp_pool_patcher.stop()
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
        self.assertEqual(payload["profile"]["diagnostics"]["status"], "ready")
        self.assertEqual(
            payload["profile"]["diagnostics"]["recommended_action"],
            "use-profile",
        )
        self.assertEqual(payload["profile"]["diagnostics"]["summary"]["code"], "ready")
        self.assertIn("Ready:", payload["profile"]["diagnostics"]["summary_line"])
        self.assertEqual(
            payload["profile"]["diagnostics"]["probe"]["status"],
            "mcp-connected",
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
            system_path = container.browser_state_root.config_dir / "system.json"
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
            client.app.state.container.engine.dispose()
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

    def test_browser_profile_management_endpoints_manage_state_root(self) -> None:
        create_response = self.client.post(
            "/browser/profiles",
            json={
                "name": "work",
                "cdp_url": "http://browser.example:9555",
                "set_as_default": True,
            },
        )
        self.assertEqual(create_response.status_code, 200)
        create_payload = create_response.json()
        self.assertEqual(create_payload["default_profile"], "work")
        self.assertIn("work", [item["name"] for item in create_payload["profiles"]])

        update_response = self.client.put(
            "/browser/profiles/work",
            json={
                "user_data_dir": "/tmp/work-profile",
                "attach_only": True,
            },
        )
        self.assertEqual(update_response.status_code, 200)
        updated_work = next(
            item for item in update_response.json()["profiles"] if item["name"] == "work"
        )
        self.assertEqual(updated_work["user_data_dir"], "/tmp/work-profile")
        self.assertTrue(updated_work["attach_only"])

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
        self.assertFalse(
            (self.client.app.state.container.browser_state_root.profiles_dir / "work").exists()
        )

    def test_browser_control_reset_clears_runtime_state_and_userdata(self) -> None:
        open_response = self.client.post(
            "/browser/control",
            json={
                "kind": "open-tab",
                "payload": {"url": "https://example.com"},
            },
        )
        self.assertEqual(open_response.status_code, 200)
        runtime_path = self.client.app.state.container.browser_state_root.runtime_dir / "crxzipple.json"
        self.assertTrue(runtime_path.exists())

        userdata_dir = (
            self.client.app.state.container.browser_state_root.profiles_dir
            / "crxzipple"
            / "userdata"
        )
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
        system_path = self.client.app.state.container.browser_state_root.config_dir / "system.json"
        payload = json.loads(system_path.read_text(encoding="utf-8"))
        payload["managed_tab_limit"] = 1
        system_path.write_text(
            json.dumps(payload, indent=2, sort_keys=True),
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

    def test_browser_existing_session_tabs_do_not_expose_ws_url(self) -> None:
        response = self.client.post(
            "/browser/control",
            json={
                "profile_name": "user",
                "kind": "open-tab",
                "payload": {"url": "https://example.com"},
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.json()["value"]["ws_url"])
        self.assertIsNone(response.json()["value"]["json_endpoints"])
