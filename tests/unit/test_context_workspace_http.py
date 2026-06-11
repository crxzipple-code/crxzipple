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
            "/sessions/session:adapter/messages",
            json={
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

        self.assertTrue(any(node["id"] == "session.segment.current" for node in nodes))
        self.assertTrue(any(node["id"] == "session.messages.current" for node in nodes))

    def test_context_workspace_tree_action_and_render_snapshot(self) -> None:
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
        prompt_body = render_payload["prompt_body"]
        self.assertIn("<context_tree", prompt_body)
        self.assertIn("rendered_prompt", render_payload["estimate_breakdown"])
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
            "/context-workspaces/by-session/session:http/render-snapshots",
            json={
                "run_id": "run-http",
                "prompt_body": prompt_body,
                "estimate": render_payload["estimate"],
                "included_node_ids": render_payload["included_node_ids"],
            },
        )
        self.assertEqual(snapshot_response.status_code, 200)
        self.assertEqual(snapshot_response.json()["snapshot"]["run_id"], "run-http")
        snapshot_id = snapshot_response.json()["snapshot"]["id"]

        get_snapshot_response = self.client.get(
            "/context-workspaces/runs/run-http/render-snapshot",
        )
        self.assertEqual(get_snapshot_response.status_code, 200)
        self.assertEqual(
            get_snapshot_response.json()["snapshot"]["prompt_body"],
            prompt_body,
        )

        get_snapshot_by_id_response = self.client.get(
            f"/context-workspaces/render-snapshots/{snapshot_id}",
        )
        self.assertEqual(get_snapshot_by_id_response.status_code, 200)
        self.assertEqual(
            get_snapshot_by_id_response.json()["snapshot"]["id"],
            snapshot_id,
        )
