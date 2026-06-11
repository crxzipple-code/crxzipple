from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from crxzipple.modules.browser.domain import (
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileCapabilities,
    BrowserProfileConfig,
    BrowserProfileRuntimeState,
    BrowserSystemConfig,
    BrowserTab,
    ResolvedBrowserProfile,
)
from crxzipple.modules.browser.infrastructure import (
    BrowserDiagnosticsService,
    BrowserPageNetworkFetchService,
    CdpBackedPlaywrightActionEngine,
    InMemoryBrowserRefStore,
)
from crxzipple.modules.daemon import (
    DaemonApplicationService,
    DaemonInstance,
    DaemonServiceSpec,
    FileBackedDaemonInstanceStore,
    FileBackedDaemonLeaseStore,
    FileBackedDaemonServiceSpecStore,
    bootstrap_daemon_state_root,
)
from tests.unit.support import FakePlaywrightCdpSessionPool


class BrowserPlaywrightActionEngineTestCase(unittest.TestCase):
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
        )

    def setUp(self) -> None:
        self._tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tempdir.cleanup)
        self.daemon_service = self._build_daemon_service(Path(self._tempdir.name))
        self.daemon_service.save_instance(
            DaemonInstance(
                id="browser-host-crxzipple",
                service_key="host:browser:crxzipple",
                status="ready",
                pid=8123,
                endpoint="http://127.0.0.1:9222",
            )
        )
        self.session_pool = FakePlaywrightCdpSessionPool()
        self.ref_store = InMemoryBrowserRefStore()
        self.emitted_browser_events: list[tuple[str, dict[str, object]]] = []
        self.engine = CdpBackedPlaywrightActionEngine(
            session_pool=self.session_pool,
            ref_store=self.ref_store,
            daemon_service=self.daemon_service,
            network_page_fetch_service=BrowserPageNetworkFetchService(
                event_emitter=lambda event_name, payload: self.emitted_browser_events.append(
                    (event_name, payload),
                ),
            ),
            diagnostics_service=BrowserDiagnosticsService(
                event_emitter=lambda event_name, payload: self.emitted_browser_events.append(
                    (event_name, payload),
                ),
            ),
        )
        self.profile = ResolvedBrowserProfile(
            name="crxzipple",
            driver="managed",
            cdp_url="http://127.0.0.1:9222",
            cdp_port=9222,
            user_data_dir=None,
            attach_only=False,
            is_loopback=True,
        )
        self.system = BrowserSystemConfig(
            default_profile="crxzipple",
            profiles=(BrowserProfileConfig(name="crxzipple"),),
        )
        self.capabilities = BrowserProfileCapabilities(
            mode="local-managed",
            is_remote=False,
            control_family="cdp-control",
            action_family="cdp-backed-playwright",
            can_launch=True,
            supports_reset=True,
            supports_per_tab_ws=True,
            supports_json_tab_endpoints=True,
            supports_managed_tab_limit=True,
        )
        self.runtime_state = BrowserProfileRuntimeState(profile_name="crxzipple")
        self.tab = BrowserTab(target_id="tab-1", url="https://example.com")

    def _plan(self, command: BrowserPageActionCommand) -> BrowserExecutionPlan:
        return BrowserExecutionPlan(
            command=command,
            system=self.system,
            profile=self.profile,
            capabilities=self.capabilities,
            control_family="cdp-control",
            action_family="cdp-backed-playwright",
            launch_policy="attach-only",
            tab_selection_policy="sticky-last-target",
        )
