from __future__ import annotations

import unittest

from crxzipple.modules.browser.domain import (
    BrowserActionTarget,
    BrowserExecutionPlan,
    BrowserPageActionCommand,
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
    CdpBackedPlaywrightActionEngine,
    InMemoryBrowserRefStore,
)
from tests.unit.support import FakePlaywrightCdpSessionPool


class BrowserPlaywrightActionEngineTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.session_pool = FakePlaywrightCdpSessionPool()
        self.ref_store = InMemoryBrowserRefStore()
        self.engine = CdpBackedPlaywrightActionEngine(
            session_pool=self.session_pool,
            ref_store=self.ref_store,
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

    def test_click_and_type_use_locator_actions(self) -> None:
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

        type_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="type",
            target=BrowserActionTarget(target_id="tab-1", selector="#query"),
            payload={"text": "search"},
        )
        type_result = self.engine.execute(
            plan=self._plan(type_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=type_command,
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(click_result.value["engine"], "cdp-backed-playwright")
        self.assertEqual(click_result.value["selector"], "#submit")
        self.assertEqual(type_result.value["result"]["text"], "search")

        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        self.assertEqual(page.operations[0][0], "click")
        self.assertIn("type", [operation[0] for operation in page.operations])
        self.assertEqual(click_result.value["result"]["mode"], "direct")

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

    def test_interactive_snapshot_assigns_nth_for_duplicate_semantic_refs(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#message-star-1",
                "resolved_selector": "#message-star-1",
                "label": "Not starred",
                "role": "button",
                "text": "Not starred",
                "tag": "button",
            },
            {
                "selector": "#message-star-2",
                "resolved_selector": "#message-star-2",
                "label": "Not starred",
                "role": "button",
                "text": "Not starred",
                "tag": "button",
            },
        ]

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "interactive", "mode": "wide"},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        refs = snapshot_result.value["result"]["value"]["refs"]
        self.assertEqual(refs[0]["nth"], 0)
        self.assertEqual(refs[1]["nth"], 1)

    def test_snapshot_can_focus_active_overlay(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.active_overlay_selector = ".city-autocomplete-list"
        page.interactive_items = [
            {
                "selector": "#page-search",
                "resolved_selector": "#page-search",
                "label": "Search",
                "role": "button",
                "text": "Search",
                "tag": "button",
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

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "interactive", "active_overlay": True},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        self.assertTrue(snapshot_result.ok)
        self.assertEqual(snapshot_result.value["result"]["root_selector"], ".city-autocomplete-list")
        refs = snapshot_result.value["result"]["value"]["refs"]
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["label"], "Hangzhou")

    def test_interactive_snapshot_retries_once_when_frame_detaches_during_dom_fallback(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.evaluate_failures = [
            RuntimeError("Frame.evaluate: Frame was detached"),
        ]
        page.interactive_items = [
            {
                "selector": "#compose",
                "resolved_selector": "#compose",
                "label": "Compose",
                "role": "button",
                "text": "Compose",
                "tag": "button",
            }
        ]

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "interactive", "mode": "focused"},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        self.assertTrue(snapshot_result.ok)
        refs = snapshot_result.value["result"]["value"]["refs"]
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["label"], "Compose")
        frame_evaluates = [
            op
            for op in page.operations
            if op[0] == "frame.evaluate"
        ]
        self.assertEqual(len(frame_evaluates), 2)




    def test_snapshot_active_overlay_prefers_bound_overlay_context(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.active_overlay_selector = ".depart-overlay"
        self.runtime_state.remember_active_overlay(
            target_id="tab-1",
            overlay_selector=".depart-overlay",
            source_selector="#depart-city",
        )

        self.runtime_state.remember_active_overlay(
            target_id="tab-1",
            overlay_selector=".arrival-overlay",
            source_selector="#arrival-city",
        )
        page.active_overlay_selector = ".arrival-overlay"
        page.interactive_items = [
            {
                "selector": ".depart-option",
                "resolved_selector": ".depart-option",
                "label": "Hangzhou",
                "role": "option",
                "text": "Hangzhou",
                "tag": "li",
                "scope_selector": ".depart-overlay",
            },
            {
                "selector": ".arrival-option",
                "resolved_selector": ".arrival-option",
                "label": "Kunming",
                "role": "option",
                "text": "Kunming",
                "tag": "li",
                "scope_selector": ".arrival-overlay",
            },
        ]

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "format": "interactive",
                "active_overlay": True,
                "overlay_source_selector": "#depart-city",
            },
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        self.assertTrue(snapshot_result.ok)
        self.assertEqual(snapshot_result.value["result"]["root_selector"], ".depart-overlay")
        refs = snapshot_result.value["result"]["value"]["refs"]
        self.assertEqual(len(refs), 1)
        self.assertEqual(refs[0]["label"], "Hangzhou")

























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

    def test_aria_snapshot_returns_role_tree_text(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = "\n".join(
            [
                '- banner:',
                '  - button "Menu"',
                '  - link "Deals"',
            ]
        )

        snapshot_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "aria"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "aria"},
            ),
        )

        result = snapshot_result.value["result"]
        self.assertEqual(result["format"], "aria")
        self.assertIn('- button "Menu"', result["value"]["snapshot"])
        self.assertEqual(result["frame_count"], 1)
        self.assertEqual(result["ref_count"], 0)

    def test_snapshot_refs_mode_can_select_aria_and_role_views(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#menu",
                "label": "Menu",
                "role": "button",
                "text": "Menu",
                "tag": "button",
            },
        ]
        page.main_frame.aria_snapshot_text = '- button "Menu"'

        aria_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"refs_mode": "aria"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"refs_mode": "aria"},
            ),
        )
        role_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"refs_mode": "role"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"refs_mode": "role"},
            ),
        )

        self.assertEqual(aria_result.value["result"]["format"], "aria")
        self.assertEqual(aria_result.value["result"]["refs_mode"], "aria")
        self.assertEqual(role_result.value["result"]["format"], "role")
        self.assertEqual(role_result.value["result"]["refs_mode"], "role")
        self.assertEqual(role_result.value["result"]["ref_count"], 1)

    def test_snapshot_refs_mode_rejects_conflicting_format(self) -> None:
        with self.assertRaises(BrowserValidationError):
            self.engine.execute(
                plan=self._plan(
                    BrowserPageActionCommand(
                        profile_name="crxzipple",
                        kind="snapshot",
                        target=BrowserActionTarget(target_id="tab-1"),
                        payload={"format": "role", "refs_mode": "aria"},
                    )
                ),
                runtime_state=self.runtime_state,
                tab=self.tab,
                command=BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "role", "refs_mode": "aria"},
                ),
            )

    def test_role_snapshot_persists_role_refs_and_click_can_use_them(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#menu",
                "label": "Menu",
                "role": "button",
                "text": "Menu",
                "tag": "button",
            },
            {
                "selector": "#deals",
                "label": "Deals",
                "role": "link",
                "text": "Deals",
                "tag": "a",
            },
        ]
        page.main_frame.aria_snapshot_text = "\n".join(
            [
                '- banner:',
                '  - button "Menu"',
                '  - link "Deals"',
            ]
        )

        snapshot_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "role"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "role"},
            ),
        )

        result = snapshot_result.value["result"]
        self.assertEqual(result["format"], "role")
        self.assertIn('[ref=r1]', result["value"]["snapshot"])
        self.assertEqual(result["ref_count"], 2)
        self.assertEqual(result["value"]["stats"]["refs"], 2)
        stored_refs = self.ref_store.get_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
        )
        self.assertEqual(
            stored_refs,
            (
                BrowserStoredRef(
                    ref="r1",
                    nth=None,
                    generation=1,
                    snapshot_format="role",
                    label="Menu",
                    role="button",
                    text="Menu",
                    tag="button",
                ),
                BrowserStoredRef(
                    ref="r2",
                    nth=None,
                    generation=1,
                    snapshot_format="role",
                    label="Deals",
                    role="link",
                    text="Deals",
                    tag="link",
                ),
            ),
        )

        click_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="click",
                    target=BrowserActionTarget(target_id="tab-1", ref="r1"),
                    payload={"button": "left"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="click",
                target=BrowserActionTarget(target_id="tab-1", ref="r1"),
                payload={"button": "left"},
            ),
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(click_result.value["selector"], 'role=button[name="Menu"]')
        self.assertEqual(page.operations[-1][0], "click")
        self.assertEqual(page.operations[-1][1], "#menu")

    def test_interactive_snapshot_persists_refs_and_click_can_use_ref(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#submit",
                "label": "Submit",
                "role": "button",
                "text": "Submit",
                "tag": "button",
            },
            {
                "selector": "#query",
                "label": "Search",
                "role": "textbox",
                "text": "",
                "tag": "input",
            },
        ]
        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "interactive"},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        stored_refs = self.ref_store.get_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
        )
        self.assertEqual(
            stored_refs,
            (
                BrowserStoredRef(
                    ref="r1",
                    nth=None,
                    generation=1,
                    snapshot_format="interactive",
                    label="Submit",
                    role="button",
                    text="Submit",
                    tag="button",
                ),
                BrowserStoredRef(
                    ref="r2",
                    nth=None,
                    generation=1,
                    snapshot_format="interactive",
                    label="Search",
                    role="textbox",
                    text="Search",
                    tag="textbox",
                ),
            ),
        )
        self.assertEqual(snapshot_result.value["result"]["format"], "interactive")
        self.assertEqual(snapshot_result.value["result"]["generation"], 1)
        self.assertEqual(snapshot_result.value["result"]["mode"], "efficient")
        self.assertTrue(snapshot_result.value["result"]["compact"])
        self.assertEqual(snapshot_result.value["result"]["depth"], 6)
        self.assertEqual(snapshot_result.value["result"]["value"]["refs"][0]["ref"], "r1")
        self.assertIsNone(snapshot_result.value["result"]["value"]["refs"][0]["selector"])
        self.assertIsNone(snapshot_result.value["result"]["value"]["refs"][0]["nth"])
        self.assertIn('[ref=r1]', snapshot_result.value["result"]["value"]["snapshot"])
        self.assertEqual(snapshot_result.value["result"]["ref_count"], 2)
        self.assertEqual(snapshot_result.value["result"]["frame_count"], 1)
        self.assertEqual(
            self.runtime_state.page_state(target_id="tab-1"),
            {
                "current_ref_generation": 1,
                "last_action_kind": "snapshot",
                "last_snapshot_format": "interactive",
                "last_snapshot_ref_count": 2,
                "last_snapshot_frame_count": 1,
                "ref_session_restored": False,
            },
        )

        click_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="click",
            target=BrowserActionTarget(target_id="tab-1", ref="r1"),
            payload={"button": "left"},
        )
        click_result = self.engine.execute(
            plan=self._plan(click_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=click_command,
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(click_result.value["selector"], 'role=button[name="Submit"]')
        self.assertEqual(page.operations[-1][0], "click")
        self.assertEqual(page.operations[-1][1], "#submit")
        self.assertEqual(
            self.runtime_state.page_state(target_id="tab-1"),
            {
                "current_ref_generation": 1,
                "last_action_kind": "click",
                "last_snapshot_format": "interactive",
                "last_snapshot_ref_count": 2,
                "last_snapshot_frame_count": 1,
                "ref_session_restored": False,
            },
        )

    def test_interactive_snapshot_tracks_frame_path_and_click_uses_child_frame(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.interactive_items = []
        page.add_child_frame(
            path=(0,),
            interactive_items=[
                {
                    "selector": "#confirm",
                    "label": "Confirm",
                    "role": "button",
                    "text": "Confirm",
                    "tag": "button",
                }
            ],
        )

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "interactive"},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        stored_refs = self.ref_store.get_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
        )
        self.assertEqual(
            stored_refs,
            (
                BrowserStoredRef(
                    ref="r1",
                    nth=None,
                    generation=1,
                    snapshot_format="interactive",
                    frame_path=(0,),
                    label="Confirm",
                    role="button",
                    text="Confirm",
                    tag="button",
                ),
            ),
        )
        self.assertEqual(snapshot_result.value["result"]["generation"], 1)
        self.assertEqual(snapshot_result.value["result"]["value"]["refs"][0]["frame_path"], [0])
        self.assertIsNone(snapshot_result.value["result"]["value"]["refs"][0]["selector"])
        self.assertEqual(snapshot_result.value["result"]["ref_count"], 1)
        self.assertEqual(snapshot_result.value["result"]["frame_count"], 1)

        click_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="click",
            target=BrowserActionTarget(target_id="tab-1", ref="r1"),
            payload={"button": "left"},
        )
        click_result = self.engine.execute(
            plan=self._plan(click_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=click_command,
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(click_result.value["frame_path"], [0])
        self.assertEqual(click_result.value["selector"], 'role=button[name="Confirm"]')
        self.assertEqual(page.operations[-1][0], "click")
        self.assertEqual(page.operations[-1][1], "#confirm")
        self.assertEqual(page.operations[-1][-1], (0,))

    def test_interactive_snapshot_can_scope_to_frame_selector(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.interactive_items = [
            {
                "selector": "#menu",
                "label": "Menu",
                "role": "button",
                "text": "Menu",
                "tag": "button",
            },
        ]
        page.add_child_frame(
            path=(0,),
            selector="iframe.booking",
            interactive_items=[
                {
                    "selector": "#confirm",
                    "label": "Confirm",
                    "role": "button",
                    "text": "Confirm",
                    "tag": "button",
                }
            ],
            aria_snapshot_text='- button "Confirm"',
        )

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "interactive", "frame_selector": "iframe.booking"},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        stored_refs = self.ref_store.get_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
        )
        self.assertEqual(len(stored_refs), 1)
        self.assertEqual(stored_refs[0].label, "Confirm")
        self.assertEqual(stored_refs[0].frame_path, (0,))
        self.assertEqual(snapshot_result.value["result"]["frame_selector"], "iframe.booking")
        self.assertEqual(snapshot_result.value["result"]["frame_count"], 1)
        self.assertEqual(snapshot_result.value["result"]["value"]["refs"][0]["label"], "Confirm")

    def test_role_snapshot_can_scope_to_frame_selector(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = '- button "Menu"'
        page.add_child_frame(
            path=(0,),
            selector="iframe.booking",
            aria_snapshot_text='\n'.join(
                [
                    '- region "Booking"',
                    '  - button "Search"',
                ]
            ),
        )

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "role", "frame_selector": "iframe.booking"},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        result = snapshot_result.value["result"]
        self.assertEqual(result["frame_selector"], "iframe.booking")
        self.assertEqual(result["frame_count"], 1)
        self.assertIn('button "Search"', result["value"]["snapshot"])
        self.assertNotIn('button "Menu"', result["value"]["snapshot"])

    def test_role_snapshot_can_scope_to_root_selector(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = None
        page.main_frame.interactive_items = [
            {
                "selector": "#menu",
                "label": "Menu",
                "role": "button",
                "text": "Menu",
                "tag": "button",
                "scope_selector": "#nav",
            },
            {
                "selector": "#search",
                "label": "Search",
                "role": "button",
                "text": "Search",
                "tag": "button",
                "scope_selector": "#booking",
            },
        ]

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1", selector="#booking"),
            payload={"format": "role"},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        result = snapshot_result.value["result"]
        self.assertEqual(snapshot_result.value["selector"], "#booking")
        self.assertEqual(result["root_selector"], "#booking")
        self.assertIn('button "Search"', result["value"]["snapshot"])
        self.assertNotIn('button "Menu"', result["value"]["snapshot"])
        self.assertEqual(result["ref_count"], 1)

    def test_interactive_snapshot_can_scope_to_root_selector(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = None
        page.main_frame.interactive_items = [
            {
                "selector": "#menu",
                "label": "Menu",
                "role": "button",
                "text": "Menu",
                "tag": "button",
                "scope_selector": "#nav",
            },
            {
                "selector": "#search",
                "label": "Search",
                "role": "button",
                "text": "Search",
                "tag": "button",
                "scope_selector": "#booking",
            },
        ]

        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1", selector="#booking"),
            payload={"format": "interactive"},
        )
        snapshot_result = self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        result = snapshot_result.value["result"]
        self.assertEqual(snapshot_result.value["selector"], "#booking")
        self.assertEqual(result["root_selector"], "#booking")
        self.assertEqual(result["ref_count"], 1)
        self.assertEqual(result["value"]["refs"][0]["label"], "Search")

    def test_interactive_snapshot_dom_fallback_groups_refs_by_scope_selector(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = ""
        page.main_frame.interactive_items = [
            {
                "selector": "#depart",
                "label": "Depart",
                "role": "button",
                "text": "Depart",
                "tag": "button",
                "scope_selector": "#search-form",
            },
            {
                "selector": "#arrival",
                "label": "Arrival",
                "role": "textbox",
                "text": "Arrival",
                "tag": "input",
                "scope_selector": "#search-form",
            },
            {
                "selector": "#direct-only",
                "label": "Direct only",
                "role": "checkbox",
                "text": "Direct only",
                "tag": "input",
                "scope_selector": "#filters",
            },
        ]

        snapshot_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive"},
            ),
        )

        snapshot_text = snapshot_result.value["result"]["value"]["snapshot"]
        self.assertIn('- scope "#search-form":', snapshot_text)
        self.assertIn('  - button "Depart" [ref=r1]', snapshot_text)
        self.assertIn('  - textbox "Arrival" [ref=r2]', snapshot_text)
        self.assertIn('- scope "#filters":', snapshot_text)
        self.assertIn('  - checkbox "Direct only" [ref=r3]', snapshot_text)

    def test_interactive_snapshot_uses_role_nth_for_duplicate_accessible_names(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#submit-primary",
                "label": "Submit",
                "role": "button",
                "text": "Submit",
                "tag": "button",
            },
            {
                "selector": "#submit-secondary",
                "label": "Submit",
                "role": "button",
                "text": "Submit",
                "tag": "button",
            },
        ]

        snapshot_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive"},
            ),
        )

        stored_refs = self.ref_store.get_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
        )
        self.assertEqual(stored_refs[0].nth, 0)
        self.assertEqual(stored_refs[1].nth, 1)
        self.assertEqual(snapshot_result.value["result"]["value"]["refs"][0]["nth"], 0)
        self.assertEqual(snapshot_result.value["result"]["value"]["refs"][1]["nth"], 1)

        click_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="click",
                    target=BrowserActionTarget(target_id="tab-1", ref="r2"),
                    payload={"button": "left"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="click",
                target=BrowserActionTarget(target_id="tab-1", ref="r2"),
                payload={"button": "left"},
            ),
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(
            click_result.value["selector"],
            'role=button[name="Submit"][nth=1]',
        )
        self.assertEqual(page.operations[-1][1], "#submit-secondary")

    def test_click_rejects_stale_ref_after_new_snapshot_generation(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#submit",
                "label": "Submit",
                "role": "button",
                "text": "Submit",
                "tag": "button",
            },
        ]
        snapshot_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="snapshot",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={"format": "interactive"},
        )
        self.engine.execute(
            plan=self._plan(snapshot_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=snapshot_command,
        )

        self.ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    selector="#submit",
                    generation=1,
                    snapshot_format="interactive",
                    label="Submit",
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

        with self.assertRaises(BrowserValidationError):
            self.engine.execute(
                plan=self._plan(
                    BrowserPageActionCommand(
                        profile_name="crxzipple",
                        kind="click",
                        target=BrowserActionTarget(target_id="tab-1", ref="r1"),
                        payload={"button": "left"},
                    )
                ),
                runtime_state=self.runtime_state,
                tab=self.tab,
                command=BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="click",
                    target=BrowserActionTarget(target_id="tab-1", ref="r1"),
                    payload={"button": "left"},
                ),
            )

    def test_click_can_rebind_stale_ref_within_scoped_container(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": ".depart-submit",
                "scope_selector": "#depart-panel",
                "label": "Submit",
                "role": "button",
                "text": "Submit",
                "tag": "button",
            },
            {
                "selector": ".return-submit",
                "scope_selector": "#return-panel",
                "label": "Submit",
                "role": "button",
                "text": "Submit",
                "tag": "button",
            },
        ]
        self.ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    scope_selector="#depart-panel",
                    generation=1,
                    snapshot_format="interactive",
                    label="Submit",
                    role="button",
                    text="Submit",
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

        click_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="click",
                    target=BrowserActionTarget(target_id="tab-1", ref="r1"),
                    payload={"button": "left"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="click",
                target=BrowserActionTarget(target_id="tab-1", ref="r1"),
                payload={"button": "left"},
            ),
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(
            click_result.value["selector"],
            '#depart-panel >> role=button[name="Submit"]',
        )
        self.assertEqual(page.operations[-1][1], ".depart-submit")

    def test_interactive_snapshot_efficient_mode_defaults_to_smaller_ref_budget_than_wide(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": f"#item-{index}",
                "label": f"Item {index}",
                "role": "button",
                "text": f"Item {index}",
                "tag": "button",
                "visible": True,
            }
            for index in range(1, 46)
        ]

        interactive_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive"},
            ),
        )

        wide_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive", "mode": "wide"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive", "mode": "wide"},
            ),
        )

        self.assertEqual(interactive_result.value["result"]["ref_count"], 40)
        self.assertEqual(len(interactive_result.value["result"]["value"]["refs"]), 40)
        self.assertEqual(wide_result.value["result"]["ref_count"], 45)
        self.assertEqual(len(wide_result.value["result"]["value"]["refs"]), 45)

    def test_interactive_snapshot_honors_depth_and_compact_options(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = "\n".join(
            [
                '- banner:',
                '  - button "Menu"',
                '  - button',
                '  - group:',
                '    - link "Deals"',
                '    - textbox',
                '    - button',
            ]
        )

        result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={
                        "format": "interactive",
                        "compact": True,
                        "depth": 1,
                    },
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={
                    "format": "interactive",
                    "compact": True,
                    "depth": 1,
                },
            ),
        )

        value = result.value["result"]["value"]["refs"]
        self.assertEqual(
            [(item["role"], item["label"]) for item in value],
            [("button", "Menu")],
        )
        self.assertTrue(result.value["result"]["compact"])
        self.assertEqual(result.value["result"]["depth"], 1)

    def test_interactive_snapshot_supports_wide_and_focused_modes(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = "\n".join(
            [
                "- main:",
                '  - button "Primary"',
                "  - button",
                "  - textbox",
            ]
        )

        wide_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive", "mode": "wide"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive", "mode": "wide"},
            ),
        )

        default_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive", "mode": "focused"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive", "mode": "focused"},
            ),
        )

        focused_result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive", "mode": "focused"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive", "mode": "focused"},
            ),
        )

        self.assertEqual(wide_result.value["result"]["mode"], "wide")
        self.assertEqual(default_result.value["result"]["mode"], "focused")
        self.assertEqual(focused_result.value["result"]["mode"], "focused")
        self.assertEqual(
            [(item["role"], item["label"]) for item in wide_result.value["result"]["value"]["refs"]],
            [("button", "Primary"), ("button", None), ("textbox", None)],
        )
        self.assertEqual(
            [(item["role"], item["label"]) for item in default_result.value["result"]["value"]["refs"]],
            [("button", "Primary"), ("textbox", None)],
        )
        self.assertEqual(
            [(item["role"], item["label"]) for item in focused_result.value["result"]["value"]["refs"]],
            [("button", "Primary"), ("textbox", None)],
        )
        self.assertIn('[ref=r1]', wide_result.value["result"]["value"]["snapshot"])
        self.assertEqual(
            [operation[0] for operation in page.operations if operation[0] in {"aria_snapshot", "frame.evaluate"}],
            ["aria_snapshot", "aria_snapshot", "aria_snapshot"],
        )

    def test_interactive_snapshot_falls_back_to_dom_when_focused_role_snapshot_is_too_sparse(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.active_overlay_selector = "#compose"
        page.main_frame.aria_snapshot_text = "\n".join(
            [
                "- dialog:",
                '  - button "Dismiss"',
            ]
        )
        page.interactive_items = [
            {
                "selector": "input[aria-label='To recipients']",
                "label": "To recipients",
                "role": "textbox",
                "text": "",
                "tag": "input",
                "scope_selector": "#compose",
            },
            {
                "selector": "input[aria-label='Subject']",
                "label": "Subject",
                "role": "textbox",
                "text": "",
                "tag": "input",
                "scope_selector": "#compose",
            },
            {
                "selector": "div[aria-label='Message Body']",
                "label": "Message Body",
                "role": "textbox",
                "text": "",
                "tag": "div",
                "scope_selector": "#compose",
            },
            {
                "selector": "div[aria-label^='Send']",
                "label": "Send",
                "role": "button",
                "text": "Send",
                "tag": "div",
                "scope_selector": "#compose",
            },
        ]

        result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive", "mode": "focused", "active_overlay": True},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive", "mode": "focused", "active_overlay": True},
            ),
        )

        refs = result.value["result"]["value"]["refs"]
        self.assertEqual(
            [(item["role"], item["label"]) for item in refs],
            [
                ("textbox", "To recipients"),
                ("textbox", "Subject"),
                ("button", "Send"),
                ("textbox", "Message Body"),
            ],
        )
        self.assertIn('[ref=r1]', result.value["result"]["value"]["snapshot"])
        self.assertEqual(
            [operation[0] for operation in page.operations if operation[0] in {"aria_snapshot", "frame.evaluate"}],
            ["aria_snapshot", "frame.evaluate"],
        )

    def test_interactive_snapshot_focused_excludes_skip_to_content_ref(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = "\n".join(
            [
                "- main:",
                '  - link "Skip to content"',
                '  - textbox "To recipients"',
                '  - textbox "Subject"',
            ]
        )

        result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive", "mode": "focused"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive", "mode": "focused"},
            ),
        )

        refs = result.value["result"]["value"]["refs"]
        self.assertEqual(
            [(item["role"], item["label"]) for item in refs],
            [("textbox", "To recipients"), ("textbox", "Subject")],
        )

    def test_interactive_snapshot_efficient_mode_defaults_compact_and_depth(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = "\n".join(
            [
                '- main:',
                '  - button "Search"',
                '  - group:',
                '    - button',
                '    - textbox',
            ]
        )

        result = self.engine.execute(
            plan=self._plan(
                BrowserPageActionCommand(
                    profile_name="crxzipple",
                    kind="snapshot",
                    target=BrowserActionTarget(target_id="tab-1"),
                    payload={"format": "interactive", "mode": "efficient"},
                )
            ),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="snapshot",
                target=BrowserActionTarget(target_id="tab-1"),
                payload={"format": "interactive", "mode": "efficient"},
            ),
        )

        self.assertEqual(result.value["result"]["mode"], "efficient")
        self.assertTrue(result.value["result"]["compact"])
        self.assertEqual(result.value["result"]["depth"], 6)
        self.assertEqual(
            [(item["role"], item["label"]) for item in result.value["result"]["value"]["refs"]],
            [("button", "Search"), ("textbox", None)],
        )


if __name__ == "__main__":
    unittest.main()
