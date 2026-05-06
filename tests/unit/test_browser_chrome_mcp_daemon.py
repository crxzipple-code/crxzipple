from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from crxzipple.modules.browser.domain import BrowserProfileConfig, BrowserSystemConfig, BrowserValidationError
from crxzipple.modules.browser.infrastructure.chrome_mcp import ChromeMcpClientPool
from crxzipple.modules.daemon import (
    DaemonInstance,
    DaemonApplicationService,
    DaemonServiceSpec,
    FileBackedDaemonInstanceStore,
    FileBackedDaemonLeaseEventLog,
    FileBackedDaemonLeaseStore,
    FileBackedDaemonServiceSpecStore,
    bootstrap_daemon_state_root,
)


class _SuccessfulClient:
    def __init__(self) -> None:
        self.command = ("npx", "-y", "chrome-devtools-mcp@latest")
        self.pid = 4567

    def call_tool(self, *, tool_name: str, arguments: dict[str, object]):  # noqa: ANN201
        del arguments
        if tool_name == "list_pages":
            return {
                "structuredContent": {
                    "pages": [
                        {
                            "id": 1,
                            "url": "https://mail.google.com",
                            "selected": True,
                        },
                    ],
                },
            }
        raise AssertionError(f"unexpected tool: {tool_name}")

    def close(self) -> None:
        return None


class _FailingClient(_SuccessfulClient):
    def call_tool(self, *, tool_name: str, arguments: dict[str, object]):  # noqa: ANN201
        del tool_name, arguments
        raise BrowserValidationError("chrome mcp attach failed")


class ChromeMcpDaemonIntegrationTestCase(unittest.TestCase):
    def _build_daemon_service(self, root_dir: Path) -> DaemonApplicationService:
        state_root = bootstrap_daemon_state_root(str(root_dir))
        spec_store = FileBackedDaemonServiceSpecStore(
            state_root.config_dir,
            bootstrap_specs=(
                DaemonServiceSpec(
                    key="capability:chrome-mcp:user",
                    role="capability",
                    managed_by="internal",
                    transport="process",
                    start_policy="lazy",
                    restart_policy="on-failure",
                ),
            ),
        )
        return DaemonApplicationService(
            service_spec_store=spec_store,
            instance_store=FileBackedDaemonInstanceStore(state_root.instances_dir),
            lease_store=FileBackedDaemonLeaseStore(state_root.leases_dir),
            lease_event_log=FileBackedDaemonLeaseEventLog(state_root.leases_dir),
        )

    def _system(self) -> BrowserSystemConfig:
        return BrowserSystemConfig(
            default_profile="user",
            profiles=(BrowserProfileConfig(name="user", driver="existing-session"),),
        )

    def test_list_tabs_marks_daemon_instance_ready_and_close_marks_stopped(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            daemon_service = self._build_daemon_service(Path(temp_dir))
            pool = ChromeMcpClientPool(
                client_factory=lambda *_args: _SuccessfulClient(),
                daemon_service=daemon_service,
            )

            tabs = pool.list_tabs(profile_name="user", system=self._system())

            self.assertEqual(len(tabs), 1)
            instance = daemon_service.list_instances(service_key="capability:chrome-mcp:user")[0]
            self.assertEqual(instance.status, "ready")
            self.assertEqual(instance.pid, 4567)

            pool.close_profile(profile_name="user")

            instance = daemon_service.list_instances(service_key="capability:chrome-mcp:user")[0]
            self.assertEqual(instance.status, "stopped")
            leases = daemon_service.list_leases(service_key="capability:chrome-mcp:user")
            self.assertEqual(leases, ())

    def test_failed_call_marks_daemon_instance_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            daemon_service = self._build_daemon_service(Path(temp_dir))
            pool = ChromeMcpClientPool(
                client_factory=lambda *_args: _FailingClient(),
                daemon_service=daemon_service,
            )

            with self.assertRaises(BrowserValidationError):
                pool.list_tabs(profile_name="user", system=self._system())

            instance = daemon_service.list_instances(service_key="capability:chrome-mcp:user")[0]
            self.assertEqual(instance.status, "failed")
            self.assertIn("attach failed", instance.last_error or "")

    def test_ready_sync_reuses_existing_process_backed_instance(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            daemon_service = self._build_daemon_service(Path(temp_dir))
            existing = DaemonInstance.create(service_key="capability:chrome-mcp:user")
            existing.pid = 9999
            existing.metadata = {
                "process_id": "proc-1",
                "command": "python -m crxzipple.main browser mcp run --profile user",
            }
            existing.mark_ready(pid=9999)
            daemon_service.save_instance(existing)
            pool = ChromeMcpClientPool(
                client_factory=lambda *_args: _SuccessfulClient(),
                daemon_service=daemon_service,
            )

            tabs = pool.list_tabs(profile_name="user", system=self._system())

            self.assertEqual(len(tabs), 1)
            instances = daemon_service.list_instances(service_key="capability:chrome-mcp:user")
            self.assertEqual(len(instances), 1)
            instance = instances[0]
            self.assertEqual(instance.id, existing.id)
            self.assertEqual(instance.pid, 9999)
            self.assertEqual(instance.endpoint, "stdio")
            self.assertEqual(instance.metadata.get("chrome_mcp_pid"), 4567)


if __name__ == "__main__":
    unittest.main()
