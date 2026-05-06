from __future__ import annotations

from pathlib import Path
import tempfile
import time
import unittest

from crxzipple.modules.browser.application import (
    BrowserExecutionCoordinatorService,
    DefaultBrowserCapabilitiesResolver,
    DefaultBrowserControlCommandAssembler,
    DefaultBrowserExecutionPlanner,
    DefaultBrowserPageActionAssembler,
    DefaultBrowserProfileResolver,
    DefaultBrowserProfileSelectionOpsFactory,
    DefaultBrowserProfileTabOpsFactory,
)
from crxzipple.modules.browser.domain import (
    BrowserControlCommand,
    BrowserExecutionPlan,
    BrowserProfileConfig,
    BrowserProfileCapabilities,
    BrowserProfileRuntimeState,
    BrowserStoredRef,
    BrowserSystemConfig,
    BrowserTab,
    ResolvedBrowserProfile,
)
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
    DaemonInstance,
    DaemonServiceSpec,
    FileBackedDaemonInstanceStore,
    FileBackedDaemonLeaseStore,
    FileBackedDaemonServiceSpecStore,
    bootstrap_daemon_state_root,
)
from tests.unit.support import FakeCdpServer


class BrowserCdpControlTestCase(unittest.TestCase):
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
        service = DaemonApplicationService(
            service_spec_store=spec_store,
            instance_store=FileBackedDaemonInstanceStore(state_root.instances_dir),
            lease_store=FileBackedDaemonLeaseStore(state_root.leases_dir),
        )
        service.save_instance(
            DaemonInstance(
                id="browser-host-crxzipple",
                service_key="host:browser:crxzipple",
                status="ready",
                pid=8123,
                endpoint=self.fake_cdp.base_url,
            )
        )
        return service

    def setUp(self) -> None:
        self.fake_cdp = FakeCdpServer()
        self.fake_cdp.start()
        self._tempdir = tempfile.TemporaryDirectory()
        self.daemon_service = self._build_daemon_service(Path(self._tempdir.name))
        self.system = BrowserSystemConfig(
            default_profile="crxzipple",
            profiles=(
                BrowserProfileConfig(
                    name="crxzipple",
                    cdp_url=self.fake_cdp.base_url,
                ),
            ),
        )
        self.runtime_state_store = InMemoryBrowserRuntimeStateStore()
        self.coordinator = BrowserExecutionCoordinatorService(
            system_config_store=InMemoryBrowserSystemConfigStore(self.system),
            profile_resolver=DefaultBrowserProfileResolver(),
            capabilities_resolver=DefaultBrowserCapabilitiesResolver(),
            runtime_state_store=self.runtime_state_store,
            ref_store=InMemoryBrowserRefStore(),
            execution_planner=DefaultBrowserExecutionPlanner(),
            engine_registry=StaticBrowserEngineRegistry(
                cdp_control=CdpControlEngine(
                    daemon_service=self.daemon_service,
                    ws_connect=self.fake_cdp.websocket_factory(),
                ),
                mcp_control=InMemoryMcpControlEngine(),
                cdp_backed_playwright=InMemoryCdpBackedPlaywrightActionEngine(),
                mcp_backed=InMemoryMcpActionEngine(),
            ),
            tab_ops_factory=DefaultBrowserProfileTabOpsFactory(),
            selection_ops_factory=DefaultBrowserProfileSelectionOpsFactory(),
        )
        self.control_assembler = DefaultBrowserControlCommandAssembler()
        self.page_action_assembler = DefaultBrowserPageActionAssembler()

    def tearDown(self) -> None:
        self.fake_cdp.close()
        self._tempdir.cleanup()

    def test_cdp_control_engine_open_list_focus_and_close_tabs(self) -> None:
        open_result = self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="crxzipple",
                kind="open-tab",
                payload={"url": "https://example.com"},
            )
        )
        self.assertTrue(open_result.ok)
        self.assertEqual(open_result.value.url, "https://example.com")
        self.assertEqual(
            open_result.value.ws_url,
            f"{self.fake_cdp.base_url.replace('http://', 'ws://')}/devtools/page/{open_result.target_id}",
        )
        self.assertEqual(
            open_result.value.json_endpoints,
            {
                "version": f"{self.fake_cdp.base_url}/json/version",
                "list": f"{self.fake_cdp.base_url}/json/list",
                "new": f"{self.fake_cdp.base_url}/json/new",
                "activate": f"{self.fake_cdp.base_url}/json/activate/{open_result.target_id}",
                "close": f"{self.fake_cdp.base_url}/json/close/{open_result.target_id}",
            },
        )

        list_result = self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="crxzipple",
                kind="list-tabs",
            )
        )
        self.assertEqual(len(list_result.value), 1)
        self.assertEqual(list_result.value[0].target_id, open_result.target_id)
        self.assertEqual(list_result.value[0].ws_url, open_result.value.ws_url)
        self.assertEqual(list_result.value[0].json_endpoints, open_result.value.json_endpoints)

        focus_result = self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="crxzipple",
                kind="focus-tab",
                target_id=open_result.target_id,
            )
        )
        self.assertTrue(focus_result.ok)
        self.assertEqual(focus_result.target_id, open_result.target_id)

        close_result = self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="crxzipple",
                kind="close-tab",
                target_id=open_result.target_id,
            )
        )
        self.assertTrue(close_result.ok)

        list_after_close = self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="crxzipple",
                kind="list-tabs",
            )
        )
        self.assertEqual(list_after_close.value, ())

    def test_cdp_control_engine_navigates_existing_tab_via_cdp_websocket(self) -> None:
        open_result = self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="crxzipple",
                kind="open-tab",
                payload={"url": "https://example.com/start"},
            )
        )

        navigate_result = self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="crxzipple",
                kind="navigate",
                target_id=open_result.target_id,
                payload={"url": "https://example.com/next"},
            )
        )

        self.assertTrue(navigate_result.ok)
        self.assertEqual(navigate_result.target_id, open_result.target_id)
        self.assertEqual(navigate_result.value.url, "https://example.com/next")

    def test_cdp_control_engine_open_tab_uses_live_tab_id_after_refresh(self) -> None:
        engine = CdpControlEngine(
            daemon_service=self.daemon_service,
            ws_connect=self.fake_cdp.websocket_factory(),
        )
        runtime_state = BrowserProfileRuntimeState(profile_name="crxzipple")
        command = BrowserControlCommand(
            profile_name="crxzipple",
            kind="open-tab",
            payload={"url": "https://mail.google.com"},
        )
        plan = BrowserExecutionPlan(
            command=command,
            system=self.system,
            profile=ResolvedBrowserProfile(
                name="crxzipple",
                driver="managed",
                cdp_url=self.fake_cdp.base_url,
                cdp_port=None,
                user_data_dir=None,
                attach_only=False,
                is_loopback=True,
            ),
            capabilities=BrowserProfileCapabilities(
                mode="local-managed",
                is_remote=False,
                control_family="cdp-control",
                action_family="cdp-backed-playwright",
                can_launch=True,
                supports_reset=True,
                supports_per_tab_ws=True,
                supports_json_tab_endpoints=True,
                supports_managed_tab_limit=True,
            ),
            control_family="cdp-control",
            action_family="cdp-backed-playwright",
            launch_policy="attach-only",
            tab_selection_policy="sticky-last-target",
        )
        stale_payload = {
            "id": "stale-tab",
            "type": "page",
            "title": "https://mail.google.com",
            "url": "https://mail.google.com",
            "webSocketDebuggerUrl": f"{self.fake_cdp.base_url.replace('http://', 'ws://')}/devtools/page/stale-tab",
        }
        live_tab = BrowserTab(
            target_id="live-tab",
            url="https://mail.google.com",
            title="https://mail.google.com",
            type="page",
            ws_url=f"{self.fake_cdp.base_url.replace('http://', 'ws://')}/devtools/page/live-tab",
            json_endpoints={
                "version": f"{self.fake_cdp.base_url}/json/version",
                "list": f"{self.fake_cdp.base_url}/json/list",
                "new": f"{self.fake_cdp.base_url}/json/new",
                "activate": f"{self.fake_cdp.base_url}/json/activate/live-tab",
                "close": f"{self.fake_cdp.base_url}/json/close/live-tab",
            },
        )

        object.__setattr__(
            engine,
            "_current_cdp_base_url",
            lambda *, plan, runtime_state: self.fake_cdp.base_url,
        )
        object.__setattr__(
            engine,
            "_request_cdp_json",
            lambda *, plan, runtime_state, path, methods=("put", "get"): (stale_payload, self.fake_cdp.base_url),
        )
        object.__setattr__(
            engine,
            "_list_tabs_unleased",
            lambda *, plan, runtime_state: (live_tab,),
        )

        tab = engine.open_tab(plan=plan, runtime_state=runtime_state, url="https://mail.google.com")

        self.assertEqual(tab.target_id, "live-tab")
        self.assertEqual(runtime_state.metadata.get("active_target_id"), "live-tab")

    def test_cdp_control_engine_open_tab_preserves_nested_query_string(self) -> None:
        open_result = self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="crxzipple",
                kind="open-tab",
                payload={"url": "https://www.google.com/search?q="},
            )
        )

        self.assertTrue(open_result.ok)
        self.assertEqual(open_result.value.url, "https://www.google.com/search?q=")

    def test_cdp_control_engine_marks_runtime_state_attached_with_live_browser_ref(self) -> None:
        self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="crxzipple",
                kind="open-tab",
                payload={"url": "https://example.com"},
            )
        )

        runtime_state = self.runtime_state_store.get(profile_name="crxzipple")
        self.assertIsNotNone(runtime_state)
        assert runtime_state is not None
        self.assertEqual(runtime_state.attachment_status, "attached")
        self.assertEqual(runtime_state.browser_ref, self.fake_cdp.browser_ws_url)

    def test_cdp_control_engine_skips_live_tab_refresh_when_cached_tabs_are_fresh(self) -> None:
        engine = CdpControlEngine(
            daemon_service=self.daemon_service,
            ws_connect=self.fake_cdp.websocket_factory(),
        )
        runtime_state = BrowserProfileRuntimeState(
            profile_name="crxzipple",
            attachment_status="attached",
            browser_ref=self.fake_cdp.browser_ws_url,
            running_pid=8123,
            metadata={
                "cdp_base_url": self.fake_cdp.base_url,
                "tabs": [
                    {
                        "target_id": "cached-tab",
                        "url": "https://example.com",
                        "title": "Cached",
                        "type": "page",
                    }
                ],
                "tabs_refreshed_at": time.time(),
            },
        )
        command = BrowserControlCommand(
            profile_name="crxzipple",
            kind="list-tabs",
            payload={},
        )
        plan = BrowserExecutionPlan(
            command=command,
            system=self.system,
            profile=ResolvedBrowserProfile(
                name="crxzipple",
                driver="managed",
                cdp_url=self.fake_cdp.base_url,
                cdp_port=None,
                user_data_dir=None,
                attach_only=False,
                is_loopback=True,
            ),
            capabilities=BrowserProfileCapabilities(
                mode="local-managed",
                is_remote=False,
                control_family="cdp-control",
                action_family="cdp-backed-playwright",
                can_launch=True,
                supports_reset=True,
                supports_per_tab_ws=True,
                supports_json_tab_endpoints=True,
                supports_managed_tab_limit=True,
            ),
            control_family="cdp-control",
            action_family="cdp-backed-playwright",
            launch_policy="attach-only",
            tab_selection_policy="sticky-last-target",
        )

        def _unexpected_list_tabs(*, plan, runtime_state):  # noqa: ANN001
            raise AssertionError("fresh cached tabs should avoid live list_tabs during ensure_attached")

        object.__setattr__(
            engine,
            "_find_matching_managed_process",
            lambda *, plan: {"pid": 8123, "headless": False},
        )
        object.__setattr__(
            engine,
            "_find_process_for_cdp_port",
            lambda *, plan: None,
        )
        object.__setattr__(engine, "list_tabs", _unexpected_list_tabs)

        updated = engine.ensure_attached(plan=plan, runtime_state=runtime_state)

        self.assertEqual(updated.metadata["tabs"][0]["target_id"], "cached-tab")
        self.assertEqual(updated.metadata["cdp_base_url"], self.fake_cdp.base_url)

    def test_cdp_control_engine_launches_local_managed_browser_when_missing(self) -> None:
        delayed_cdp = FakeCdpServer()
        tempdir = tempfile.TemporaryDirectory()

        class _FakeProcess:
            def __init__(self, pid: int) -> None:
                self.pid = pid
                self._returncode = None
                self.terminated = False

            def poll(self):
                return self._returncode

            def terminate(self) -> None:
                self.terminated = True
                self._returncode = 0

            def kill(self) -> None:
                self.terminated = True
                self._returncode = -9

            def wait(self, timeout=None) -> int:  # noqa: ANN001
                del timeout
                if self._returncode is None:
                    self._returncode = 0
                return self._returncode

        launches: list[list[str]] = []

        def _launch(command, **kwargs):  # noqa: ANN001
            del kwargs
            launches.append(list(command))
            delayed_cdp.start()
            return _FakeProcess(pid=4242)

        system = BrowserSystemConfig(
            default_profile="crxzipple",
            profiles=(
                BrowserProfileConfig(
                    name="crxzipple",
                    cdp_url=delayed_cdp.base_url,
                ),
            ),
            headless=True,
            cdp_port_range_start=18800,
            cdp_port_range_end=18832,
        )
        runtime_state_store = InMemoryBrowserRuntimeStateStore()
        engine = CdpControlEngine(
            daemon_service=self.daemon_service,
            profiles_root=Path(tempdir.name),
            ws_connect=delayed_cdp.websocket_factory(),
            popen=_launch,
            request_timeout_s=0.05,
            launch_timeout_s=1.0,
            launch_poll_interval_s=0.01,
        )
        coordinator = BrowserExecutionCoordinatorService(
            system_config_store=InMemoryBrowserSystemConfigStore(system),
            profile_resolver=DefaultBrowserProfileResolver(),
            capabilities_resolver=DefaultBrowserCapabilitiesResolver(),
            runtime_state_store=runtime_state_store,
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

        try:
            result = coordinator.execute(
                self.control_assembler.assemble(
                    profile_name="crxzipple",
                    kind="open-tab",
                    payload={"url": "https://example.com"},
                )
            )
            self.assertTrue(result.ok)
            self.assertEqual(len(launches), 1)
            self.assertIn("--headless=new", launches[0])
            cdp_port = int(result.target_id and runtime_state_store.get(profile_name="crxzipple").metadata["cdp_base_url"].rsplit(":", 1)[1])  # type: ignore[union-attr]
            self.assertIn(
                f"--remote-allow-origins=http://127.0.0.1:{cdp_port},http://localhost:{cdp_port},http://[::1]:{cdp_port}",
                launches[0],
            )
            self.assertIn(
                f"--user-data-dir={Path(tempdir.name).resolve() / 'crxzipple' / 'userdata'}",
                launches[0],
            )
            self.assertNotIn("about:blank", launches[0])

            runtime_state = runtime_state_store.get(profile_name="crxzipple")
            self.assertIsNotNone(runtime_state)
            assert runtime_state is not None
            self.assertEqual(runtime_state.running_pid, 4242)
            self.assertEqual(runtime_state.attachment_status, "attached")
        finally:
            engine.close()
            delayed_cdp.close()
            tempdir.cleanup()

    def test_cdp_control_engine_close_keeps_managed_browser_alive_without_host_ownership(self) -> None:
        delayed_cdp = FakeCdpServer()
        tempdir = tempfile.TemporaryDirectory()
        launched_processes: list[object] = []

        class _FakeProcess:
            def __init__(self, pid: int) -> None:
                self.pid = pid
                self._returncode = None
                self.terminated = False

            def poll(self):
                return self._returncode

            def terminate(self) -> None:
                self.terminated = True
                self._returncode = 0

            def kill(self) -> None:
                self.terminated = True
                self._returncode = -9

            def wait(self, timeout=None) -> int:  # noqa: ANN001
                del timeout
                if self._returncode is None:
                    self._returncode = 0
                return self._returncode

        def _launch(command, **kwargs):  # noqa: ANN001
            del command, kwargs
            delayed_cdp.start()
            process = _FakeProcess(pid=4333)
            launched_processes.append(process)
            return process

        system = BrowserSystemConfig(
            default_profile="crxzipple",
            profiles=(BrowserProfileConfig(name="crxzipple", cdp_url=delayed_cdp.base_url),),
            headless=False,
            cdp_port_range_start=18800,
            cdp_port_range_end=18832,
        )
        runtime_state_store = InMemoryBrowserRuntimeStateStore()
        engine = CdpControlEngine(
            daemon_service=self.daemon_service,
            profiles_root=Path(tempdir.name),
            ws_connect=delayed_cdp.websocket_factory(),
            popen=_launch,
            request_timeout_s=0.05,
            launch_timeout_s=1.0,
            launch_poll_interval_s=0.01,
        )
        coordinator = BrowserExecutionCoordinatorService(
            system_config_store=InMemoryBrowserSystemConfigStore(system),
            profile_resolver=DefaultBrowserProfileResolver(),
            capabilities_resolver=DefaultBrowserCapabilitiesResolver(),
            runtime_state_store=runtime_state_store,
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

        try:
            result = coordinator.execute(
                self.control_assembler.assemble(
                    profile_name="crxzipple",
                    kind="open-tab",
                    payload={"url": "https://example.com"},
                )
            )
            self.assertTrue(result.ok)
            self.assertEqual(len(launched_processes), 1)

            engine.close()

            self.assertFalse(launched_processes[0].terminated)
            instance = self.daemon_service.list_instances(service_key="host:browser:crxzipple")[0]
            self.assertEqual(instance.status, "ready")
            self.assertEqual(instance.pid, 4333)
        finally:
            delayed_cdp.close()
            tempdir.cleanup()

    def test_find_matching_managed_process_rejects_stale_remote_allow_origins_policy(self) -> None:
        tempdir = tempfile.TemporaryDirectory()
        try:
            system = BrowserSystemConfig(
                default_profile="crxzipple",
                profiles=(BrowserProfileConfig(name="crxzipple"),),
                cdp_port_range_start=18800,
                cdp_port_range_end=18832,
            )
            profile = DefaultBrowserProfileResolver().resolve(
                system=system,
                profile_name="crxzipple",
            )
            capabilities = DefaultBrowserCapabilitiesResolver().resolve(profile=profile)
            command = BrowserControlCommand(
                profile_name="crxzipple",
                kind="list-tabs",
                payload={},
            )
            plan = BrowserExecutionPlan(
                command=command,
                system=system,
                profile=profile,
                capabilities=capabilities,
                control_family="cdp-control",
                action_family="cdp-backed-playwright",
                launch_policy="launch-if-missing",
                tab_selection_policy="sticky-last-target",
            )

            user_data_dir = Path(tempdir.name).resolve() / "crxzipple" / "userdata"
            user_data_dir.mkdir(parents=True, exist_ok=True)
            engine = CdpControlEngine(
                daemon_service=self.daemon_service,
                profiles_root=Path(tempdir.name),
                list_processes=lambda: [
                    {
                        "pid": 44087,
                        "command": (
                            f"/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge "
                            f"--remote-debugging-address=127.0.0.1 "
                            f"--remote-debugging-port={profile.cdp_port} "
                            f"--remote-allow-origins=http://127.0.0.1:{profile.cdp_port} "
                            f"--user-data-dir={user_data_dir} about:blank"
                        ),
                    }
                ],
            )

            self.assertIsNone(engine._find_matching_managed_process(plan=plan))  # noqa: SLF001
        finally:
            tempdir.cleanup()

    def test_cdp_control_engine_accepts_browser_when_launch_wrapper_exits_early(self) -> None:
        delayed_cdp = FakeCdpServer()
        tempdir = tempfile.TemporaryDirectory()
        fake_port = int(delayed_cdp.base_url.rsplit(":", 1)[1])

        class _FakeProcess:
            def __init__(self, pid: int) -> None:
                self.pid = pid
                self._returncode = 0

            def poll(self):
                return self._returncode

            def terminate(self) -> None:
                self._returncode = 0

            def kill(self) -> None:
                self._returncode = -9

            def wait(self, timeout=None) -> int:  # noqa: ANN001
                del timeout
                return self._returncode

        launches: list[list[str]] = []
        process_rows: list[dict[str, object]] = []

        def _launch(command, **kwargs):  # noqa: ANN001
            del kwargs
            launches.append(list(command))
            delayed_cdp.start()
            user_data_dir = Path(tempdir.name).resolve() / "crxzipple" / "userdata"
            process_rows[:] = [
                {
                    "pid": 4343,
                    "command": (
                        f"/Applications/Microsoft Edge --remote-debugging-port={fake_port} "
                        f"--remote-allow-origins=http://127.0.0.1:{fake_port},http://localhost:{fake_port},http://[::1]:{fake_port} "
                        f"--user-data-dir={user_data_dir} about:blank"
                    ),
                }
            ]
            return _FakeProcess(pid=4242)

        system = BrowserSystemConfig(
            default_profile="crxzipple",
            profiles=(
                BrowserProfileConfig(
                    name="crxzipple",
                    cdp_url=delayed_cdp.base_url,
                ),
            ),
            headless=False,
            cdp_port_range_start=fake_port,
            cdp_port_range_end=fake_port + 32,
        )
        runtime_state_store = InMemoryBrowserRuntimeStateStore()
        engine = CdpControlEngine(
            daemon_service=self.daemon_service,
            profiles_root=Path(tempdir.name),
            ws_connect=delayed_cdp.websocket_factory(),
            popen=_launch,
            list_processes=lambda: list(process_rows),
            request_timeout_s=0.05,
            launch_timeout_s=1.0,
            launch_poll_interval_s=0.01,
        )
        coordinator = BrowserExecutionCoordinatorService(
            system_config_store=InMemoryBrowserSystemConfigStore(system),
            profile_resolver=DefaultBrowserProfileResolver(),
            capabilities_resolver=DefaultBrowserCapabilitiesResolver(),
            runtime_state_store=runtime_state_store,
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

        try:
            result = coordinator.execute(
                self.control_assembler.assemble(
                    profile_name="crxzipple",
                    kind="open-tab",
                    payload={"url": "https://example.com"},
                )
            )
            self.assertTrue(result.ok)
            self.assertEqual(len(launches), 1)
            runtime_state = runtime_state_store.get(profile_name="crxzipple")
            self.assertIsNotNone(runtime_state)
            assert runtime_state is not None
            self.assertEqual(runtime_state.running_pid, 4343)
            self.assertEqual(runtime_state.attachment_status, "attached")
        finally:
            engine.close()
            delayed_cdp.close()
            tempdir.cleanup()

    def test_cdp_control_engine_relaunches_headless_managed_process_when_config_is_visible(self) -> None:
        tempdir = tempfile.TemporaryDirectory()
        profiles_root = Path(tempdir.name)
        user_data_dir = profiles_root / "crxzipple" / "userdata"
        user_data_dir.mkdir(parents=True, exist_ok=True)
        fake_port = int(self.fake_cdp.base_url.rsplit(":", 1)[1])

        launches: list[list[str]] = []
        terminated_pids: list[int] = []
        process_rows = [
            {
                "pid": 6111,
                "command": (
                    f"/Applications/Microsoft Edge --remote-debugging-port={fake_port} "
                    f"--user-data-dir={user_data_dir.resolve()} --headless=new about:blank"
                ),
            }
        ]

        class _FakeProcess:
            def __init__(self, pid: int) -> None:
                self.pid = pid
                self._returncode = None

            def poll(self):
                return self._returncode

            def terminate(self) -> None:
                self._returncode = 0

            def kill(self) -> None:
                self._returncode = -9

            def wait(self, timeout=None) -> int:  # noqa: ANN001
                del timeout
                if self._returncode is None:
                    self._returncode = 0
                return self._returncode

        def _launch(command, **kwargs):  # noqa: ANN001
            del kwargs
            launches.append(list(command))
            process_rows[:] = [
                {
                    "pid": 6222,
                    "command": (
                        f"/Applications/Microsoft Edge --remote-debugging-port={fake_port} "
                        f"--user-data-dir={user_data_dir.resolve()} about:blank"
                    ),
                }
            ]
            return _FakeProcess(pid=6222)

        def _terminate_pid(pid: int) -> None:
            terminated_pids.append(pid)
            process_rows[:] = []

        system = BrowserSystemConfig(
            default_profile="crxzipple",
            profiles=(
                BrowserProfileConfig(
                    name="crxzipple",
                    cdp_url=self.fake_cdp.base_url,
                ),
            ),
            headless=False,
            cdp_port_range_start=fake_port,
            cdp_port_range_end=fake_port + 32,
        )
        runtime_state_store = InMemoryBrowserRuntimeStateStore()
        engine = CdpControlEngine(
            daemon_service=self.daemon_service,
            profiles_root=profiles_root,
            ws_connect=self.fake_cdp.websocket_factory(),
            popen=_launch,
            list_processes=lambda: list(process_rows),
            terminate_pid=_terminate_pid,
        )
        coordinator = BrowserExecutionCoordinatorService(
            system_config_store=InMemoryBrowserSystemConfigStore(system),
            profile_resolver=DefaultBrowserProfileResolver(),
            capabilities_resolver=DefaultBrowserCapabilitiesResolver(),
            runtime_state_store=runtime_state_store,
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

        try:
            result = coordinator.execute(
                self.control_assembler.assemble(
                    profile_name="crxzipple",
                    kind="open-tab",
                    payload={"url": "https://example.com"},
                )
            )

            self.assertTrue(result.ok)
            self.assertEqual(terminated_pids, [6111])
            self.assertEqual(len(launches), 1)
            self.assertNotIn("--headless=new", launches[0])
            self.assertNotIn("about:blank", launches[0])
            runtime_state = runtime_state_store.get(profile_name="crxzipple")
            self.assertIsNotNone(runtime_state)
            assert runtime_state is not None
            self.assertEqual(runtime_state.running_pid, 6222)
        finally:
            engine.close()
            tempdir.cleanup()

    def test_cdp_control_engine_reclaims_cdp_port_from_conflicting_managed_process(self) -> None:
        tempdir = tempfile.TemporaryDirectory()
        profiles_root = Path(tempdir.name)
        expected_user_data_dir = profiles_root / "crxzipple" / "userdata"
        expected_user_data_dir.mkdir(parents=True, exist_ok=True)
        fake_port = int(self.fake_cdp.base_url.rsplit(":", 1)[1])
        conflicting_user_data_dir = (
            Path(tempdir.name) / "tmp-run" / "browser" / "profiles" / "crxzipple" / "userdata"
        )
        conflicting_user_data_dir.mkdir(parents=True, exist_ok=True)

        launches: list[list[str]] = []
        terminated_pids: list[int] = []
        process_rows = [
            {
                "pid": 7111,
                "command": (
                    f"/Applications/Microsoft Edge --remote-debugging-port={fake_port} "
                    f"--user-data-dir={conflicting_user_data_dir.resolve()} --headless=new about:blank"
                ),
            }
        ]

        class _FakeProcess:
            def __init__(self, pid: int) -> None:
                self.pid = pid
                self._returncode = None

            def poll(self):
                return self._returncode

            def terminate(self) -> None:
                self._returncode = 0

            def kill(self) -> None:
                self._returncode = -9

            def wait(self, timeout=None) -> int:  # noqa: ANN001
                del timeout
                if self._returncode is None:
                    self._returncode = 0
                return self._returncode

        def _launch(command, **kwargs):  # noqa: ANN001
            del kwargs
            launches.append(list(command))
            process_rows[:] = [
                {
                    "pid": 7222,
                    "command": (
                        f"/Applications/Microsoft Edge --remote-debugging-port={fake_port} "
                        f"--user-data-dir={expected_user_data_dir.resolve()} about:blank"
                    ),
                }
            ]
            return _FakeProcess(pid=7222)

        def _terminate_pid(pid: int) -> None:
            terminated_pids.append(pid)
            process_rows[:] = []

        system = BrowserSystemConfig(
            default_profile="crxzipple",
            profiles=(
                BrowserProfileConfig(
                    name="crxzipple",
                    cdp_url=self.fake_cdp.base_url,
                ),
            ),
            headless=False,
            cdp_port_range_start=fake_port,
            cdp_port_range_end=fake_port + 32,
        )
        runtime_state_store = InMemoryBrowserRuntimeStateStore()
        engine = CdpControlEngine(
            daemon_service=self.daemon_service,
            profiles_root=profiles_root,
            ws_connect=self.fake_cdp.websocket_factory(),
            popen=_launch,
            list_processes=lambda: list(process_rows),
            terminate_pid=_terminate_pid,
        )
        coordinator = BrowserExecutionCoordinatorService(
            system_config_store=InMemoryBrowserSystemConfigStore(system),
            profile_resolver=DefaultBrowserProfileResolver(),
            capabilities_resolver=DefaultBrowserCapabilitiesResolver(),
            runtime_state_store=runtime_state_store,
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

        try:
            result = coordinator.execute(
                self.control_assembler.assemble(
                    profile_name="crxzipple",
                    kind="open-tab",
                    payload={"url": "https://example.com"},
                )
            )

            self.assertTrue(result.ok)
            self.assertEqual(terminated_pids, [7111])
            self.assertEqual(len(launches), 1)
            self.assertNotIn("--headless=new", launches[0])
            self.assertIn(
                f"--user-data-dir={expected_user_data_dir.resolve()}",
                launches[0],
            )
            self.assertNotIn("about:blank", launches[0])
            runtime_state = runtime_state_store.get(profile_name="crxzipple")
            self.assertIsNotNone(runtime_state)
            assert runtime_state is not None
            self.assertEqual(runtime_state.running_pid, 7222)
        finally:
            engine.close()
            tempdir.cleanup()

    def test_cdp_control_engine_reset_clears_userdata_and_runtime_state(self) -> None:
        tempdir = tempfile.TemporaryDirectory()

        class _FakeProcess:
            def __init__(self, pid: int) -> None:
                self.pid = pid
                self._returncode = None
                self.terminated = False

            def poll(self):
                return self._returncode

            def terminate(self) -> None:
                self.terminated = True
                self._returncode = 0

            def kill(self) -> None:
                self.terminated = True
                self._returncode = -9

            def wait(self, timeout=None) -> int:  # noqa: ANN001
                del timeout
                if self._returncode is None:
                    self._returncode = 0
                return self._returncode

        launched_processes: list[_FakeProcess] = []

        def _launch(command, **kwargs):  # noqa: ANN001
            del command, kwargs
            process = _FakeProcess(pid=5151)
            launched_processes.append(process)
            return process

        profiles_root = Path(tempdir.name)
        user_data_dir = profiles_root / "crxzipple" / "userdata"
        user_data_dir.mkdir(parents=True, exist_ok=True)
        sentinel = user_data_dir / "sentinel.txt"
        sentinel.write_text("keep me", encoding="utf-8")

        system = BrowserSystemConfig(
            default_profile="crxzipple",
            profiles=(
                BrowserProfileConfig(
                    name="crxzipple",
                    cdp_url="http://127.0.0.1:18800",
                ),
            ),
        )
        runtime_state_store = InMemoryBrowserRuntimeStateStore()
        ref_store = InMemoryBrowserRefStore()
        engine = CdpControlEngine(
            daemon_service=self.daemon_service,
            profiles_root=profiles_root,
            popen=_launch,
        )
        coordinator = BrowserExecutionCoordinatorService(
            system_config_store=InMemoryBrowserSystemConfigStore(system),
            profile_resolver=DefaultBrowserProfileResolver(),
            capabilities_resolver=DefaultBrowserCapabilitiesResolver(),
            runtime_state_store=runtime_state_store,
            ref_store=ref_store,
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

        runtime_state = BrowserProfileRuntimeState(
            profile_name="crxzipple",
            attachment_status="attached",
            browser_ref="ws://browser.example/devtools/browser/123",
            last_target_id="tab-1",
            running_pid=5151,
            metadata={"tabs": [{"target_id": "tab-1", "url": "https://example.com"}]},
        )
        runtime_state_store.save(runtime_state)
        ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
            refs=(BrowserStoredRef(ref="r1", selector="#submit"),),
        )
        engine._launched_processes["crxzipple"] = _launch([])

        try:
            result = coordinator.execute(
                self.control_assembler.assemble(
                    profile_name="crxzipple",
                    kind="reset",
                )
            )

            self.assertTrue(result.ok)
            self.assertEqual(result.value["profile_name"], "crxzipple")
            self.assertEqual(len(launched_processes), 1)
            self.assertTrue(launched_processes[0].terminated)
            self.assertTrue(user_data_dir.exists())
            self.assertEqual(list(user_data_dir.iterdir()), [])
            self.assertIsNone(runtime_state_store.get(profile_name="crxzipple"))
            self.assertEqual(
                ref_store.get_tab_refs(profile_name="crxzipple", target_id="tab-1"),
                (),
            )
        finally:
            engine.close()
            tempdir.cleanup()


if __name__ == "__main__":
    unittest.main()
