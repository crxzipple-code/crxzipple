from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import unittest
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


class BrowserProfilePoolE2ETestCase(unittest.TestCase):
    def setUp(self) -> None:
        self._previous_browser_profile_specs = os.environ.get("APP_BROWSER_PROFILE_SPECS")
        self._fake_cdp_server = FakeCdpServer()
        self._fake_cdp_server.start()
        os.environ["APP_BROWSER_PROFILE_SPECS"] = json.dumps(
            [
                {
                    "name": "crxzipple",
                    "cdp_url": self._fake_cdp_server.base_url,
                },
            ],
        )
        self._harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            database_url=self._harness.database_url,
            authorization_enabled=False,
            browser_state_dir=str(Path(self._harness._tempdir.name) / "browser"),
            events_backend="file",
            events_state_dir=str(Path(self._harness._tempdir.name) / "events"),
            operations_state_dir=str(Path(self._harness._tempdir.name) / "operations"),
        )
        self._settings = settings
        self._harness.initialize_schema(settings=settings)
        self._playwright_pool_patcher = patch(
            "crxzipple.app.assembly.browser.PlaywrightCdpSessionPool",
            FakePlaywrightCdpSessionPool,
        )
        self._playwright_pool_patcher.start()
        self._client_context = TestClient(
            create_app(
                settings=settings,
                database_url=self._harness.database_url,
            ),
        )
        self.client = self._client_context.__enter__()

    def tearDown(self) -> None:
        self._client_context.__exit__(None, None, None)
        self._playwright_pool_patcher.stop()
        self._harness.close()
        self._fake_cdp_server.close()
        if self._previous_browser_profile_specs is None:
            os.environ.pop("APP_BROWSER_PROFILE_SPECS", None)
        else:
            os.environ["APP_BROWSER_PROFILE_SPECS"] = (
                self._previous_browser_profile_specs
            )

    def test_pool_allocations_are_visible_in_operations_projection(self) -> None:
        secret_marker = "super-secret-proxy-password"
        for index, profile_name in enumerate(("crawler-a", "crawler-b", "crawler-c"), start=1):
            create_response = self.client.post(
                "/browser/profiles",
                json={
                    "name": profile_name,
                    "driver": "managed",
                    "cdp_url": self._fake_cdp_server.base_url,
                    "proxy_mode": "static",
                    "proxy_server": f"http://proxy-{index}.local:8080",
                },
            )
            self.assertEqual(create_response.status_code, 200)

        self._mark_profiles_ready("crawler-a", "crawler-b", "crawler-c")

        pool_response = self.client.post(
            "/browser/pools",
            json={
                "pool_id": "ctrip-collectors",
                "profile_names": ["crawler-a", "crawler-b", "crawler-c"],
                "target_hosts": ["flights.ctrip.com"],
                "selection_strategy": "least_busy",
                "max_concurrency_per_profile": 1,
                "max_concurrency_total": 3,
                "allocation_ttl_seconds": 600,
                "metadata": {"internal_secret": secret_marker},
            },
        )
        self.assertEqual(pool_response.status_code, 200)

        navigate_payloads: list[dict[str, object]] = []
        for index in range(3):
            response = self.client.post(
                "/tools/browser.navigate/runs",
                json={
                    "run_id": f"browser-pool-nav-{index + 1}",
                    "arguments": {
                        "url": "https://flights.ctrip.com/online/channel/domestic",
                        "profile_pool": "ctrip-collectors",
                    },
                },
            )
            self.assertEqual(response.status_code, 201)
            payload = response.json()
            self.assertEqual(payload["status"], "succeeded", payload)
            navigate_payloads.append(payload)

        allocated_profiles = {
            str(payload["result"]["metadata"]["profile_name"])
            for payload in navigate_payloads
        }
        self.assertEqual(allocated_profiles, {"crawler-a", "crawler-b", "crawler-c"})
        allocation_ids = {
            str(payload["result"]["metadata"]["browser_allocation_id"])
            for payload in navigate_payloads
        }
        self.assertEqual(len(allocation_ids), 3)

        first_navigation = navigate_payloads[0]
        first_target_id = str(first_navigation["output_payload"]["target_id"])
        first_profile = str(first_navigation["result"]["metadata"]["profile_name"])
        self._seed_interactive_snapshot_page(first_target_id)
        snapshot_response = self.client.post(
            "/tools/browser.snapshot/runs",
            json={
                "run_id": "browser-pool-snapshot-1",
                "arguments": {
                    "target_id": first_target_id,
                    "profile": first_profile,
                    "format": "interactive",
                },
            },
        )
        self.assertEqual(snapshot_response.status_code, 201)
        self.assertEqual(snapshot_response.json()["status"], "succeeded")

        self._materialize_operations("browser", "tool")

        browser_response = self.client.get("/operations/browser")
        self.assertEqual(browser_response.status_code, 200)
        browser_payload = browser_response.json()
        pool_row = next(
            row
            for row in browser_payload["profile_pools"]["rows"]
            if row["cells"]["pool"] == "ctrip-collectors"
        )
        self.assertEqual(pool_row["cells"]["active_allocations"], "3")
        self.assertEqual(pool_row["cells"]["ready_profiles"], "3")
        allocation_rows = browser_payload["profile_allocations"]["rows"]
        pool_allocation_rows = [
            row
            for row in allocation_rows
            if row["cells"]["pool"] == "ctrip-collectors"
        ]
        self.assertEqual(len(pool_allocation_rows), 3)
        self.assertEqual(
            {row["cells"]["profile"] for row in pool_allocation_rows},
            {"crawler-a", "crawler-b", "crawler-c"},
        )
        self.assertNotIn(secret_marker, json.dumps(browser_payload))

        tool_response = self.client.get("/operations/tool")
        self.assertEqual(tool_response.status_code, 200)
        tool_payload = tool_response.json()
        browser_cells = [
            row["cells"]["browser"]
            for row in tool_payload["tool_runs"]["rows"]
            if row["cells"]["tool_id"] == "browser.navigate"
        ]
        self.assertTrue(any("pool:ctrip-collectors" in cell for cell in browser_cells))
        self.assertTrue(any("alloc:browser_" in cell for cell in browser_cells))
        self.assertNotIn(secret_marker, json.dumps(tool_payload))

        detail_response = self.client.get(
            "/operations/tool/runs/browser-pool-nav-1/detail",
        )
        self.assertEqual(detail_response.status_code, 200)
        detail_payload = detail_response.json()
        summary = {item["label"]: item["value"] for item in detail_payload["summary"]}
        self.assertEqual(summary["Browser Profile Pool"], "ctrip-collectors")
        self.assertIn("browser_alloc_", summary["Browser Allocation"])
        self.assertEqual(summary["Target Host"], "flights.ctrip.com")
        self.assertNotIn(secret_marker, json.dumps(detail_payload))

    def _mark_profiles_ready(self, *profile_names: str) -> None:
        daemon_service = self.client.app.state.container.require(AppKey.DAEMON_SERVICE)
        for profile_name in profile_names:
            instance = DaemonInstance.create(
                service_key=f"host:browser:{profile_name}",
                endpoint=self._fake_cdp_server.base_url,
                metadata={"profile_name": profile_name},
            )
            instance.mark_ready(endpoint=self._fake_cdp_server.base_url)
            daemon_service.save_instance(instance)

    def _materialize_operations(self, *modules: str) -> None:
        self.client.app.state.container.require(
            AppKey.OPERATIONS_PROJECTION_MATERIALIZER,
        ).materialize_modules(modules)

    @staticmethod
    def _seed_interactive_snapshot_page(target_id: str) -> None:
        pool = FakePlaywrightCdpSessionPool.last_created
        if pool is None:
            raise AssertionError("Fake Playwright pool was not created.")
        page = pool.resolve_page(profile=object(), target_id=target_id)
        page.main_frame.interactive_items = [
            {
                "selector": "#from-city",
                "label": "From city",
                "role": "textbox",
                "text": "昆明",
                "tag": "input",
            },
            {
                "selector": "#to-city",
                "label": "To city",
                "role": "textbox",
                "text": "上海",
                "tag": "input",
            },
        ]
