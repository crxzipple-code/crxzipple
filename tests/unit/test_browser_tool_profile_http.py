from __future__ import annotations

from dataclasses import replace
import json as _json
import os
from pathlib import Path
import unittest

from fastapi.testclient import TestClient

from crxzipple.core.config import load_settings
from crxzipple.interfaces.http.app import create_app
from crxzipple.interfaces.runtime_container import AppKey
from crxzipple.modules.daemon import DaemonInstance
from tests.unit.support import FakeCdpServer, SqliteTestHarness


def _mark_browser_profile_ready(client: TestClient, profile_name: str, *, endpoint: str) -> None:
    daemon_service = client.app.state.container.require(AppKey.DAEMON_SERVICE)
    instance = DaemonInstance.create(
        service_key=f"host:browser:{profile_name}",
        endpoint=endpoint,
        metadata={"profile_name": profile_name},
    )
    instance.mark_ready(endpoint=endpoint)
    daemon_service.save_instance(instance)


class BrowserToolProfileHttpTestCase(unittest.TestCase):
    def test_browser_tool_profile_context_uses_configured_browser_endpoint(self) -> None:
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
            create_app(settings=settings, database_url=harness.database_url),
        )

        try:
            _mark_browser_profile_ready(
                client,
                "crxzipple",
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

            container = client.app.state.container
            browser_infrastructure = container.require(AppKey.BROWSER_INFRASTRUCTURE)
            runtime_path = browser_infrastructure.state_root.runtime_dir / "crxzipple.json"
            self.assertTrue(runtime_path.exists())
            self.assertEqual(open_response.json()["tool_id"], "browser.navigate")
            self.assertEqual(
                open_response.json()["output_payload"]["command"]["profile_name"],
                "crxzipple",
            )

            legacy_response = client.post(
                "/tools/browser_control/runs",
                json={"arguments": {"kind": "reset"}},
            )

            self.assertEqual(legacy_response.status_code, 404)
        finally:
            client.close()
            client.app.state.container.require(AppKey.DATABASE_ENGINE).dispose()
            harness.close()
            fake_cdp_server.close()
            if previous_specs is None:
                os.environ.pop("APP_BROWSER_PROFILE_SPECS", None)
            else:
                os.environ["APP_BROWSER_PROFILE_SPECS"] = previous_specs
