from __future__ import annotations

import json as _json
from types import SimpleNamespace

from tests.unit.cli_test_support import *


class BrowserCliTestCase(CliModuleTestCase):
    def setUp(self) -> None:
        super().setUp()
        FakePlaywrightCdpSessionPool.page_initializers = {}
        FakePlaywrightCdpSessionPool.last_created = None
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
        seed_browser_state_root(
            Path(self.harness._tempdir.name) / "browser",
            profiles=[
                {
                    "name": "crxzipple",
                    "cdp_url": self._fake_cdp_server.base_url,
                },
                {
                    "name": "user",
                    "driver": "existing-session",
                    "attach_only": True,
                },
            ],
        )
        self.env["APP_BROWSER_PROFILE_SPECS"] = _json.dumps(
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

    def tearDown(self) -> None:
        self._fake_cdp_server.close()
        self._playwright_pool_patcher.stop()
        self._mcp_pool_patcher.stop()
        FakePlaywrightCdpSessionPool.page_initializers = {}
        FakePlaywrightCdpSessionPool.last_created = None
        super().tearDown()

    def test_browser_profiles_command_returns_profile_matrix(self) -> None:
        result = self.runner.invoke(app, ["browser", "profiles"], env=self.env)

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
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

    def test_browser_profile_diagnose_command_returns_actionable_status(self) -> None:
        result = self.runner.invoke(app, ["browser", "profile", "diagnose", "user"], env=self.env)

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertEqual(payload["profile"]["name"], "user")
        self.assertEqual(payload["profile"]["diagnostics"]["status"], "ready")
        self.assertEqual(payload["profile"]["diagnostics"]["recommended_action"], "use-profile")
        self.assertEqual(payload["profile"]["diagnostics"]["summary"]["code"], "ready")
        self.assertIn("Ready:", payload["profile"]["diagnostics"]["summary_line"])
        self.assertEqual(
            payload["profile"]["diagnostics"]["probe"]["status"],
            "mcp-connected",
        )

    def test_browser_control_open_tab_command_returns_serialized_result(self) -> None:
        result = self.runner.invoke(
            app,
            [
                "browser",
                "control",
                "open-tab",
                "--payload",
                '{"url":"https://example.com"}',
            ],
            env=self.env,
        )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"]["family"], "control")
        self.assertEqual(payload["command"]["kind"], "open-tab")
        self.assertTrue(payload["value"]["url"].startswith("https://example.com"))
        self.assertEqual(
            payload["value"]["ws_url"],
            f"{self._fake_cdp_server.base_url.replace('http://', 'ws://')}/devtools/page/{payload['target_id']}",
        )
        self.assertEqual(
            payload["value"]["json_endpoints"],
            {
                "version": f"{self._fake_cdp_server.base_url}/json/version",
                "list": f"{self._fake_cdp_server.base_url}/json/list",
                "new": f"{self._fake_cdp_server.base_url}/json/new",
                "activate": f"{self._fake_cdp_server.base_url}/json/activate/{payload['target_id']}",
                "close": f"{self._fake_cdp_server.base_url}/json/close/{payload['target_id']}",
            },
        )

    def test_browser_host_run_uses_host_loop(self) -> None:
        container = SimpleNamespace(
            browser_system_config_store=SimpleNamespace(
                load=lambda: SimpleNamespace(default_profile="crxzipple"),
            ),
            browser_cdp_control=SimpleNamespace(
                terminate_owned_processes_on_close=False,
            ),
        )

        with patch(
            "crxzipple.modules.browser.interfaces.cli.ensure_container",
            return_value=container,
        ), patch(
            "crxzipple.modules.browser.interfaces.cli._run_host_loop",
        ) as mocked_loop:
            result = self.runner.invoke(
                app,
                [
                    "browser",
                    "host",
                    "run",
                    "--profile",
                    "crxzipple",
                    "--poll-interval-seconds",
                    "1.5",
                    "--max-cycles",
                    "2",
                ],
                env=self.env,
            )

        self.assertEqual(result.exit_code, 0)
        args = mocked_loop.call_args
        self.assertIsNotNone(args)
        self.assertEqual(args.args[0], container)
        self.assertEqual(args.kwargs["profile_name"], "crxzipple")
        self.assertEqual(args.kwargs["poll_interval_seconds"], 1.5)
        self.assertEqual(args.kwargs["max_cycles"], 2)
        self.assertTrue(container.browser_cdp_control.terminate_owned_processes_on_close)

    def test_browser_mcp_run_uses_mcp_loop(self) -> None:
        container = SimpleNamespace(
            browser_system_config_store=SimpleNamespace(
                load=lambda: SimpleNamespace(default_profile="user"),
            ),
        )

        with patch(
            "crxzipple.modules.browser.interfaces.cli.ensure_container",
            return_value=container,
        ), patch(
            "crxzipple.modules.browser.interfaces.cli._run_mcp_loop",
        ) as mocked_loop:
            result = self.runner.invoke(
                app,
                [
                    "browser",
                    "mcp",
                    "run",
                    "--profile",
                    "user",
                    "--poll-interval-seconds",
                    "1.5",
                    "--max-cycles",
                    "2",
                ],
                env=self.env,
            )

        self.assertEqual(result.exit_code, 0)
        args = mocked_loop.call_args
        self.assertIsNotNone(args)
        self.assertEqual(args.args[0], container)
        self.assertEqual(args.kwargs["profile_name"], "user")
        self.assertEqual(args.kwargs["poll_interval_seconds"], 1.5)
        self.assertEqual(args.kwargs["max_cycles"], 2)

    def test_browser_act_snapshot_command_exposes_frame_path(self) -> None:
        open_result = self.runner.invoke(
            app,
            [
                "browser",
                "control",
                "open-tab",
                "--payload",
                '{"url":"https://example.com"}',
            ],
            env=self.env,
        )

        self.assertEqual(open_result.exit_code, 0)
        target_id = json.loads(open_result.stdout)["target_id"]
        def _seed_frame(page) -> None:  # noqa: ANN001
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

        FakePlaywrightCdpSessionPool.page_initializers[target_id] = _seed_frame

        snapshot_result = self.runner.invoke(
            app,
            [
                "browser",
                "act",
                "snapshot",
                "--target-id",
                target_id,
                "--payload",
                '{"format":"interactive"}',
            ],
            env=self.env,
        )

        self.assertEqual(snapshot_result.exit_code, 0)
        payload = json.loads(snapshot_result.stdout)
        self.assertEqual(payload["value"]["result"]["value"]["refs"][0]["frame_path"], [0])

    def test_browser_profile_commands_manage_profiles(self) -> None:
        create_result = self.runner.invoke(
            app,
            [
                "browser",
                "profile",
                "create",
                "work",
                "--cdp-url",
                "http://browser.example:9555",
                "--set-default",
            ],
            env=self.env,
        )
        self.assertEqual(create_result.exit_code, 0)
        create_payload = json.loads(create_result.stdout)
        self.assertEqual(create_payload["default_profile"], "work")

        update_result = self.runner.invoke(
            app,
            [
                "browser",
                "profile",
                "update",
                "work",
                "--user-data-dir",
                "/tmp/work-profile",
                "--attach-only",
            ],
            env=self.env,
        )
        self.assertEqual(update_result.exit_code, 0)
        update_payload = json.loads(update_result.stdout)
        updated_work = next(
            item for item in update_payload["profiles"] if item["name"] == "work"
        )
        self.assertEqual(updated_work["user_data_dir"], "/tmp/work-profile")
        self.assertTrue(updated_work["attach_only"])

        default_result = self.runner.invoke(
            app,
            ["browser", "profile", "set-default", "user"],
            env=self.env,
        )
        self.assertEqual(default_result.exit_code, 0)
        self.assertEqual(json.loads(default_result.stdout)["default_profile"], "user")

        delete_result = self.runner.invoke(
            app,
            ["browser", "profile", "delete", "work"],
            env=self.env,
        )
        self.assertEqual(delete_result.exit_code, 0)
        delete_payload = json.loads(delete_result.stdout)
        self.assertNotIn("work", [item["name"] for item in delete_payload["profiles"]])

    def test_browser_control_reset_command_clears_runtime_state_and_userdata(self) -> None:
        open_result = self.runner.invoke(
            app,
            [
                "browser",
                "control",
                "open-tab",
                "--payload",
                '{"url":"https://example.com"}',
            ],
            env=self.env,
        )
        self.assertEqual(open_result.exit_code, 0)

        runtime_path = Path(self.harness._tempdir.name) / "browser" / "runtime" / "crxzipple.json"
        self.assertTrue(runtime_path.exists())
        userdata_dir = (
            Path(self.harness._tempdir.name)
            / "browser"
            / "profiles"
            / "crxzipple"
            / "userdata"
        )
        sentinel = userdata_dir / "sentinel.txt"
        sentinel.write_text("state", encoding="utf-8")

        reset_result = self.runner.invoke(
            app,
            ["browser", "control", "reset"],
            env=self.env,
        )

        self.assertEqual(reset_result.exit_code, 0)
        payload = json.loads(reset_result.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["command"]["kind"], "reset")
        self.assertEqual(payload["value"]["profile_name"], "crxzipple")
        self.assertFalse(runtime_path.exists())
        self.assertEqual(list(userdata_dir.iterdir()), [])

    def test_browser_control_reset_command_rejects_existing_session_profiles(self) -> None:
        result = self.runner.invoke(
            app,
            ["browser", "control", "reset", "--profile", "user"],
            env=self.env,
        )

        self.assertNotEqual(result.exit_code, 0)
        self.assertIn("does not support reset", result.output)

    def test_browser_existing_session_open_tab_command_omits_ws_url(self) -> None:
        result = self.runner.invoke(
            app,
            [
                "browser",
                "control",
                "open-tab",
                "--profile",
                "user",
                "--payload",
                '{"url":"https://example.com"}',
            ],
            env=self.env,
        )

        self.assertEqual(result.exit_code, 0)
        payload = json.loads(result.stdout)
        self.assertIsNone(payload["value"]["ws_url"])
        self.assertIsNone(payload["value"]["json_endpoints"])
