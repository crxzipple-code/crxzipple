from __future__ import annotations

from tests.unit.cli_test_support import *


class SessionCliTestCase(CliModuleTestCase):
    def _register_llm_and_agent(self) -> None:
        llm_result = self.invoke_cli(
            [
                "llm",
                "register-profile",
                "openai.gpt-5.4-mini",
                "openai",
                "openai_responses",
                "gpt-5.4-mini",
                "--credential-binding-id",
                "openai-api-key",
            ],
        )
        self.assertEqual(llm_result.exit_code, 0)
        agent_result = self.invoke_cli(
            [
                "agent",
                "register-profile",
                "assistant",
                "Assistant",
                "openai.gpt-5.4-mini",
            ],
        )
        self.assertEqual(agent_result.exit_code, 0)

    def test_session_commands_manage_history_and_reset_instances(self) -> None:
        self._register_llm_and_agent()

        start_result = self.invoke_cli(
            [
                "session",
                "start",
                "agent:assistant:main",
                "--agent-id",
                "assistant",
                "--channel",
                "webchat",
                "--chat-type",
                "direct",
                "--metadata",
                '{"scope":"main"}',
            ],
        )

        self.assertEqual(start_result.exit_code, 0)
        start_payload = json.loads(start_result.stdout)
        self.assertEqual(start_payload["key"], "agent:assistant:main")
        self.assertEqual(start_payload["runtime_binding"]["agent_id"], "assistant")
        self.assertTrue(start_payload["runtime_binding"]["workspace"])
        first_active_session_id = start_payload["active_session_id"]

        append_user_result = self.invoke_cli(
            [
                "session",
                "append-message",
                "agent:assistant:main",
                "user",
                "--content-payload",
                '{"blocks":[{"type":"text","text":"hello"}]}',
            ],
        )
        append_assistant_result = self.invoke_cli(
            [
                "session",
                "append-message",
                "agent:assistant:main",
                "assistant",
                "--content-payload",
                '{"blocks":[{"type":"text","text":"hi there"}]}',
            ],
        )

        self.assertEqual(append_user_result.exit_code, 0)
        self.assertEqual(append_assistant_result.exit_code, 0)
        append_user_payload = json.loads(append_user_result.stdout)
        append_assistant_payload = json.loads(append_assistant_result.stdout)
        self.assertEqual(append_user_payload["session_id"], first_active_session_id)
        self.assertEqual(append_user_payload["sequence_no"], 1)
        self.assertEqual(append_user_payload["kind"], "message")
        self.assertEqual(
            append_user_payload["content_payload"],
            {"blocks": [{"type": "text", "text": "hello"}]},
        )
        self.assertEqual(append_assistant_payload["sequence_no"], 2)

        history_result = self.invoke_cli(
            ["session", "history", "agent:assistant:main"],
        )

        self.assertEqual(history_result.exit_code, 0)
        history_payload = json.loads(history_result.stdout)
        self.assertEqual(
            [item["content_payload"] for item in history_payload],
            [
                {"blocks": [{"type": "text", "text": "hello"}]},
                {"blocks": [{"type": "text", "text": "hi there"}]},
            ],
        )

        reset_result = self.invoke_cli(
            ["session", "reset", "agent:assistant:main"],
        )

        self.assertEqual(reset_result.exit_code, 0)
        reset_payload = json.loads(reset_result.stdout)
        self.assertNotEqual(reset_payload["active_session_id"], first_active_session_id)

        instances_result = self.invoke_cli(
            ["session", "instances", "agent:assistant:main"],
        )
        self.assertEqual(instances_result.exit_code, 0)
        instances_payload = json.loads(instances_result.stdout)
        self.assertEqual(len(instances_payload), 2)
        self.assertEqual(instances_payload[0]["id"], first_active_session_id)
        self.assertEqual(
            instances_payload[0]["runtime_binding"]["agent_id"],
            "assistant",
        )
        self.assertTrue(instances_payload[0]["runtime_binding"]["workspace"])
        self.assertEqual(instances_payload[0]["kind"], "main")
        self.assertEqual(instances_payload[0]["status"], "closed")
        self.assertEqual(instances_payload[0]["reset_reason"], "manual")
        self.assertEqual(instances_payload[1]["id"], reset_payload["active_session_id"])
        self.assertEqual(instances_payload[1]["status"], "active")

        active_history_result = self.invoke_cli(
            ["session", "history", "agent:assistant:main", "--active-only"],
        )
        self.assertEqual(active_history_result.exit_code, 0)
        self.assertEqual(json.loads(active_history_result.stdout), [])

        append_fresh_result = self.invoke_cli(
            [
                "session",
                "append-message",
                "agent:assistant:main",
                "user",
                "--content-payload",
                '{"blocks":[{"type":"text","text":"fresh start"}]}',
            ],
        )
        get_result = self.invoke_cli(
            ["session", "get", "agent:assistant:main"],
        )

        self.assertEqual(append_fresh_result.exit_code, 0)
        self.assertEqual(get_result.exit_code, 0)
        self.assertEqual(
            json.loads(append_fresh_result.stdout)["session_id"],
            reset_payload["active_session_id"],
        )
        self.assertEqual(
            json.loads(get_result.stdout)["active_session_id"],
            reset_payload["active_session_id"],
        )

    def test_session_append_message_command_supports_structured_payloads(self) -> None:
        self._register_llm_and_agent()

        start_result = self.invoke_cli(
            [
                "session",
                "start",
                "agent:assistant:main",
                "--agent-id",
                "assistant",
            ],
        )
        self.assertEqual(start_result.exit_code, 0)

        append_result = self.invoke_cli(
            [
                "session",
                "append-message",
                "agent:assistant:main",
                "tool",
                "--kind",
                "tool_result",
                "--content-payload",
                '{"tool":"search","result":"ok"}',
                "--source-kind",
                "tool_run",
                "--source-id",
                "run-1",
                "--visibility",
                "internal",
            ],
        )

        self.assertEqual(append_result.exit_code, 0)
        append_payload = json.loads(append_result.stdout)
        self.assertEqual(append_payload["sequence_no"], 1)
        self.assertEqual(append_payload["kind"], "tool_result")
        self.assertEqual(append_payload["content_payload"]["tool"], "search")
        self.assertEqual(append_payload["source_kind"], "tool_run")
        self.assertEqual(append_payload["source_id"], "run-1")
        self.assertEqual(append_payload["visibility"], "internal")

    def test_session_start_command_accepts_reply_payload(self) -> None:
        self._register_llm_and_agent()

        start_result = self.invoke_cli(
            [
                "session",
                "start",
                "agent:assistant:main",
                "--agent-id",
                "assistant",
                "--reply",
                '{"channel":"webchat","to":"user:1"}',
            ],
        )

        self.assertEqual(start_result.exit_code, 0)
        start_payload = json.loads(start_result.stdout)
        self.assertEqual(start_payload["reply"], {"channel": "webchat", "to": "user:1"})
        self.assertNotIn("delivery", start_payload)

    def test_session_resolve_key_command_routes_and_ensures_main_session(self) -> None:
        self._register_llm_and_agent()

        resolve_result = self.invoke_cli(
            [
                "session",
                "resolve-key",
                "assistant",
                "--channel",
                "webchat",
                "--label",
                "browser",
                "--surface",
                "chat",
                "--metadata",
                '{"scope":"main"}',
                "--ensure",
            ],
        )

        self.assertEqual(resolve_result.exit_code, 0)
        resolve_payload = json.loads(resolve_result.stdout)
        self.assertEqual(resolve_payload["key"], "agent:assistant:main")
        self.assertEqual(resolve_payload["kind"], "main")
        self.assertTrue(resolve_payload["created"])
        self.assertEqual(resolve_payload["session"]["chat_type"], "direct")
        self.assertEqual(resolve_payload["session"]["channel"], "webchat")
        self.assertEqual(
            resolve_payload["session"]["runtime_binding"]["agent_id"],
            "assistant",
        )
        self.assertTrue(resolve_payload["session"]["runtime_binding"]["workspace"])
        self.assertEqual(
            resolve_payload["active_instance"]["runtime_binding"]["agent_id"],
            "assistant",
        )
        self.assertTrue(
            resolve_payload["active_instance"]["runtime_binding"]["workspace"],
        )
        self.assertEqual(resolve_payload["active_instance"]["kind"], "main")

        instances_result = self.invoke_cli(
            ["session", "instances", "agent:assistant:main"],
        )
        self.assertEqual(instances_result.exit_code, 0)
        instances_payload = json.loads(instances_result.stdout)
        self.assertEqual(len(instances_payload), 1)
        self.assertEqual(instances_payload[0]["kind"], "main")
        self.assertEqual(instances_payload[0]["status"], "active")


if __name__ == "__main__":
    unittest.main()
