from __future__ import annotations

from dataclasses import replace
import os
import unittest

from fastapi.testclient import TestClient

from crxzipple.core.config import load_settings
from crxzipple.interfaces.http.app import create_app
from tests.unit.support import SqliteTestHarness


_LIVE_SMOKE_ENABLED = os.getenv("APP_BROWSER_LIVE_SMOKE", "").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
_LIVE_SMOKE_URL = os.getenv("APP_BROWSER_LIVE_IFRAME_URL", "https://music.163.com/").strip()
_LIVE_SMOKE_WAIT_MS = max(int(os.getenv("APP_BROWSER_LIVE_WAIT_MS", "4000")), 1)


@unittest.skipUnless(_LIVE_SMOKE_ENABLED, "live browser smoke test is disabled")
class BrowserLiveIframeSmokeTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=False,
            browser_state_dir=str(self.harness._tempdir.name + "/browser"),
            browser_headless=True,
        )
        self.harness.initialize_schema(settings=settings)
        self.client = TestClient(
            create_app(
                settings=settings,
                database_url=self.harness.database_url,
            ),
        )

    def tearDown(self) -> None:
        self.client.close()
        self.client.app.state.container.engine.dispose()
        self.harness.close()

    def test_netease_iframe_snapshot_ref_and_action_flow(self) -> None:
        open_response = self.client.post(
            "/browser/control",
            json={
                "kind": "open-tab",
                "payload": {"url": _LIVE_SMOKE_URL},
                "timeout_ms": 15_000,
            },
        )
        if open_response.status_code != 200:
            detail = open_response.text
            if "executable" in detail.lower() or "cdp" in detail.lower():
                self.skipTest(detail)
            self.fail(f"open-tab failed: {detail}")
        target_id = open_response.json()["target_id"]

        wait_iframe_response = self.client.post(
            "/browser/actions",
            json={
                "kind": "wait",
                "target_id": target_id,
                "selector": "#g_iframe",
                "payload": {"state": "visible"},
                "timeout_ms": 15_000,
            },
        )
        self.assertEqual(wait_iframe_response.status_code, 200, wait_iframe_response.text)

        settle_response = self.client.post(
            "/browser/actions",
            json={
                "kind": "wait",
                "target_id": target_id,
                "payload": {"delay_ms": _LIVE_SMOKE_WAIT_MS},
                "timeout_ms": _LIVE_SMOKE_WAIT_MS + 2_000,
            },
        )
        self.assertEqual(settle_response.status_code, 200, settle_response.text)

        snapshot_response = self.client.post(
            "/browser/actions",
            json={
                "kind": "snapshot",
                "target_id": target_id,
                "payload": {"format": "interactive", "limit": 200},
                "timeout_ms": 20_000,
            },
        )
        self.assertEqual(snapshot_response.status_code, 200, snapshot_response.text)
        snapshot_payload = snapshot_response.json()
        items = snapshot_payload["value"]["result"]["value"]
        self.assertTrue(items, "interactive snapshot returned no items")

        frame_items = [item for item in items if item.get("frame_path")]
        self.assertTrue(frame_items, "interactive snapshot returned no child-frame refs")
        target_item = frame_items[0]

        action_response = self.client.post(
            "/browser/actions",
            json={
                "kind": "scroll-into-view",
                "target_id": target_id,
                "ref": target_item["ref"],
                "timeout_ms": 15_000,
            },
        )
        self.assertEqual(action_response.status_code, 200, action_response.text)
        action_payload = action_response.json()
        self.assertTrue(action_payload["ok"])
        self.assertEqual(action_payload["value"]["frame_path"], target_item["frame_path"])

        close_response = self.client.post(
            "/browser/control",
            json={
                "kind": "close-tab",
                "target_id": target_id,
                "timeout_ms": 10_000,
            },
        )
        self.assertEqual(close_response.status_code, 200, close_response.text)
