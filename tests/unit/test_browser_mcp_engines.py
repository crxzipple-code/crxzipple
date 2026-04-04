from __future__ import annotations

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
from crxzipple.modules.browser.domain import BrowserProfileConfig, BrowserSystemConfig
from crxzipple.modules.browser.domain import BrowserStoredRef, BrowserValidationError
from crxzipple.modules.browser.infrastructure import (
    InMemoryBrowserRefStore,
    InMemoryBrowserRuntimeStateStore,
    InMemoryBrowserSystemConfigStore,
    InMemoryCdpBackedPlaywrightActionEngine,
    InMemoryCdpControlEngine,
    McpBackedActionEngine,
    McpControlEngine,
    StaticBrowserEngineRegistry,
)
from tests.unit.support import FakeChromeMcpClientPool


class BrowserMcpEnginesTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.system = BrowserSystemConfig(
            default_profile="user",
            profiles=(
                BrowserProfileConfig(
                    name="user",
                    driver="existing-session",
                    user_data_dir="/tmp/browser-user",
                ),
            ),
        )
        self.runtime_state_store = InMemoryBrowserRuntimeStateStore()
        self.ref_store = InMemoryBrowserRefStore()
        self.mcp_pool = FakeChromeMcpClientPool()
        self.coordinator = BrowserExecutionCoordinatorService(
            system_config_store=InMemoryBrowserSystemConfigStore(self.system),
            profile_resolver=DefaultBrowserProfileResolver(),
            capabilities_resolver=DefaultBrowserCapabilitiesResolver(),
            runtime_state_store=self.runtime_state_store,
            ref_store=self.ref_store,
            execution_planner=DefaultBrowserExecutionPlanner(),
            engine_registry=StaticBrowserEngineRegistry(
                cdp_control=InMemoryCdpControlEngine(),
                mcp_control=McpControlEngine(mcp_pool=self.mcp_pool),
                cdp_backed_playwright=InMemoryCdpBackedPlaywrightActionEngine(),
                mcp_backed=McpBackedActionEngine(
                    mcp_pool=self.mcp_pool,
                    ref_store=self.ref_store,
                ),
            ),
            tab_ops_factory=DefaultBrowserProfileTabOpsFactory(),
            selection_ops_factory=DefaultBrowserProfileSelectionOpsFactory(),
        )
        self.control_assembler = DefaultBrowserControlCommandAssembler()
        self.page_action_assembler = DefaultBrowserPageActionAssembler()

    def test_mcp_control_engine_manages_existing_session_tabs(self) -> None:
        open_result = self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="user",
                kind="open-tab",
                payload={"url": "https://example.com/start"},
            )
        )
        self.assertTrue(open_result.ok)
        self.assertEqual(open_result.target_id, "1")

        navigate_result = self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="user",
                kind="navigate",
                target_id="1",
                payload={"url": "https://example.com/next"},
            )
        )
        self.assertEqual(navigate_result.value.url, "https://example.com/next")

        list_result = self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="user",
                kind="list-tabs",
            )
        )
        self.assertEqual(len(list_result.value), 1)
        self.assertEqual(list_result.value[0].target_id, "1")

        focus_result = self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="user",
                kind="focus-tab",
                target_id="1",
            )
        )
        self.assertTrue(focus_result.ok)

        close_result = self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="user",
                kind="close-tab",
                target_id="1",
            )
        )
        self.assertTrue(close_result.ok)

        runtime_state = self.runtime_state_store.get(profile_name="user")
        self.assertIsNotNone(runtime_state)
        assert runtime_state is not None
        self.assertEqual(runtime_state.attachment_status, "attached")
        self.assertEqual(runtime_state.browser_ref, "mcp:user")
        self.assertEqual(runtime_state.running_pid, 4321)
        self.assertIn(("ensure_available", "user", "/tmp/browser-user"), self.mcp_pool.operations)
        self.assertIn(("open_tab", "user", "https://example.com/start", "/tmp/browser-user"), self.mcp_pool.operations)

    def test_mcp_action_engine_uses_snapshot_refs_and_mcp_tools(self) -> None:
        self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="user",
                kind="open-tab",
                payload={"url": "https://example.org"},
            )
        )
        self.mcp_pool.set_snapshot(
            profile_name="user",
            target_id="1",
            snapshot={
                "role": "document",
                "children": [
                    {"id": "e1", "role": "button", "name": "Submit"},
                    {"id": "e2", "role": "textbox", "name": "Query"},
                ],
            },
        )

        snapshot_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="snapshot",
                target_id="1",
                payload={"format": "interactive"},
            )
        )
        self.assertEqual(snapshot_result.value["engine"], "mcp-backed")
        self.assertEqual(snapshot_result.value["result"]["format"], "interactive")
        self.assertEqual(snapshot_result.value["result"]["generation"], 1)
        refs = self.ref_store.get_tab_refs(profile_name="user", target_id="1")
        self.assertEqual(refs[0].ref, "r1")
        self.assertEqual(refs[0].uid, "e1")
        self.assertEqual(refs[0].generation, 1)
        self.assertEqual(refs[1].uid, "e2")
        self.assertEqual(refs[1].generation, 1)

        click_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="click",
                target_id="1",
                ref="r1",
            )
        )
        fill_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="fill",
                target_id="1",
                ref="r2",
                payload={"text": "search"},
            )
        )
        wait_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="wait",
                target_id="1",
                payload={"text": "ready"},
            )
        )
        evaluate_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="evaluate",
                target_id="1",
                payload={"expression": "() => ({ ok: true })"},
            )
        )
        screenshot_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="screenshot",
                target_id="1",
                ref="r1",
                payload={"type": "png"},
            )
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(click_result.value["uid"], "e1")
        self.assertTrue(fill_result.ok)
        self.assertEqual(fill_result.value["result"]["text"], "search")
        self.assertEqual(wait_result.value["result"]["text"], ["ready"])
        self.assertEqual(
            evaluate_result.value["result"]["value"],
            {"fn": "() => ({ ok: true })", "args": []},
        )
        self.assertEqual(screenshot_result.value["result"]["content_type"], "image/png")

        self.assertIn(("click", "user", "1", "e1", "/tmp/browser-user", False), self.mcp_pool.operations)
        self.assertIn(("fill", "user", "1", "e2", "search", "/tmp/browser-user"), self.mcp_pool.operations)
        self.assertIn(
            ("wait_for_text", "user", "1", ("ready",), "/tmp/browser-user", None),
            self.mcp_pool.operations,
        )

    def test_mcp_evaluate_supports_fn_alias_and_ref_argument(self) -> None:
        self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="user",
                kind="open-tab",
                payload={"url": "https://example.org"},
            )
        )
        self.ref_store.save_tab_refs(
            profile_name="user",
            target_id="1",
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    uid="e1",
                    generation=1,
                    snapshot_format="interactive",
                    label="Query",
                    role="textbox",
                ),
            ),
        )
        runtime_state = self.runtime_state_store.get(profile_name="user")
        assert runtime_state is not None
        runtime_state.remember_page_snapshot(
            target_id="1",
            generation=1,
            snapshot_format="interactive",
            ref_count=1,
            frame_count=1,
        )
        self.runtime_state_store.save(runtime_state)

        evaluate_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="evaluate",
                target_id="1",
                ref="r1",
                payload={"fn": "(el) => el.textContent"},
            )
        )

        self.assertTrue(evaluate_result.ok)
        self.assertEqual(evaluate_result.value["result"]["expression"], "(el) => el.textContent")
        self.assertIn(
            (
                "evaluate_script",
                "user",
                "1",
                "(el) => el.textContent",
                "/tmp/browser-user",
                ("e1",),
            ),
            self.mcp_pool.operations,
        )

    def test_mcp_wait_supports_selector_text_gone_load_state_and_fn(self) -> None:
        self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="user",
                kind="open-tab",
                payload={"url": "https://example.org"},
            )
        )

        selector_wait_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="wait",
                target_id="1",
                selector="#ready",
                payload={"state": "attached"},
            )
        )
        text_gone_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="wait",
                target_id="1",
                payload={"text_gone": "Loading"},
            )
        )
        load_state_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="wait",
                target_id="1",
                payload={"load_state": "domcontentloaded"},
            )
        )
        fn_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="wait",
                target_id="1",
                payload={"fn": "() => window.ready === true"},
            )
        )

        self.assertEqual(selector_wait_result.value["result"]["selector"], "#ready")
        self.assertEqual(selector_wait_result.value["result"]["state"], "attached")
        self.assertEqual(text_gone_result.value["result"]["text_gone"], ["Loading"])
        self.assertEqual(load_state_result.value["result"]["load_state"], "domcontentloaded")
        self.assertEqual(fn_result.value["result"]["expression"], "() => window.ready === true")
        self.assertIn(
            (
                "evaluate_script",
                "user",
                "1",
                '() => Boolean(document.querySelector("#ready"))',
                "/tmp/browser-user",
                (),
            ),
            self.mcp_pool.operations,
        )

    def test_mcp_fill_supports_form_fields(self) -> None:
        self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="user",
                kind="open-tab",
                payload={"url": "https://example.org"},
            )
        )
        self.ref_store.save_tab_refs(
            profile_name="user",
            target_id="1",
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    uid="e1",
                    generation=1,
                    snapshot_format="interactive",
                    label="Query",
                    role="textbox",
                ),
                BrowserStoredRef(
                    ref="r2",
                    uid="e2",
                    generation=1,
                    snapshot_format="interactive",
                    label="Newsletter",
                    role="checkbox",
                ),
            ),
        )
        runtime_state = self.runtime_state_store.get(profile_name="user")
        assert runtime_state is not None
        runtime_state.remember_page_snapshot(
            target_id="1",
            generation=1,
            snapshot_format="interactive",
            ref_count=2,
            frame_count=1,
        )
        self.runtime_state_store.save(runtime_state)

        fill_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="fill",
                target_id="1",
                payload={
                    "fields": [
                        {"ref": "r1", "type": "text", "value": "hello"},
                        {"ref": "r2", "type": "checkbox", "value": True},
                    ]
                },
            )
        )

        self.assertTrue(fill_result.ok)
        self.assertEqual(len(fill_result.value["result"]["fields"]), 2)
        self.assertIn(("fill", "user", "1", "e1", "hello", "/tmp/browser-user"), self.mcp_pool.operations)
        self.assertIn(("fill", "user", "1", "e2", "true", "/tmp/browser-user"), self.mcp_pool.operations)

    def test_mcp_drag_supports_start_and_end_ref_aliases(self) -> None:
        self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="user",
                kind="open-tab",
                payload={"url": "https://example.org"},
            )
        )
        self.ref_store.save_tab_refs(
            profile_name="user",
            target_id="1",
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    uid="e1",
                    generation=1,
                    snapshot_format="interactive",
                    label="From",
                    role="button",
                ),
                BrowserStoredRef(
                    ref="r2",
                    uid="e2",
                    generation=1,
                    snapshot_format="interactive",
                    label="To",
                    role="button",
                ),
            ),
        )
        runtime_state = self.runtime_state_store.get(profile_name="user")
        assert runtime_state is not None
        runtime_state.remember_page_snapshot(
            target_id="1",
            generation=1,
            snapshot_format="interactive",
            ref_count=2,
            frame_count=1,
        )
        self.runtime_state_store.save(runtime_state)

        drag_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="drag",
                target_id="1",
                payload={"start_ref": "r1", "end_ref": "r2"},
            )
        )

        self.assertTrue(drag_result.ok)
        self.assertEqual(drag_result.value["result"]["start_ref"], "r1")
        self.assertEqual(drag_result.value["result"]["target_uid"], "e2")
        self.assertIn(("drag", "user", "1", "e1", "e2", "/tmp/browser-user"), self.mcp_pool.operations)

    def test_mcp_resize_supports_width_and_height(self) -> None:
        self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="user",
                kind="open-tab",
                payload={"url": "https://example.org"},
            )
        )

        resize_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="resize",
                target_id="1",
                payload={"width": 1024, "height": 768},
            )
        )

        self.assertTrue(resize_result.ok)
        self.assertEqual(resize_result.value["result"]["width"], 1024)
        self.assertEqual(resize_result.value["result"]["height"], 768)
        self.assertIn(
            ("resize_page", "user", "1", 1024, 768, "/tmp/browser-user"),
            self.mcp_pool.operations,
        )

    def test_mcp_batch_is_rejected(self) -> None:
        self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="user",
                kind="open-tab",
                payload={"url": "https://example.org"},
            )
        )

        with self.assertRaises(BrowserValidationError):
            self.coordinator.execute(
                self.page_action_assembler.assemble(
                    profile_name="user",
                    kind="batch",
                    target_id="1",
                    payload={
                        "actions": [
                            {"kind": "click", "ref": "r1"},
                        ]
                    },
                )
            )

    def test_mcp_snapshot_rejects_selector_or_frame_scoping(self) -> None:
        self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="user",
                kind="open-tab",
                payload={"url": "https://example.org"},
            )
        )

        with self.assertRaises(BrowserValidationError):
            self.coordinator.execute(
                self.page_action_assembler.assemble(
                    profile_name="user",
                    kind="snapshot",
                    target_id="1",
                    selector="#booking",
                    payload={"format": "interactive"},
                )
            )

        with self.assertRaises(BrowserValidationError):
            self.coordinator.execute(
                self.page_action_assembler.assemble(
                    profile_name="user",
                    kind="snapshot",
                    target_id="1",
                    payload={"format": "interactive", "frame_selector": "iframe.booking"},
                )
            )


if __name__ == "__main__":
    unittest.main()
