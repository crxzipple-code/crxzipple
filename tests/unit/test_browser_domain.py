from __future__ import annotations

import unittest

from crxzipple.modules.browser.application import (
    BrowserExecutionCoordinatorService,
    BrowserProfileAdminService,
    DefaultBrowserCapabilitiesResolver,
    DefaultBrowserControlCommandAssembler,
    DefaultBrowserExecutionPlanner,
    DefaultBrowserPageActionAssembler,
    DefaultBrowserProfileResolver,
    DefaultBrowserProfileSelectionOpsFactory,
    DefaultBrowserProfileTabOpsFactory,
)
from crxzipple.modules.browser.application.runtime_payloads import (
    browser_runtime_state_applies_to_profile,
)
from crxzipple.modules.browser.domain import (
    BrowserActionResult,
    BrowserActionTarget,
    BrowserProfileConfig,
    BrowserProfileRuntimeState,
    BrowserStoredRef,
    BrowserSystemConfig,
    BrowserTab,
    BrowserValidationError,
)
from crxzipple.modules.browser.infrastructure import (
    InMemoryBrowserRefStore,
    InMemoryBrowserRuntimeStateStore,
    InMemoryBrowserSystemConfigStore,
    InMemoryCdpBackedPlaywrightActionEngine,
    InMemoryCdpControlEngine,
    StaticBrowserEngineRegistry,
)


class _UnsupportedCdpActionEngine(InMemoryCdpBackedPlaywrightActionEngine):
    def supports(self, *, command):  # type: ignore[override]
        del command
        return False


class BrowserDomainTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.system = BrowserSystemConfig(
            default_profile="crxzipple",
            profiles=(
                BrowserProfileConfig(name="crxzipple"),
                BrowserProfileConfig(
                    name="user",
                    driver="existing-session",
                    user_data_dir="/tmp/user-profile",
                ),
                BrowserProfileConfig(
                    name="remote",
                    cdp_url="http://browser.example:9444",
                ),
            ),
            cdp_port_range_start=9333,
            cdp_port_range_end=9340,
        )
        self.profile_resolver = DefaultBrowserProfileResolver()
        self.capabilities_resolver = DefaultBrowserCapabilitiesResolver()
        self.control_command_assembler = DefaultBrowserControlCommandAssembler()
        self.page_action_assembler = DefaultBrowserPageActionAssembler()
        self.execution_planner = DefaultBrowserExecutionPlanner()
        self.tab_ops_factory = DefaultBrowserProfileTabOpsFactory()
        self.selection_ops_factory = DefaultBrowserProfileSelectionOpsFactory()

    def test_static_proxy_rejects_credentials_in_proxy_server(self) -> None:
        with self.assertRaisesRegex(BrowserValidationError, "must not contain credentials"):
            BrowserProfileConfig(
                name="proxied",
                proxy_mode="static",
                proxy_server="http://user:secret@proxy.example:8080",
            )

    def _build_coordinator(
        self,
    ) -> tuple[
        BrowserExecutionCoordinatorService,
        InMemoryBrowserRuntimeStateStore,
        InMemoryBrowserRefStore,
    ]:
        runtime_state_store = InMemoryBrowserRuntimeStateStore()
        ref_store = InMemoryBrowserRefStore()
        coordinator = BrowserExecutionCoordinatorService(
            system_config_store=InMemoryBrowserSystemConfigStore(self.system),
            profile_resolver=self.profile_resolver,
            capabilities_resolver=self.capabilities_resolver,
            runtime_state_store=runtime_state_store,
            ref_store=ref_store,
            execution_planner=self.execution_planner,
            engine_registry=StaticBrowserEngineRegistry(
                cdp_control=InMemoryCdpControlEngine(),
                cdp_backed_playwright=InMemoryCdpBackedPlaywrightActionEngine(),
            ),
            tab_ops_factory=self.tab_ops_factory,
            selection_ops_factory=self.selection_ops_factory,
        )
        return coordinator, runtime_state_store, ref_store

    def _build_profile_admin(
        self,
    ) -> tuple[
        BrowserProfileAdminService,
        InMemoryBrowserSystemConfigStore,
        InMemoryBrowserRuntimeStateStore,
        InMemoryBrowserRefStore,
    ]:
        system_store = InMemoryBrowserSystemConfigStore(self.system)
        runtime_state_store = InMemoryBrowserRuntimeStateStore()
        ref_store = InMemoryBrowserRefStore()
        admin = BrowserProfileAdminService(
            system_config_store=system_store,
            runtime_state_store=runtime_state_store,
            ref_store=ref_store,
        )
        return admin, system_store, runtime_state_store, ref_store

    def test_profile_resolver_allocates_local_managed_profile_from_port_range(self) -> None:
        profile = self.profile_resolver.resolve(
            system=self.system,
            profile_name="crxzipple",
        )

        self.assertEqual(profile.name, "crxzipple")
        self.assertEqual(profile.driver, "managed")
        self.assertEqual(profile.cdp_port, 9333)
        self.assertEqual(profile.cdp_url, "http://127.0.0.1:9333")
        self.assertTrue(profile.is_loopback)
        self.assertFalse(profile.attach_only)
        self.assertTrue(profile.enabled)

    def test_profile_resolver_resolves_existing_session_as_attach_only_cdp(self) -> None:
        profile = self.profile_resolver.resolve(
            system=self.system,
            profile_name="user",
        )

        self.assertEqual(profile.name, "user")
        self.assertEqual(profile.driver, "existing-session")
        self.assertIsNone(profile.cdp_url)
        self.assertIsNone(profile.cdp_port)
        self.assertEqual(profile.user_data_dir, "/tmp/user-profile")
        self.assertTrue(profile.attach_only)
        self.assertFalse(profile.is_loopback)

    def test_profile_resolver_keeps_explicit_existing_session_cdp_endpoint(self) -> None:
        system = BrowserSystemConfig(
            default_profile="user",
            profiles=(
                BrowserProfileConfig(
                    name="user",
                    driver="existing-session",
                    cdp_url="http://127.0.0.1:9444",
                ),
            ),
        )

        profile = self.profile_resolver.resolve(system=system, profile_name="user")

        self.assertEqual(profile.cdp_url, "http://127.0.0.1:9444")
        self.assertEqual(profile.cdp_port, 9444)
        self.assertTrue(profile.attach_only)
        self.assertTrue(profile.is_loopback)

    def test_execution_coordinator_accepts_registered_page_action_kinds(self) -> None:
        coordinator, _runtime_state_store, _ref_store = self._build_coordinator()
        open_result = coordinator.execute(
            self.control_command_assembler.assemble(
                profile_name="crxzipple",
                kind="open-tab",
                payload={"url": "https://example.com/start"},
            )
        )
        target_id = open_result.target_id or ""

        for kind in (
            "dom-inspect",
            "storage-indexeddb-list",
            "storage-cache-list",
            "service-worker-list",
            "network-inspect",
            "cdp-raw",
        ):
            with self.subTest(kind=kind):
                result = coordinator.execute(
                    self.page_action_assembler.assemble(
                        profile_name="crxzipple",
                        kind=kind,
                        target_id=target_id,
                        payload={},
                    )
                )

                self.assertTrue(result.ok)
                self.assertEqual(result.value["payload"], {})

    def test_stale_existing_session_runtime_does_not_apply_without_endpoint(self) -> None:
        profile = self.profile_resolver.resolve(
            system=self.system,
            profile_name="user",
        )
        runtime_state = BrowserProfileRuntimeState(
            profile_name="user",
            attachment_status="failed",
            browser_ref="ws://127.0.0.1:18801/devtools/browser/old",
            running_pid=123,
            last_error="old endpoint failed",
        )

        self.assertFalse(
            browser_runtime_state_applies_to_profile(
                runtime_state,
                resolved_profile=profile,
            ),
        )

        explicit_system = BrowserSystemConfig(
            default_profile="user",
            profiles=(
                BrowserProfileConfig(
                    name="user",
                    driver="existing-session",
                    cdp_url="http://127.0.0.1:9222",
                ),
            ),
        )
        explicit_profile = self.profile_resolver.resolve(
            system=explicit_system,
            profile_name="user",
        )

        self.assertTrue(
            browser_runtime_state_applies_to_profile(
                runtime_state,
                resolved_profile=explicit_profile,
            ),
        )

    def test_capabilities_resolver_maps_three_profile_families(self) -> None:
        local_profile = self.profile_resolver.resolve(
            system=self.system,
            profile_name="crxzipple",
        )
        existing_profile = self.profile_resolver.resolve(
            system=self.system,
            profile_name="user",
        )
        remote_profile = self.profile_resolver.resolve(
            system=self.system,
            profile_name="remote",
        )

        local_capabilities = self.capabilities_resolver.resolve(profile=local_profile)
        existing_capabilities = self.capabilities_resolver.resolve(profile=existing_profile)
        remote_capabilities = self.capabilities_resolver.resolve(profile=remote_profile)

        self.assertEqual(local_capabilities.mode, "local-managed")
        self.assertEqual(local_capabilities.control_family, "cdp-control")
        self.assertEqual(local_capabilities.action_family, "cdp-backed-playwright")
        self.assertTrue(local_capabilities.can_launch)
        self.assertTrue(local_capabilities.supports_reset)

        self.assertEqual(existing_capabilities.mode, "local-existing-session")
        self.assertEqual(existing_capabilities.control_family, "cdp-control")
        self.assertEqual(existing_capabilities.action_family, "cdp-backed-playwright")
        self.assertFalse(existing_capabilities.can_launch)
        self.assertFalse(existing_capabilities.supports_reset)

        self.assertEqual(remote_capabilities.mode, "remote-cdp")
        self.assertEqual(remote_capabilities.control_family, "cdp-control")
        self.assertEqual(remote_capabilities.action_family, "cdp-backed-playwright")
        self.assertTrue(remote_capabilities.is_remote)
        self.assertFalse(remote_capabilities.can_launch)

    def test_runtime_state_drops_legacy_mcp_browser_ref(self) -> None:
        runtime_state = BrowserProfileRuntimeState(
            profile_name="user",
            attachment_status="attached",
            browser_ref="mcp:user",
            running_pid=123,
        )

        self.assertIsNone(runtime_state.browser_ref)
        runtime_state.mark_attached(browser_ref="mcp:user")
        self.assertIsNone(runtime_state.browser_ref)
        runtime_state.mark_attached(browser_ref="ws://127.0.0.1:18801/devtools/browser/1")
        self.assertEqual(
            runtime_state.browser_ref,
            "ws://127.0.0.1:18801/devtools/browser/1",
        )

    def test_execution_coordinator_reset_clears_runtime_state_and_refs(self) -> None:
        coordinator, runtime_state_store, ref_store = self._build_coordinator()

        open_result = coordinator.execute(
            self.control_command_assembler.assemble(
                profile_name="crxzipple",
                kind="open-tab",
                payload={"url": "https://example.com"},
            )
        )
        assert open_result.target_id is not None
        ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id=open_result.target_id,
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    selector="#submit",
                ),
            ),
        )

        reset_result = coordinator.execute(
            self.control_command_assembler.assemble(
                profile_name="crxzipple",
                kind="reset",
            )
        )

        self.assertTrue(reset_result.ok)
        self.assertEqual(reset_result.value["profile_name"], "crxzipple")
        self.assertIsNone(runtime_state_store.get(profile_name="crxzipple"))
        self.assertEqual(
            ref_store.get_tab_refs(profile_name="crxzipple", target_id=open_result.target_id),
            (),
        )

    def test_runtime_state_failure_clears_stale_attachment_reference(self) -> None:
        runtime_state = BrowserProfileRuntimeState(
            profile_name="user",
            attachment_status="attached",
            browser_ref="mcp:user",
            running_pid=123,
            last_target_id="target-1",
        )

        runtime_state.mark_failed("CDP endpoint is not reachable.")

        self.assertEqual(runtime_state.attachment_status, "failed")
        self.assertIsNone(runtime_state.browser_ref)
        self.assertIsNone(runtime_state.running_pid)
        self.assertIsNone(runtime_state.last_target_id)
        self.assertEqual(runtime_state.last_error, "CDP endpoint is not reachable.")

    def test_execution_coordinator_status_start_and_stop_profile(self) -> None:
        coordinator, runtime_state_store, ref_store = self._build_coordinator()

        status_result = coordinator.execute(
            self.control_command_assembler.assemble(
                profile_name="crxzipple",
                kind="status",
            )
        )

        self.assertTrue(status_result.ok)
        self.assertEqual(status_result.value["profile_name"], "crxzipple")
        self.assertEqual(status_result.value["runtime"]["attachment_status"], "idle")
        self.assertEqual(status_result.value["tab_count"], 0)

        start_result = coordinator.execute(
            self.control_command_assembler.assemble(
                profile_name="crxzipple",
                kind="start",
            )
        )

        self.assertTrue(start_result.ok)
        self.assertEqual(start_result.value["profile_name"], "crxzipple")
        self.assertEqual(start_result.value["runtime"]["attachment_status"], "attached")

        open_result = coordinator.execute(
            self.control_command_assembler.assemble(
                profile_name="crxzipple",
                kind="open-tab",
                payload={"url": "https://example.com"},
            )
        )
        assert open_result.target_id is not None
        ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id=open_result.target_id,
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    selector="#submit",
                ),
            ),
        )

        stop_result = coordinator.execute(
            self.control_command_assembler.assemble(
                profile_name="crxzipple",
                kind="stop",
            )
        )

        self.assertTrue(stop_result.ok)
        self.assertEqual(stop_result.value["profile_name"], "crxzipple")
        self.assertEqual(stop_result.value["runtime"]["attachment_status"], "closed")
        runtime_state = runtime_state_store.get(profile_name="crxzipple")
        self.assertIsNotNone(runtime_state)
        assert runtime_state is not None
        self.assertEqual(runtime_state.attachment_status, "closed")
        self.assertEqual(
            ref_store.get_tab_refs(profile_name="crxzipple", target_id=open_result.target_id),
            (),
        )

    def test_execution_coordinator_rejects_runtime_actions_for_disabled_profile(self) -> None:
        disabled_system = BrowserSystemConfig(
            default_profile="disabled",
            profiles=(BrowserProfileConfig(name="disabled", enabled=False),),
            cdp_port_range_start=9333,
            cdp_port_range_end=9340,
        )
        runtime_state_store = InMemoryBrowserRuntimeStateStore()
        coordinator = BrowserExecutionCoordinatorService(
            system_config_store=InMemoryBrowserSystemConfigStore(disabled_system),
            profile_resolver=self.profile_resolver,
            capabilities_resolver=self.capabilities_resolver,
            runtime_state_store=runtime_state_store,
            ref_store=InMemoryBrowserRefStore(),
            execution_planner=self.execution_planner,
            engine_registry=StaticBrowserEngineRegistry(
                cdp_control=InMemoryCdpControlEngine(),
                cdp_backed_playwright=InMemoryCdpBackedPlaywrightActionEngine(),
            ),
            tab_ops_factory=self.tab_ops_factory,
            selection_ops_factory=self.selection_ops_factory,
        )

        status_result = coordinator.execute(
            self.control_command_assembler.assemble(
                profile_name="disabled",
                kind="status",
            )
        )

        self.assertTrue(status_result.ok)
        self.assertFalse(status_result.value["enabled"])
        with self.assertRaisesRegex(BrowserValidationError, "disabled"):
            coordinator.execute(
                self.control_command_assembler.assemble(
                    profile_name="disabled",
                    kind="start",
                )
            )

    def test_execution_coordinator_rejects_reset_for_existing_session(self) -> None:
        coordinator, _runtime_state_store, _ref_store = self._build_coordinator()

        with self.assertRaises(BrowserValidationError):
            coordinator.execute(
                self.control_command_assembler.assemble(
                    profile_name="user",
                    kind="reset",
                )
            )

    def test_execution_coordinator_enforces_managed_tab_limit(self) -> None:
        limited_system = BrowserSystemConfig(
            default_profile="crxzipple",
            profiles=(
                BrowserProfileConfig(name="crxzipple"),
                BrowserProfileConfig(
                    name="user",
                    driver="existing-session",
                    user_data_dir="/tmp/user-profile",
                ),
            ),
            managed_tab_limit=1,
            cdp_port_range_start=9333,
            cdp_port_range_end=9340,
        )
        runtime_state_store = InMemoryBrowserRuntimeStateStore()
        ref_store = InMemoryBrowserRefStore()
        coordinator = BrowserExecutionCoordinatorService(
            system_config_store=InMemoryBrowserSystemConfigStore(limited_system),
            profile_resolver=self.profile_resolver,
            capabilities_resolver=self.capabilities_resolver,
            runtime_state_store=runtime_state_store,
            ref_store=ref_store,
            execution_planner=self.execution_planner,
            engine_registry=StaticBrowserEngineRegistry(
                cdp_control=InMemoryCdpControlEngine(),
                cdp_backed_playwright=InMemoryCdpBackedPlaywrightActionEngine(),
            ),
            tab_ops_factory=self.tab_ops_factory,
            selection_ops_factory=self.selection_ops_factory,
        )

        first_result = coordinator.execute(
            self.control_command_assembler.assemble(
                profile_name="crxzipple",
                kind="open-tab",
                payload={"url": "https://example.com/one"},
            )
        )
        self.assertTrue(first_result.ok)

        with self.assertRaises(BrowserValidationError):
            coordinator.execute(
                self.control_command_assembler.assemble(
                    profile_name="crxzipple",
                    kind="open-tab",
                    payload={"url": "https://example.com/two"},
                )
            )

        user_result = coordinator.execute(
            self.control_command_assembler.assemble(
                profile_name="user",
                kind="open-tab",
                payload={"url": "https://example.com/user"},
            )
        )
        self.assertTrue(user_result.ok)

    def test_selection_ops_prefers_sticky_last_target(self) -> None:
        profile = self.profile_resolver.resolve(system=self.system, profile_name="crxzipple")
        capabilities = self.capabilities_resolver.resolve(profile=profile)
        command = self.page_action_assembler.assemble(
            profile_name="crxzipple",
            kind="click",
        )
        plan = self.execution_planner.plan(
            system=self.system,
            profile=profile,
            capabilities=capabilities,
            command=command,
        )
        runtime_state = BrowserProfileRuntimeState(
            profile_name="crxzipple",
            last_target_id="tab-2",
        )
        runtime_state.metadata["tabs"] = [
            {"target_id": "tab-1", "url": "https://one.example", "type": "page"},
            {"target_id": "tab-2", "url": "https://two.example", "type": "page"},
        ]
        control_engine = InMemoryCdpControlEngine()
        tab_ops = self.tab_ops_factory.create(
            plan=plan,
            runtime_state=runtime_state,
            control_engine=control_engine,
        )
        selection_ops = self.selection_ops_factory.create(
            plan=plan,
            runtime_state=runtime_state,
            tab_ops=tab_ops,
        )

        resolved = selection_ops.ensure_tab_available(
            requested_target=BrowserActionTarget(),
        )

        self.assertEqual(resolved.target_id, "tab-2")

    def test_selection_ops_uses_cached_tabs_without_live_list_lookup(self) -> None:
        profile = self.profile_resolver.resolve(system=self.system, profile_name="crxzipple")
        capabilities = self.capabilities_resolver.resolve(profile=profile)
        command = self.page_action_assembler.assemble(
            profile_name="crxzipple",
            kind="click",
        )
        plan = self.execution_planner.plan(
            system=self.system,
            profile=profile,
            capabilities=capabilities,
            command=command,
        )
        runtime_state = BrowserProfileRuntimeState(profile_name="crxzipple")
        runtime_state.metadata["tabs"] = [
            {
                "target_id": "tab-cached",
                "url": "https://cached.example",
                "title": "Cached",
                "type": "page",
            }
        ]

        class _FailingTabOps:
            def list_tabs(self) -> tuple[BrowserTab, ...]:
                raise AssertionError("selection should use cached tabs before live list_tabs")

            def open_tab(self, url: str) -> BrowserTab:
                raise AssertionError(f"unexpected open_tab({url})")

            def navigate_tab(self, target_id: str, url: str) -> BrowserTab:
                raise AssertionError(f"unexpected navigate_tab({target_id}, {url})")

            def focus_tab(self, target_id: str) -> BrowserTab:
                raise AssertionError(f"unexpected focus_tab({target_id})")

            def close_tab(self, target_id: str) -> None:
                raise AssertionError(f"unexpected close_tab({target_id})")

        selection_ops = self.selection_ops_factory.create(
            plan=plan,
            runtime_state=runtime_state,
            tab_ops=_FailingTabOps(),
        )

        resolved = selection_ops.ensure_tab_available(
            requested_target=BrowserActionTarget(),
        )

        self.assertEqual(resolved.target_id, "tab-cached")

    def test_selection_ops_falls_back_to_active_tab_when_requested_page_action_target_is_stale(self) -> None:
        profile = self.profile_resolver.resolve(system=self.system, profile_name="crxzipple")
        capabilities = self.capabilities_resolver.resolve(profile=profile)
        command = self.page_action_assembler.assemble(
            profile_name="crxzipple",
            kind="click",
            target_id="stale-tab",
        )
        plan = self.execution_planner.plan(
            system=self.system,
            profile=profile,
            capabilities=capabilities,
            command=command,
        )
        runtime_state = BrowserProfileRuntimeState(
            profile_name="crxzipple",
            last_target_id="tab-2",
            metadata={"active_target_id": "tab-1"},
        )
        runtime_state.metadata["tabs"] = [
            {"target_id": "tab-1", "url": "https://one.example", "type": "page"},
            {"target_id": "tab-2", "url": "https://two.example", "type": "page"},
        ]
        control_engine = InMemoryCdpControlEngine()
        tab_ops = self.tab_ops_factory.create(
            plan=plan,
            runtime_state=runtime_state,
            control_engine=control_engine,
        )
        selection_ops = self.selection_ops_factory.create(
            plan=plan,
            runtime_state=runtime_state,
            tab_ops=tab_ops,
        )

        resolved = selection_ops.ensure_tab_available(
            requested_target=BrowserActionTarget(target_id="stale-tab"),
        )

        self.assertEqual(resolved.target_id, "tab-1")

    def test_selection_ops_treats_missing_numeric_target_as_page_tab_ordinal(self) -> None:
        profile = self.profile_resolver.resolve(system=self.system, profile_name="crxzipple")
        capabilities = self.capabilities_resolver.resolve(profile=profile)
        command = self.page_action_assembler.assemble(
            profile_name="crxzipple",
            kind="click",
            target_id="2",
        )
        plan = self.execution_planner.plan(
            system=self.system,
            profile=profile,
            capabilities=capabilities,
            command=command,
        )
        runtime_state = BrowserProfileRuntimeState(
            profile_name="crxzipple",
            last_target_id="tab-3",
            metadata={"active_target_id": "missing-active"},
        )
        runtime_state.metadata["tabs"] = [
            {"target_id": "worker-1", "url": "blob:https://example.test/worker", "type": "worker"},
            {"target_id": "tab-1", "url": "https://one.example", "type": "page"},
            {"target_id": "tab-2", "url": "https://two.example", "type": "page"},
            {"target_id": "tab-3", "url": "https://three.example", "type": "page"},
        ]
        control_engine = InMemoryCdpControlEngine()
        tab_ops = self.tab_ops_factory.create(
            plan=plan,
            runtime_state=runtime_state,
            control_engine=control_engine,
        )
        selection_ops = self.selection_ops_factory.create(
            plan=plan,
            runtime_state=runtime_state,
            tab_ops=tab_ops,
        )

        resolved = selection_ops.ensure_tab_available(
            requested_target=BrowserActionTarget(target_id="2"),
        )

        self.assertEqual(resolved.target_id, "tab-2")

    def test_selection_ops_does_not_fall_back_for_control_command_with_stale_target(self) -> None:
        profile = self.profile_resolver.resolve(system=self.system, profile_name="crxzipple")
        capabilities = self.capabilities_resolver.resolve(profile=profile)
        command = self.control_command_assembler.assemble(
            profile_name="crxzipple",
            kind="focus-tab",
            target_id="stale-tab",
        )
        plan = self.execution_planner.plan(
            system=self.system,
            profile=profile,
            capabilities=capabilities,
            command=command,
        )
        runtime_state = BrowserProfileRuntimeState(
            profile_name="crxzipple",
            last_target_id="tab-2",
            metadata={"active_target_id": "tab-1"},
        )
        runtime_state.metadata["tabs"] = [
            {"target_id": "tab-1", "url": "https://one.example", "type": "page"},
            {"target_id": "tab-2", "url": "https://two.example", "type": "page"},
        ]
        control_engine = InMemoryCdpControlEngine()
        tab_ops = self.tab_ops_factory.create(
            plan=plan,
            runtime_state=runtime_state,
            control_engine=control_engine,
        )
        selection_ops = self.selection_ops_factory.create(
            plan=plan,
            runtime_state=runtime_state,
            tab_ops=tab_ops,
        )

        with self.assertRaises(BrowserValidationError):
            selection_ops.ensure_tab_available(
                requested_target=BrowserActionTarget(target_id="stale-tab"),
            )

    def test_execution_coordinator_runs_local_managed_flow(self) -> None:
        coordinator, runtime_state_store, _ref_store = self._build_coordinator()

        open_result = coordinator.execute(
            self.control_command_assembler.assemble(
                profile_name="crxzipple",
                kind="open-tab",
                payload={"url": "https://example.com"},
            )
        )
        click_result = coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="crxzipple",
                kind="click",
                selector="#submit",
                payload={"button": "left"},
            )
        )

        self.assertTrue(open_result.ok)
        self.assertEqual(open_result.value.target_id, open_result.target_id)
        self.assertIsNotNone(open_result.value.ws_url)
        self.assertIsNotNone(open_result.value.json_endpoints)
        self.assertTrue(click_result.ok)
        self.assertEqual(click_result.value["engine"], "cdp-backed-playwright")
        self.assertEqual(click_result.value["control_family"], "cdp-control")
        self.assertEqual(click_result.value["profile"], "crxzipple")
        self.assertEqual(click_result.value["selector"], "#submit")
        self.assertEqual(click_result.target_id, open_result.target_id)

        runtime_state = runtime_state_store.get(profile_name="crxzipple")
        self.assertIsNotNone(runtime_state)
        self.assertEqual(runtime_state.attachment_status, "attached")
        self.assertEqual(runtime_state.browser_ref, "cdp:crxzipple")
        self.assertEqual(runtime_state.last_target_id, open_result.target_id)

    def test_execution_coordinator_runs_existing_session_cdp_flow(self) -> None:
        coordinator, runtime_state_store, _ref_store = self._build_coordinator()

        open_result = coordinator.execute(
            self.control_command_assembler.assemble(
                profile_name="user",
                kind="open-tab",
                payload={"url": "https://example.org"},
            )
        )
        click_result = coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="click",
                ref="e12",
            )
        )

        self.assertTrue(open_result.ok)
        self.assertIsNotNone(open_result.value.ws_url)
        self.assertIsNotNone(open_result.value.json_endpoints)
        self.assertTrue(click_result.ok)
        self.assertEqual(click_result.value["engine"], "cdp-backed-playwright")
        self.assertEqual(click_result.value["control_family"], "cdp-control")
        self.assertEqual(click_result.value["profile"], "user")
        self.assertEqual(click_result.value["ref"], "e12")

        runtime_state = runtime_state_store.get(profile_name="user")
        self.assertIsNotNone(runtime_state)
        self.assertEqual(runtime_state.attachment_status, "attached")
        self.assertEqual(runtime_state.browser_ref, "cdp:user")
        self.assertEqual(runtime_state.running_pid, 1)

    def test_execution_coordinator_rejects_page_action_via_engine_registry_dispatch(self) -> None:
        runtime_state_store = InMemoryBrowserRuntimeStateStore()
        ref_store = InMemoryBrowserRefStore()
        coordinator = BrowserExecutionCoordinatorService(
            system_config_store=InMemoryBrowserSystemConfigStore(self.system),
            profile_resolver=self.profile_resolver,
            capabilities_resolver=self.capabilities_resolver,
            runtime_state_store=runtime_state_store,
            ref_store=ref_store,
            execution_planner=self.execution_planner,
            engine_registry=StaticBrowserEngineRegistry(
                cdp_control=InMemoryCdpControlEngine(),
                cdp_backed_playwright=_UnsupportedCdpActionEngine(),
            ),
            tab_ops_factory=self.tab_ops_factory,
            selection_ops_factory=self.selection_ops_factory,
        )

        with self.assertRaises(BrowserValidationError) as context:
            coordinator.execute(
                self.page_action_assembler.assemble(
                    profile_name="crxzipple",
                    kind="click",
                    selector="#submit",
                )
            )

        self.assertIn("does not support 'click'", str(context.exception))

    def test_existing_session_unsupported_download_comes_from_cdp_action_engine(self) -> None:
        runtime_state_store = InMemoryBrowserRuntimeStateStore()
        ref_store = InMemoryBrowserRefStore()
        coordinator = BrowserExecutionCoordinatorService(
            system_config_store=InMemoryBrowserSystemConfigStore(self.system),
            profile_resolver=self.profile_resolver,
            capabilities_resolver=self.capabilities_resolver,
            runtime_state_store=runtime_state_store,
            ref_store=ref_store,
            execution_planner=self.execution_planner,
            engine_registry=StaticBrowserEngineRegistry(
                cdp_control=InMemoryCdpControlEngine(),
                cdp_backed_playwright=_UnsupportedCdpActionEngine(),
            ),
            tab_ops_factory=self.tab_ops_factory,
            selection_ops_factory=self.selection_ops_factory,
        )

        with self.assertRaises(BrowserValidationError) as context:
            coordinator.execute(
                self.page_action_assembler.assemble(
                    profile_name="user",
                    kind="download",
                    ref="r1",
                )
            )

        self.assertIn("does not support 'download'", str(context.exception))

    def test_execution_coordinator_close_tab_clears_last_target(self) -> None:
        coordinator, runtime_state_store, ref_store = self._build_coordinator()

        open_result = coordinator.execute(
            self.control_command_assembler.assemble(
                profile_name="crxzipple",
                kind="open-tab",
                payload={"url": "https://example.net"},
            )
        )
        ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id=open_result.target_id or "",
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    selector="#submit",
                    label="Submit",
                ),
            ),
        )
        runtime_state = runtime_state_store.get(profile_name="crxzipple")
        self.assertIsNotNone(runtime_state)
        assert runtime_state is not None
        runtime_state.remember_target(open_result.target_id)
        runtime_state.remember_page_action(
            target_id=open_result.target_id or "",
            action_kind="snapshot",
        )
        runtime_state_store.save(runtime_state)
        close_result = coordinator.execute(
            self.control_command_assembler.assemble(
                profile_name="crxzipple",
                kind="close-tab",
                target_id=open_result.target_id,
            )
        )
        list_result = coordinator.execute(
            self.control_command_assembler.assemble(
                profile_name="crxzipple",
                kind="list-tabs",
            )
        )

        self.assertTrue(close_result.ok)
        self.assertEqual(close_result.target_id, open_result.target_id)
        self.assertEqual(list_result.value, ())

        runtime_state = runtime_state_store.get(profile_name="crxzipple")
        self.assertIsNotNone(runtime_state)
        self.assertIsNone(runtime_state.last_target_id)
        self.assertIsNone(runtime_state.page_state(target_id=open_result.target_id or ""))
        self.assertEqual(
            ref_store.get_tab_refs(
                profile_name="crxzipple",
                target_id=open_result.target_id or "",
            ),
            (),
        )

    def test_execution_coordinator_requires_payload_url_for_open_tab(self) -> None:
        coordinator, _runtime_state_store, _ref_store = self._build_coordinator()

        with self.assertRaises(BrowserValidationError):
            coordinator.execute(
                self.control_command_assembler.assemble(
                    profile_name="crxzipple",
                    kind="open-tab",
                )
            )

    def test_profile_admin_service_manages_profiles_and_default(self) -> None:
        admin, system_store, runtime_state_store, ref_store = self._build_profile_admin()
        runtime_state_store.save(
            BrowserProfileRuntimeState(
                profile_name="remote",
                attachment_status="closed",
            )
        )
        ref_store.save_tab_refs(
            profile_name="remote",
            target_id="tab-9",
            refs=(
                BrowserStoredRef(
                    ref="r9",
                    selector="#remote",
                ),
            ),
        )

        created = admin.create_profile(
            name="work",
            cdp_url="http://browser.example:9555",
            set_as_default=True,
        )
        self.assertEqual(created.default_profile, "work")
        self.assertEqual([profile.name for profile in created.profiles], ["crxzipple", "user", "remote", "work"])

        updated = admin.update_profile(
            profile_name="work",
            user_data_dir="/tmp/work-profile",
            attach_only=True,
        )
        work = next(profile for profile in updated.profiles if profile.name == "work")
        self.assertEqual(work.user_data_dir, "/tmp/work-profile")
        self.assertTrue(work.attach_only)

        disabled = admin.disable_profile(profile_name="work")
        work = next(profile for profile in disabled.profiles if profile.name == "work")
        self.assertFalse(work.enabled)

        enabled = admin.enable_profile(profile_name="work")
        work = next(profile for profile in enabled.profiles if profile.name == "work")
        self.assertTrue(work.enabled)

        switched = admin.set_default_profile(profile_name="user")
        self.assertEqual(switched.default_profile, "user")

        deleted = admin.delete_profile(profile_name="remote")
        self.assertEqual([profile.name for profile in deleted.profiles], ["crxzipple", "user", "work"])
        self.assertIsNone(runtime_state_store.get(profile_name="remote"))
        self.assertEqual(
            ref_store.get_tab_refs(profile_name="remote", target_id="tab-9"),
            (),
        )
        self.assertEqual(system_store.load().default_profile, "user")

    def test_profile_admin_rejects_default_or_running_profile_removal(self) -> None:
        admin, _system_store, runtime_state_store, _ref_store = self._build_profile_admin()

        with self.assertRaisesRegex(BrowserValidationError, "default browser profile"):
            admin.delete_profile(profile_name="crxzipple")

        runtime_state_store.save(
            BrowserProfileRuntimeState(
                profile_name="remote",
                attachment_status="attached",
                browser_ref="cdp:remote",
            )
        )

        with self.assertRaisesRegex(BrowserValidationError, "while it is running"):
            admin.delete_profile(profile_name="remote")
        with self.assertRaisesRegex(BrowserValidationError, "while it is running"):
            admin.disable_profile(profile_name="remote")

    def test_profile_admin_emits_profile_events(self) -> None:
        system_store = InMemoryBrowserSystemConfigStore(self.system)
        events: list[tuple[str, dict[str, object]]] = []
        admin = BrowserProfileAdminService(
            system_config_store=system_store,
            runtime_state_store=InMemoryBrowserRuntimeStateStore(),
            ref_store=InMemoryBrowserRefStore(),
            event_emitter=lambda event_name, payload: events.append((event_name, payload)),
        )

        admin.create_profile(name="work")
        admin.disable_profile(profile_name="work")
        admin.enable_profile(profile_name="work")
        admin.set_default_profile(profile_name="user")
        admin.delete_profile(profile_name="work")

        event_names = [event_name for event_name, _payload in events]
        self.assertIn("browser.profile.created", event_names)
        self.assertIn("browser.profile.updated", event_names)
        self.assertIn("browser.profile.disabled", event_names)
        self.assertIn("browser.profile.enabled", event_names)
        self.assertIn("browser.profile.deleted", event_names)
        disabled_event = next(
            payload for event_name, payload in events if event_name == "browser.profile.disabled"
        )
        self.assertEqual(disabled_event["profile_name"], "work")
        self.assertEqual(disabled_event["status"], "disabled")
        self.assertEqual(disabled_event["changed_fields"], ["enabled"])

    def test_profile_admin_records_sanitized_egress_and_emits_event(self) -> None:
        system_store = InMemoryBrowserSystemConfigStore(self.system)
        runtime_state_store = InMemoryBrowserRuntimeStateStore()
        events: list[tuple[str, dict[str, object]]] = []
        admin = BrowserProfileAdminService(
            system_config_store=system_store,
            runtime_state_store=runtime_state_store,
            ref_store=InMemoryBrowserRefStore(),
            event_emitter=lambda event_name, payload: events.append((event_name, payload)),
        )

        state = admin.record_profile_egress(
            profile_name="crxzipple",
            result={
                "status": "ready",
                "ip": "203.0.113.44",
                "url": "https://example.com/ip",
                "http_status": 200,
                "reason": "x" * 300,
                "secret": "must-not-leak",
            },
        )

        self.assertEqual(state.profile_name, "crxzipple")
        stored = runtime_state_store.get(profile_name="crxzipple")
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.metadata["proxy_egress_status"], "ready")
        self.assertEqual(stored.metadata["proxy_egress_ip"], "203.0.113.44")
        egress = stored.metadata["proxy_egress"]
        self.assertNotIn("secret", egress)
        self.assertEqual(len(egress["reason"]), 240)
        event_name, event = events[-1]
        self.assertEqual(event_name, "browser.profile.updated")
        self.assertEqual(event["status"], "egress_checked")
        self.assertEqual(event["changed_fields"], ["proxy_egress"])
        self.assertEqual(event["proxy_egress_status"], "ready")
        self.assertEqual(event["proxy_egress_ip"], "203.0.113.44")
        self.assertIn("proxy_egress_checked_at", event)

    def test_execution_coordinator_navigate_clears_tab_refs(self) -> None:
        coordinator, _runtime_state_store, ref_store = self._build_coordinator()

        open_result = coordinator.execute(
            self.control_command_assembler.assemble(
                profile_name="crxzipple",
                kind="open-tab",
                payload={"url": "https://example.com/start"},
            )
        )
        target_id = open_result.target_id or ""
        ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id=target_id,
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    selector="#submit",
                ),
            ),
        )
        runtime_state = coordinator.runtime_state_store.get(profile_name="crxzipple")
        self.assertIsNotNone(runtime_state)
        assert runtime_state is not None
        runtime_state.remember_target(target_id)
        runtime_state.remember_page_action(
            target_id=target_id,
            action_kind="snapshot",
        )
        coordinator.runtime_state_store.save(runtime_state)

        navigate_result = coordinator.execute(
            self.control_command_assembler.assemble(
                profile_name="crxzipple",
                kind="navigate",
                target_id=target_id,
                payload={"url": "https://example.com/next"},
            )
        )

        self.assertTrue(navigate_result.ok)
        self.assertEqual(
            ref_store.get_tab_refs(profile_name="crxzipple", target_id=target_id),
            (),
        )
        runtime_state = coordinator.runtime_state_store.get(profile_name="crxzipple")
        self.assertIsNotNone(runtime_state)
        self.assertEqual(
            runtime_state.page_state(target_id=target_id),
            {
                "page_generation": 2,
                "page_generation_reason": "navigate",
            },
        )

    def test_runtime_state_can_restore_page_ref_session_from_stored_refs(self) -> None:
        runtime_state = BrowserProfileRuntimeState(profile_name="crxzipple")

        restored = runtime_state.restore_page_ref_session(
            target_id="tab-1",
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    selector="#submit",
                    generation=3,
                    snapshot_format="role",
                    frame_path=(0,),
                    label="Submit",
                ),
            ),
        )

        self.assertTrue(restored)
        self.assertEqual(
            runtime_state.page_state(target_id="tab-1"),
            {
                "last_action_kind": "snapshot",
                "page_generation": 1,
                "current_ref_generation": 3,
                "snapshot_generation": 3,
                "last_snapshot_format": "role",
                "last_snapshot_ref_count": 1,
                "last_snapshot_frame_count": 1,
                "ref_session_restored": True,
            },
        )

    def test_runtime_state_tracks_active_overlay_with_optional_source_binding(self) -> None:
        runtime_state = BrowserProfileRuntimeState(profile_name="crxzipple")

        runtime_state.remember_active_overlay(
            target_id="tab-1",
            overlay_selector=".city-autocomplete-list",
            source_selector="#depart-city",
            source_scope_selector="#depart-pane",
        )

        self.assertEqual(
            runtime_state.active_overlay_selector(target_id="tab-1"),
            ".city-autocomplete-list",
        )
        self.assertEqual(
            runtime_state.active_overlay_selector(
                target_id="tab-1",
                source_selectors=("#depart-city",),
            ),
            ".city-autocomplete-list",
        )
        self.assertEqual(
            runtime_state.active_overlay_selector(
                target_id="tab-1",
                source_scope_selectors=("#depart-pane",),
            ),
            ".city-autocomplete-list",
        )
        self.assertIsNone(
            runtime_state.active_overlay_selector(
                target_id="tab-1",
                source_selectors=("#arrival-city",),
            )
        )

        runtime_state.clear_active_overlay(target_id="tab-1")
        self.assertEqual(
            runtime_state.active_overlay_selector(
                target_id="tab-1",
                source_selectors=("#depart-city",),
            ),
            ".city-autocomplete-list",
        )
        self.assertIsNone(runtime_state.active_overlay_selector(target_id="tab-1"))

    def test_execution_coordinator_restores_ref_session_before_ref_action(self) -> None:
        class _InspectingActionEngine:
            family = "cdp-backed-playwright"

            def __init__(self) -> None:
                self.seen_page_state = None

            def supports(self, *, command):  # noqa: ANN001, ANN201
                del command
                return True

            def execute(self, *, plan, runtime_state, tab, command):  # noqa: ANN001, ANN201
                self.seen_page_state = runtime_state.page_state(target_id=tab.target_id if tab else "")
                return BrowserActionResult(
                    command=command,
                    ok=True,
                    target_id=tab.target_id if tab is not None else None,
                    value={"restored": self.seen_page_state},
                    message="ok",
                )

            def clear_profile(self, *, profile_name):  # noqa: ANN001, ANN201
                del profile_name

        runtime_state_store = InMemoryBrowserRuntimeStateStore()
        ref_store = InMemoryBrowserRefStore()
        action_engine = _InspectingActionEngine()
        coordinator = BrowserExecutionCoordinatorService(
            system_config_store=InMemoryBrowserSystemConfigStore(self.system),
            profile_resolver=self.profile_resolver,
            capabilities_resolver=self.capabilities_resolver,
            runtime_state_store=runtime_state_store,
            ref_store=ref_store,
            execution_planner=self.execution_planner,
            engine_registry=StaticBrowserEngineRegistry(
                cdp_control=InMemoryCdpControlEngine(),
                cdp_backed_playwright=action_engine,
            ),
            tab_ops_factory=self.tab_ops_factory,
            selection_ops_factory=self.selection_ops_factory,
        )

        open_result = coordinator.execute(
            self.control_command_assembler.assemble(
                profile_name="crxzipple",
                kind="open-tab",
                payload={"url": "https://example.com/start"},
            )
        )
        target_id = open_result.target_id or ""
        ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id=target_id,
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    selector="#submit",
                    generation=3,
                    snapshot_format="role",
                    frame_path=(0,),
                    label="Submit",
                ),
            ),
        )

        click_result = coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="crxzipple",
                kind="click",
                target_id=target_id,
                ref="r1",
                payload={"button": "left"},
            )
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(
            action_engine.seen_page_state,
            {
                "last_action_kind": "snapshot",
                "page_generation": 1,
                "page_generation_reason": "open-tab",
                "current_ref_generation": 3,
                "snapshot_generation": 3,
                "last_snapshot_format": "role",
                "last_snapshot_ref_count": 1,
                "last_snapshot_frame_count": 1,
                "ref_session_restored": True,
            },
        )
        runtime_state = runtime_state_store.get(profile_name="crxzipple")
        self.assertIsNotNone(runtime_state)
        assert runtime_state is not None
        self.assertEqual(runtime_state.page_state(target_id=target_id), action_engine.seen_page_state)


if __name__ == "__main__":
    unittest.main()
