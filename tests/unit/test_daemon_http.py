from __future__ import annotations

from types import SimpleNamespace

from tests.unit.http_test_support import *


class DaemonHttpTestCase(HttpModuleTestCase):
    def test_daemon_leases_endpoint_lists_and_filters_status(self) -> None:
        container = self.client.app.state.container

        with patch.object(
            type(container.daemon_service),
            "list_leases",
            autospec=True,
            return_value=(
                SimpleNamespace(
                    id="lease-1",
                    service_key="host:browser:crxzipple",
                    instance_id="inst-1",
                    owner_kind="browser_profile",
                    owner_id="crxzipple",
                    status="active",
                    acquired_at=datetime.now(timezone.utc),
                    heartbeat_at=None,
                    expires_at=None,
                    metadata={},
                ),
                SimpleNamespace(
                    id="lease-2",
                    service_key="host:browser:crxzipple",
                    instance_id="inst-1",
                    owner_kind="browser_profile",
                    owner_id="crxzipple",
                    status="released",
                    acquired_at=datetime.now(timezone.utc),
                    heartbeat_at=None,
                    expires_at=None,
                    metadata={},
                ),
            ),
        ):
            response = self.client.get(
                "/daemon/leases",
                params={"service_key": "host:browser:crxzipple", "status": "active"},
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload), 1)
        self.assertEqual(payload[0]["id"], "lease-1")
        self.assertEqual(payload[0]["status"], "active")

    def test_daemon_service_detail_endpoint_returns_summary(self) -> None:
        container = self.client.app.state.container

        with patch.object(
            type(container.daemon_service),
            "get_service_spec",
            autospec=True,
            return_value=SimpleNamespace(
                key="host:browser:crxzipple",
                display_name="Managed Browser",
                service_group="browser",
                role="host",
                managed_by="internal",
                transport="process",
                replica_mode="singleton",
                desired_replicas=1,
                start_policy="ensure",
                restart_policy="on-failure",
                healthcheck_policy="cdp-version",
                match_policy="cdp-port",
                metadata={"cdp_port": 18800},
            ),
        ), patch.object(
            type(container.daemon_manager),
            "list_instances",
            autospec=True,
            return_value=(
                SimpleNamespace(
                    id="inst-1",
                    service_key="host:browser:crxzipple",
                    status="failed",
                    worker_id=None,
                    pid=1234,
                    endpoint="http://127.0.0.1:18800",
                    started_at=None,
                    last_healthcheck_at=datetime.now(timezone.utc),
                    last_error="cdp unavailable",
                    metadata={
                        "browser_pid": 1234,
                        "env_drift_detected": True,
                        "env_fingerprint": "fingerprint-a",
                        "expected_env_fingerprint": "fingerprint-b",
                        "actual_env_fingerprint": None,
                        "env_keys": ["PYTHONPATH", "APP_EVENTS_BACKEND"],
                    },
                ),
            ),
        ), patch.object(
            type(container.daemon_service),
            "list_leases",
            autospec=True,
            return_value=(
                SimpleNamespace(
                    id="lease-1",
                    service_key="host:browser:crxzipple",
                    instance_id="inst-1",
                    owner_kind="browser_profile",
                    owner_id="crxzipple",
                    status="active",
                    acquired_at=datetime.now(timezone.utc),
                    heartbeat_at=None,
                    expires_at=None,
                    metadata={},
                ),
            ),
        ):
            response = self.client.get("/daemon/services/host:browser:crxzipple")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["service"]["key"], "host:browser:crxzipple")
        self.assertEqual(payload["summary"]["availability"], "leased")
        self.assertEqual(payload["summary"]["lease_counts"], {"active": 1})
        self.assertEqual(payload["summary"]["recent_errors"][0]["last_error"], "cdp unavailable")
        self.assertEqual(payload["summary"]["env_drift_instance_count"], 1)
        self.assertEqual(payload["summary"]["environment_consistency"], "consistent")
        self.assertEqual(payload["summary"]["env_fingerprints"], ["fingerprint-a"])
        self.assertEqual(payload["summary"]["drifted_instances"][0]["instance_id"], "inst-1")
        self.assertEqual(payload["instances"][0]["env_drift_detected"], True)
        self.assertEqual(payload["instances"][0]["env_fingerprint"], "fingerprint-a")
        self.assertEqual(payload["instances"][0]["expected_env_fingerprint"], "fingerprint-b")

    def test_daemon_service_sets_endpoint_lists_predefined_sets(self) -> None:
        container = self.client.app.state.container

        with patch.object(
            type(container.daemon_service),
            "list_service_sets",
            autospec=True,
            return_value=(
                SimpleNamespace(
                    key="workers",
                    display_name="Workers",
                    description="All internal worker daemons.",
                    service_keys=(),
                    service_roles=("worker",),
                    service_groups=(),
                ),
            ),
        ):
            response = self.client.get("/daemon/service-sets")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["key"], "workers")
        self.assertEqual(payload[0]["service_roles"], ["worker"])

    def test_daemon_services_endpoint_lists_specs(self) -> None:
        container = self.client.app.state.container

        with patch.object(
            type(container.daemon_service),
            "list_service_specs",
            autospec=True,
            return_value=(
                SimpleNamespace(
                    key="worker:orchestration",
                    display_name="Orchestration Executor",
                    service_group="core",
                    role="worker",
                    managed_by="internal",
                    transport="process",
                    replica_mode="replicated",
                    desired_replicas=1,
                    start_policy="eager",
                    restart_policy="on-failure",
                    healthcheck_policy=None,
                    match_policy=None,
                    metadata={"cli_args": ["orchestration-executor", "run-executor"]},
                ),
            ),
        ):
            response = self.client.get("/daemon/services")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["key"], "worker:orchestration")
        self.assertEqual(payload[0]["service_group"], "core")

    def test_daemon_ensure_endpoint_uses_manager(self) -> None:
        container = self.client.app.state.container

        with patch.object(
            type(container.daemon_manager),
            "ensure_service",
            autospec=True,
            return_value=(
                SimpleNamespace(
                    id="inst-1",
                    service_key="worker:tool",
                    status="ready",
                    worker_id="worker-tool-1",
                    pid=2222,
                    endpoint=None,
                    started_at=None,
                    last_healthcheck_at=None,
                    last_error=None,
                    metadata={
                        "process_id": "proc-1",
                        "env_fingerprint": "fingerprint-a",
                        "env_keys": ["PYTHONPATH"],
                    },
                ),
            ),
        ) as mocked:
            response = self.client.post("/daemon/services/worker:tool/ensure")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["service_key"], "worker:tool")
        self.assertEqual(payload[0]["env_fingerprint"], "fingerprint-a")
        self.assertEqual(mocked.call_args.args[1], "worker:tool")

    def test_daemon_healthcheck_endpoint_uses_manager(self) -> None:
        container = self.client.app.state.container

        with patch.object(
            type(container.daemon_manager),
            "healthcheck_service",
            autospec=True,
            return_value=(
                SimpleNamespace(
                    id="inst-1",
                    service_key="worker:tool",
                    status="ready",
                    worker_id="worker-tool-1",
                    pid=2222,
                    endpoint=None,
                    started_at=None,
                    last_healthcheck_at=None,
                    last_error=None,
                    metadata={"process_id": "proc-1"},
                ),
            ),
        ) as mocked:
            response = self.client.post("/daemon/services/worker:tool/healthcheck")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["service_key"], "worker:tool")
        self.assertEqual(mocked.call_args.args[1], "worker:tool")

    def test_daemon_reconcile_endpoint_uses_manager(self) -> None:
        container = self.client.app.state.container

        with patch.object(
            type(container.daemon_manager),
            "reconcile_service",
            autospec=True,
            return_value=(
                SimpleNamespace(
                    id="inst-1",
                    service_key="worker:tool",
                    status="ready",
                    worker_id="worker-tool-1",
                    pid=2222,
                    endpoint=None,
                    started_at=None,
                    last_healthcheck_at=None,
                    last_error=None,
                    metadata={"process_id": "proc-1"},
                ),
            ),
        ) as mocked:
            response = self.client.post("/daemon/services/worker:tool/reconcile")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload[0]["service_key"], "worker:tool")
        self.assertEqual(mocked.call_args.args[1], "worker:tool")
