from __future__ import annotations

import unittest

from crxzipple.modules.browser.domain import (
    BrowserActionTarget,
    BrowserPageActionCommand,
    BrowserStoredRef,
    BrowserValidationError,
)
from tests.unit.browser_playwright_action_support import BrowserPlaywrightActionEngineTestCase


class BrowserPlaywrightSnapshotActionsTestCase(BrowserPlaywrightActionEngineTestCase):
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
                "page_generation": 1,
                "snapshot_generation": 1,
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
                "page_generation": 1,
                "snapshot_generation": 1,
                "current_ref_generation": 1,
                "last_action_kind": "click",
                "last_snapshot_format": "interactive",
                "last_snapshot_ref_count": 2,
                "last_snapshot_frame_count": 1,
                "ref_session_restored": False,
            },
        )

    def test_click_prefers_devtools_backend_node_over_stored_selector(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#actual-submit",
                "label": "Submit",
                "role": "button",
                "text": "Submit",
                "tag": "button",
            },
        ]
        page.backend_node_selectors[42] = "#actual-submit"
        self.ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    selector="#stale-submit",
                    backend_node_id=42,
                    generation=1,
                    snapshot_format="interactive",
                    label="Submit",
                    role="button",
                    text="Submit",
                    tag="button",
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
        self.assertEqual(click_result.value["selector"], "backendNodeId=42")
        self.assertIn(
            ("cdp.send", "DOM.resolveNode", {"backendNodeId": 42}),
            page.operations,
        )
        self.assertEqual(page.operations[-1][0], "click")
        self.assertEqual(page.operations[-1][1], "#actual-submit")

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

    def test_interactive_snapshot_skips_detached_child_frames(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = '- button "Open calendar"'
        page.interactive_items = [
            {
                "selector": "#calendar",
                "label": "Open calendar",
                "role": "button",
                "text": "Open calendar",
                "tag": "button",
            },
        ]
        child_frame = page.add_child_frame(path=(0,), aria_snapshot_text="")
        child_frame.evaluate_failures.append(RuntimeError("Frame was detached"))

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
            [("button", "Open calendar")],
        )
        self.assertEqual(
            [
                (operation[0], operation[-1])
                for operation in page.operations
                if operation[0] == "frame.evaluate"
            ],
            [
                ("frame.evaluate", ()),
                ("frame.evaluate", (0,)),
            ],
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

    def test_interactive_snapshot_uses_dom_for_active_datepicker_overlay(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.active_overlay_selector = ".date-picker-panel"
        page.main_frame.aria_snapshot_text = "\n".join(
            [
                '- button "Previous month"',
                '- button "Next month"',
            ]
        )
        page.interactive_items = [
            {
                "selector": ".date-picker-panel .day:nth-of-type(1)",
                "label": "May 27",
                "role": None,
                "text": "27",
                "tag": "div",
                "scope_selector": ".date-picker-panel",
            },
            {
                "selector": ".date-picker-panel .day:nth-of-type(2)",
                "label": "May 28",
                "role": None,
                "text": "28",
                "tag": "div",
                "scope_selector": ".date-picker-panel",
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
        self.assertEqual(snapshot_result.value["result"]["root_selector"], ".date-picker-panel")
        refs = snapshot_result.value["result"]["value"]["refs"]
        self.assertEqual(
            [(item["label"], item["text"], item["tag"]) for item in refs],
            [("May 27", "27", "div"), ("May 28", "28", "div")],
        )
        self.assertEqual(
            [
                operation[0]
                for operation in page.operations
                if operation[0] in {"aria_snapshot", "frame.evaluate"}
            ],
            ["aria_snapshot", "frame.evaluate"],
        )

    def test_interactive_snapshot_exposes_semantic_free_mobile_form_controls(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.main_frame.aria_snapshot_text = ""
        page.dom_nodes_for_location[(160, 341)] = {"backendNodeId": 901}
        page.interactive_items = [
            {
                "selector": ".ticket-search .city-left",
                "label": "上海",
                "role": "button",
                "text": "上海",
                "tag": "div",
                "bbox": {"x": 120, "y": 320, "width": 80, "height": 42},
                "evidence": ["visible-text", "hit-test", "visual-fallback"],
                "confidence": 0.45,
            },
            {
                "selector": ".ticket-search .city-right",
                "label": "北京",
                "role": "button",
                "text": "北京",
                "tag": "div",
                "bbox": {"x": 260, "y": 320, "width": 80, "height": 42},
                "evidence": ["visible-text", "hit-test", "visual-fallback"],
                "confidence": 0.45,
            },
            {
                "selector": ".ticket-search .search-btn",
                "label": "搜索机票",
                "role": "button",
                "text": "搜索机票",
                "tag": "div",
                "bbox": {"x": 90, "y": 420, "width": 280, "height": 48},
                "evidence": ["visible-text", "hit-test", "visual-fallback"],
                "confidence": 0.45,
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

        result = snapshot_result.value["result"]
        refs = result["value"]["refs"]
        self.assertEqual(result["ref_count"], 3)
        self.assertEqual(
            [(item["label"], item["role"], item["tag"]) for item in refs],
            [("上海", "button", "div"), ("北京", "button", "div"), ("搜索机票", "button", "div")],
        )
        self.assertEqual(refs[0]["bbox"], {"x": 120.0, "y": 320.0, "width": 80.0, "height": 42.0})
        self.assertEqual(refs[0]["backend_node_id"], 901)
        self.assertEqual(
            refs[0]["evidence"],
            ["visible-text", "hit-test", "visual-fallback", "devtools-hit-test"],
        )
        self.assertEqual(refs[0]["confidence"], 0.5)
        self.assertIn('- button "搜索机票" [ref=r3]', result["value"]["snapshot"])
        self.assertIn(
            "[evidence=visible-text,hit-test,visual-fallback,devtools-hit-test]",
            result["value"]["snapshot"],
        )

    def test_interactive_snapshot_dedupes_nested_overlay_refs(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.active_overlay_selector = ".city-autocomplete-list"
        page.main_frame.aria_snapshot_text = ""
        page.interactive_items = [
            {
                "selector": ".city-autocomplete-list > li",
                "label": "昆明(昆明长水)",
                "role": "button",
                "text": "昆明(昆明长水)",
                "tag": "li",
                "scope_selector": ".city-autocomplete-list",
            },
            {
                "selector": ".city-autocomplete-list > li > span",
                "label": "昆明(昆明长水)",
                "role": "button",
                "text": "昆明(昆明长水)",
                "tag": "span",
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

        result = snapshot_result.value["result"]
        refs = result["value"]["refs"]
        self.assertEqual(result["ref_count"], 1)
        self.assertEqual(refs[0]["ref"], "r1")
        self.assertEqual(refs[0]["tag"], "li")
        self.assertIn('- scope ".city-autocomplete-list":', result["value"]["snapshot"])
        self.assertIn('  - button "昆明(昆明长水)" [ref=r1]', result["value"]["snapshot"])
        self.assertNotIn("[ref=r2]", result["value"]["snapshot"])

    def test_interactive_snapshot_dedupes_descendant_overlay_refs(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.active_overlay_selector = ".city-autocomplete-list"
        page.main_frame.aria_snapshot_text = ""
        page.interactive_items = [
            {
                "selector": ".city-autocomplete-list li",
                "label": "上海虹桥",
                "role": "option",
                "text": "上海虹桥",
                "tag": "li",
                "scope_selector": ".city-autocomplete-list",
            },
            {
                "selector": ".city-autocomplete-list li span",
                "label": "上海虹桥",
                "role": "option",
                "text": "上海虹桥",
                "tag": "span",
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

        result = snapshot_result.value["result"]
        self.assertEqual(result["ref_count"], 1)
        refs = result["value"]["refs"]
        self.assertEqual(refs[0]["selector"], ".city-autocomplete-list li")
        self.assertEqual(refs[0]["tag"], "li")



























if __name__ == "__main__":
    unittest.main()
