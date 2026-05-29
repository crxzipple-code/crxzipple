from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from crxzipple.interfaces.http.app import create_app
from crxzipple.modules.session.interfaces.http_models import (
    SessionRequest,
    SessionResponse,
)
from tests.unit.skill_test_support import write_skill_package
from tests.unit.support import SqliteTestHarness


class SessionHttpTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_openapi_provider_paths = os.environ.get(
            "APP_TOOL_OPENAPI_PROVIDER_PATHS",
        )
        os.environ["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = os.pathsep
        self._skills_tempdir = tempfile.TemporaryDirectory()
        skills_root = Path(self._skills_tempdir.name)
        self._global_skills_patcher = patch(
            "crxzipple.modules.skills.infrastructure.filesystem.repository.DEFAULT_GLOBAL_SKILLS_DIR",
            skills_root / "global",
        )
        self._system_skills_patcher = patch(
            "crxzipple.modules.skills.infrastructure.filesystem.repository.DEFAULT_SYSTEM_SKILLS_DIR",
            skills_root / "system",
        )
        self._global_skills_patcher.start()
        self._system_skills_patcher.start()
        write_skill_package(
            skills_root / "system" / "memory-recall",
            name="memory-recall",
            description=(
                "Use this skill when earlier decisions, preferences, commitments, "
                "or durable workspace context may affect the current answer."
            ),
            instructions=(
                "# Memory Recall\n\n"
                "Use this skill when earlier decisions, preferences, commitments, "
                "or durable workspace context may affect the current answer.\n"
            ),
            allowed_tools=("memory_search", "memory_read", "memory_write_daily"),
        )
        self.harness = SqliteTestHarness()
        self.harness.initialize_schema()
        self.client = TestClient(create_app(database_url=self.harness.database_url))

    def tearDown(self) -> None:
        self.client.close()
        self.client.app.state.container.close()
        self.harness.close()
        self._system_skills_patcher.stop()
        self._global_skills_patcher.stop()
        self._skills_tempdir.cleanup()
        if self.previous_openapi_provider_paths is None:
            os.environ.pop("APP_TOOL_OPENAPI_PROVIDER_PATHS", None)
        else:
            os.environ["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = (
                self.previous_openapi_provider_paths
            )

    def _register_llm_and_agent(self) -> str:
        llm_response = self.client.post(
            "/llms",
            json={
                "id": "openai.gpt-5.4-mini",
                "provider": "openai",
                "api_family": "openai_responses",
                "model_name": "gpt-5.4-mini",
                "credential_binding_id": "openai-api-key",
            },
        )
        self.assertEqual(llm_response.status_code, 201)

        agent_response = self.client.post(
            "/agents",
            json={
                "id": "assistant",
                "name": "Assistant",
                "llm_routing_policy": {"default_llm_id": "openai.gpt-5.4-mini"},
            },
        )
        self.assertEqual(agent_response.status_code, 201)
        return agent_response.json()["runtime_preferences"]["home_dir"]

    def test_session_http_models_only_expose_reply(self) -> None:
        request_schema = SessionRequest.model_json_schema()
        response_schema = SessionResponse.model_json_schema()

        self.assertIn("reply", request_schema["properties"])
        self.assertNotIn("delivery", request_schema["properties"])
        self.assertIn("reply", response_schema["properties"])
        self.assertNotIn("delivery", response_schema["properties"])

    def test_session_endpoints_manage_history_and_reset_instances(self) -> None:
        agent_home = self._register_llm_and_agent()

        create_response = self.client.post(
            "/sessions",
            json={
                "key": "agent:assistant:main",
                "runtime_binding": {
                    "agent_id": "assistant",
                },
                "channel": "webchat",
                "chat_type": "direct",
                "origin": {"provider": "webchat", "surface": "browser"},
                "reply": {"channel": "webchat", "to": "user:1"},
                "metadata": {"scope": "main"},
            },
        )

        self.assertEqual(create_response.status_code, 201)
        create_payload = create_response.json()
        self.assertEqual(create_payload["key"], "agent:assistant:main")
        self.assertEqual(
            create_payload["runtime_binding"],
            {
                "agent_id": "assistant",
                "workspace": agent_home,
            },
        )
        self.assertEqual(create_payload["channel"], "webchat")
        self.assertEqual(create_payload["reply"], {"channel": "webchat", "to": "user:1"})
        self.assertNotIn("delivery", create_payload)
        self.assertTrue(create_payload["created_at"].endswith("+00:00"))
        self.assertTrue(create_payload["updated_at"].endswith("+00:00"))
        self.assertTrue(create_payload["last_reset_at"].endswith("+00:00"))
        first_active_session_id = create_payload["active_session_id"]

        get_response = self.client.get("/sessions/agent:assistant:main")
        list_response = self.client.get("/sessions")

        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["active_session_id"], first_active_session_id)
        self.assertNotIn("compatibility_turn_stream", get_response.json())
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual([item["key"] for item in list_response.json()], ["agent:assistant:main"])

        first_message = self.client.post(
            "/sessions/agent:assistant:main/messages",
            json={
                "role": "user",
                "content_payload": {"blocks": [{"type": "text", "text": "hello"}]},
            },
        )
        second_message = self.client.post(
            "/sessions/agent:assistant:main/messages",
            json={
                "role": "assistant",
                "content_payload": {"blocks": [{"type": "text", "text": "hi there"}]},
            },
        )

        self.assertEqual(first_message.status_code, 201)
        self.assertEqual(second_message.status_code, 201)
        self.assertEqual(first_message.json()["session_id"], first_active_session_id)
        self.assertEqual(second_message.json()["session_id"], first_active_session_id)
        self.assertEqual(first_message.json()["sequence_no"], 1)
        self.assertEqual(first_message.json()["kind"], "message")
        self.assertTrue(first_message.json()["created_at"].endswith("+00:00"))
        self.assertTrue(second_message.json()["created_at"].endswith("+00:00"))
        self.assertEqual(
            first_message.json()["content_payload"],
            {"blocks": [{"type": "text", "text": "hello"}]},
        )
        self.assertEqual(second_message.json()["sequence_no"], 2)

        history_response = self.client.get("/sessions/agent:assistant:main/messages")
        active_history_response = self.client.get(
            "/sessions/agent:assistant:main/messages",
            params={"active_session_only": True},
        )

        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(
            history_response.json()[0]["content_payload"],
            {"blocks": [{"type": "text", "text": "hello"}]},
        )
        self.assertEqual(
            history_response.json()[1]["content_payload"],
            {"blocks": [{"type": "text", "text": "hi there"}]},
        )
        self.assertEqual(len(active_history_response.json()), 2)

        reset_response = self.client.post(
            "/sessions/agent:assistant:main/reset",
            json={},
        )

        self.assertEqual(reset_response.status_code, 200)
        reset_payload = reset_response.json()
        self.assertNotEqual(reset_payload["active_session_id"], first_active_session_id)

        instances_response = self.client.get("/sessions/agent:assistant:main/instances")
        self.assertEqual(instances_response.status_code, 200)
        instances_payload = instances_response.json()
        self.assertEqual(len(instances_payload), 2)
        self.assertEqual(instances_payload[0]["id"], first_active_session_id)
        self.assertEqual(
            instances_payload[0]["runtime_binding"],
            {
                "agent_id": "assistant",
                "workspace": agent_home,
            },
        )
        self.assertEqual(instances_payload[0]["kind"], "main")
        self.assertEqual(instances_payload[0]["status"], "closed")
        self.assertEqual(instances_payload[0]["reset_reason"], "manual")
        self.assertTrue(instances_payload[0]["opened_at"].endswith("+00:00"))
        self.assertTrue(instances_payload[0]["closed_at"].endswith("+00:00"))
        self.assertEqual(instances_payload[1]["id"], reset_payload["active_session_id"])
        self.assertEqual(instances_payload[1]["status"], "active")
        self.assertTrue(instances_payload[1]["opened_at"].endswith("+00:00"))

        active_history_after_reset = self.client.get(
            "/sessions/agent:assistant:main/messages",
            params={"active_session_only": True},
        )
        self.assertEqual(active_history_after_reset.status_code, 200)
        self.assertEqual(active_history_after_reset.json(), [])

        third_message = self.client.post(
            "/sessions/agent:assistant:main/messages",
            json={
                "role": "user",
                "content_payload": {"blocks": [{"type": "text", "text": "fresh start"}]},
            },
        )
        latest_active_history = self.client.get(
            "/sessions/agent:assistant:main/messages",
            params={"active_session_only": True},
        )

        self.assertEqual(third_message.status_code, 201)
        self.assertEqual(
            third_message.json()["session_id"],
            reset_payload["active_session_id"],
        )
        self.assertEqual(
            latest_active_history.json()[0]["content_payload"],
            {"blocks": [{"type": "text", "text": "fresh start"}]},
        )

    def test_session_message_endpoint_accepts_structured_payload_only_messages(self) -> None:
        self._register_llm_and_agent()

        create_response = self.client.post(
            "/sessions",
            json={
                "key": "agent:assistant:main",
                "runtime_binding": {
                    "agent_id": "assistant",
                },
            },
        )
        self.assertEqual(create_response.status_code, 201)

        message_response = self.client.post(
            "/sessions/agent:assistant:main/messages",
            json={
                "role": "tool",
                "kind": "tool_result",
                "content_payload": {"tool": "search", "result": "ok"},
                "source_kind": "tool_run",
                "source_id": "run-1",
                "visibility": "internal",
            },
        )

        self.assertEqual(message_response.status_code, 201)
        message_payload = message_response.json()
        self.assertEqual(message_payload["sequence_no"], 1)
        self.assertEqual(message_payload["kind"], "tool_result")
        self.assertEqual(message_payload["content_payload"]["tool"], "search")
        self.assertEqual(message_payload["source_kind"], "tool_run")
        self.assertEqual(message_payload["source_id"], "run-1")
        self.assertEqual(message_payload["visibility"], "internal")

    def test_session_create_endpoint_accepts_runtime_binding_payload(self) -> None:
        self._register_llm_and_agent()

        create_response = self.client.post(
            "/sessions",
            json={
                "key": "agent:assistant:main",
                "runtime_binding": {
                    "agent_id": "assistant",
                    "workspace": "/tmp/legacy-session-workspace",
                },
            },
        )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(
            create_response.json()["runtime_binding"],
            {
                "agent_id": "assistant",
                "workspace": "/tmp/legacy-session-workspace",
            },
        )

    def test_session_resolve_endpoint_routes_and_ensures_main_session(self) -> None:
        agent_home = self._register_llm_and_agent()

        resolve_response = self.client.post(
            "/sessions/resolve",
            json={
                "agent_id": "assistant",
                "channel": "webchat",
                "label": "browser",
                "surface": "chat",
                "metadata": {"scope": "main"},
                "ensure": True,
            },
        )

        self.assertEqual(resolve_response.status_code, 200)
        resolve_payload = resolve_response.json()
        self.assertEqual(resolve_payload["key"], "agent:assistant:main")
        self.assertEqual(resolve_payload["kind"], "main")
        self.assertTrue(resolve_payload["created"])
        self.assertEqual(resolve_payload["session"]["chat_type"], "direct")
        self.assertEqual(resolve_payload["session"]["channel"], "webchat")
        self.assertEqual(
            resolve_payload["session"]["runtime_binding"],
            {
                "agent_id": "assistant",
                "workspace": agent_home,
            },
        )
        self.assertEqual(
            resolve_payload["active_instance"]["runtime_binding"],
            {
                "agent_id": "assistant",
                "workspace": agent_home,
            },
        )
        self.assertEqual(resolve_payload["active_instance"]["kind"], "main")

        instances_response = self.client.get("/sessions/agent:assistant:main/instances")
        self.assertEqual(instances_response.status_code, 200)
        instances_payload = instances_response.json()
        self.assertEqual(len(instances_payload), 1)
        self.assertEqual(instances_payload[0]["kind"], "main")
        self.assertEqual(instances_payload[0]["status"], "active")


if __name__ == "__main__":
    unittest.main()
