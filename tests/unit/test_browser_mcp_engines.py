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

    def test_mcp_storage_supports_set_get_and_clear(self) -> None:
        self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="user",
                kind="open-tab",
                payload={"url": "https://example.org"},
            )
        )

        set_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="storage",
                target_id="1",
                payload={
                    "storage_kind": "local",
                    "storage_operation": "set",
                    "storage_key": "theme",
                    "storage_value": "dark",
                },
            )
        )
        get_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="storage",
                target_id="1",
                payload={
                    "storage_kind": "local",
                    "storage_operation": "get",
                    "storage_key": "theme",
                },
            )
        )
        clear_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="storage",
                target_id="1",
                payload={
                    "storage_kind": "local",
                    "storage_operation": "clear",
                },
            )
        )

        self.assertTrue(set_result.ok)
        self.assertEqual(set_result.value["engine"], "mcp-backed")
        self.assertEqual(set_result.value["result"]["values"], {"theme": "dark"})
        self.assertEqual(get_result.value["result"]["values"], {"theme": "dark"})
        self.assertEqual(clear_result.value["result"]["values"], {})
        self.assertTrue(
            any(
                operation[0] == "evaluate_script"
                and operation[1] == "user"
                and operation[2] == "1"
                and operation[4] == "/tmp/browser-user"
                for operation in self.mcp_pool.operations
            )
        )

    def test_mcp_cookies_supports_set_get_and_clear(self) -> None:
        self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="user",
                kind="open-tab",
                payload={"url": "https://example.org"},
            )
        )

        set_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="cookies",
                target_id="1",
                payload={
                    "cookies_operation": "set",
                    "cookie": {
                        "name": "session",
                        "value": "abc123",
                        "path": "/",
                    },
                },
            )
        )
        get_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="cookies",
                target_id="1",
                payload={"cookies_operation": "get"},
            )
        )
        clear_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="cookies",
                target_id="1",
                payload={"cookies_operation": "clear"},
            )
        )

        self.assertTrue(set_result.ok)
        self.assertEqual(set_result.value["engine"], "mcp-backed")
        self.assertEqual(set_result.value["result"]["count"], 1)
        self.assertEqual(set_result.value["result"]["cookies"][0]["name"], "session")
        self.assertEqual(get_result.value["result"]["cookies"][0]["value"], "abc123")
        self.assertEqual(clear_result.value["result"]["cookies"], [])

    def test_mcp_dialog_supports_accept_and_prompt_text(self) -> None:
        self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="user",
                kind="open-tab",
                payload={"url": "https://example.org"},
            )
        )

        dialog_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="dialog",
                target_id="1",
                payload={"accept": True, "prompt_text": "Shanghai"},
            )
        )

        self.assertTrue(dialog_result.ok)
        self.assertEqual(dialog_result.value["engine"], "mcp-backed")
        self.assertEqual(dialog_result.value["result"]["kind"], "dialog")
        self.assertEqual(dialog_result.value["result"]["handled_as"], "accept")
        self.assertEqual(dialog_result.value["result"]["prompt_text"], "Shanghai")
        self.assertIn(
            ("handle_dialog", "user", "1", "accept", "Shanghai", "/tmp/browser-user"),
            self.mcp_pool.operations,
        )

    def test_mcp_upload_supports_single_file_path(self) -> None:
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
                    label="Upload",
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
            ref_count=1,
            frame_count=1,
        )
        self.runtime_state_store.save(runtime_state)

        upload_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="upload",
                target_id="1",
                ref="r1",
                payload={"paths": ["/tmp/a.txt"]},
            )
        )

        self.assertTrue(upload_result.ok)
        self.assertEqual(upload_result.value["engine"], "mcp-backed")
        self.assertEqual(upload_result.value["result"]["kind"], "upload")
        self.assertEqual(upload_result.value["result"]["paths"], ["/tmp/a.txt"])
        self.assertIn(
            ("upload_file", "user", "1", "e1", "/tmp/a.txt", "/tmp/browser-user"),
            self.mcp_pool.operations,
        )

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

    def test_mcp_scroll_into_view_uses_ref_uid(self) -> None:
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
                    label="Submit",
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
            ref_count=1,
            frame_count=1,
        )
        self.runtime_state_store.save(runtime_state)

        scroll_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="scroll-into-view",
                target_id="1",
                ref="r1",
            )
        )

        self.assertTrue(scroll_result.ok)
        self.assertEqual(scroll_result.value["engine"], "mcp-backed")
        self.assertEqual(scroll_result.value["result"]["kind"], "scroll-into-view")
        self.assertTrue(
            any(
                operation[0] == "evaluate_script"
                and operation[1] == "user"
                and operation[2] == "1"
                and operation[4] == "/tmp/browser-user"
                and operation[5] == ("e1",)
                for operation in self.mcp_pool.operations
            )
        )

    def test_mcp_batch_executes_actions_in_order(self) -> None:
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
                    label="Submit",
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
            ref_count=1,
            frame_count=1,
        )
        self.runtime_state_store.save(runtime_state)

        batch_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="batch",
                target_id="1",
                payload={
                    "actions": [
                        {"kind": "click", "ref": "r1"},
                        {"kind": "evaluate", "fn": "() => document.title"},
                    ]
                },
            )
        )

        self.assertTrue(batch_result.ok)
        self.assertEqual(batch_result.value["engine"], "mcp-backed")
        self.assertEqual(batch_result.value["result"]["kind"], "batch")
        self.assertEqual(len(batch_result.value["result"]["results"]), 2)
        self.assertTrue(batch_result.value["result"]["results"][0]["ok"])
        self.assertEqual(batch_result.value["result"]["results"][0]["kind"], "click")
        self.assertTrue(batch_result.value["result"]["results"][1]["ok"])
        self.assertEqual(batch_result.value["result"]["results"][1]["kind"], "evaluate")
        self.assertIn(("click", "user", "1", "e1", "/tmp/browser-user", False), self.mcp_pool.operations)
        self.assertIn(
            (
                "evaluate_script",
                "user",
                "1",
                "() => document.title",
                "/tmp/browser-user",
                (),
            ),
            self.mcp_pool.operations,
        )

    def test_mcp_batch_stop_on_error_false_continues_after_failure(self) -> None:
        self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="user",
                kind="open-tab",
                payload={"url": "https://example.org"},
            )
        )

        batch_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="batch",
                target_id="1",
                payload={
                    "actions": [
                        {"kind": "pdf"},
                        {"kind": "evaluate", "fn": "() => document.title"},
                    ],
                    "stop_on_error": False,
                },
            )
        )

        self.assertTrue(batch_result.ok)
        results = batch_result.value["result"]["results"]
        self.assertFalse(results[0]["ok"])
        self.assertEqual(results[0]["kind"], "pdf")
        self.assertTrue(results[1]["ok"])
        self.assertEqual(results[1]["kind"], "evaluate")

    def test_mcp_console_supports_filter_limit_and_clear(self) -> None:
        self.coordinator.execute(
            self.control_assembler.assemble(
                profile_name="user",
                kind="open-tab",
                payload={"url": "https://example.org"},
            )
        )
        self.mcp_pool.set_console_messages(
            profile_name="user",
            target_id="1",
            messages=[
                {
                    "level": "log",
                    "text": "boot",
                    "captured_at_ms": 100,
                },
                {
                    "level": "warn",
                    "text": "careful",
                    "location": {
                        "url": "https://example.org/app.js",
                        "line_number": 12,
                        "column_number": 4,
                    },
                    "captured_at_ms": 200,
                },
                {
                    "level": "warn",
                    "text": "heads-up",
                    "captured_at_ms": 300,
                },
            ],
        )

        console_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="console",
                target_id="1",
                payload={"level": "warn", "limit": 1, "clear": True},
            )
        )

        self.assertTrue(console_result.ok)
        self.assertEqual(console_result.value["engine"], "mcp-backed")
        self.assertEqual(console_result.value["result"]["kind"], "console")
        self.assertEqual(console_result.value["result"]["count"], 1)
        self.assertEqual(console_result.value["result"]["level"], "warn")
        self.assertEqual(console_result.value["result"]["limit"], 1)
        self.assertTrue(console_result.value["result"]["cleared"])
        self.assertEqual(
            console_result.value["result"]["messages"],
            [
                {
                    "level": "warn",
                    "text": "heads-up",
                    "location": None,
                    "captured_at_ms": 300,
                }
            ],
        )

        cleared_result = self.coordinator.execute(
            self.page_action_assembler.assemble(
                profile_name="user",
                kind="console",
                target_id="1",
            )
        )
        self.assertTrue(cleared_result.ok)
        self.assertEqual(cleared_result.value["result"]["count"], 0)
        self.assertEqual(cleared_result.value["result"]["messages"], [])

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
