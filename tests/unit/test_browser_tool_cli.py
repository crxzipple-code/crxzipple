from __future__ import annotations

import json as _json

from tests.unit.cli_test_support import *


class BrowserToolCliTestCase(CliModuleTestCase):
    def setUp(self) -> None:
        super().setUp()
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
        super().tearDown()

    def test_browser_tool_is_listed_and_can_open_tab(self) -> None:
        list_result = self.runner.invoke(app, ["tool", "list"], env=self.env)

        self.assertEqual(list_result.exit_code, 0)
        self.assertIn('"id": "browser_profile"', list_result.stdout)
        self.assertIn('"id": "browser_control"', list_result.stdout)
        self.assertIn('"id": "browser_script"', list_result.stdout)
        self.assertIn('"id": "browser_snapshot"', list_result.stdout)
        self.assertIn('"id": "browser_action"', list_result.stdout)

        run_result = self.runner.invoke(
            app,
            [
                "tool",
                "run",
                "browser_control",
                "--input",
                '{"kind":"open-tab","url":"https://example.com"}',
            ],
            env=self.env,
        )

        self.assertEqual(run_result.exit_code, 0)
        payload = json.loads(run_result.stdout)
        self.assertEqual(payload["tool_id"], "browser_control")
        self.assertEqual(payload["status"], "succeeded")
        self.assertEqual(payload["output_payload"]["command"]["kind"], "open-tab")
        self.assertTrue(
            payload["output_payload"]["value"]["url"].startswith("https://example.com")
        )
        self.assertEqual(
            payload["output_payload"]["value"]["ws_url"],
            f"{self._fake_cdp_server.base_url.replace('http://', 'ws://')}/devtools/page/{payload['output_payload']['target_id']}",
        )
        self.assertEqual(
            payload["output_payload"]["value"]["json_endpoints"],
            {
                "version": f"{self._fake_cdp_server.base_url}/json/version",
                "list": f"{self._fake_cdp_server.base_url}/json/list",
                "new": f"{self._fake_cdp_server.base_url}/json/new",
                "activate": f"{self._fake_cdp_server.base_url}/json/activate/{payload['output_payload']['target_id']}",
                "close": f"{self._fake_cdp_server.base_url}/json/close/{payload['output_payload']['target_id']}",
            },
        )
