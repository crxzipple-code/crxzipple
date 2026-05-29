from __future__ import annotations

from pathlib import Path
import socket
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
    BrowserValidationError,
    ResolvedBrowserProfile,
)
from crxzipple.modules.browser.infrastructure import (
    BrowserHostProcessRunner,
    CdpControlEngine,
    InMemoryBrowserRefStore,
    InMemoryBrowserRuntimeStateStore,
    InMemoryBrowserSystemConfigStore,
    InMemoryCdpBackedPlaywrightActionEngine,
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

    def _build_daemon_service_without_ready_instance(
        self,
        root_dir: Path,
    ) -> DaemonApplicationService:
        state_root = bootstrap_daemon_state_root(str(root_dir))
        return DaemonApplicationService(
            service_spec_store=FileBackedDaemonServiceSpecStore(
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
            ),
            instance_store=FileBackedDaemonInstanceStore(state_root.instances_dir),
            lease_store=FileBackedDaemonLeaseStore(state_root.leases_dir),
        )

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
                cdp_backed_playwright=InMemoryCdpBackedPlaywrightActionEngine(),
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

    def test_host_generation_change_invalidates_profile_refs_and_page_state(self) -> None:
        runtime_state = BrowserProfileRuntimeState(
            profile_name="crxzipple",
            attachment_status="attached",
            browser_ref="old-browser",
            running_pid=999,
            metadata={
                "host_generation": "old-generation",
                "page_state_by_target": {
                    "target-1": {
                        "current_ref_generation": 3,
                        "last_snapshot_format": "accessibility",
                    },
                },
            },
        )
        runtime_state_store = InMemoryBrowserRuntimeStateStore()
        runtime_state_store.save(runtime_state)
        ref_store = InMemoryBrowserRefStore()
        ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id="target-1",
            refs=(
                BrowserStoredRef(
                    ref="ref-1",
                    selector="#old",
                    generation=3,
                    snapshot_format="accessibility",
                ),
            ),
        )
        coordinator = BrowserExecutionCoordinatorService(
            system_config_store=InMemoryBrowserSystemConfigStore(self.system),
            profile_resolver=DefaultBrowserProfileResolver(),
            capabilities_resolver=DefaultBrowserCapabilitiesResolver(),
            runtime_state_store=runtime_state_store,
            ref_store=ref_store,
            execution_planner=DefaultBrowserExecutionPlanner(),
            engine_registry=StaticBrowserEngineRegistry(
                cdp_control=CdpControlEngine(
                    daemon_service=self.daemon_service,
                    ws_connect=self.fake_cdp.websocket_factory(),
                    list_processes=lambda: [],
                ),
                cdp_backed_playwright=InMemoryCdpBackedPlaywrightActionEngine(),
            ),
            tab_ops_factory=DefaultBrowserProfileTabOpsFactory(),
            selection_ops_factory=DefaultBrowserProfileSelectionOpsFactory(),
        )

        result = coordinator.execute(
            self.control_assembler.assemble(
                profile_name="crxzipple",
                kind="list-tabs",
            )
        )

        self.assertTrue(result.ok)
        self.assertEqual(
            ref_store.get_tab_refs(profile_name="crxzipple", target_id="target-1"),
            (),
        )
        saved_state = runtime_state_store.get(profile_name="crxzipple")
        self.assertIsNotNone(saved_state)
        assert saved_state is not None
        self.assertNotEqual(saved_state.metadata.get("host_generation"), "old-generation")
        self.assertNotIn("page_state_by_target", saved_state.metadata)
        self.assertEqual(saved_state.metadata["host_generation_changed"], True)

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

    def test_cdp_control_engine_prefers_daemon_host_endpoint_over_profile_url(self) -> None:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            unused_port = int(probe.getsockname()[1])
        runtime_state_store = InMemoryBrowserRuntimeStateStore()
        coordinator = BrowserExecutionCoordinatorService(
            system_config_store=InMemoryBrowserSystemConfigStore(
                BrowserSystemConfig(
                    default_profile="crxzipple",
                    profiles=(
                        BrowserProfileConfig(
                            name="crxzipple",
                            cdp_url=f"http://127.0.0.1:{unused_port}",
                        ),
                    ),
                ),
            ),
            profile_resolver=DefaultBrowserProfileResolver(),
            capabilities_resolver=DefaultBrowserCapabilitiesResolver(),
            runtime_state_store=runtime_state_store,
            ref_store=InMemoryBrowserRefStore(),
            execution_planner=DefaultBrowserExecutionPlanner(),
            engine_registry=StaticBrowserEngineRegistry(
                cdp_control=CdpControlEngine(
                    daemon_service=self.daemon_service,
                    ws_connect=self.fake_cdp.websocket_factory(),
                    list_processes=lambda: [],
                ),
                cdp_backed_playwright=InMemoryCdpBackedPlaywrightActionEngine(),
            ),
            tab_ops_factory=DefaultBrowserProfileTabOpsFactory(),
            selection_ops_factory=DefaultBrowserProfileSelectionOpsFactory(),
        )

        result = coordinator.execute(
            self.control_assembler.assemble(
                profile_name="crxzipple",
                kind="open-tab",
                payload={"url": "https://example.com"},
            ),
        )

        self.assertTrue(result.ok)
        runtime_state = runtime_state_store.get(profile_name="crxzipple")
        self.assertIsNotNone(runtime_state)
        assert runtime_state is not None
        self.assertEqual(runtime_state.metadata["cdp_base_url"], self.fake_cdp.base_url)

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

    def test_ensure_attached_ignores_renderer_port_process_when_managed_process_matches(self) -> None:
        tempdir = tempfile.TemporaryDirectory()
        try:
            system = BrowserSystemConfig(
                default_profile="crxzipple",
                profiles=(BrowserProfileConfig(name="crxzipple", cdp_url=self.fake_cdp.base_url),),
                cdp_port_range_start=int(self.fake_cdp.base_url.rsplit(":", 1)[1]),
                cdp_port_range_end=int(self.fake_cdp.base_url.rsplit(":", 1)[1]),
            )
            profile = DefaultBrowserProfileResolver().resolve(
                system=system,
                profile_name="crxzipple",
            )
            capabilities = DefaultBrowserCapabilitiesResolver().resolve(profile=profile)
            plan = BrowserExecutionPlan(
                command=BrowserControlCommand(
                    profile_name="crxzipple",
                    kind="list-tabs",
                    payload={},
                ),
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
            remote_allow_origins = (
                f"http://127.0.0.1:{profile.cdp_port},"
                f"http://localhost:{profile.cdp_port},"
                f"http://[::1]:{profile.cdp_port}"
            )
            renderer_command = (
                "/Applications/Microsoft Edge Helper "
                f"--type=renderer --user-data-dir={user_data_dir} "
                f"--remote-debugging-port={profile.cdp_port}"
            )
            browser_command = (
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge "
                f"--remote-debugging-address=127.0.0.1 "
                f"--remote-debugging-port={profile.cdp_port} "
                f"--remote-allow-origins={remote_allow_origins} "
                f"--user-data-dir={user_data_dir} about:blank"
            )
            engine = CdpControlEngine(
                daemon_service=self.daemon_service,
                profiles_root=Path(tempdir.name),
                ws_connect=self.fake_cdp.websocket_factory(),
                list_processes=lambda: [
                    {"pid": 77001, "command": renderer_command},
                    {"pid": 77002, "command": browser_command},
                ],
            )

            updated = engine.ensure_attached(
                plan=plan,
                runtime_state=BrowserProfileRuntimeState(profile_name="crxzipple"),
            )

            self.assertEqual(updated.attachment_status, "attached")
            self.assertEqual(updated.running_pid, 77002)
            self.assertIsNone(updated.last_error)
        finally:
            tempdir.cleanup()

    def test_browser_host_runner_launches_local_managed_browser(self) -> None:
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
        launched_processes: list[_FakeProcess] = []
        fake_executable = Path(tempdir.name) / "browser-bin"
        fake_executable.write_text("#!/bin/sh\n", encoding="utf-8")

        def _launch(command, **kwargs):  # noqa: ANN001
            del kwargs
            launches.append(list(command))
            delayed_cdp.start()
            process = _FakeProcess(pid=4242)
            launched_processes.append(process)
            return process

        system = BrowserSystemConfig(
            default_profile="crxzipple",
            profiles=(
                BrowserProfileConfig(
                    name="crxzipple",
                    cdp_url=delayed_cdp.base_url,
                    profile_directory="Profile 1",
                    proxy_mode="static",
                    proxy_server="socks5://127.0.0.1:7890",
                    proxy_bypass_list=("localhost", "127.0.0.1"),
                ),
            ),
            headless=True,
            executable_path=str(fake_executable),
            cdp_port_range_start=18800,
            cdp_port_range_end=18832,
        )
        profile = DefaultBrowserProfileResolver().resolve(
            system=system,
            profile_name="crxzipple",
        )
        capabilities = DefaultBrowserCapabilitiesResolver().resolve(profile=profile)
        runner = BrowserHostProcessRunner(
            daemon_service=self.daemon_service,
            system=system,
            profile=profile,
            capabilities=capabilities,
            profiles_root=Path(tempdir.name),
            popen=_launch,
            request_timeout_s=0.05,
            launch_timeout_s=1.0,
            launch_poll_interval_s=0.01,
        )

        try:
            endpoint = runner.start()

            self.assertEqual(endpoint, delayed_cdp.base_url)
            self.assertEqual(len(launches), 1)
            self.assertIn("--headless=new", launches[0])
            self.assertIn("--profile-directory=Profile 1", launches[0])
            self.assertIn("--proxy-server=socks5://127.0.0.1:7890", launches[0])
            self.assertIn("--proxy-bypass-list=localhost;127.0.0.1", launches[0])
            cdp_port = int(delayed_cdp.base_url.rsplit(":", 1)[1])
            self.assertIn(
                f"--remote-allow-origins=http://127.0.0.1:{cdp_port},http://localhost:{cdp_port},http://[::1]:{cdp_port}",
                launches[0],
            )
            self.assertIn(
                f"--user-data-dir={Path(tempdir.name).resolve() / 'crxzipple' / 'userdata'}",
                launches[0],
            )
            instance = self.daemon_service.list_instances(service_key="host:browser:crxzipple")[0]
            self.assertEqual(instance.status, "ready")
            self.assertEqual(instance.pid, 4242)
            self.assertEqual(instance.endpoint, delayed_cdp.base_url)
        finally:
            runner.close()
            self.assertTrue(launched_processes[0].terminated)
            delayed_cdp.close()
            tempdir.cleanup()

    def test_browser_host_runner_uses_local_proxy_adapter_for_access_binding(self) -> None:
        delayed_cdp = FakeCdpServer()
        tempdir = tempfile.TemporaryDirectory()

        class _FakeProcess:
            pid = 4344
            terminated = False

            def poll(self):
                return None

            def terminate(self) -> None:
                self.terminated = True

            def kill(self) -> None:
                self.terminated = True

            def wait(self, timeout=None) -> int:  # noqa: ANN001
                del timeout
                return 0

        class _CredentialProvider:
            def __init__(self) -> None:
                self.calls: list[tuple[str, dict[str, object]]] = []

            def resolve_credential(self, binding: str, **kwargs):  # noqa: ANN001
                self.calls.append((binding, dict(kwargs)))
                return "proxy-user:proxy-secret"

        class _FakeProxyAdapter:
            def __init__(
                self,
                *,
                upstream_proxy_url: str,
                credential: str,
                credential_kind: str = "basic",
            ) -> None:
                self.upstream_proxy_url = upstream_proxy_url
                self.credential = credential
                self.credential_kind = credential_kind
                self.started = False
                self.closed = False
                self.egress_url: str | None = None

            def start(self) -> str:
                self.started = True
                return "http://127.0.0.1:40123"

            def check_egress(self, url: str):
                self.egress_url = url
                return {"status": "ready", "ip": "203.0.113.10", "url": url}

            def metadata(self):
                return {
                    "proxy_adapter": "local_http_basic",
                    "proxy_upstream": self.upstream_proxy_url,
                    "proxy_local_url": "http://127.0.0.1:40123",
                }

            def close(self) -> None:
                self.closed = True

        launches: list[list[str]] = []
        adapters: list[_FakeProxyAdapter] = []
        fake_executable = Path(tempdir.name) / "browser-bin"
        fake_executable.write_text("#!/bin/sh\n", encoding="utf-8")

        def _launch(command, **kwargs):  # noqa: ANN001
            del kwargs
            launches.append(list(command))
            delayed_cdp.start()
            return _FakeProcess()

        def _proxy_adapter_factory(**kwargs):  # noqa: ANN001
            adapter = _FakeProxyAdapter(**kwargs)
            adapters.append(adapter)
            return adapter

        credential_provider = _CredentialProvider()
        system = BrowserSystemConfig(
            default_profile="crxzipple",
            profiles=(
                BrowserProfileConfig(
                    name="crxzipple",
                    cdp_url=delayed_cdp.base_url,
                    proxy_mode="access_binding",
                    proxy_server="http://proxy.example:8080",
                    proxy_binding_id="proxy-basic",
                ),
            ),
            executable_path=str(fake_executable),
        )
        profile = DefaultBrowserProfileResolver().resolve(
            system=system,
            profile_name="crxzipple",
        )
        capabilities = DefaultBrowserCapabilitiesResolver().resolve(profile=profile)
        runner = BrowserHostProcessRunner(
            daemon_service=self.daemon_service,
            system=system,
            profile=profile,
            capabilities=capabilities,
            profiles_root=Path(tempdir.name),
            popen=_launch,
            credential_provider=credential_provider,
            proxy_adapter_factory=_proxy_adapter_factory,
            proxy_egress_check_url="https://egress.example/ip",
            request_timeout_s=0.05,
            launch_timeout_s=1.0,
            launch_poll_interval_s=0.01,
        )

        try:
            endpoint = runner.start()

            self.assertEqual(endpoint, delayed_cdp.base_url)
            self.assertEqual(len(launches), 1)
            command_text = " ".join(launches[0])
            self.assertIn("--proxy-server=http://127.0.0.1:40123", command_text)
            self.assertNotIn("proxy-secret", command_text)
            self.assertNotIn("proxy-user", command_text)
            self.assertNotIn("proxy.example", command_text)
            self.assertEqual(credential_provider.calls[0][0], "proxy-basic")
            self.assertEqual(credential_provider.calls[0][1]["expected_kind"], "basic")
            self.assertEqual(len(adapters), 1)
            self.assertTrue(adapters[0].started)
            self.assertEqual(adapters[0].credential, "proxy-user:proxy-secret")
            self.assertEqual(adapters[0].egress_url, "https://egress.example/ip")
            instance = self.daemon_service.list_instances(service_key="host:browser:crxzipple")[0]
            self.assertEqual(instance.metadata["proxy_adapter"], "local_http_basic")
            self.assertEqual(instance.metadata["proxy_binding_id"], "proxy-basic")
            self.assertEqual(instance.metadata["proxy_upstream"], "http://proxy.example:8080")
            self.assertEqual(instance.metadata["proxy_egress_ip"], "203.0.113.10")
        finally:
            runner.close()
            if adapters:
                self.assertTrue(adapters[0].closed)
            delayed_cdp.close()
            tempdir.cleanup()

    def test_browser_host_runner_adopts_matching_managed_browser(self) -> None:
        cdp = FakeCdpServer()
        cdp.start()
        tempdir = tempfile.TemporaryDirectory()
        try:
            fake_executable = Path(tempdir.name) / "browser-bin"
            fake_executable.write_text("#!/bin/sh\n", encoding="utf-8")
            cdp_port = int(cdp.base_url.rsplit(":", 1)[1])
            user_data_dir = Path(tempdir.name).resolve() / "crxzipple" / "userdata"
            matching_command = " ".join(
                (
                    str(fake_executable),
                    f"--remote-debugging-port={cdp_port}",
                    f"--remote-allow-origins=http://127.0.0.1:{cdp_port},http://localhost:{cdp_port},http://[::1]:{cdp_port}",
                    f"--user-data-dir={user_data_dir}",
                    "--profile-directory=Profile 1",
                    "--headless=new",
                )
            )
            system = BrowserSystemConfig(
                default_profile="crxzipple",
                profiles=(
                    BrowserProfileConfig(
                        name="crxzipple",
                        cdp_url=cdp.base_url,
                        profile_directory="Profile 1",
                    ),
                ),
                headless=True,
                executable_path=str(fake_executable),
                cdp_port_range_start=cdp_port,
                cdp_port_range_end=cdp_port,
            )
            profile = DefaultBrowserProfileResolver().resolve(
                system=system,
                profile_name="crxzipple",
            )
            capabilities = DefaultBrowserCapabilitiesResolver().resolve(profile=profile)
            launches: list[list[str]] = []
            runner = BrowserHostProcessRunner(
                daemon_service=self.daemon_service,
                system=system,
                profile=profile,
                capabilities=capabilities,
                profiles_root=Path(tempdir.name),
                popen=lambda command, **kwargs: launches.append(list(command)),  # noqa: ARG005
                list_processes=lambda: [{"pid": 4343, "command": matching_command}],
                request_timeout_s=0.05,
            )

            endpoint = runner.start()

            self.assertEqual(endpoint, cdp.base_url)
            self.assertEqual(launches, [])
            instance = self.daemon_service.list_instances(service_key="host:browser:crxzipple")[0]
            self.assertEqual(instance.status, "ready")
            self.assertEqual(instance.pid, 4343)
            self.assertEqual(instance.endpoint, cdp.base_url)
            self.assertEqual(instance.metadata["browser_pid"], 4343)
            self.assertEqual(instance.metadata["adopted"], True)
            self.assertIsInstance(instance.metadata.get("launch_fingerprint"), str)
        finally:
            runner.close()
            cdp.close()
            tempdir.cleanup()

    def test_browser_host_runner_rejects_conflicting_cdp_port_without_launch(self) -> None:
        tempdir = tempfile.TemporaryDirectory()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            cdp_port = int(probe.getsockname()[1])
        try:
            fake_executable = Path(tempdir.name) / "browser-bin"
            fake_executable.write_text("#!/bin/sh\n", encoding="utf-8")
            conflicting_command = " ".join(
                (
                    str(fake_executable),
                    f"--remote-debugging-port={cdp_port}",
                    "--user-data-dir=/tmp/not-crxzipple",
                    "--headless=new",
                )
            )
            system = BrowserSystemConfig(
                default_profile="crxzipple",
                profiles=(
                    BrowserProfileConfig(
                        name="crxzipple",
                        cdp_url=f"http://127.0.0.1:{cdp_port}",
                    ),
                ),
                headless=True,
                executable_path=str(fake_executable),
                cdp_port_range_start=cdp_port,
                cdp_port_range_end=cdp_port,
            )
            profile = DefaultBrowserProfileResolver().resolve(
                system=system,
                profile_name="crxzipple",
            )
            capabilities = DefaultBrowserCapabilitiesResolver().resolve(profile=profile)
            launches: list[list[str]] = []
            runner = BrowserHostProcessRunner(
                daemon_service=self.daemon_service,
                system=system,
                profile=profile,
                capabilities=capabilities,
                profiles_root=Path(tempdir.name),
                popen=lambda command, **kwargs: launches.append(list(command)),  # noqa: ARG005
                list_processes=lambda: [{"pid": 5454, "command": conflicting_command}],
                request_timeout_s=0.05,
            )

            with self.assertRaisesRegex(BrowserValidationError, "does not match"):
                runner.start()

            self.assertEqual(launches, [])
            instance = self.daemon_service.list_instances(service_key="host:browser:crxzipple")[0]
            self.assertEqual(instance.status, "failed")
            self.assertEqual(instance.metadata["conflict_pid"], 5454)
            self.assertNotIn("conflict_command", instance.metadata)
        finally:
            tempdir.cleanup()

    def test_browser_host_runner_start_failure_does_not_report_stopped(self) -> None:
        tempdir = tempfile.TemporaryDirectory()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            unused_port = int(probe.getsockname()[1])

        class _ExitedProcess:
            pid = 5151

            def poll(self) -> int:
                return 1

            def terminate(self) -> None:
                return None

            def kill(self) -> None:
                return None

            def wait(self, timeout=None) -> int:  # noqa: ANN001
                del timeout
                return 1

        try:
            fake_executable = Path(tempdir.name) / "browser-bin"
            fake_executable.write_text("#!/bin/sh\n", encoding="utf-8")
            system = BrowserSystemConfig(
                default_profile="crxzipple",
                profiles=(
                    BrowserProfileConfig(
                        name="crxzipple",
                        cdp_url=f"http://127.0.0.1:{unused_port}",
                    ),
                ),
                headless=True,
                executable_path=str(fake_executable),
                cdp_port_range_start=unused_port,
                cdp_port_range_end=unused_port,
            )
            profile = DefaultBrowserProfileResolver().resolve(
                system=system,
                profile_name="crxzipple",
            )
            capabilities = DefaultBrowserCapabilitiesResolver().resolve(profile=profile)
            runner = BrowserHostProcessRunner(
                daemon_service=self.daemon_service,
                system=system,
                profile=profile,
                capabilities=capabilities,
                profiles_root=Path(tempdir.name),
                popen=lambda *args, **kwargs: _ExitedProcess(),  # noqa: ARG005
                request_timeout_s=0.05,
                launch_timeout_s=0.1,
                launch_poll_interval_s=0.01,
            )

            with self.assertRaisesRegex(
                BrowserValidationError,
                "exited before CDP became available",
            ):
                runner.start()
            runner.close()

            instance = self.daemon_service.list_instances(service_key="host:browser:crxzipple")[0]
            self.assertEqual(instance.status, "failed")
            self.assertNotEqual(instance.status, "stopped")
        finally:
            tempdir.cleanup()

    def test_cdp_control_engine_requires_daemon_host_when_managed_cdp_missing(self) -> None:
        tempdir = tempfile.TemporaryDirectory()
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
            probe.bind(("127.0.0.1", 0))
            unused_port = int(probe.getsockname()[1])
        try:
            system = BrowserSystemConfig(
                default_profile="crxzipple",
                profiles=(
                    BrowserProfileConfig(
                        name="crxzipple",
                        cdp_url=f"http://127.0.0.1:{unused_port}",
                    ),
                ),
                cdp_port_range_start=unused_port,
                cdp_port_range_end=unused_port,
            )
            runtime_state_store = InMemoryBrowserRuntimeStateStore()
            daemon_service = self._build_daemon_service_without_ready_instance(
                Path(tempdir.name),
            )
            engine = CdpControlEngine(
                daemon_service=daemon_service,
                profiles_root=Path(tempdir.name),
                list_processes=lambda: [],
                request_timeout_s=0.05,
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
                    cdp_backed_playwright=InMemoryCdpBackedPlaywrightActionEngine(),
                ),
                tab_ops_factory=DefaultBrowserProfileTabOpsFactory(),
                selection_ops_factory=DefaultBrowserProfileSelectionOpsFactory(),
            )

            with self.assertRaisesRegex(BrowserValidationError, "host:browser:crxzipple"):
                coordinator.execute(
                    self.control_assembler.assemble(
                        profile_name="crxzipple",
                        kind="open-tab",
                        payload={"url": "https://example.com"},
                    )
                )
        finally:
            tempdir.cleanup()

    def test_cdp_control_engine_reset_clears_userdata_and_runtime_state(self) -> None:
        tempdir = tempfile.TemporaryDirectory()
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
                cdp_backed_playwright=InMemoryCdpBackedPlaywrightActionEngine(),
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

        try:
            result = coordinator.execute(
                self.control_assembler.assemble(
                    profile_name="crxzipple",
                    kind="reset",
                )
            )

            self.assertTrue(result.ok)
            self.assertEqual(result.value["profile_name"], "crxzipple")
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
