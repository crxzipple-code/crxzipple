from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from crxzipple.core.config import load_settings
from crxzipple.interfaces.http.app import create_app
from crxzipple.interfaces.runtime_container import AppKey
from crxzipple.modules.daemon import DaemonInstance
from tests.unit.support import (
    FakeCdpServer,
    FakePlaywrightCdpSessionPool,
    SqliteTestHarness,
)
from tests.unit.http_test_support import HttpModuleTestCase
from tests.unit.http_test_support import _fake_cdp_control_engine


def _mark_browser_profiles_ready(client: TestClient, *profile_names: str, endpoint: str) -> None:
    daemon_service = client.app.state.container.require(AppKey.DAEMON_SERVICE)
    for profile_name in profile_names:
        instance = DaemonInstance.create(
            service_key=f"host:browser:{profile_name}",
            endpoint=endpoint,
            metadata={"profile_name": profile_name},
        )
        instance.mark_ready(endpoint=endpoint)
        daemon_service.save_instance(instance)


class BrowserToolHttpRuntimeTestCase(HttpModuleTestCase):
    def test_browser_tool_is_listed_and_can_open_tab(self) -> None:
        previous_specs = os.environ.get("APP_BROWSER_PROFILE_SPECS")
        fake_cdp_server = FakeCdpServer()
        fake_cdp_server.start()
        os.environ["APP_BROWSER_PROFILE_SPECS"] = json.dumps(
            [
                {
                    "name": "crxzipple",
                    "cdp_url": fake_cdp_server.base_url,
                },
                {
                    "name": "user",
                    "driver": "existing-session",
                    "cdp_url": fake_cdp_server.base_url,
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
            "crxzipple.app.assembly.browser.CdpControlEngine",
            _fake_cdp_control_engine,
        ):
            client = TestClient(
                create_app(
                    settings=settings,
                    database_url=harness.database_url,
                )
            )

        try:
            _mark_browser_profiles_ready(
                client,
                "crxzipple",
                "user",
                endpoint=fake_cdp_server.base_url,
            )
            list_response = client.get("/tools")

            self.assertEqual(list_response.status_code, 200)
            tool_ids = [item["id"] for item in list_response.json()]
            self.assertIn("browser.navigate", tool_ids)
            self.assertIn("browser.observe", tool_ids)
            self.assertIn("browser.action.trace", tool_ids)
            self.assertIn("browser.snapshot", tool_ids)
            self.assertIn("browser.click", tool_ids)
            self.assertIn("browser.code.search", tool_ids)
            self.assertIn("browser.runtime.inspect", tool_ids)
            self.assertIn("browser.script.list", tool_ids)
            self.assertIn("browser.script.find_request", tool_ids)
            self.assertIn("browser.script.inspect", tool_ids)
            self.assertIn("browser.network.inspect", tool_ids)
            self.assertNotIn("browser_profile", tool_ids)
            self.assertNotIn("browser_control", tool_ids)
            self.assertNotIn("browser_snapshot", tool_ids)
            self.assertNotIn("browser_action", tool_ids)

            run_response = client.post(
                "/tools/browser.navigate/runs",
                json={
                    "arguments": {
                        "url": "https://example.com",
                    },
                },
            )

            self.assertEqual(run_response.status_code, 201)
            payload = run_response.json()
            target_id = payload["output_payload"]["target_id"]
            self.assertEqual(payload["tool_id"], "browser.navigate")
            self.assertEqual(payload["status"], "succeeded")
            self.assertEqual(
                payload["result"]["metadata"]["profile_name"],
                "crxzipple",
            )
            self.assertEqual(
                payload["result"]["metadata"]["profile_source"],
                "browser.default_profile",
            )
            self.assertEqual(
                payload["result"]["metadata"]["browser_host_service_key"],
                "host:browser:crxzipple",
            )
            self.assertEqual(
                payload["result"]["metadata"]["browser_target_id"],
                target_id,
            )
            self.assertEqual(payload["output_payload"]["command"]["kind"], "navigate")
            self.assertEqual(
                payload["output_payload"]["command"]["payload"]["url"],
                "https://example.com",
            )
            self.assertEqual(
                payload["output_payload"]["value"]["ws_url"],
                f"{fake_cdp_server.base_url.replace('http://', 'ws://')}/devtools/page/{target_id}",
            )
            self.assertEqual(
                payload["output_payload"]["value"]["json_endpoints"],
                {
                    "version": f"{fake_cdp_server.base_url}/json/version",
                    "list": f"{fake_cdp_server.base_url}/json/list",
                    "new": f"{fake_cdp_server.base_url}/json/new",
                    "activate": f"{fake_cdp_server.base_url}/json/activate/{target_id}",
                    "close": f"{fake_cdp_server.base_url}/json/close/{target_id}",
                },
            )

            explicit_profile_response = client.post(
                "/tools/browser.navigate/runs",
                json={
                    "arguments": {
                        "profile": "user",
                        "url": "https://example.com/profile",
                    },
                },
            )

            self.assertEqual(explicit_profile_response.status_code, 201)
            explicit_payload = explicit_profile_response.json()
            self.assertEqual(
                explicit_payload["output_payload"]["command"]["profile_name"],
                "user",
            )
            self.assertEqual(
                explicit_payload["result"]["metadata"]["profile_source"],
                "input.profile",
            )
            self.assertEqual(
                explicit_payload["result"]["metadata"]["browser_host_service_key"],
                "host:browser:user",
            )
            self.assertEqual(
                explicit_payload["result"]["metadata"]["browser_target_id"],
                explicit_payload["output_payload"]["target_id"],
            )
        finally:
            client.close()
            client.app.state.container.require(AppKey.DATABASE_ENGINE).dispose()
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
        os.environ["APP_BROWSER_PROFILE_SPECS"] = json.dumps(
            [
                {
                    "name": "crxzipple",
                    "cdp_url": fake_cdp_server.base_url,
                },
                {
                    "name": "user",
                    "driver": "existing-session",
                    "cdp_url": fake_cdp_server.base_url,
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
            "crxzipple.app.assembly.browser.PlaywrightCdpSessionPool",
            FakePlaywrightCdpSessionPool,
        ), patch(
            "crxzipple.app.assembly.browser.CdpControlEngine",
            _fake_cdp_control_engine,
        ):
            client = TestClient(
                create_app(
                    settings=settings,
                    database_url=harness.database_url,
                ),
            )

        try:
            _mark_browser_profiles_ready(
                client,
                "crxzipple",
                "user",
                endpoint=fake_cdp_server.base_url,
            )
            open_response = client.post(
                "/tools/browser.navigate/runs",
                json={
                    "arguments": {
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
                "/tools/browser.snapshot/runs",
                json={
                    "arguments": {
                        "target_id": target_id,
                        "format": "interactive",
                    },
                },
            )

            self.assertEqual(snapshot_response.status_code, 201)
            snapshot_payload = snapshot_response.json()
            output_payload = snapshot_payload["output_payload"]
            self.assertEqual(output_payload["value"]["result"]["value"]["refs"][0]["frame_path"], [0])
            self.assertEqual(
                snapshot_payload["result"]["metadata"]["profile_name"],
                "crxzipple",
            )
            self.assertEqual(
                snapshot_payload["result"]["metadata"]["profile_source"],
                "browser.default_profile",
            )
            self.assertEqual(
                snapshot_payload["result"]["metadata"]["browser_target_id"],
                target_id,
            )
        finally:
            client.close()
            client.app.state.container.require(AppKey.DATABASE_ENGINE).dispose()
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
        os.environ["APP_BROWSER_PROFILE_SPECS"] = json.dumps(
            [
                {
                    "name": "crxzipple",
                    "cdp_url": fake_cdp_server.base_url,
                },
                {
                    "name": "user",
                    "driver": "existing-session",
                    "cdp_url": fake_cdp_server.base_url,
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
            "crxzipple.app.assembly.browser.CdpControlEngine",
            _fake_cdp_control_engine,
        ):
            client = TestClient(
                create_app(
                    settings=settings,
                    database_url=harness.database_url,
                )
            )

        try:
            _mark_browser_profiles_ready(
                client,
                "crxzipple",
                "user",
                endpoint=fake_cdp_server.base_url,
            )
            container = client.app.state.container
            system_path = (
                container.require(AppKey.BROWSER_INFRASTRUCTURE).state_root.config_dir
                / "system.json"
            )
            payload = json.loads(system_path.read_text(encoding="utf-8"))
            payload["default_profile"] = "user"
            system_path.write_text(
                json.dumps(payload, indent=2, sort_keys=True),
                encoding="utf-8",
            )

            run_response = client.post(
                "/tools/browser.navigate/runs",
                json={
                    "arguments": {
                        "url": "https://example.com",
                    },
                },
            )

            self.assertEqual(run_response.status_code, 201)
            payload = run_response.json()
            output_payload = payload["output_payload"]
            self.assertEqual(output_payload["command"]["profile_name"], "user")
            self.assertEqual(payload["result"]["metadata"]["profile_name"], "user")
            self.assertEqual(
                payload["result"]["metadata"]["profile_source"],
                "browser.default_profile",
            )
        finally:
            client.close()
            client.app.state.container.require(AppKey.DATABASE_ENGINE).dispose()
            harness.close()
            fake_cdp_server.close()
            if previous_specs is None:
                os.environ.pop("APP_BROWSER_PROFILE_SPECS", None)
            else:
                os.environ["APP_BROWSER_PROFILE_SPECS"] = previous_specs
