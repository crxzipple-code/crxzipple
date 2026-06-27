from __future__ import annotations

import unittest

from crxzipple.modules.browser.domain import (
    BrowserActionTarget,
    BrowserPageActionCommand,
    BrowserStoredRef,
)
from crxzipple.modules.browser.infrastructure.action_trace import (
    _trace_action_envelope,
    _trace_recommendation,
    _trace_snapshot_limit_for_action_ref,
    _trace_snapshot_payload,
)
from tests.unit.browser_playwright_action_support import BrowserPlaywrightActionEngineTestCase


class BrowserPlaywrightCoreActionsTestCase(BrowserPlaywrightActionEngineTestCase):
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
        click_envelope = click_result.value["action_envelope"]
        self.assertTrue(click_envelope["tool_ok"])
        self.assertFalse(click_envelope["page_effect_ok"])
        self.assertEqual(click_envelope["page_effect_status"], "no_observable_change")
        self.assertEqual(click_envelope["before"]["url"], "https://example.com")
        self.assertEqual(click_envelope["after"]["url"], "https://example.com")
        self.assertEqual(
            click_envelope["next_action"],
            "use-action-trace-or-observe",
        )
        self.assertEqual(type_result.value["result"]["text"], "search")
        self.assertIn("action_envelope", type_result.value)

        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        action_names = [operation[0] for operation in page.operations]
        self.assertIn("click", action_names)
        self.assertIn("type", action_names)
        self.assertEqual(click_result.value["result"]["mode"], "direct")

    def test_click_can_target_viewport_coordinates(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        click_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="click",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "x": 530,
                "y": 636,
                "button": "left",
                "double_click": True,
            },
            timeout_ms=1500,
        )

        click_result = self.engine.execute(
            plan=self._plan(click_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=click_command,
        )

        self.assertTrue(click_result.ok)
        self.assertEqual(click_result.value["result"]["mode"], "coordinate")
        self.assertEqual(click_result.value["result"]["x"], 530.0)
        self.assertEqual(click_result.value["result"]["y"], 636.0)
        self.assertIn(
            ("mouse.click", 530.0, 636.0, {"button": "left", "click_count": 2}),
            page.operations,
        )

    def test_action_trace_wraps_action_with_before_after_state(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.emit_console(text="Boot complete", message_type="info")
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="action-trace",
            target=BrowserActionTarget(target_id="tab-1", selector="#query"),
            payload={
                "action": "type",
                "text": "Kunming",
                "include_network": False,
                "snapshot_limit": 5,
                "stabilize_ms": 0,
                "trace_id": "trace-query",
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        self.assertTrue(result.ok)
        trace = result.value["result"]
        self.assertEqual(trace["kind"], "action-trace")
        self.assertEqual(trace["trace_id"], "trace-query")
        self.assertEqual(trace["action"]["kind"], "type")
        self.assertTrue(trace["action"]["ok"])
        self.assertEqual(trace["action"]["resolved_selector"], "#query")
        self.assertEqual(trace["action"]["result"]["text"], "Kunming")
        self.assertEqual(trace["before"]["format"], "interactive")
        self.assertEqual(trace["after"]["format"], "interactive")
        self.assertEqual(trace["console"]["before_count"], 1)
        self.assertEqual(trace["console"]["after_count"], 1)
        self.assertEqual(trace["console"]["new"], [])
        self.assertFalse(trace["network"]["started"])
        self.assertEqual(
            trace["recommendation"]["next_action"],
            "observe-or-inspect-clickability",
        )
        envelope = trace["action_envelope"]
        self.assertEqual(envelope["kind"], "type")
        self.assertTrue(envelope["tool_ok"])
        self.assertFalse(envelope["page_effect_ok"])
        self.assertEqual(envelope["page_effect_status"], "no_observable_change")
        self.assertEqual(
            envelope["next_action"],
            "observe-or-inspect-clickability",
        )
        self.assertIn(("type", "#query", "Kunming", {}, ()), page.operations)

    def test_action_trace_fill_readonly_combobox_uses_overlay_candidate(self) -> None:
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
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="action-trace",
            target=BrowserActionTarget(target_id="tab-1", selector="#depart-city"),
            payload={
                "action": "fill",
                "text": "Kunming",
                "include_network": False,
                "snapshot_limit": 5,
                "stabilize_ms": 0,
                "trace_id": "trace-custom-fill",
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        self.assertTrue(result.ok)
        trace = result.value["result"]
        self.assertEqual(trace["trace_id"], "trace-custom-fill")
        self.assertEqual(trace["action"]["kind"], "fill")
        self.assertTrue(trace["action"]["ok"])
        self.assertEqual(trace["action"]["result"]["input_mode"], "custom-overlay")
        self.assertEqual(trace["action"]["result"]["selected"]["text"], "Kunming")
        self.assertTrue(trace["action_envelope"]["tool_ok"])
        self.assertIn(
            ("click", "#depart-city", {"button": "left", "timeout": 2000.0}, ()),
            page.operations,
        )
        self.assertIn(
            ("click", ".city-overlay .option-kmg", {"timeout": 2000.0}, ()),
            page.operations,
        )

    def test_action_trace_preserves_high_ref_when_snapshot_limit_is_smaller(self) -> None:
        self.assertEqual(
            _trace_snapshot_limit_for_action_ref(
                snapshot_format="interactive",
                current_limit=12,
                action_ref="r19",
            ),
            40,
        )
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": f"#item-{index}",
                "resolved_selector": f"#item-{index}",
                "label": f"Action {index}",
                "role": "button",
                "text": f"Action {index}",
                "tag": "button",
                "visible": True,
            }
            for index in range(1, 21)
        ]
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="action-trace",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "action": "click",
                "action_ref": "r19",
                "include_network": False,
                "snapshot_limit": 12,
                "stabilize_ms": 0,
                "trace_id": "trace-high-ref",
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        self.assertTrue(result.ok)
        trace = result.value["result"]
        self.assertTrue(trace["action"]["ok"])
        self.assertEqual(trace["before"]["ref_count"], 20)
        self.assertEqual(trace["after"]["ref_count"], 20)
        self.assertIn(
            ("click", "#item-19", {"timeout": 2000.0}, ()),
            page.operations,
        )

    def test_action_trace_bounds_snapshot_preview_size(self) -> None:
        payload = _trace_snapshot_payload(
            {
                "kind": "snapshot",
                "format": "interactive",
                "generation": 1,
                "ref_count": 1,
                "frame_count": 1,
                "mode": "efficient",
                "compact": True,
                "value": {"snapshot": "x" * 6000},
            },
        )

        self.assertEqual(len(payload["snapshot_preview"]), 4000)
        self.assertTrue(payload["snapshot_preview"].endswith("..."))

    def test_action_trace_preserves_precise_ref_locator_when_before_snapshot_is_role_only(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.interactive_items = [
            {
                "selector": "#depart-primary",
                "resolved_selector": "#depart-primary",
                "label": "出发",
                "role": "textbox",
                "text": "出发",
                "tag": "input",
                "visible": True,
            },
            {
                "selector": "#depart-popup",
                "resolved_selector": "#depart-popup",
                "label": "出发",
                "role": "textbox",
                "text": "出发",
                "tag": "input",
                "visible": True,
            },
        ]
        page.main_frame.aria_snapshot_text = '- textbox "出发"'
        self.ref_store.save_tab_refs(
            profile_name="crxzipple",
            target_id="tab-1",
            refs=(
                BrowserStoredRef(
                    ref="r1",
                    selector="#depart-primary",
                    generation=1,
                    snapshot_format="interactive",
                    label="出发",
                    role="textbox",
                    text="出发",
                    tag="input",
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
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="action-trace",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "action": "click",
                "action_ref": "r1",
                "include_network": False,
                "snapshot_limit": 1,
                "stabilize_ms": 0,
                "trace_id": "trace-precise-ref",
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        self.assertTrue(result.ok)
        trace = result.value["result"]
        self.assertTrue(trace["action"]["ok"])
        self.assertEqual(trace["action"]["resolved_selector"], "#depart-primary")
        self.assertIn(
            ("click", "#depart-primary", {"timeout": 2000.0}, ()),
            page.operations,
        )

    def test_action_trace_spa_form_chain_captures_submit_request(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
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
                "selector": ".depart-overlay .option-kmg",
                "resolved_selector": ".depart-overlay .option-kmg",
                "label": "Kunming",
                "role": "option",
                "text": "Kunming",
                "tag": "li",
                "scope_selector": ".depart-overlay",
                "source_selector": "#depart-city",
                "visible": True,
            },
            {
                "selector": "#arrival-city",
                "resolved_selector": "#arrival-city",
                "label": "Arrival city",
                "role": "combobox",
                "tag": "input",
                "readonly": True,
                "visible": True,
            },
            {
                "selector": ".arrival-overlay .option-sha",
                "resolved_selector": ".arrival-overlay .option-sha",
                "label": "Shanghai",
                "role": "option",
                "text": "Shanghai",
                "tag": "li",
                "scope_selector": ".arrival-overlay",
                "source_selector": "#arrival-city",
                "visible": True,
            },
            {
                "selector": "#search-flights",
                "resolved_selector": "#search-flights",
                "label": "Search flights",
                "role": "button",
                "text": "Search flights",
                "tag": "button",
                "visible": True,
            },
        ]
        page.network_events_on_operation["click:#search-flights"] = [
            {
                "event": "Network.requestWillBeSent",
                "payload": {
                    "requestId": "req-flight-search",
                    "type": "XHR",
                    "frameId": "frame-tab-1",
                    "loaderId": "loader-1",
                    "request": {
                        "url": "https://example.com/api/flights/search",
                        "method": "POST",
                        "headers": {"Content-Type": "application/json"},
                        "postData": '{"from":"KMG","to":"SHA"}',
                    },
                    "initiator": {"type": "other"},
                },
            },
            {
                "event": "Network.responseReceived",
                "payload": {
                    "requestId": "req-flight-search",
                    "type": "XHR",
                    "response": {
                        "status": 200,
                        "headers": {"Content-Type": "application/json"},
                        "mimeType": "application/json",
                        "timing": {"receiveHeadersEnd": 16.0},
                    },
                },
            },
            {
                "event": "Network.loadingFinished",
                "payload": {
                    "requestId": "req-flight-search",
                    "encodedDataLength": 1024,
                },
            },
        ]

        for selector, text, overlay in (
            ("#depart-city", "Kunming", ".depart-overlay"),
            ("#arrival-city", "Shanghai", ".arrival-overlay"),
        ):
            page.active_overlay_selector = overlay
            fill_command = BrowserPageActionCommand(
                profile_name="crxzipple",
                kind="action-trace",
                target=BrowserActionTarget(target_id="tab-1", selector=selector),
                payload={
                    "action": "fill",
                    "text": text,
                    "include_network": False,
                    "snapshot_limit": 5,
                    "stabilize_ms": 0,
                },
            )
            fill_result = self.engine.execute(
                plan=self._plan(fill_command),
                runtime_state=self.runtime_state,
                tab=self.tab,
                command=fill_command,
            )

            self.assertTrue(fill_result.ok)
            self.assertEqual(
                fill_result.value["result"]["action"]["result"]["input_mode"],
                "custom-overlay",
            )
            self.assertEqual(
                fill_result.value["result"]["action"]["result"]["selected"]["text"],
                text,
            )

        search_command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="action-trace",
            target=BrowserActionTarget(target_id="tab-1", selector="#search-flights"),
            payload={
                "action": "click",
                "snapshot_limit": 5,
                "stabilize_ms": 0,
                "trace_id": "trace-spa-search",
            },
        )
        search_result = self.engine.execute(
            plan=self._plan(search_command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=search_command,
        )

        self.assertTrue(search_result.ok)
        trace = search_result.value["result"]
        self.assertEqual(trace["trace_id"], "trace-spa-search")
        self.assertEqual(trace["network"]["request_count"], 1)
        request = trace["network"]["requests"][0]
        self.assertEqual(request["request_id"], "req-flight-search")
        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["resource_type"], "xhr")
        self.assertEqual(trace["recommendation"]["next_action"], "inspect-network-delta")
        envelope = trace["action_envelope"]
        self.assertTrue(envelope["tool_ok"])
        self.assertTrue(envelope["page_effect_ok"])
        self.assertEqual(envelope["changes"]["network_request_count"], 1)
        self.assertIn(
            ("click", ".depart-overlay .option-kmg", {"timeout": 2000.0}, ()),
            page.operations,
        )
        self.assertIn(
            ("click", ".arrival-overlay .option-sha", {"timeout": 2000.0}, ()),
            page.operations,
        )
        self.assertIn(
            ("click", "#search-flights", {"timeout": 2000.0}, ()),
            page.operations,
        )

    def test_action_trace_summarizes_script_initiated_network_delta(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.network_events_on_operation["type:#query"] = [
            {
                "event": "Network.requestWillBeSent",
                "payload": {
                    "requestId": "req-search",
                    "type": "XHR",
                    "frameId": "frame-tab-1",
                    "loaderId": "loader-1",
                    "request": {
                        "url": "https://example.com/api/flights?city=kunming",
                        "method": "POST",
                        "headers": {"Content-Type": "application/json"},
                        "postData": '{"city":"kunming"}',
                    },
                    "initiator": {
                        "type": "script",
                        "stack": {
                            "callFrames": [
                                {
                                    "functionName": "searchFlights",
                                    "url": "https://example.com/assets/app.js",
                                    "lineNumber": 40,
                                    "columnNumber": 8,
                                }
                            ]
                        },
                    },
                },
            },
            {
                "event": "Network.responseReceived",
                "payload": {
                    "requestId": "req-search",
                    "type": "XHR",
                    "response": {
                        "status": 200,
                        "headers": {"Content-Type": "application/json"},
                        "mimeType": "application/json",
                        "timing": {"receiveHeadersEnd": 12.0},
                    },
                },
            },
            {
                "event": "Network.loadingFinished",
                "payload": {
                    "requestId": "req-search",
                    "encodedDataLength": 512,
                },
            },
        ]
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="action-trace",
            target=BrowserActionTarget(target_id="tab-1", selector="#query"),
            payload={
                "action": "type",
                "text": "Kunming",
                "snapshot_limit": 5,
                "stabilize_ms": 0,
                "trace_id": "trace-network",
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        self.assertTrue(result.ok)
        trace = result.value["result"]
        self.assertEqual(trace["network"]["request_count"], 1)
        request = trace["network"]["requests"][0]
        self.assertEqual(request["request_id"], "req-search")
        self.assertEqual(request["resource_type"], "xhr")
        self.assertEqual(request["initiator_summary"]["type"], "script")
        self.assertEqual(
            request["initiator_summary"]["script_url"],
            "https://example.com/assets/app.js",
        )
        self.assertEqual(request["initiator_summary"]["function_name"], "searchFlights")
        self.assertEqual(request["initiator_summary"]["line_number"], 41)
        causality = trace["network"]["causality"]
        self.assertEqual(causality["initiator_counts"], {"script": 1})
        self.assertEqual(causality["script_request_count"], 1)
        self.assertEqual(causality["script_frames"][0]["request_id"], "req-search")
        self.assertEqual(
            trace["recommendation"]["next_action"],
            "inspect-script-initiator",
        )
        envelope = trace["action_envelope"]
        self.assertTrue(envelope["tool_ok"])
        self.assertTrue(envelope["page_effect_ok"])
        self.assertEqual(envelope["page_effect_status"], "observed_change")
        self.assertEqual(envelope["changes"]["network_request_count"], 1)
        self.assertEqual(envelope["next_action"], "inspect-script-initiator")
        captures = self.engine.network_capture_service.list_captures(
            profile_name="crxzipple",
            target_id="tab-1",
        )
        trace_capture = next(
            item
            for item in captures
            if item.capture_id == trace["network"]["capture_id"]
        )
        self.assertEqual(trace_capture.metadata["source"], "browser.action_trace")
        self.assertEqual(trace_capture.metadata["trace_id"], "trace-network")
        self.assertEqual(trace_capture.metadata["action_kind"], "type")
        self.assertEqual(
            trace_capture.metadata["action_target"],
            {
                "target_id": "tab-1",
                "ref": None,
                "selector": "#query",
            },
        )

    def test_action_trace_summarizes_storage_and_lifecycle_delta(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="action-trace",
            target=BrowserActionTarget(target_id="tab-1"),
            payload={
                "action": "evaluate",
                "expression": "/*__crxzipple_test_action_trace_mutate__*/() => true",
                "include_network": False,
                "snapshot_limit": 5,
                "stabilize_ms": 0,
                "trace_id": "trace-storage-lifecycle",
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        self.assertTrue(result.ok)
        trace = result.value["result"]
        self.assertEqual(trace["trace_id"], "trace-storage-lifecycle")
        self.assertTrue(trace["storage"]["changed"])
        self.assertEqual(trace["storage"]["local"]["added_keys"], ["flight_search"])
        self.assertEqual(trace["storage"]["session"]["added_keys"], ["search_step"])
        self.assertTrue(trace["lifecycle"]["changed"])
        self.assertEqual(
            trace["lifecycle"]["changed_fields"]["url"]["before"],
            "https://example.com",
        )
        self.assertEqual(
            trace["lifecycle"]["changed_fields"]["url"]["after"],
            "https://example.com/flights/results",
        )
        self.assertEqual(
            trace["recommendation"]["next_action"],
            "inspect-page-lifecycle",
        )
        envelope = trace["action_envelope"]
        self.assertTrue(envelope["page_effect_ok"])
        self.assertEqual(envelope["page_effect_status"], "observed_change")
        self.assertEqual(envelope["before"]["url"], "https://example.com")
        self.assertEqual(
            envelope["after"]["url"],
            "https://example.com/flights/results",
        )
        self.assertTrue(envelope["changes"]["storage_changed"])
        self.assertTrue(envelope["changes"]["lifecycle_changed"])
        self.assertIn("flight_search", page.local_storage)
        self.assertIn("search_step", page.session_storage)

    def test_action_trace_partial_snapshot_errors_are_display_safe(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.evaluate_failures = [
            RuntimeError(
                "Storage failed at "
                "https://example.com/store?token=secret-token#session "
                "Authorization: Bearer secret-token"
            ),
            RuntimeError(
                "Lifecycle failed with api_key=secret-token and password=secret"
            ),
        ]
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="action-trace",
            target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
            payload={
                "action": "click",
                "include_network": False,
                "stabilize_ms": 0,
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        self.assertTrue(result.ok)
        trace = result.value["result"]
        storage_errors = trace["storage"]["errors"]
        lifecycle_errors = trace["lifecycle"]["errors"]
        self.assertEqual(storage_errors[0]["source"], "storage-snapshot")
        self.assertEqual(lifecycle_errors[0]["source"], "lifecycle-snapshot")
        rendered_errors = " ".join(
            error["message"] for error in [*storage_errors, *lifecycle_errors]
        )
        self.assertIn("https://example.com/store?[redacted]", rendered_errors)
        self.assertIn("Authorization: [redacted]", rendered_errors)
        self.assertIn("api_key=[redacted]", rendered_errors)
        self.assertIn("password=[redacted]", rendered_errors)
        self.assertNotIn("secret-token", rendered_errors)
        self.assertNotIn("#session", rendered_errors)

    def test_action_trace_reports_action_error_without_losing_after_state(self) -> None:
        page = self.session_pool.resolve_page(profile=self.profile, target_id="tab-1")
        page.click_failures["#submit"] = [RuntimeError("detached")]
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="action-trace",
            target=BrowserActionTarget(target_id="tab-1", selector="#submit"),
            payload={
                "action": "click",
                "include_network": False,
                "stabilize_ms": 0,
            },
        )

        result = self.engine.execute(
            plan=self._plan(command),
            runtime_state=self.runtime_state,
            tab=self.tab,
            command=command,
        )

        self.assertTrue(result.ok)
        trace = result.value["result"]
        self.assertFalse(trace["action"]["ok"])
        self.assertEqual(trace["action"]["kind"], "click")
        self.assertEqual(trace["action"]["error"]["type"], "RuntimeError")
        self.assertEqual(trace["before"]["format"], "interactive")
        self.assertEqual(trace["after"]["format"], "interactive")
        self.assertEqual(trace["recommendation"]["next_action"], "inspect-target")
        envelope = trace["action_envelope"]
        self.assertFalse(envelope["tool_ok"])
        self.assertFalse(envelope["page_effect_ok"])
        self.assertEqual(envelope["page_effect_status"], "action_failed")
        self.assertEqual(envelope["next_action"], "inspect-target")
        self.assertTrue(
            any(
                operation[0] == "click" and operation[1] == "#submit"
                for operation in page.operations
            )
        )

    def test_action_trace_separates_action_failure_from_observed_page_effect(self) -> None:
        action_error = {"type": "TimeoutError", "message": "navigation wait timed out"}
        diff = {
            "snapshot_changed": True,
            "before_chars": 28,
            "after_chars": 363,
            "ref_count_delta": 9,
        }
        network = {"request_count": 5}
        lifecycle_delta = {
            "changed": True,
            "before": {"url": "https://example.com/", "title": "Example Domain"},
            "after": {
                "url": "https://www.iana.org/help/example-domains",
                "title": "Example Domains",
            },
            "changed_fields": {
                "url": {
                    "before": "https://example.com/",
                    "after": "https://www.iana.org/help/example-domains",
                },
            },
        }
        recommendation = _trace_recommendation(
            action_error=action_error,
            diff=diff,
            network=network,
            console_delta=[],
            page_error_delta=[],
            storage_delta=None,
            lifecycle_delta=lifecycle_delta,
        )
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="action-trace",
            target=BrowserActionTarget(target_id="tab-1", ref="r1"),
            payload={"action": "click"},
        )

        envelope = _trace_action_envelope(
            action_command=command,
            action_error=action_error,
            diff=diff,
            network=network,
            console_delta=[],
            page_error_delta=[],
            storage_delta=None,
            lifecycle_delta=lifecycle_delta,
            recommendation=recommendation,
        )

        self.assertEqual(recommendation["next_action"], "continue-from-after-snapshot")
        self.assertFalse(envelope["tool_ok"])
        self.assertTrue(envelope["page_effect_ok"])
        self.assertEqual(
            envelope["page_effect_status"],
            "action_failed_with_observed_effect",
        )
        self.assertEqual(
            envelope["after"]["url"],
            "https://www.iana.org/help/example-domains",
        )

    def test_action_trace_does_not_count_background_network_when_ref_missing(self) -> None:
        action_error = {
            "type": "BrowserValidationError",
            "message": "Browser ref 'r999' was not found for tab 'tab-1'.",
        }
        diff = {
            "snapshot_changed": False,
            "before_chars": 434,
            "after_chars": 434,
            "ref_count_delta": 0,
        }
        network = {
            "request_count": 1,
            "requests": [
                {
                    "method": "GET",
                    "url": "https://wkbrs1.tingyun.com/replay",
                },
            ],
        }
        lifecycle_delta = {
            "changed": False,
            "before": {"url": "https://www.ceair.com/zh/cny/home"},
            "after": {"url": "https://www.ceair.com/zh/cny/home"},
            "changed_fields": {},
        }
        recommendation = _trace_recommendation(
            action_error=action_error,
            diff=diff,
            network=network,
            console_delta=[],
            page_error_delta=[],
            storage_delta=None,
            lifecycle_delta=lifecycle_delta,
        )
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="action-trace",
            target=BrowserActionTarget(target_id="tab-1", ref="r999"),
            payload={"action": "click"},
        )

        envelope = _trace_action_envelope(
            action_command=command,
            action_error=action_error,
            diff=diff,
            network=network,
            console_delta=[],
            page_error_delta=[],
            storage_delta=None,
            lifecycle_delta=lifecycle_delta,
            recommendation=recommendation,
        )

        self.assertEqual(recommendation["next_action"], "inspect-target")
        self.assertFalse(envelope["tool_ok"])
        self.assertFalse(envelope["page_effect_ok"])
        self.assertEqual(envelope["page_effect_status"], "action_failed")

    def test_action_trace_does_not_count_background_network_when_locator_is_ambiguous(self) -> None:
        action_error = {
            "type": "Error",
            "message": (
                'Locator.click: Error: strict mode violation: get_by_role("textbox", '
                'name="出发", exact=True) resolved to 2 elements.'
            ),
        }
        diff = {
            "snapshot_changed": False,
            "before_chars": 620,
            "after_chars": 620,
            "ref_count_delta": 0,
        }
        network = {
            "request_count": 1,
            "requests": [
                {
                    "method": "POST",
                    "url": "https://wkbrs1.tingyun.com/replay",
                },
            ],
        }
        lifecycle_delta = {
            "changed": False,
            "before": {"url": "https://www.ceair.com/zh/cny/home"},
            "after": {"url": "https://www.ceair.com/zh/cny/home"},
            "changed_fields": {},
        }
        recommendation = _trace_recommendation(
            action_error=action_error,
            diff=diff,
            network=network,
            console_delta=[],
            page_error_delta=[],
            storage_delta=None,
            lifecycle_delta=lifecycle_delta,
        )
        command = BrowserPageActionCommand(
            profile_name="crxzipple",
            kind="action-trace",
            target=BrowserActionTarget(target_id="tab-1", ref="r19"),
            payload={"action": "click"},
        )

        envelope = _trace_action_envelope(
            action_command=command,
            action_error=action_error,
            diff=diff,
            network=network,
            console_delta=[],
            page_error_delta=[],
            storage_delta=None,
            lifecycle_delta=lifecycle_delta,
            recommendation=recommendation,
        )

        self.assertEqual(recommendation["next_action"], "inspect-target")
        self.assertFalse(envelope["tool_ok"])
        self.assertFalse(envelope["page_effect_ok"])
        self.assertEqual(envelope["page_effect_status"], "action_failed")



if __name__ == "__main__":
    unittest.main()
