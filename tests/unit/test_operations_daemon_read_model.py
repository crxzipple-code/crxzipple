from __future__ import annotations

from datetime import datetime, timezone
from unittest import TestCase

from crxzipple.modules.daemon import DaemonInstance, DaemonServiceSpec
from crxzipple.modules.operations.application.read_models.daemon import (
    DaemonOperationsQuery,
    DaemonOperationsReadModelProvider,
)


class _DaemonService:
    def __init__(self, specs: tuple[DaemonServiceSpec, ...]) -> None:
        self._specs = specs

    def list_service_specs(self) -> tuple[DaemonServiceSpec, ...]:
        return self._specs

    def list_service_sets(self) -> tuple[object, ...]:
        return ()

    def list_leases(self) -> tuple[object, ...]:
        return ()


class _DaemonManager:
    def __init__(self, instances: tuple[DaemonInstance, ...]) -> None:
        self._instances = instances
        self.refresh_values: list[bool] = []

    def list_instances(
        self,
        *,
        service_key: str | None = None,
        refresh: bool = True,
    ) -> tuple[DaemonInstance, ...]:
        self.refresh_values.append(refresh)
        if service_key is None:
            return self._instances
        return tuple(item for item in self._instances if item.service_key == service_key)


class OperationsDaemonReadModelTestCase(TestCase):
    def test_browser_host_instances_expose_runtime_semantics(self) -> None:
        timestamp = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)
        host_spec = DaemonServiceSpec(
            key="host:browser:crxzipple",
            display_name="Managed Browser (crxzipple)",
            service_group="browser",
            role="host",
            managed_by="internal",
            transport="process",
            start_policy="ensure",
            restart_policy="on-failure",
            healthcheck_policy="cdp-version",
            match_policy="cdp-port",
            metadata={
                "profile_name": "crxzipple",
                "server_url": "http://127.0.0.1:9222",
                "cdp_port": 9222,
            },
        )
        host_instance = DaemonInstance(
            id="daemon-host-browser-crxzipple",
            service_key="host:browser:crxzipple",
            status="ready",
            worker_id="browser-host-crxzipple",
            pid=5111,
            endpoint="http://127.0.0.1:9222",
            started_at=timestamp,
            last_healthcheck_at=timestamp,
            metadata={
                "profile_name": "crxzipple",
                "mode": "managed-cdp",
                "server_url": "http://127.0.0.1:9222",
                "cdp_port": 9222,
                "browser_pid": 6222,
                "adopted": True,
                "manifest_status": "active",
                "launch_fingerprint": "sha256:abcdef0123456789",
                "user_data_dir": "/tmp/crxzipple-browser-profile",
                "profile_directory": "Default",
                "proxy_mode": "none",
            },
        )
        daemon_manager = _DaemonManager((host_instance,))
        provider = DaemonOperationsReadModelProvider(
            daemon_service=_DaemonService((host_spec,)),
            daemon_manager=daemon_manager,
        )

        page = provider.page(DaemonOperationsQuery(service_group="browser"))

        self.assertEqual(daemon_manager.refresh_values, [False])
        column_keys = [column.key for column in page.instances.columns]
        self.assertIn("runtime", column_keys)
        rows = {row.id: row for row in page.instances.rows}
        self.assertEqual(
            rows["daemon-host-browser-crxzipple"].cells["runtime"],
            "Browser Host · Active",
        )
        details = {item.instance_id: item for item in page.instance_details}
        host_summary = {
            item.label: (item.value, item.tone)
            for item in details["daemon-host-browser-crxzipple"].summary
        }
        self.assertEqual(host_summary["Runtime Kind"][0], "Browser Host")
        self.assertEqual(host_summary["Host Runner PID"][0], "5111")
        self.assertEqual(host_summary["Browser PID"][0], "6222")
        self.assertEqual(host_summary["Manifest"], ("Active", "success"))
        self.assertEqual(host_summary["CDP Endpoint"][0], "http://127.0.0.1:9222")
        self.assertEqual(host_summary["Profile Directory"][0], "Default")
