from __future__ import annotations

from tests.unit.http_test_support import HttpModuleTestCase


class ContextWorkspaceHttpTestCase(HttpModuleTestCase):
    def test_context_workspace_uses_session_owner_adapter(self) -> None:
        session_response = self.client.post(
            "/sessions",
            json={
                "key": "session:adapter",
                "runtime_binding": {"agent_id": "assistant"},
            },
        )
        self.assertEqual(session_response.status_code, 201)
        append_response = self.client.post(
            "/sessions/session:adapter/items",
            json={
                "kind": "user_message",
                "role": "user",
                "content_payload": {
                    "blocks": [{"type": "text", "text": "hello from session"}],
                },
            },
        )
        self.assertEqual(append_response.status_code, 201)

        ensure_response = self.client.post(
            "/context-workspaces/by-session/session:adapter/ensure",
            json={"agent_id": "assistant"},
        )
        self.assertEqual(ensure_response.status_code, 201)
        tree_response = self.client.get(
            "/context-workspaces/by-session/session:adapter/tree",
        )
        self.assertEqual(tree_response.status_code, 200)
        nodes = tree_response.json()["nodes"]

        self.assertTrue(any(node["id"] == "session.instance.active" for node in nodes))
        self.assertTrue(any(node["id"] == "session.segments.active" for node in nodes))
        self.assertTrue(any(node["id"] == "session.segment.active" for node in nodes))
        self.assertTrue(any(node["id"] == "session.items.current" for node in nodes))
        expand_response = self.client.post(
            "/context-workspaces/by-session/session:adapter/nodes/session.items.current/actions/expand",
            json={"actor_kind": "user", "actor_id": "tester"},
        )
        self.assertEqual(expand_response.status_code, 200)
        expanded_tree_response = self.client.get(
            "/context-workspaces/by-session/session:adapter/tree",
        )
        self.assertEqual(expanded_tree_response.status_code, 200)
        expanded_nodes = expanded_tree_response.json()["nodes"]
        item_nodes = [
            node
            for node in expanded_nodes
            if node.get("parent_id") == "session.items.current"
        ]
        self.assertTrue(item_nodes)
        self.assertIn("hello from session", item_nodes[0]["summary"])
        self.assertEqual(
            item_nodes[0]["owner_ref"]["session_item_id"],
            append_response.json()["id"],
        )

    def test_context_workspace_does_not_promote_tool_evidence_to_tree_nodes(self) -> None:
        self.client.post(
            "/sessions",
            json={
                "key": "session:evidence-items",
                "runtime_binding": {"agent_id": "assistant"},
            },
        )
        self.client.post(
            "/sessions/session:evidence-items/items",
            json={
                "kind": "user_message",
                "role": "user",
                "source_kind": "orchestration_run",
                "source_id": "run-evidence-items",
                "content_payload": {
                    "blocks": [{"type": "text", "text": "inspect api"}],
                },
            },
        )
        self.client.post(
            "/sessions/session:evidence-items/items",
            json={
                "kind": "tool_call",
                "role": "assistant",
                "call_id": "call-network",
                "tool_name": "browser.network.fetch",
                "content_payload": {
                    "type": "function_call",
                    "call_id": "call-network",
                    "name": "browser.network.fetch",
                    "arguments": {"url": "/api/flights"},
                },
                "metadata": {
                    "tool_call_id": "call-network",
                    "tool_name": "browser.network.fetch",
                },
            },
        )
        result_response = self.client.post(
            "/sessions/session:evidence-items/items",
            json={
                "kind": "tool_result",
                "role": "tool",
                "call_id": "call-network",
                "tool_name": "browser.network.fetch",
                "content_payload": {
                    "tool_name": "browser.network.fetch",
                    "tool_call_id": "call-network",
                    "status": "succeeded",
                    "metadata": {
                        "profile": "crxzipple",
                        "target_id": "tab-east",
                        "verified_ref": "ref-flight-date",
                    },
                    "details": {"url": "/api/flights", "method": "POST"},
                    "content": [{"type": "text", "text": "flight response"}],
                },
                "metadata": {
                    "tool_call_id": "call-network",
                    "tool_name": "browser.network.fetch",
                },
            },
        )
        self.assertEqual(result_response.status_code, 201)

        ensure_response = self.client.post(
            "/context-workspaces/by-session/session:evidence-items/ensure",
            json={"agent_id": "assistant", "metadata": {"last_run_id": "run-evidence-items"}},
        )
        self.assertEqual(ensure_response.status_code, 201)
        tree_response = self.client.get(
            "/context-workspaces/by-session/session:evidence-items/tree",
        )
        self.assertEqual(tree_response.status_code, 200)
        nodes = tree_response.json()["nodes"]

        self.assertFalse(
            any(node["id"] == "session.evidence.current" for node in nodes),
        )
        self.assertFalse(
            any(node["kind"] == "session_evidence" for node in nodes),
        )

    def test_context_workspace_does_not_generate_browser_warning_nodes(self) -> None:
        self.client.post(
            "/sessions",
            json={
                "key": "session:warning-items",
                "runtime_binding": {"agent_id": "assistant"},
            },
        )
        self.client.post(
            "/sessions/session:warning-items/items",
            json={
                "kind": "user_message",
                "role": "user",
                "source_kind": "orchestration_run",
                "source_id": "run-warning-items",
                "content_payload": {
                    "blocks": [{"type": "text", "text": "inspect browser"}],
                },
            },
        )
        for index, payload in enumerate(
            (
                (
                    "browser.network.start_capture",
                    "call-capture",
                    {"capture_id": "cap-flight"},
                    "Network capture started:\n- Capture: cap-flight",
                ),
                (
                    "browser.evaluate",
                    "call-probe",
                    {"fn": "() => window.location.href", "target_id": "tab-1"},
                    "Evaluate result: https://example.com",
                ),
                (
                    "browser.network.list_requests",
                    "call-list",
                    {"capture_id": "cap-flight"},
                    "Network requests: 0 shown of 0\n- No matching requests.",
                ),
            ),
            start=1,
        ):
            tool_name, call_id, arguments, text = payload
            self.client.post(
                "/sessions/session:warning-items/items",
                json={
                    "kind": "tool_call",
                    "role": "assistant",
                    "call_id": call_id,
                    "tool_name": tool_name,
                    "content_payload": {
                        "type": "function_call",
                        "call_id": call_id,
                        "name": tool_name,
                        "arguments": arguments,
                    },
                    "metadata": {"tool_call_id": call_id, "tool_name": tool_name},
                },
            )
            self.client.post(
                "/sessions/session:warning-items/items",
                json={
                    "kind": "tool_result",
                    "role": "tool",
                    "call_id": call_id,
                    "tool_name": tool_name,
                    "content_payload": {
                        "tool_name": tool_name,
                        "tool_call_id": call_id,
                        "status": "succeeded",
                        "content": [{"type": "text", "text": text}],
                    },
                    "metadata": {
                        "tool_call_id": call_id,
                        "tool_name": tool_name,
                        "pair_index": index,
                    },
                },
            )

        ensure_response = self.client.post(
            "/context-workspaces/by-session/session:warning-items/ensure",
            json={"agent_id": "assistant", "metadata": {"last_run_id": "run-warning-items"}},
        )
        self.assertEqual(ensure_response.status_code, 201)
        tree_response = self.client.get(
            "/context-workspaces/by-session/session:warning-items/tree",
        )
        self.assertEqual(tree_response.status_code, 200)
        warnings = [
            node
            for node in tree_response.json()["nodes"]
            if node["kind"] == "investigation_warning"
        ]

        self.assertEqual(warnings, [])

    def test_context_workspace_historical_range_uses_session_items(self) -> None:
        self.client.post(
            "/sessions",
            json={
                "key": "session:history-items",
                "runtime_binding": {"agent_id": "assistant"},
            },
        )
        old_item = self.client.post(
            "/sessions/session:history-items/items",
            json={
                "kind": "user_message",
                "role": "user",
                "content_payload": {
                    "blocks": [{"type": "text", "text": "before reset item"}],
                },
            },
        )
        self.assertEqual(old_item.status_code, 201)
        reset_response = self.client.post("/sessions/session:history-items/reset", json={})
        self.assertEqual(reset_response.status_code, 200)
        self.client.post(
            "/sessions/session:history-items/items",
            json={
                "kind": "user_message",
                "role": "user",
                "content_payload": {
                    "blocks": [{"type": "text", "text": "after reset item"}],
                },
            },
        )

        ensure_response = self.client.post(
            "/context-workspaces/by-session/session:history-items/ensure",
            json={"agent_id": "assistant"},
        )
        self.assertEqual(ensure_response.status_code, 201)
        tree_response = self.client.get(
            "/context-workspaces/by-session/session:history-items/tree",
        )
        self.assertEqual(tree_response.status_code, 200)
        closed_segment = next(
            node
            for node in tree_response.json()["nodes"]
            if node["kind"] == "session_segment"
            and node["id"].startswith("session.segment.closed.")
        )
        expand_segment = self.client.post(
            f"/context-workspaces/by-session/session:history-items/nodes/{closed_segment['id']}/actions/expand",
            json={"actor_kind": "user", "actor_id": "tester"},
        )
        self.assertEqual(expand_segment.status_code, 200)
        range_tree = self.client.get(
            "/context-workspaces/by-session/session:history-items/tree",
        ).json()["nodes"]
        range_node = next(
            node
            for node in range_tree
            if node.get("parent_id") == closed_segment["id"]
            and node["kind"] == "session_item_range"
        )
        expand_range = self.client.post(
            f"/context-workspaces/by-session/session:history-items/nodes/{range_node['id']}/actions/expand",
            json={"actor_kind": "user", "actor_id": "tester"},
        )
        self.assertEqual(expand_range.status_code, 200)
        expanded_tree = self.client.get(
            "/context-workspaces/by-session/session:history-items/tree",
        ).json()["nodes"]
        history_item_nodes = [
            node
            for node in expanded_tree
            if node.get("parent_id") == range_node["id"]
        ]

        self.assertTrue(history_item_nodes)
        self.assertIn("before reset item", history_item_nodes[0]["summary"])
        self.assertEqual(
            history_item_nodes[0]["owner_ref"]["session_item_id"],
            old_item.json()["id"],
        )

    def test_context_workspace_tree_action_and_snapshot(self) -> None:
        ensure_response = self.client.post(
            "/context-workspaces/by-session/session:http/ensure",
            json={"agent_id": "assistant"},
        )
        self.assertEqual(ensure_response.status_code, 201)
        workspace_payload = ensure_response.json()["workspace"]
        self.assertEqual(workspace_payload["session_key"], "session:http")

        tree_response = self.client.get(
            "/context-workspaces/by-session/session:http/tree",
        )
        self.assertEqual(tree_response.status_code, 200)
        tree_payload = tree_response.json()
        self.assertTrue(
            any(node["id"] == "tools.available" for node in tree_payload["nodes"]),
        )

        action_response = self.client.post(
            "/context-workspaces/by-session/session:http/nodes/tools.available/actions/expand",
            json={"actor_kind": "user", "actor_id": "tester"},
        )
        self.assertEqual(action_response.status_code, 200)
        self.assertFalse(action_response.json()["node"]["state"]["collapsed"])

        render_response = self.client.post(
            "/context-workspaces/by-session/session:http/render",
        )
        self.assertEqual(render_response.status_code, 200)
        render_payload = render_response.json()
        debug_body = render_payload["debug_body"]
        self.assertIn("<context_tree", debug_body)
        self.assertIn("debug_body", render_payload["estimate_breakdown"])
        self.assertIn("node_visible", render_payload["estimate_breakdown"])
        self.assertTrue(render_payload["estimate_breakdown"]["top_rendered_nodes"])
        self.assertIn(
            "tool_schema_mirror_budget",
            render_payload["provider_attachment_report"],
        )
        self.assertIn("contract_version", render_payload["runtime_contract"])
        self.assertIsInstance(render_payload["mirrored_node_ids"], list)
        self.assertIsInstance(render_payload["provider_attachments"], dict)

        snapshot_response = self.client.post(
            "/context-workspaces/by-session/session:http/snapshots",
            json={
                "run_id": "run-http",
                "debug_body": debug_body,
                "estimate": render_payload["estimate"],
                "included_node_ids": render_payload["included_node_ids"],
                "included_refs": [
                    {
                        "owner_module": "session",
                        "owner_kind": "session_item",
                        "owner_id": "item-http-1",
                        "item_id": "item-http-1",
                    },
                ],
                "protocol_required_refs": [
                    {
                        "owner_module": "session",
                        "owner_kind": "session_item",
                        "owner_id": "item-http-1",
                        "item_id": "item-http-1",
                        "protocol_required": True,
                    },
                ],
            },
        )
        self.assertEqual(snapshot_response.status_code, 200)
        self.assertEqual(snapshot_response.json()["snapshot"]["run_id"], "run-http")
        self.assertNotIn("debug_body", snapshot_response.json()["snapshot"])
        self.assertEqual(
            snapshot_response.json()["snapshot"]["included_refs"][0]["item_id"],
            "item-http-1",
        )
        self.assertEqual(
            snapshot_response.json()["snapshot"]["protocol_required_refs"][0][
                "protocol_required"
            ],
            True,
        )
        snapshot_id = snapshot_response.json()["snapshot"]["id"]

        get_snapshot_response = self.client.get(
            "/context-workspaces/runs/run-http/snapshot",
        )
        self.assertEqual(get_snapshot_response.status_code, 200)
        self.assertNotIn("debug_body", get_snapshot_response.json()["snapshot"])
        get_snapshot_with_debug_response = self.client.get(
            "/context-workspaces/runs/run-http/snapshot?include_debug_body=true",
        )
        self.assertEqual(get_snapshot_with_debug_response.status_code, 200)
        self.assertEqual(
            get_snapshot_with_debug_response.json()["snapshot"]["debug_body"],
            debug_body,
        )
        self.assertEqual(
            get_snapshot_response.json()["snapshot"]["included_refs"][0]["item_id"],
            "item-http-1",
        )

        get_snapshot_by_id_response = self.client.get(
            f"/context-workspaces/snapshots/{snapshot_id}",
        )
        self.assertEqual(get_snapshot_by_id_response.status_code, 200)
        self.assertNotIn("debug_body", get_snapshot_by_id_response.json()["snapshot"])
        self.assertEqual(
            get_snapshot_by_id_response.json()["snapshot"]["id"],
            snapshot_id,
        )
        get_snapshot_by_id_with_debug_response = self.client.get(
            f"/context-workspaces/snapshots/{snapshot_id}?include_debug_body=true",
        )
        self.assertEqual(get_snapshot_by_id_with_debug_response.status_code, 200)
        self.assertEqual(
            get_snapshot_by_id_with_debug_response.json()["snapshot"]["debug_body"],
            debug_body,
        )
