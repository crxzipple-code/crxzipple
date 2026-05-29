from __future__ import annotations

import unittest

from crxzipple.modules.daemon.domain import (
    DaemonInstance,
    DaemonLease,
    DaemonServiceSpec,
    DaemonValidationError,
)


class DaemonDomainTestCase(unittest.TestCase):
    def test_service_spec_validates_singleton_replicas(self) -> None:
        with self.assertRaises(DaemonValidationError):
            DaemonServiceSpec(
                key="worker:orchestration",
                role="worker",
                managed_by="internal",
                transport="process",
                replica_mode="singleton",
                desired_replicas=2,
            )

    def test_instance_create_and_mark_ready(self) -> None:
        instance = DaemonInstance.create(
            service_key="worker:tool",
            worker_id="tool-worker-1",
        )

        instance.mark_ready(pid=4242, endpoint="stdio://tool-worker")

        self.assertEqual(instance.status, "ready")
        self.assertEqual(instance.pid, 4242)
        self.assertEqual(instance.endpoint, "stdio://tool-worker")
        self.assertIsNotNone(instance.started_at)
        self.assertIsNotNone(instance.last_healthcheck_at)

    def test_lease_lifecycle(self) -> None:
        lease = DaemonLease.create(
            service_key="host:browser:user",
            instance_id="instance-1",
            owner_kind="tool_run",
            owner_id="run-1",
            ttl_seconds=30,
        )

        self.assertEqual(lease.status, "active")
        self.assertIsNotNone(lease.expires_at)

        lease.heartbeat(ttl_seconds=60)
        self.assertEqual(lease.status, "active")
        self.assertIsNotNone(lease.heartbeat_at)

        lease.release()
        self.assertEqual(lease.status, "released")


if __name__ == "__main__":
    unittest.main()
