from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from crxzipple.modules.browser.domain import (
    BrowserActionTarget,
    BrowserPageActionCommand,
    BrowserProfileRuntimeState,
    BrowserStoredRef,
    BrowserValidationError,
)
from crxzipple.modules.browser.infrastructure import CdpBackedPlaywrightActionEngine
from crxzipple.modules.daemon import DaemonInstance
from tests.unit.browser_playwright_action_support import BrowserPlaywrightActionEngineTestCase


class BrowserPlaywrightLocatorActionsTestCase(BrowserPlaywrightActionEngineTestCase):
    def test_action_engine_prefers_runtime_cdp_url_over_profile_url(self) -> None:
        self.runtime_state.metadata["cdp_base_url"] = "http://localhost:18800"
        click_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="click",
            target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
            payload={"button": "left"},
        )

        result = self.engine.execute(
            plan=self._plan(click_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=click_command,
        )

        self.assertTrue(result.ok)
        self.assertEqual(
            self.session_pool.resolve_calls[-1]["cdp_url"],
            "http://localhost:18800",
        )

    def test_execute_acquires_and_releases_host_daemon_lease_for_local_managed_profile(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            daemon_service = self._build_daemon_service(Path(temp_dir))
            daemon_service.save_instance(
                DaemonInstance(
                    id="browser-host-crxzipple",
                    service_key="host:browser:crxzipple",
                    status="ready",
                    pid=8123,
                    endpoint="http://127.0.0.1:9222",
                )
            )
            engine = CdpBackedPlaywrightActionEngine(
                session_pool=self.session_pool,
                ref_store=self.ref_store,
                daemon_service=daemon_service,
            )
            click_command = BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="click",
                target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
                payload={"button": "left"},
            )

            result = engine.execute(
                plan=self._plan(click_command),
                runtime_state=self.runtime_state,
                tab=self.tab,
                command=click_command,
            )

            self.assertTrue(result.ok)
            leases = daemon_service.list_leases(service_key="host:browser:crxzipple")
            self.assertEqual(leases, ())

    def test_execute_uses_runtime_user_data_dir_for_host_daemon_lease_owner(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            daemon_service = self._build_daemon_service(Path(temp_dir))
            daemon_service.save_instance(
                DaemonInstance(
                    id="browser-host-crxzipple",
                    service_key="host:browser:crxzipple",
                    status="ready",
                    pid=8123,
                    endpoint="http://127.0.0.1:9222",
                )
            )
            user_data_dir = str((Path(temp_dir) / "browser" / "profiles" / "crxzipple" / "userdata").resolve())
            owner_id = f"crxzipple:{hashlib.sha1(user_data_dir.encode('utf-8')).hexdigest()[:8]}"
            lease = daemon_service.acquire_lease(
                service_key="host:browser:crxzipple",
                owner_kind="browser_profile",
                owner_id=owner_id,
                ttl_seconds=60,
                metadata={"profile_name": "crxzipple", "user_data_dir": user_data_dir},
            )
            runtime_state = BrowserProfileRuntimeState(
                profile_name="crxzipple",
                metadata={"user_data_dir": user_data_dir},
            )
            engine = CdpBackedPlaywrightActionEngine(
                session_pool=self.session_pool,
                ref_store=self.ref_store,
                daemon_service=daemon_service,
            )
            click_command = BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="click",
                target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
                payload={"button": "left"},
            )

            result = engine.execute(
                plan=self._plan(click_command),
                runtime_state=runtime_state,
                tab=self.tab,
                command=click_command,
            )

            self.assertTrue(result.ok)
            active_leases = daemon_service.list_leases(service_key="host:browser:crxzipple")
            self.assertEqual(len(active_leases), 1)
            self.assertEqual(active_leases[0].id, lease.id)
            daemon_service.release_lease(lease.id)

    def test_click_falls_back_to_force_when_pointer_events_intercept(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.click_failures["#submit"] = [
            RuntimeError("<div class='overlay'>...</div> intercepts pointer events")
        ]

        click_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="click",
            target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
            payload={"button": "left"},
            timeout_ms=120_000,
        )
        click_result = self.engine.execute(
            plan=self._plan(click_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=click_command,
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(click_result.value["result"]["mode"], "force")
        self.assertEqual(page.operations[0], ("click", "#submit", {"timeout": 2000.0, "button": "left"}, ()))
        self.assertEqual(page.operations[1], ("click", "#submit", {"timeout": 120000.0, "button": "left", "force": True}, ()))

    def test_click_retries_once_when_frame_detaches(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.click_failures["#submit"] = [
            RuntimeError("Frame was detached"),
        ]

        click_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="click",
            target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
            payload={"button": "left"},
            timeout_ms=1500,
        )

        click_result = self.engine.execute(
            plan=self._plan(click_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=click_command,
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(
            [operation[0] for operation in page.operations if operation[0] == "click"],
            ["click", "click"],
        )

    def test_stale_ref_rebinds_to_semantic_role_locator(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#archive-primary",
                "resolved_selector": "#archive-primary",
                "label": "Archive",
                "role": "button",
                "text": "Archive",
                "tag": "button",
            },
            {
                "selector": "#archive-secondary",
                "resolved_selector": "#archive-secondary",
                "label": "Archive",
                "role": "button",
                "text": "Archive",
                "tag": "button",
            },
        ]
        self.ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    selector="#archive-secondary-legacy",
                    role="button",
                    label="Archive",
                    nth=1,
                    generation=1,
                    snapshot_format="interactive",
                ),
            ),
        )
        self.runtime_state.remember_page_snapshot(
            target_id="tab-1",
            generation=2,
            snapshot_format="interactive",
            ref_count=1,
            frame_count=1,
        )

        click_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="click",
            target=BrowserActionTarget(target_id="tab-1", ref="r1"),
            payload={},
        )
        click_result = self.engine.execute(
            plan=self._plan(click_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=click_command,
        )

        self.assertTrue(click_result.ok)
        self.assertIn(
            ("click", "#archive-secondary", {"timeout": 2000.0}, ()),
            page.operations,
        )

    def test_click_selector_supports_scope_selector_and_ordinal(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": ".result",
                "resolved_selector": "#left .result:nth-of-type(1)",
                "label": "Open",
                "role": "button",
                "text": "Open",
                "tag": "button",
                "scope_selector": "#left",
            },
            {
                "selector": ".result",
                "resolved_selector": "#right .result:nth-of-type(1)",
                "label": "Open",
                "role": "button",
                "text": "Open",
                "tag": "button",
                "scope_selector": "#right",
            },
            {
                "selector": ".result",
                "resolved_selector": "#right .result:nth-of-type(2)",
                "label": "Open",
                "role": "button",
                "text": "Open",
                "tag": "button",
                "scope_selector": "#right",
            },
        ]

        click_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="click",
            target=BrowserActionTarget(target_id="tab-1", selector=".result"),
            payload={"scope_selector": "#right", "ordinal": 1},
        )
        click_result = self.engine.execute(
            plan=self._plan(click_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=click_command,
        )

        self.assertTrue(click_result.ok)
        self.assertIn(
            ("click", "#right .result:nth-of-type(2)", {"timeout": 2000.0}, ()),
            page.operations,
        )

    def test_fill_selector_prefers_focused_candidate_when_selector_matches_multiple_inputs(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        selector = "input[aria-label*='To'], textarea[aria-label*='To'], input[peoplekit-id]"
        page.interactive_items = [
            {
                "selector": selector,
                "resolved_selector": "#compose-a input.to",
                "label": "To recipients",
                "role": "combobox",
                "tag": "input",
                "visible": True,
            },
            {
                "selector": selector,
                "resolved_selector": "#compose-b input.to",
                "label": "To recipients",
                "role": "combobox",
                "tag": "input",
                "visible": True,
                "focused": True,
            },
        ]

        fill_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="fill",
            target=BrowserActionTarget(target_id="tab-1", selector=selector),
            payload={"text": "657658113@qq.com"},
        )
        fill_result = self.engine.execute(
            plan=self._plan(fill_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=fill_command,
        )

        self.assertTrue(fill_result.ok)
        self.assertIn(
            ("fill", "#compose-b input.to", "657658113@qq.com", {}, ()),
            page.operations,
        )

    def test_wait_selector_prefers_focused_candidate_when_selector_matches_multiple_inputs(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        selector = "input[aria-label*='To'], textarea[aria-label*='To'], input[peoplekit-id]"
        page.interactive_items = [
            {
                "selector": selector,
                "resolved_selector": "#compose-a input.to",
                "label": "To recipients",
                "role": "combobox",
                "tag": "input",
                "visible": True,
            },
            {
                "selector": selector,
                "resolved_selector": "#compose-b input.to",
                "label": "To recipients",
                "role": "combobox",
                "tag": "input",
                "visible": True,
                "focused": True,
            },
        ]

        wait_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="wait",
            target=BrowserActionTarget(target_id="tab-1", selector=selector),
            payload={"state": "visible"},
        )
        wait_result = self.engine.execute(
            plan=self._plan(wait_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=wait_command,
        )

        self.assertTrue(wait_result.ok)
        self.assertIn(
            ("wait", "#compose-b input.to", {"state": "visible"}, ()),
            page.operations,
        )

    def test_fill_ref_rejects_non_editable_link_target_with_clear_error(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#skip-link",
                "resolved_selector": "#skip-link",
                "label": "Skip to content",
                "role": "link",
                "text": "Skip to content",
                "tag": "a",
                "visible": True,
            }
        ]
        self.ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
            refs=(
                BrowserStoredRef(
                    ref="r13",
                    role="link",
                    label="Skip to content",
                    generation=1,
                    snapshot_format="interactive",
                ),
            ),
        )
        self.runtime_state.remember_page_snapshot(
            target_id="tab-1",
            generation=1,
            snapshot_format="interactive",
            ref_count=1,
            frame_count=1,
        )

        fill_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="fill",
            target=BrowserActionTarget(target_id="tab-1", ref="r13"),
            payload={"text": "657658113@qq.com"},
        )

        with self.assertRaises(BrowserValidationError) as exc_info:
            self.engine.execute(
                plan=self._plan(fill_command),
                runtime_state=self.runtime_state,
                tab=self.tab,
                command=fill_command,
            )

        self.assertIn("non-editable element", str(exc_info.exception))
        self.assertIn("role=link", str(exc_info.exception))

    def test_fill_readonly_combobox_selects_matching_overlay_candidate(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.active_overlay_selector = ".city-overlay"
        page.interactive_items = [
            {
                "selector": "#depart-city",
                "resolved_selector": "#depart-city",
                "label": "Departure city",
                "role": "combobox",
                "tag": "input",
                "readonly": True,
                "visible": True,
            },
            {
                "selector": ".city-overlay .option-kmg",
                "resolved_selector": ".city-overlay .option-kmg",
                "label": "Kunming",
                "role": "option",
                "text": "Kunming",
                "tag": "li",
                "scope_selector": ".city-overlay",
                "source_selector": "#depart-city",
                "visible": True,
            },
        ]

        fill_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="fill",
            target=BrowserActionTarget(target_id="tab-1", selector="#depart-city"),
            payload={"text": "Kunming"},
        )
        fill_result = self.engine.execute(
            plan=self._plan(fill_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=fill_command,
        )

        self.assertTrue(fill_result.ok)
        result = fill_result.value["result"]
        self.assertEqual(result["kind"], "fill")
        self.assertEqual(result["input_mode"], "custom-overlay")
        self.assertEqual(result["selected"]["text"], "Kunming")
        self.assertIn(
            ("click", "#depart-city", {"button": "left", "timeout": 2000.0}, ()),
            page.operations,
        )
        self.assertIn(
            ("click", ".city-overlay .option-kmg", {"timeout": 2000.0}, ()),
            page.operations,
        )

    def test_wait_evaluate_snapshot_and_screenshot_return_structured_results(self) -> None:
        wait_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="wait",
            target=BrowserActionTarget(target_id="tab-1", selector="#ready"),
            payload={"state": "visible"},
        )
        wait_result = self.engine.execute(
            plan=self._plan(wait_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=wait_command,
        )

        evaluate_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="evaluate",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"expression": "() => 42"},
        )
        evaluate_result = self.engine.execute(
            plan=self._plan(evaluate_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=evaluate_command,
        )

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "html"},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        screenshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="screenshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"type": "png"},
        )
        screenshot_result = self.engine.execute(
            plan=self._plan(screenshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=screenshot_command,
        )

        self.assertEqual(wait_result.value["result"]["kind"], "wait")
        self.assertEqual(evaluate_result.value["result"]["expression"], "() => 42")
        self.assertEqual(snapshot_result.value["result"]["format"], "html")
        self.assertEqual(screenshot_result.value["result"]["content_type"], "image/png")
        self.assertEqual(screenshot_result.value["result"]["encoding"], "base64")

    def test_evaluate_retries_once_when_execution_context_is_destroyed(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.evaluate_failures = [
            RuntimeError("Execution context was destroyed, most likely because of a navigation."),
        ]

        evaluate_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="evaluate",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"expression": "() => 42"},
        )

        evaluate_result = self.engine.execute(
            plan=self._plan(evaluate_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=evaluate_command,
        )

        self.assertTrue(evaluate_result.ok)
        self.assertEqual(evaluate_result.value["result"]["expression"], "() => 42")
        self.assertEqual(
            [operation[0] for operation in page.operations if operation[0] == "evaluate"],
            ["evaluate", "evaluate"],
        )

    def test_wait_text_supports_scope_exact_and_ordinal(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#pane-a-done",
                "resolved_selector": "#pane-a-done",
                "label": "Done",
                "role": "status",
                "text": "Done",
                "tag": "div",
                "scope_selector": "#pane-a",
            },
            {
                "selector": "#pane-b-done-1",
                "resolved_selector": "#pane-b-done-1",
                "label": "Done",
                "role": "status",
                "text": "Done",
                "tag": "div",
                "scope_selector": "#pane-b",
            },
            {
                "selector": "#pane-b-done-2",
                "resolved_selector": "#pane-b-done-2",
                "label": "Done",
                "role": "status",
                "text": "Done",
                "tag": "div",
                "scope_selector": "#pane-b",
            },
        ]

        wait_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="wait",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "text": "Done",
                "scope_selector": "#pane-b",
                "exact": True,
                "ordinal": 1,
            },
        )
        wait_result = self.engine.execute(
            plan=self._plan(wait_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=wait_command,
        )

        self.assertTrue(wait_result.ok)
        self.assertIn(
            ("wait", "#pane-b-done-2", {}, ()),
            page.operations,
        )

    def test_evaluate_supports_fn_alias_and_ref_scoped_execution(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        self.ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    selector="#query",
                    generation=1,
                    snapshot_format="interactive",
                    label="Query",
                    role="textbox",
                ),
            ),
        )
        self.runtime_state.remember_page_snapshot(
            target_id="tab-1",
            generation=1,
            snapshot_format="interactive",
            ref_count=1,
            frame_count=1,
        )

        evaluate_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="evaluate",
            target=BrowserActionTarget(target_id="tab-1", ref="r1"),
            payload={"fn": "(el) => el.tagName", "arg": {"debug": True}},
        )
        evaluate_result = self.engine.execute(
            plan=self._plan(evaluate_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=evaluate_command,
        )

        self.assertEqual(evaluate_result.value["result"]["selector"], "#query")
        self.assertEqual(evaluate_result.value["result"]["expression"], "(el) => el.tagName")
        self.assertEqual(evaluate_result.value["result"]["arg"], {"debug": True})
        self.assertIn(
            ("locator.evaluate", "#query", "(el) => el.tagName", {"debug": True}, ()),
            page.operations,
        )

    def test_evaluate_supports_script_alias(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")

        evaluate_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="evaluate",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"script": "() => document.title"},
        )
        evaluate_result = self.engine.execute(
            plan=self._plan(evaluate_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=evaluate_command,
        )

        self.assertEqual(evaluate_result.value["result"]["expression"], "() => document.title")
        self.assertIn(("evaluate", "() => document.title", None), page.operations)

    def test_wait_can_target_text_without_selector(self) -> None:
        wait_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="wait",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"text": "Ready"},
            timeout_ms=2500,
        )

        wait_result = self.engine.execute(
            plan=self._plan(wait_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=wait_command,
        )

        self.assertEqual(wait_result.value["result"]["kind"], "wait")
        self.assertEqual(wait_result.value["result"]["text"], ["Ready"])
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        self.assertIn(("wait", "text=Ready", {"timeout": 2500.0}, ()), page.operations)

    def test_wait_supports_text_gone_load_state_and_fn_alias(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")

        text_gone_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="wait",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"text_gone": "Loading"},
                    timeout_ms=2000,
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="wait",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"text_gone": "Loading"},
                timeout_ms=2000,
            ),
        )
        load_state_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="wait",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"load_state": "domcontentloaded"},
                    timeout_ms=2000,
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="wait",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"load_state": "domcontentloaded"},
                timeout_ms=2000,
            ),
        )
        fn_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="wait",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"fn": "() => window.ready === true"},
                    timeout_ms=2000,
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="wait",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"fn": "() => window.ready === true"},
                timeout_ms=2000,
            ),
        )

        self.assertEqual(text_gone_result.value["result"]["text_gone"], ["Loading"])
        self.assertEqual(load_state_result.value["result"]["load_state"], "domcontentloaded")
        self.assertEqual(fn_result.value["result"]["expression"], "() => window.ready === true")
        self.assertIn(("wait", "text=Loading", {"state": "hidden", "timeout": 2000.0}, ()), page.operations)
        self.assertIn(("wait_for_load_state", "domcontentloaded", {"timeout": 2000.0}), page.operations)
        self.assertIn(("wait_for_function", "() => window.ready === true", None, {"timeout": 2000.0}), page.operations)

    def test_wait_text_prefers_bound_active_overlay_context(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": ".page-option",
                "resolved_selector": ".page-option",
                "label": "Hangzhou",
                "role": "option",
                "text": "Hangzhou",
                "tag": "li",
            },
            {
                "selector": ".overlay-option",
                "resolved_selector": ".overlay-option",
                "label": "Hangzhou",
                "role": "option",
                "text": "Hangzhou",
                "tag": "li",
                "scope_selector": ".city-autocomplete-list",
            },
        ]
        self.runtime_state.remember_active_overlay(
            target_id="tab-1",
            overlay_selector=".city-autocomplete-list",
            source_selector="#depart-city",
        )

        wait_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="wait",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"text": "Hangzhou"},
            timeout_ms=2000,
        )
        wait_result = self.engine.execute(
            plan=self._plan(wait_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=wait_command,
        )

        self.assertTrue(wait_result.ok)
        self.assertIn(
            ("wait", ".overlay-option", {"timeout": 2000.0}, ()),
            page.operations,
        )


    def test_fill_supports_form_fields_by_ref(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#query",
                "label": "Query",
                "role": "textbox",
                "text": "",
                "tag": "input",
            },
            {
                "selector": "#newsletter",
                "label": "Newsletter",
                "role": "checkbox",
                "text": "",
                "tag": "input",
            },
        ]
        self.ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    selector="#query",
                    generation=1,
                    snapshot_format="interactive",
                    label="Query",
                    role="textbox",
                ),
                BrowserStoredRef(
                    ref="r2",
                    selector="#newsletter",
                    generation=1,
                    snapshot_format="interactive",
                    label="Newsletter",
                    role="checkbox",
                ),
            ),
        )
        self.runtime_state.remember_page_snapshot(
            target_id="tab-1",
            generation=1,
            snapshot_format="interactive",
            ref_count=2,
            frame_count=1,
        )

        fill_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="fill",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "fields": [
                    {"ref": "r1", "type": "text", "value": "hello"},
                    {"ref": "r2", "type": "checkbox", "value": True},
                ]
            },
        )

        fill_result = self.engine.execute(
            plan=self._plan(fill_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=fill_command,
        )

        self.assertEqual(fill_result.value["result"]["kind"], "fill")
        self.assertEqual(len(fill_result.value["result"]["fields"]), 2)
        self.assertIn(("fill", "#query", "hello", {}, ()), page.operations)
        self.assertIn(("set_checked", "#newsletter", True, {}, ()), page.operations)

    def test_drag_supports_start_and_end_aliases(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#from",
                "label": "From",
                "role": "button",
                "text": "From",
                "tag": "button",
            },
            {
                "selector": "#to",
                "label": "To",
                "role": "button",
                "text": "To",
                "tag": "button",
            },
        ]
        self.ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    selector="#from",
                    generation=1,
                    snapshot_format="interactive",
                    label="From",
                    role="button",
                ),
                BrowserStoredRef(
                    ref="r2",
                    selector="#to",
                    generation=1,
                    snapshot_format="interactive",
                    label="To",
                    role="button",
                ),
            ),
        )
        self.runtime_state.remember_page_snapshot(
            target_id="tab-1",
            generation=1,
            snapshot_format="interactive",
            ref_count=2,
            frame_count=1,
        )

        drag_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="drag",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"start_ref": "r1", "end_ref": "r2"},
        )

        drag_result = self.engine.execute(
            plan=self._plan(drag_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=drag_command,
        )

        self.assertTrue(drag_result.ok)
        self.assertEqual(drag_result.value["result"]["start_ref"], "r1")
        self.assertEqual(drag_result.value["result"]["end_ref"], "r2")
        self.assertIn(("drag", "#from", "#to", {}, ()), page.operations)

    def test_resize_updates_viewport(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")

        resize_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="resize",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"width": 800, "height": 600},
        )

        resize_result = self.engine.execute(
            plan=self._plan(resize_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=resize_command,
        )

        self.assertTrue(resize_result.ok)
        self.assertEqual(resize_result.value["result"]["width"], 800)
        self.assertEqual(resize_result.value["result"]["height"], 600)
        self.assertEqual(page.viewport, {"width": 800, "height": 600})
        self.assertIn(("set_viewport_size", {"width": 800, "height": 600}), page.operations)

    def test_batch_executes_actions_in_order(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")

        batch_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="batch",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "actions": [
                    {"kind": "resize", "width": 800, "height": 600},
                    {"kind": "evaluate", "fn": "() => document.title"},
                ]
            },
        )

        batch_result = self.engine.execute(
            plan=self._plan(batch_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=batch_command,
        )

        self.assertTrue(batch_result.ok)
        self.assertEqual(batch_result.value["result"]["kind"], "batch")
        self.assertEqual(len(batch_result.value["result"]["results"]), 2)
        self.assertEqual(batch_result.value["result"]["results"][0]["kind"], "resize")
        self.assertEqual(batch_result.value["result"]["results"][1]["kind"], "evaluate")
        self.assertEqual(page.operations[0], ("set_viewport_size", {"width": 800, "height": 600}))
        self.assertEqual(page.operations[1][0], "evaluate")

    def test_batch_stop_on_error_false_continues_after_failure(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.click_failures["#submit"] = [RuntimeError("boom")]

        batch_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="batch",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "actions": [
                    {"kind": "click", "selector": "#submit"},
                    {"kind": "resize", "width": 640, "height": 480},
                ],
                "stop_on_error": False,
            },
        )

        batch_result = self.engine.execute(
            plan=self._plan(batch_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=batch_command,
        )

        self.assertTrue(batch_result.ok)
        results = batch_result.value["result"]["results"]
        self.assertFalse(results[0]["ok"])
        self.assertEqual(results[0]["kind"], "click")
        self.assertTrue(results[1]["ok"])
        self.assertEqual(results[1]["kind"], "resize")
        self.assertIn(("set_viewport_size", {"width": 640, "height": 480}), page.operations)



if __name__ == "__main__":
    unittest.main()
