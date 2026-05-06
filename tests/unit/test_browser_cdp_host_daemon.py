from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from crxzipple.modules.browser.application import (
    BrowserExecutionCoordinatorService,
    DefaultBrowserCapabilitiesResolver,
    DefaultBrowserControlCommandAssembler,
    DefaultBrowserExecutionPlanner,
    DefaultBrowserProfileResolver,
    DefaultBrowserProfileSelectionOpsFactory,
    DefaultBrowserProfileTabOpsFactory,
)
from crxzipple.modules.browser.domain import BrowserProfileConfig, BrowserSystemConfig
from crxzipple.modules.browser.infrastructure import (
    CdpControlEngine,
    InMemoryBrowserRefStore,
    InMemoryBrowserRuntimeStateStore,
    InMemoryBrowserSystemConfigStore,
    InMemoryCdpBackedPlaywrightActionEngine,
    InMemoryMcpActionEngine,
    InMemoryMcpControlEngine,
    StaticBrowserEngineRegistry,
)
from crxzipple.modules.daemon import (
    DaemonApplicationService,
    DaemonServiceSpec,
    FileBackedDaemonInstanceStore,
    FileBackedDaemonLeaseEventLog,
    FileBackedDaemonLeaseStore,
    FileBackedDaemonServiceSpecStore,
    bootstrap_daemon_state_root,
)
from tests.unit.support import FakeCdpServer


class BrowserCdpHostDaemonIntegrationTestCase(unittest.TestCase):
    def _build_daemon_service(self, root_dir: Path) -> DaemonApplicationService:
        state_root = bootstrap_daemon_state_root(str(root_dir))
        spec_store = FileBackedDaemonServiceSpecStore(
            state_root.config_dir,
            bootstrap_specs=(
                DaemonServiceSpec(
                    key="host:browser:crxzipple",
                    role="host",
                    managed_by="internal",
                    transport="process",
                    start_policy="ensure",
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

    def test_local_managed_open_tab_marks_host_daemon_ready_and_reset_marks_stopped(self) -> None:
        fake_cdp = FakeCdpServer()
        fake_cdp.start()
        try:
            with tempfile.TemporaryDirectory() as temp_dir:
                daemon_service = self._build_daemon_service(Path(temp_dir))
                system = BrowserSystemConfig(
                    default_profile="crxzipple",
                    profiles=(
                        BrowserProfileConfig(
                            name="crxzipple",
                            cdp_url=fake_cdp.base_url,
                        ),
                    ),
                    cdp_port_range_start=int(fake_cdp.base_url.rsplit(":", 1)[1]),
                    cdp_port_range_end=int(fake_cdp.base_url.rsplit(":", 1)[1]) + 8,
                )
                expected_user_data_dir = (
                    Path(temp_dir).resolve() / "crxzipple" / "userdata"
                )
                engine = CdpControlEngine(
                    profiles_root=Path(temp_dir),
                    ws_connect=fake_cdp.websocket_factory(),
                    list_processes=lambda: [
                        {
                            "pid": 8123,
                            "command": (
                                f"/Applications/Google Chrome "
                                f"--remote-debugging-port={int(fake_cdp.base_url.rsplit(':', 1)[1])} "
                                f"--user-data-dir={expected_user_data_dir} about:blank"
                            ),
                        },
                    ],
                    daemon_service=daemon_service,
                )
                coordinator = BrowserExecutionCoordinatorService(
                    system_config_store=InMemoryBrowserSystemConfigStore(system),
                    profile_resolver=DefaultBrowserProfileResolver(),
                    capabilities_resolver=DefaultBrowserCapabilitiesResolver(),
                    runtime_state_store=InMemoryBrowserRuntimeStateStore(),
                    ref_store=InMemoryBrowserRefStore(),
                    execution_planner=DefaultBrowserExecutionPlanner(),
                    engine_registry=StaticBrowserEngineRegistry(
                        cdp_control=engine,
                        mcp_control=InMemoryMcpControlEngine(),
                        cdp_backed_playwright=InMemoryCdpBackedPlaywrightActionEngine(),
                        mcp_backed=InMemoryMcpActionEngine(),
                    ),
                    tab_ops_factory=DefaultBrowserProfileTabOpsFactory(),
                    selection_ops_factory=DefaultBrowserProfileSelectionOpsFactory(),
                )
                control_assembler = DefaultBrowserControlCommandAssembler()

                open_result = coordinator.execute(
                    control_assembler.assemble(
                        profile_name="crxzipple",
                        kind="open-tab",
                        payload={"url": "https://example.com"},
                    )
                )

                self.assertTrue(open_result.ok)
                instance = daemon_service.list_instances(service_key="host:browser:crxzipple")[0]
                self.assertEqual(instance.status, "ready")
                self.assertEqual(instance.pid, 8123)
                self.assertEqual(instance.endpoint, fake_cdp.base_url)
                leases = daemon_service.list_leases(service_key="host:browser:crxzipple")
                self.assertEqual(leases, ())

                reset_result = coordinator.execute(
                    control_assembler.assemble(
                        profile_name="crxzipple",
                        kind="reset",
                    )
                )

                self.assertTrue(reset_result.ok)
                instance = daemon_service.list_instances(service_key="host:browser:crxzipple")[0]
                self.assertEqual(instance.status, "stopped")
        finally:
            fake_cdp.close()


if __name__ == "__main__":
    unittest.main()
