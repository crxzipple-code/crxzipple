from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest

from typer.testing import CliRunner

from crxzipple.interfaces.cli.main import _is_missing_database_schema_error
from crxzipple.interfaces.cli.main import app
from crxzipple.interfaces.cli import db as db_cli
from crxzipple.modules.dispatch.application import (
    CreateDispatchTaskInput,
    EnqueueDispatchTaskInput,
)
from tests.unit.support import (
    SampleApiServer,
    SampleLlmApiServer,
    SqliteTestHarness,
    fixture_path,
    openapi_fixture_path,
)

HEAD_REVISION = "0016_session_hot_path_indexes"


class CliTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.runner = CliRunner()
        self.harness = SqliteTestHarness()
        self.harness.initialize_schema()
        self.env = {
            "APP_DATABASE_URL": self.harness.database_url,
            "APP_TOOL_OPENAPI_PROVIDER_PATHS": os.pathsep,
        }

    def tearDown(self) -> None:
        self.harness.close()

    def test_root_help_exposes_module_groups(self) -> None:
        result = self.runner.invoke(app, ["--help"], env=self.env)

        self.assertEqual(result.exit_code, 0)
        self.assertIn("ask", result.stdout)
        self.assertIn("chat", result.stdout)
        self.assertIn("serve", result.stdout)
        self.assertIn("tool", result.stdout)
        self.assertIn("tool-worker", result.stdout)
        self.assertIn("dispatch", result.stdout)
        self.assertIn("orchestration", result.stdout)
        self.assertIn("orchestration-worker", result.stdout)
        self.assertIn("session", result.stdout)
        self.assertIn("llm", result.stdout)
        self.assertIn("agent", result.stdout)
        self.assertIn("auth", result.stdout)
        self.assertIn("db", result.stdout)

    def test_agent_cli_registers_and_lists_profiles(self) -> None:
        register_result = self.runner.invoke(
            app,
            [
                "agent",
                "register-profile",
                "writer",
                "Writer",
                "openai.gpt-5.4-mini",
                "--description",
                "Writes concise summaries.",
                "--display-name",
                "Writer Agent",
                "--stream-by-default",
                "--workspace",
                "/tmp/workspace",
            ],
            env=self.env,
        )

        self.assertEqual(register_result.exit_code, 0)
        self.assertIn('"id": "writer"', register_result.stdout)
        self.assertIn('"display_name": "Writer Agent"', register_result.stdout)

        list_result = self.runner.invoke(app, ["agent", "list"], env=self.env)
        get_result = self.runner.invoke(app, ["agent", "get", "writer"], env=self.env)

        self.assertEqual(list_result.exit_code, 0)
        self.assertEqual(get_result.exit_code, 0)
        self.assertIn('"name": "Writer"', list_result.stdout)
        self.assertIn('"default_llm_id": "openai.gpt-5.4-mini"', get_result.stdout)

    def test_dispatch_cli_manages_task_lifecycle(self) -> None:
        create_result = self.runner.invoke(
            app,
            [
                "dispatch",
                "create",
                "orchestration_run",
                "run-cli-1",
                "--task-id",
                "dispatch-cli-1",
                "--lane-key",
                "bulk:cli",
                "--metadata",
                '{"source":"cli"}',
            ],
            env=self.env,
        )
        self.assertEqual(create_result.exit_code, 0)
        create_payload = json.loads(create_result.stdout)
        self.assertEqual(create_payload["status"], "created")

        enqueue_result = self.runner.invoke(
            app,
            [
                "dispatch",
                "enqueue",
                "dispatch-cli-1",
                "--policy",
                "jump_queue",
                "--priority",
                "5",
            ],
            env=self.env,
        )
        self.assertEqual(enqueue_result.exit_code, 0)
        self.assertEqual(json.loads(enqueue_result.stdout)["status"], "queued")

        claim_result = self.runner.invoke(
            app,
            [
                "dispatch",
                "claim-next",
                "--owner-kind",
                "orchestration_run",
                "--worker-id",
                "cli-worker",
                "--lease-seconds",
                "30",
            ],
            env=self.env,
        )
        self.assertEqual(claim_result.exit_code, 0)
        claim_payload = json.loads(claim_result.stdout)
        self.assertEqual(claim_payload["id"], "dispatch-cli-1")
        self.assertEqual(claim_payload["status"], "claimed")
        self.assertIsNotNone(claim_payload["heartbeat_at"])
        self.assertIsNotNone(claim_payload["lease_expires_at"])

        heartbeat_result = self.runner.invoke(
            app,
            [
                "dispatch",
                "heartbeat",
                "dispatch-cli-1",
                "--worker-id",
                "cli-worker",
                "--claim-token",
                claim_payload["claim_token"],
                "--lease-seconds",
                "45",
            ],
            env=self.env,
        )
        self.assertEqual(heartbeat_result.exit_code, 0)
        self.assertEqual(json.loads(heartbeat_result.stdout)["status"], "claimed")

        wait_result = self.runner.invoke(
            app,
            [
                "dispatch",
                "wait",
                "dispatch-cli-1",
                "--reason",
                "waiting_for_event",
            ],
            env=self.env,
        )
        self.assertEqual(wait_result.exit_code, 0)
        self.assertEqual(json.loads(wait_result.stdout)["status"], "waiting")

        requeue_result = self.runner.invoke(
            app,
            [
                "dispatch",
                "requeue",
                "dispatch-cli-1",
                "--policy",
                "resume_first",
                "--reason",
                "event_ready",
            ],
            env=self.env,
        )
        self.assertEqual(requeue_result.exit_code, 0)
        self.assertEqual(json.loads(requeue_result.stdout)["policy"], "resume_first")

        get_result = self.runner.invoke(
            app,
            ["dispatch", "get", "dispatch-cli-1"],
            env=self.env,
        )
        list_result = self.runner.invoke(
            app,
            [
                "dispatch",
                "list",
                "--status",
                "queued",
                "--owner-kind",
                "orchestration_run",
            ],
            env=self.env,
        )
        self.assertEqual(get_result.exit_code, 0)
        self.assertEqual(json.loads(get_result.stdout)["id"], "dispatch-cli-1")
        self.assertEqual(list_result.exit_code, 0)
        self.assertEqual(
            [item["id"] for item in json.loads(list_result.stdout)],
            ["dispatch-cli-1"],
        )

        complete_result = self.runner.invoke(
            app,
            ["dispatch", "complete", "dispatch-cli-1"],
            env=self.env,
        )
        self.assertEqual(complete_result.exit_code, 0)
        self.assertEqual(json.loads(complete_result.stdout)["status"], "completed")

    def test_dispatch_cli_recovers_abandoned_tasks_with_owner_filter(self) -> None:
        container = self.harness.build_container()
        first = container.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-cli-tool",
                owner_kind="tool_run",
                owner_id="tool-run-cli",
            ),
        )
        second = container.dispatch_service.create_task(
            CreateDispatchTaskInput(
                task_id="dispatch-cli-orch",
                owner_kind="orchestration_run",
                owner_id="orch-run-cli",
            ),
        )
        container.dispatch_service.enqueue_task(EnqueueDispatchTaskInput(task_id=first.id))
        container.dispatch_service.enqueue_task(EnqueueDispatchTaskInput(task_id=second.id))
        container.dispatch_service.claim_next_queued_task(
            owner_kind="tool_run",
            worker_id="tool-worker",
            lease_seconds=5,
        )
        container.dispatch_service.claim_next_queued_task(
            owner_kind="orchestration_run",
            worker_id="orch-worker",
            lease_seconds=5,
        )
        with container.uow_factory() as uow:
            tool_task = uow.dispatch_tasks.get(first.id)
            orch_task = uow.dispatch_tasks.get(second.id)
            assert tool_task is not None
            assert orch_task is not None
            tool_task.lease_expires_at = tool_task.claimed_at
            orch_task.lease_expires_at = orch_task.claimed_at
            uow.dispatch_tasks.add(tool_task)
            uow.dispatch_tasks.add(orch_task)
            uow.commit()

        recover_result = self.runner.invoke(
            app,
            [
                "dispatch",
                "recover-abandoned",
                "--owner-kind",
                "tool_run",
                "--reason",
                "lease_expired",
            ],
            env=self.env,
        )
        self.assertEqual(recover_result.exit_code, 0)
        self.assertEqual(
            [item["id"] for item in json.loads(recover_result.stdout)],
            ["dispatch-cli-tool"],
        )

    def test_agent_sync_profiles_loads_yaml_configs_with_defaults(self) -> None:
        env = dict(self.env)

        with tempfile.TemporaryDirectory() as tempdir:
            profiles_dir = Path(tempdir) / "agent_profiles"
            profiles_dir.mkdir()
            (profiles_dir / "defaults.yaml").write_text(
                "\n".join(
                    [
                        "defaults:",
                        "  description: Default agent profile description.",
                        "  instruction_policy:",
                        "    stream_by_default: true",
                        "    response_style: concise",
                        "  llm_routing_policy:",
                        "    default_llm_id: openai.gpt-5.4-mini",
                        "  execution_policy:",
                        "    timeout_seconds: 180",
                        "    max_turns: 9",
                        "  runtime_preferences:",
                        "    sandbox_mode: sandbox",
                        "profiles:",
                        "  - id: writer",
                        "    name: Writer",
                        "    identity:",
                        "      display_name: Writer Agent",
                        "",
                    ],
                ),
                encoding="utf-8",
            )
            env["APP_AGENT_PROFILE_PATHS"] = str(profiles_dir)

            sync_result = self.runner.invoke(
                app,
                ["agent", "sync-profiles"],
                env=env,
            )

            self.assertEqual(sync_result.exit_code, 0)
            sync_payload = json.loads(sync_result.stdout)
            self.assertEqual([item["id"] for item in sync_payload], ["writer"])
            self.assertEqual(
                sync_payload[0]["llm_routing_policy"]["default_llm_id"],
                "openai.gpt-5.4-mini",
            )
            self.assertTrue(sync_payload[0]["instruction_policy"]["stream_by_default"])
            self.assertEqual(
                sync_payload[0]["runtime_preferences"]["sandbox_mode"],
                "sandbox",
            )

            get_result = self.runner.invoke(app, ["agent", "get", "writer"], env=env)
            self.assertEqual(get_result.exit_code, 0)
            get_payload = json.loads(get_result.stdout)
            self.assertEqual(
                get_payload["identity"]["display_name"],
                "Writer Agent",
            )
            self.assertEqual(get_payload["execution_policy"]["timeout_seconds"], 180)

    def test_session_commands_manage_history_and_reset_instances(self) -> None:
        llm_result = self.runner.invoke(
            app,
            [
                "llm",
                "register-profile",
                "openai.gpt-5.4-mini",
                "openai",
                "openai_responses",
                "gpt-5.4-mini",
            ],
            env=self.env,
        )
        self.assertEqual(llm_result.exit_code, 0)

        agent_result = self.runner.invoke(
            app,
            [
                "agent",
                "register-profile",
                "assistant",
                "Assistant",
                "openai.gpt-5.4-mini",
            ],
            env=self.env,
        )
        self.assertEqual(agent_result.exit_code, 0)

        start_result = self.runner.invoke(
            app,
            [
                "session",
                "start",
                "agent:assistant:main",
                "--agent-id",
                "assistant",
                "--llm-id",
                "openai.gpt-5.4-mini",
                "--channel",
                "webchat",
                "--chat-type",
                "direct",
                "--metadata",
                '{"scope":"main"}',
            ],
            env=self.env,
        )

        self.assertEqual(start_result.exit_code, 0)
        start_payload = json.loads(start_result.stdout)
        self.assertEqual(start_payload["key"], "agent:assistant:main")
        self.assertEqual(
            start_payload["runtime_binding"],
            {
                "agent_id": "assistant",
                "llm_id": "openai.gpt-5.4-mini",
            },
        )
        first_active_session_id = start_payload["active_session_id"]

        append_user_result = self.runner.invoke(
            app,
            [
                "session",
                "append-message",
                "agent:assistant:main",
                "user",
                "hello",
            ],
            env=self.env,
        )
        append_assistant_result = self.runner.invoke(
            app,
            [
                "session",
                "append-message",
                "agent:assistant:main",
                "assistant",
                "hi there",
            ],
            env=self.env,
        )

        self.assertEqual(append_user_result.exit_code, 0)
        self.assertEqual(append_assistant_result.exit_code, 0)
        append_user_payload = json.loads(append_user_result.stdout)
        append_assistant_payload = json.loads(append_assistant_result.stdout)
        self.assertEqual(append_user_payload["session_id"], first_active_session_id)
        self.assertEqual(append_user_payload["sequence_no"], 1)
        self.assertEqual(append_user_payload["kind"], "message")
        self.assertEqual(append_user_payload["content_payload"], {"text": "hello"})
        self.assertEqual(append_assistant_payload["sequence_no"], 2)

        history_result = self.runner.invoke(
            app,
            ["session", "history", "agent:assistant:main"],
            env=self.env,
        )

        self.assertEqual(history_result.exit_code, 0)
        history_payload = json.loads(history_result.stdout)
        self.assertEqual([item["content"] for item in history_payload], ["hello", "hi there"])

        reset_result = self.runner.invoke(
            app,
            ["session", "reset", "agent:assistant:main"],
            env=self.env,
        )

        self.assertEqual(reset_result.exit_code, 0)
        reset_payload = json.loads(reset_result.stdout)
        self.assertNotEqual(reset_payload["active_session_id"], first_active_session_id)

        instances_result = self.runner.invoke(
            app,
            ["session", "instances", "agent:assistant:main"],
            env=self.env,
        )
        self.assertEqual(instances_result.exit_code, 0)
        instances_payload = json.loads(instances_result.stdout)
        self.assertEqual(len(instances_payload), 2)
        self.assertEqual(instances_payload[0]["id"], first_active_session_id)
        self.assertEqual(
            instances_payload[0]["runtime_binding"],
            {
                "agent_id": "assistant",
                "llm_id": "openai.gpt-5.4-mini",
            },
        )
        self.assertEqual(instances_payload[0]["kind"], "main")
        self.assertEqual(instances_payload[0]["status"], "closed")
        self.assertEqual(instances_payload[0]["reset_reason"], "manual")
        self.assertEqual(instances_payload[1]["id"], reset_payload["active_session_id"])
        self.assertEqual(instances_payload[1]["status"], "active")

        active_history_result = self.runner.invoke(
            app,
            ["session", "history", "agent:assistant:main", "--active-only"],
            env=self.env,
        )
        self.assertEqual(active_history_result.exit_code, 0)
        self.assertEqual(json.loads(active_history_result.stdout), [])

        append_fresh_result = self.runner.invoke(
            app,
            [
                "session",
                "append-message",
                "agent:assistant:main",
                "user",
                "fresh start",
            ],
            env=self.env,
        )
        get_result = self.runner.invoke(
            app,
            ["session", "get", "agent:assistant:main"],
            env=self.env,
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
        llm_result = self.runner.invoke(
            app,
            [
                "llm",
                "register-profile",
                "openai.gpt-5.4-mini",
                "openai",
                "openai_responses",
                "gpt-5.4-mini",
            ],
            env=self.env,
        )
        self.assertEqual(llm_result.exit_code, 0)

        agent_result = self.runner.invoke(
            app,
            [
                "agent",
                "register-profile",
                "assistant",
                "Assistant",
                "openai.gpt-5.4-mini",
            ],
            env=self.env,
        )
        self.assertEqual(agent_result.exit_code, 0)

        start_result = self.runner.invoke(
            app,
            [
                "session",
                "start",
                "agent:assistant:main",
                "--agent-id",
                "assistant",
                "--llm-id",
                "openai.gpt-5.4-mini",
            ],
            env=self.env,
        )
        self.assertEqual(start_result.exit_code, 0)

        append_result = self.runner.invoke(
            app,
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
            env=self.env,
        )

        self.assertEqual(append_result.exit_code, 0)
        append_payload = json.loads(append_result.stdout)
        self.assertEqual(append_payload["sequence_no"], 1)
        self.assertEqual(append_payload["kind"], "tool_result")
        self.assertEqual(append_payload["content"], None)
        self.assertEqual(append_payload["content_payload"]["tool"], "search")
        self.assertEqual(append_payload["source_kind"], "tool_run")
        self.assertEqual(append_payload["source_id"], "run-1")
        self.assertEqual(append_payload["visibility"], "internal")

    def test_session_resolve_key_command_routes_and_ensures_main_session(self) -> None:
        llm_result = self.runner.invoke(
            app,
            [
                "llm",
                "register-profile",
                "openai.gpt-5.4-mini",
                "openai",
                "openai_responses",
                "gpt-5.4-mini",
            ],
            env=self.env,
        )
        self.assertEqual(llm_result.exit_code, 0)

        agent_result = self.runner.invoke(
            app,
            [
                "agent",
                "register-profile",
                "assistant",
                "Assistant",
                "openai.gpt-5.4-mini",
            ],
            env=self.env,
        )
        self.assertEqual(agent_result.exit_code, 0)

        resolve_result = self.runner.invoke(
            app,
            [
                "session",
                "resolve-key",
                "assistant",
                "openai.gpt-5.4-mini",
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
            env=self.env,
        )

        self.assertEqual(resolve_result.exit_code, 0)
        resolve_payload = json.loads(resolve_result.stdout)
        self.assertEqual(resolve_payload["key"], "agent:assistant:main")
        self.assertEqual(resolve_payload["kind"], "main")
        self.assertTrue(resolve_payload["created"])
        self.assertEqual(resolve_payload["session"]["chat_type"], "direct")
        self.assertEqual(resolve_payload["session"]["channel"], "webchat")
        self.assertEqual(
            resolve_payload["session"]["runtime_binding"],
            {
                "agent_id": "assistant",
                "llm_id": "openai.gpt-5.4-mini",
            },
        )
        self.assertEqual(
            resolve_payload["active_instance"]["runtime_binding"],
            {
                "agent_id": "assistant",
                "llm_id": "openai.gpt-5.4-mini",
            },
        )
        self.assertEqual(resolve_payload["active_instance"]["kind"], "main")

        instances_result = self.runner.invoke(
            app,
            ["session", "instances", "agent:assistant:main"],
            env=self.env,
        )

        self.assertEqual(instances_result.exit_code, 0)
        instances_payload = json.loads(instances_result.stdout)
        self.assertEqual(len(instances_payload), 1)
        self.assertEqual(instances_payload[0]["kind"], "main")
        self.assertEqual(instances_payload[0]["status"], "active")

    def test_orchestration_intake_command_accepts_prepares_and_enqueues_run(self) -> None:
        llm_result = self.runner.invoke(
            app,
            [
                "llm",
                "register-profile",
                "openai.gpt-5.4-mini",
                "openai",
                "openai_responses",
                "gpt-5.4-mini",
            ],
            env=self.env,
        )
        self.assertEqual(llm_result.exit_code, 0)

        agent_result = self.runner.invoke(
            app,
            [
                "agent",
                "register-profile",
                "assistant",
                "Assistant",
                "openai.gpt-5.4-mini",
            ],
            env=self.env,
        )
        self.assertEqual(agent_result.exit_code, 0)

        intake_result = self.runner.invoke(
            app,
            [
                "orchestration",
                "intake",
                "assistant",
                "openai.gpt-5.4-mini",
                "draft a reply",
                "--source",
                "cli",
                "--channel",
                "webchat",
                "--label",
                "terminal",
                "--surface",
                "shell",
                "--session-metadata",
                '{"scope":"main"}',
                "--run-metadata",
                '{"correlation_id":"corr-1"}',
                "--queue-policy",
                "lane_jump_queue",
                "--enqueue",
            ],
            env=self.env,
        )

        self.assertEqual(intake_result.exit_code, 0)
        intake_payload = json.loads(intake_result.stdout)
        self.assertEqual(intake_payload["status"], "queued")
        self.assertEqual(intake_payload["stage"], "queued")
        self.assertEqual(
            intake_payload["bulk_key"],
            "conversation:main:webchat:default:main",
        )
        self.assertEqual(
            intake_payload["lane_key"],
            "bulk:conversation:main:webchat:default:main",
        )
        self.assertEqual(intake_payload["queue_policy"], "lane_jump_queue")
        self.assertEqual(intake_payload["agent_id"], "assistant")
        self.assertEqual(intake_payload["metadata"]["session_key"], "agent:assistant:main")
        self.assertEqual(intake_payload["metadata"]["session_kind"], "main")
        self.assertEqual(intake_payload["metadata"]["correlation_id"], "corr-1")

        get_result = self.runner.invoke(
            app,
            ["orchestration", "get", intake_payload["id"]],
            env=self.env,
        )
        list_result = self.runner.invoke(
            app,
            ["orchestration", "list", "--status", "queued"],
            env=self.env,
        )

        self.assertEqual(get_result.exit_code, 0)
        self.assertEqual(json.loads(get_result.stdout)["id"], intake_payload["id"])
        self.assertEqual(list_result.exit_code, 0)
        self.assertEqual(
            [item["id"] for item in json.loads(list_result.stdout)],
            [intake_payload["id"]],
        )

    def test_orchestration_worker_commands_drive_run_lifecycle(self) -> None:
        llm_result = self.runner.invoke(
            app,
            [
                "llm",
                "register-profile",
                "openai.gpt-5.4-mini",
                "openai",
                "openai_responses",
                "gpt-5.4-mini",
            ],
            env=self.env,
        )
        self.assertEqual(llm_result.exit_code, 0)

        agent_result = self.runner.invoke(
            app,
            [
                "agent",
                "register-profile",
                "assistant",
                "Assistant",
                "openai.gpt-5.4-mini",
            ],
            env=self.env,
        )
        self.assertEqual(agent_result.exit_code, 0)

        intake_result = self.runner.invoke(
            app,
            [
                "orchestration",
                "intake",
                "assistant",
                "openai.gpt-5.4-mini",
                "hello",
                "--run-id",
                "run-cli-worker",
                "--channel",
                "webchat",
                "--enqueue",
            ],
            env=self.env,
        )
        self.assertEqual(intake_result.exit_code, 0)

        claim_result = self.runner.invoke(
            app,
            ["orchestration-worker", "claim-next", "--worker-id", "worker-1"],
            env=self.env,
        )
        self.assertEqual(claim_result.exit_code, 0)
        self.assertEqual(json.loads(claim_result.stdout)["status"], "running")

        heartbeat_result = self.runner.invoke(
            app,
            [
                "orchestration-worker",
                "heartbeat",
                "run-cli-worker",
                "--worker-id",
                "worker-1",
            ],
            env=self.env,
        )
        self.assertEqual(heartbeat_result.exit_code, 0)
        self.assertEqual(json.loads(heartbeat_result.stdout)["status"], "running")

        advance_result = self.runner.invoke(
            app,
            [
                "orchestration-worker",
                "advance",
                "run-cli-worker",
                "--worker-id",
                "worker-1",
                "--stage",
                "llm",
                "--step-increment",
                "1",
            ],
            env=self.env,
        )
        self.assertEqual(advance_result.exit_code, 0)
        self.assertEqual(json.loads(advance_result.stdout)["stage"], "llm")

        wait_result = self.runner.invoke(
            app,
            [
                "orchestration-worker",
                "wait-tool",
                "run-cli-worker",
                "tool-run-1",
                "--worker-id",
                "worker-1",
            ],
            env=self.env,
        )
        self.assertEqual(wait_result.exit_code, 0)
        self.assertEqual(json.loads(wait_result.stdout)["status"], "waiting")

        resume_result = self.runner.invoke(
            app,
            ["orchestration-worker", "resume", "run-cli-worker"],
            env=self.env,
        )
        self.assertEqual(resume_result.exit_code, 0)
        self.assertEqual(json.loads(resume_result.stdout)["status"], "queued")

        reclaim_result = self.runner.invoke(
            app,
            ["orchestration-worker", "claim-next", "--worker-id", "worker-1"],
            env=self.env,
        )
        self.assertEqual(reclaim_result.exit_code, 0)
        self.assertEqual(json.loads(reclaim_result.stdout)["id"], "run-cli-worker")

        complete_result = self.runner.invoke(
            app,
            [
                "orchestration-worker",
                "complete",
                "run-cli-worker",
                "--worker-id",
                "worker-1",
                "--result",
                '{"output":"done"}',
            ],
            env=self.env,
        )
        self.assertEqual(complete_result.exit_code, 0)
        complete_payload = json.loads(complete_result.stdout)
        self.assertEqual(complete_payload["status"], "completed")
        self.assertEqual(complete_payload["result_payload"], {"output": "done"})

    def test_orchestration_worker_process_next_completes_minimal_llm_run(self) -> None:
        server = SampleLlmApiServer()
        previous_token = os.environ.get("OPENAI_COMPATIBLE_TOKEN")
        os.environ["OPENAI_COMPATIBLE_TOKEN"] = "sample-compat-token"
        server.start()

        try:
            llm_result = self.runner.invoke(
                app,
                [
                    "llm",
                    "register-profile",
                    "local-chat",
                    "openai_compatible",
                    "openai_chat_compatible",
                    "llama3.2",
                    "--base-url",
                    f"{server.base_url}/v1",
                    "--credential-binding",
                    "env:OPENAI_COMPATIBLE_TOKEN",
                ],
                env=self.env,
            )
            self.assertEqual(llm_result.exit_code, 0)

            agent_result = self.runner.invoke(
                app,
                [
                    "agent",
                    "register-profile",
                    "assistant",
                    "Assistant",
                    "local-chat",
                    "--system-prompt",
                    "Be helpful.",
                ],
                env=self.env,
            )
            self.assertEqual(agent_result.exit_code, 0)

            intake_result = self.runner.invoke(
                app,
                [
                    "orchestration",
                    "intake",
                    "assistant",
                    "local-chat",
                    "hello",
                    "--run-id",
                    "run-cli-process",
                    "--channel",
                    "webchat",
                    "--enqueue",
                ],
                env=self.env,
            )
            self.assertEqual(intake_result.exit_code, 0)

            process_result = self.runner.invoke(
                app,
                ["orchestration-worker", "process-next", "--worker-id", "worker-1"],
                env=self.env,
            )

            self.assertEqual(process_result.exit_code, 0)
            payload = json.loads(process_result.stdout)
            self.assertEqual(payload["id"], "run-cli-process")
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["stage"], "completed")
            self.assertEqual(payload["current_step"], 1)
            self.assertEqual(payload["result_payload"]["output_text"], "hello from sample llm")
            self.assertEqual(payload["result_payload"]["llm_id"], "local-chat")
        finally:
            if previous_token is None:
                os.environ.pop("OPENAI_COMPATIBLE_TOKEN", None)
            else:
                os.environ["OPENAI_COMPATIBLE_TOKEN"] = previous_token
            server.close()

    def test_orchestration_worker_run_processes_queued_runs_until_limit(self) -> None:
        server = SampleLlmApiServer()
        previous_token = os.environ.get("OPENAI_COMPATIBLE_TOKEN")
        os.environ["OPENAI_COMPATIBLE_TOKEN"] = "sample-compat-token"
        server.start()

        try:
            llm_result = self.runner.invoke(
                app,
                [
                    "llm",
                    "register-profile",
                    "local-chat",
                    "openai_compatible",
                    "openai_chat_compatible",
                    "llama3.2",
                    "--base-url",
                    f"{server.base_url}/v1",
                    "--credential-binding",
                    "env:OPENAI_COMPATIBLE_TOKEN",
                ],
                env=self.env,
            )
            self.assertEqual(llm_result.exit_code, 0)

            agent_result = self.runner.invoke(
                app,
                [
                    "agent",
                    "register-profile",
                    "assistant",
                    "Assistant",
                    "local-chat",
                    "--system-prompt",
                    "Be helpful.",
                ],
                env=self.env,
            )
            self.assertEqual(agent_result.exit_code, 0)

            intake_result = self.runner.invoke(
                app,
                [
                    "orchestration",
                    "intake",
                    "assistant",
                    "local-chat",
                    "hello",
                    "--run-id",
                    "run-cli-loop",
                    "--channel",
                    "webchat",
                    "--enqueue",
                ],
                env=self.env,
            )
            self.assertEqual(intake_result.exit_code, 0)

            run_result = self.runner.invoke(
                app,
                [
                    "orchestration-worker",
                    "run",
                    "--worker-id",
                    "worker-loop-1",
                    "--max-runs",
                    "1",
                    "--poll-interval-seconds",
                    "0.05",
                ],
                env=self.env,
            )
            self.assertEqual(run_result.exit_code, 0)

            get_result = self.runner.invoke(
                app,
                ["orchestration", "get", "run-cli-loop"],
                env=self.env,
            )
            self.assertEqual(get_result.exit_code, 0)
            payload = json.loads(get_result.stdout)
            self.assertEqual(payload["status"], "completed")
            self.assertEqual(payload["result_payload"]["output_text"], "hello from sample llm")
        finally:
            if previous_token is None:
                os.environ.pop("OPENAI_COMPATIBLE_TOKEN", None)
            else:
                os.environ["OPENAI_COMPATIBLE_TOKEN"] = previous_token
            server.close()

    def test_crxzipple_ask_completes_a_turn_in_one_command(self) -> None:
        server = SampleLlmApiServer()
        previous_token = os.environ.get("OPENAI_COMPATIBLE_TOKEN")
        os.environ["OPENAI_COMPATIBLE_TOKEN"] = "sample-compat-token"
        server.start()

        try:
            llm_result = self.runner.invoke(
                app,
                [
                    "llm",
                    "register-profile",
                    "local-chat",
                    "openai_compatible",
                    "openai_chat_compatible",
                    "llama3.2",
                    "--base-url",
                    f"{server.base_url}/v1",
                    "--credential-binding",
                    "env:OPENAI_COMPATIBLE_TOKEN",
                ],
                env=self.env,
            )
            self.assertEqual(llm_result.exit_code, 0)

            agent_result = self.runner.invoke(
                app,
                [
                    "agent",
                    "register-profile",
                    "crxzipple",
                    "crxzipple",
                    "local-chat",
                    "--system-prompt",
                    "Be helpful.",
                ],
                env=self.env,
            )
            self.assertEqual(agent_result.exit_code, 0)

            ask_result = self.runner.invoke(
                app,
                [
                    "ask",
                    "hello",
                    "--agent",
                    "crxzipple",
                ],
                env=self.env,
            )

            self.assertEqual(ask_result.exit_code, 0)
            self.assertEqual(ask_result.stdout.strip(), "hello from sample llm")
        finally:
            if previous_token is None:
                os.environ.pop("OPENAI_COMPATIBLE_TOKEN", None)
            else:
                os.environ["OPENAI_COMPATIBLE_TOKEN"] = previous_token
            server.close()

    def test_crxzipple_chat_completes_a_turn_and_exits(self) -> None:
        server = SampleLlmApiServer()
        previous_token = os.environ.get("OPENAI_COMPATIBLE_TOKEN")
        os.environ["OPENAI_COMPATIBLE_TOKEN"] = "sample-compat-token"
        server.start()

        try:
            llm_result = self.runner.invoke(
                app,
                [
                    "llm",
                    "register-profile",
                    "local-chat",
                    "openai_compatible",
                    "openai_chat_compatible",
                    "llama3.2",
                    "--base-url",
                    f"{server.base_url}/v1",
                    "--credential-binding",
                    "env:OPENAI_COMPATIBLE_TOKEN",
                ],
                env=self.env,
            )
            self.assertEqual(llm_result.exit_code, 0)

            agent_result = self.runner.invoke(
                app,
                [
                    "agent",
                    "register-profile",
                    "crxzipple",
                    "crxzipple",
                    "local-chat",
                    "--system-prompt",
                    "Be helpful.",
                ],
                env=self.env,
            )
            self.assertEqual(agent_result.exit_code, 0)

            chat_result = self.runner.invoke(
                app,
                [
                    "chat",
                    "--agent",
                    "crxzipple",
                ],
                env=self.env,
                input="hello\n/exit\n",
            )

            self.assertEqual(chat_result.exit_code, 0)
            self.assertIn("Chatting with crxzipple. Type /exit to quit.", chat_result.stdout)
            self.assertIn("hello from sample llm", chat_result.stdout)
        finally:
            if previous_token is None:
                os.environ.pop("OPENAI_COMPATIBLE_TOKEN", None)
            else:
                os.environ["OPENAI_COMPATIBLE_TOKEN"] = previous_token
            server.close()

    def test_auth_commands_list_policies_and_evaluate_requests(self) -> None:
        env = dict(self.env)
        env["APP_AUTHORIZATION_ENABLED"] = "true"
        env["APP_AUTHORIZATION_POLICY_PATHS"] = str(
            Path(__file__).resolve().parents[2]
            / "config"
            / "authorization_policies"
            / "default.yaml"
        )

        policies_result = self.runner.invoke(app, ["auth", "policies"], env=env)
        self.assertEqual(policies_result.exit_code, 0)
        self.assertIn('"id": "allow_llm_invocation"', policies_result.stdout)

        check_result = self.runner.invoke(
            app,
            [
                "auth",
                "check",
                "llm.invoke",
                "llm_profile",
                "--resource-id",
                "writer",
                "--context",
                '{"interface":"cli"}',
            ],
            env=env,
        )
        self.assertEqual(check_result.exit_code, 0)
        self.assertIn('"allowed": true', check_result.stdout)

    def test_tool_run_is_denied_by_cli_guard_when_abac_blocks_it(self) -> None:
        env = dict(self.env)
        env["APP_AUTHORIZATION_ENABLED"] = "true"
        env["APP_AUTHORIZATION_POLICY_PATHS"] = str(
            Path(__file__).resolve().parents[2]
            / "config"
            / "authorization_policies"
            / "default.yaml"
        )

        register_result = self.runner.invoke(
            app,
            [
                "tool",
                "register",
                "dangerous_write",
                "Dangerous Write",
                "Mutates external systems",
                "--mutates-state",
            ],
            env=env,
        )
        self.assertEqual(register_result.exit_code, 0)

        run_result = self.runner.invoke(
            app,
            [
                "tool",
                "run",
                "dangerous_write",
                "--input",
                "{}",
            ],
            env=env,
        )
        self.assertEqual(run_result.exit_code, 1)

    def test_cli_schema_error_detector_matches_missing_table_messages(self) -> None:
        self.assertTrue(_is_missing_database_schema_error(RuntimeError("no such table: tools")))
        self.assertTrue(
            _is_missing_database_schema_error(
                RuntimeError('relation "tools" does not exist'),
            ),
        )
        self.assertFalse(
            _is_missing_database_schema_error(RuntimeError("database is locked")),
        )

    def test_tool_register_command_returns_payload(self) -> None:
        result = self.runner.invoke(
            app,
            [
                "tool",
                "register",
                "search",
                "Search",
                "Query external knowledge",
            ],
            env=self.env,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn('"id": "search"', result.stdout)
        self.assertIn('"name": "Search"', result.stdout)

        list_result = self.runner.invoke(app, ["tool", "list"], env=self.env)

        self.assertEqual(list_result.exit_code, 0)
        self.assertIn('"id": "search"', list_result.stdout)

    def test_llm_register_profile_and_list_commands_return_v2_payload(self) -> None:
        result = self.runner.invoke(
            app,
            [
                "llm",
                "register-profile",
                "writer",
                "openai",
                "openai_responses",
                "gpt-5",
                "--model-family",
                "reasoning",
                "--capability",
                "tool_calling",
                "--temperature",
                "0.2",
                "--max-output-tokens",
                "512",
                "--credential-binding",
                "env:OPENAI_API_KEY",
            ],
            env=self.env,
        )

        self.assertEqual(result.exit_code, 0)
        self.assertIn('"id": "writer"', result.stdout)
        self.assertIn('"api_family": "openai_responses"', result.stdout)
        self.assertIn('"model_family": "reasoning"', result.stdout)

        list_result = self.runner.invoke(app, ["llm", "list"], env=self.env)

        self.assertEqual(list_result.exit_code, 0)
        self.assertIn('"id": "writer"', list_result.stdout)
        self.assertIn('"credential_binding": "env:OPENAI_API_KEY"', list_result.stdout)

    def test_llm_invoke_command_uses_openai_compatible_adapter(self) -> None:
        server = SampleLlmApiServer()
        previous_token = os.environ.get("OPENAI_COMPATIBLE_TOKEN")
        os.environ["OPENAI_COMPATIBLE_TOKEN"] = "sample-compat-token"
        server.start()
        try:
            register_result = self.runner.invoke(
                app,
                [
                    "llm",
                    "register-profile",
                    "local-chat",
                    "openai_compatible",
                    "openai_chat_compatible",
                    "llama3.2",
                    "--base-url",
                    f"{server.base_url}/v1",
                    "--credential-binding",
                    "env:OPENAI_COMPATIBLE_TOKEN",
                ],
                env=self.env,
            )

            self.assertEqual(register_result.exit_code, 0)

            invoke_result = self.runner.invoke(
                app,
                [
                    "llm",
                    "invoke",
                    "local-chat",
                    "--messages",
                    '[{"role":"user","content":"hello"}]',
                    "--tool-schemas",
                    '[{"name":"search_docs","description":"Search docs","input_schema":{"type":"object","properties":{"query":{"type":"string"}}}}]',
                ],
                env=self.env,
            )

            self.assertEqual(invoke_result.exit_code, 0)
            self.assertIn('"status": "succeeded"', invoke_result.stdout)
            self.assertIn('"provider_request_id": "chatcmpl_sample_1"', invoke_result.stdout)
            self.assertIn('"text": "hello from sample llm"', invoke_result.stdout)
            self.assertIn('"name": "search_docs"', invoke_result.stdout)
        finally:
            if previous_token is None:
                os.environ.pop("OPENAI_COMPATIBLE_TOKEN", None)
            else:
                os.environ["OPENAI_COMPATIBLE_TOKEN"] = previous_token
            server.close()

    def test_llm_sync_profiles_loads_yaml_configs(self) -> None:
        env = dict(self.env)

        with tempfile.TemporaryDirectory() as tempdir:
            profiles_dir = Path(tempdir) / "llm_profiles"
            profiles_dir.mkdir()
            (profiles_dir / "openai_gpt_5_4.yaml").write_text(
                "\n".join(
                    [
                        "id: openai.gpt-5.4",
                        "provider: openai",
                        "api_family: openai_responses",
                        "model_name: gpt-5.4",
                        "model_family: reasoning",
                        "capabilities:",
                        "  - tool_calling",
                        "  - structured_output",
                        "default_params:",
                        "  reasoning_effort: medium",
                        "credential_binding: env:OPENAI_API_KEY",
                        "timeout_seconds: 120",
                        "",
                    ],
                ),
                encoding="utf-8",
            )
            env["APP_LLM_PROFILE_PATHS"] = str(profiles_dir)

            sync_result = self.runner.invoke(
                app,
                ["llm", "sync-profiles"],
                env=env,
            )

            self.assertEqual(sync_result.exit_code, 0)
            sync_payload = json.loads(sync_result.stdout)
            self.assertEqual([item["id"] for item in sync_payload], ["openai.gpt-5.4"])
            self.assertEqual(sync_payload[0]["api_family"], "openai_responses")
            self.assertEqual(
                sync_payload[0]["default_params"]["reasoning_effort"],
                "medium",
            )

            list_result = self.runner.invoke(app, ["llm", "list"], env=env)
            self.assertEqual(list_result.exit_code, 0)
            list_payload = json.loads(list_result.stdout)
            self.assertEqual([item["id"] for item in list_payload], ["openai.gpt-5.4"])

    def test_db_commands_apply_and_report_revisions(self) -> None:
        harness = SqliteTestHarness()
        env = {"APP_DATABASE_URL": harness.database_url}
        database_path = harness.database_url.removeprefix("sqlite:///")

        try:
            upgrade_result = self.runner.invoke(app, ["db", "upgrade"], env=env)

            self.assertEqual(upgrade_result.exit_code, 0)

            with sqlite3.connect(database_path) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'",
                    )
                }
                message_columns = {
                    row[1]
                    for row in connection.execute("PRAGMA table_info(session_messages)")
                }
                revision = connection.execute(
                    "SELECT version_num FROM alembic_version",
                ).fetchone()

            self.assertIn("tools", tables)
            self.assertIn("tool_runs", tables)
            self.assertIn("sessions", tables)
            self.assertIn("session_messages", tables)
            self.assertIn("session_instances", tables)
            self.assertIn("orchestration_runs", tables)
            self.assertTrue(
                {
                    "sequence_no",
                    "kind",
                    "content_payload",
                    "source_kind",
                    "source_id",
                    "visibility",
                }.issubset(message_columns),
            )
            self.assertEqual(revision[0], HEAD_REVISION)

            current_result = self.runner.invoke(app, ["db", "current"], env=env)
            history_result = self.runner.invoke(app, ["db", "history"], env=env)

            self.assertEqual(current_result.exit_code, 0)
            self.assertEqual(history_result.exit_code, 0)
            self.assertIn(HEAD_REVISION, current_result.output)
            self.assertIn(HEAD_REVISION, history_result.output)
        finally:
            harness.close()

    def test_db_downgrade_returns_schema_to_base(self) -> None:
        harness = SqliteTestHarness()
        env = {"APP_DATABASE_URL": harness.database_url}
        database_path = harness.database_url.removeprefix("sqlite:///")

        try:
            upgrade_result = self.runner.invoke(app, ["db", "upgrade"], env=env)
            self.assertEqual(upgrade_result.exit_code, 0)

            downgrade_result = self.runner.invoke(
                app,
                ["db", "downgrade", "base"],
                env=env,
            )
            self.assertEqual(downgrade_result.exit_code, 0)

            with sqlite3.connect(database_path) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'",
                    )
                }
                revision = connection.execute(
                    "SELECT version_num FROM alembic_version",
                ).fetchone()

            self.assertNotIn("tools", tables)
            self.assertNotIn("tool_runs", tables)
            self.assertNotIn("sessions", tables)
            self.assertNotIn("session_messages", tables)
            self.assertNotIn("session_instances", tables)
            self.assertNotIn("orchestration_runs", tables)
            self.assertIn("alembic_version", tables)
            self.assertIsNone(revision)
        finally:
            harness.close()

    def test_db_revision_autogenerate_creates_file_in_custom_script_location(self) -> None:
        harness = SqliteTestHarness()
        env = {"APP_DATABASE_URL": harness.database_url}

        with tempfile.TemporaryDirectory() as tempdir:
            temp_alembic_dir = Path(tempdir) / "alembic"
            shutil.copytree(db_cli.ALEMBIC_SCRIPT_PATH, temp_alembic_dir)
            env["APP_ALEMBIC_SCRIPT_LOCATION"] = str(temp_alembic_dir)

            versions_dir = temp_alembic_dir / "versions"
            before = {path.name for path in versions_dir.glob("*.py")}

            try:
                upgrade_result = self.runner.invoke(app, ["db", "upgrade"], env=env)
                self.assertEqual(upgrade_result.exit_code, 0)

                revision_result = self.runner.invoke(
                    app,
                    ["db", "revision", "noop drift check", "--autogenerate"],
                    env=env,
                )

                self.assertEqual(revision_result.exit_code, 0)

                after = {path.name for path in versions_dir.glob("*.py")}
                created = after - before

                self.assertEqual(len(created), 1)
                created_path = versions_dir / created.pop()
                self.assertIn("noop_drift_check", created_path.name)
                self.assertIn(str(created_path), revision_result.output)
            finally:
                harness.close()

    def test_db_stamp_marks_revision_without_running_migration(self) -> None:
        harness = SqliteTestHarness()
        env = {"APP_DATABASE_URL": harness.database_url}
        database_path = harness.database_url.removeprefix("sqlite:///")

        try:
            stamp_result = self.runner.invoke(app, ["db", "stamp", "head"], env=env)

            self.assertEqual(stamp_result.exit_code, 0)

            with sqlite3.connect(database_path) as connection:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type = 'table'",
                    )
                }
                revision = connection.execute(
                    "SELECT version_num FROM alembic_version",
                ).fetchone()

            self.assertNotIn("tools", tables)
            self.assertNotIn("sessions", tables)
            self.assertNotIn("orchestration_runs", tables)
            self.assertEqual(revision[0], HEAD_REVISION)
            self.assertEqual(tables, {"alembic_version"})
        finally:
            harness.close()

    def test_db_revision_empty_creates_file_in_custom_script_location(self) -> None:
        harness = SqliteTestHarness()
        env = {"APP_DATABASE_URL": harness.database_url}

        with tempfile.TemporaryDirectory() as tempdir:
            temp_alembic_dir = Path(tempdir) / "alembic"
            shutil.copytree(db_cli.ALEMBIC_SCRIPT_PATH, temp_alembic_dir)
            env["APP_ALEMBIC_SCRIPT_LOCATION"] = str(temp_alembic_dir)

            versions_dir = temp_alembic_dir / "versions"
            before = {path.name for path in versions_dir.glob("*.py")}

            try:
                upgrade_result = self.runner.invoke(app, ["db", "upgrade"], env=env)
                self.assertEqual(upgrade_result.exit_code, 0)

                revision_result = self.runner.invoke(
                    app,
                    ["db", "revision-empty", "manual checkpoint"],
                    env=env,
                )

                self.assertEqual(revision_result.exit_code, 0)

                after = {path.name for path in versions_dir.glob("*.py")}
                created = after - before

                self.assertEqual(len(created), 1)
                created_path = versions_dir / created.pop()
                self.assertIn("manual_checkpoint", created_path.name)
                self.assertIn(str(created_path), revision_result.output)
            finally:
                harness.close()

    def test_tool_discover_local_and_run_commands_return_runtime_payload(self) -> None:
        discover_result = self.runner.invoke(
            app,
            ["tool", "discover-local"],
            env=self.env,
        )

        self.assertEqual(discover_result.exit_code, 0)
        self.assertIn('"id": "echo"', discover_result.stdout)

        run_result = self.runner.invoke(
            app,
            [
                "tool",
                "run",
                "echo",
                "--input",
                '{"message": "hello"}',
            ],
            env=self.env,
        )

        self.assertEqual(run_result.exit_code, 0)
        run_payload = json.loads(run_result.stdout)
        self.assertEqual(run_payload["tool_id"], "echo")
        self.assertEqual(run_payload["status"], "succeeded")
        self.assertEqual(run_payload["output_payload"]["message"], "hello")

        runs_result = self.runner.invoke(
            app,
            ["tool", "runs", "--tool-id", "echo"],
            env=self.env,
        )

        self.assertEqual(runs_result.exit_code, 0)
        runs_payload = json.loads(runs_result.stdout)
        self.assertEqual(len(runs_payload), 1)
        self.assertEqual(runs_payload[0]["id"], run_payload["id"])

        get_run_result = self.runner.invoke(
            app,
            ["tool", "get-run", run_payload["id"]],
            env=self.env,
        )

        self.assertEqual(get_run_result.exit_code, 0)
        fetched_run_payload = json.loads(get_run_result.stdout)
        self.assertEqual(fetched_run_payload["id"], run_payload["id"])

    def test_tool_providers_and_generic_discover_commands_return_provider_payload(self) -> None:
        providers_result = self.runner.invoke(
            app,
            ["tool", "providers"],
            env=self.env,
        )

        self.assertEqual(providers_result.exit_code, 0)
        providers_payload = json.loads(providers_result.stdout)
        self.assertEqual(len(providers_payload), 1)
        self.assertEqual(providers_payload[0]["name"], "local_builtin")

        discover_result = self.runner.invoke(
            app,
            ["tool", "discover", "--provider", "local_builtin"],
            env=self.env,
        )

        self.assertEqual(discover_result.exit_code, 0)
        discover_payload = json.loads(discover_result.stdout)
        self.assertEqual([item["id"] for item in discover_payload], ["echo"])

    def test_tool_openapi_provider_commands_discover_and_execute_remote_tools(self) -> None:
        server = SampleApiServer()
        server.start()
        env = dict(self.env)
        env["SAMPLE_API_KEY"] = "sample-api-key"
        env["SAMPLE_BEARER_TOKEN"] = "sample-bearer-token"
        env["APP_TOOL_OPENAPI_PROVIDERS"] = json.dumps(
            [
                {
                    "name": "sample_api",
                    "spec_location": openapi_fixture_path("sample_openapi.json"),
                    "base_url": server.base_url,
                    "description": "Sample OpenAPI provider",
                    "timeout_seconds": 5,
                    "credentials": {
                        "ApiKeyQuery": "env:SAMPLE_API_KEY",
                        "BearerAuth": "env:SAMPLE_BEARER_TOKEN"
                    },
                },
            ],
        )

        try:
            providers_result = self.runner.invoke(
                app,
                ["tool", "providers"],
                env=env,
            )
            self.assertEqual(providers_result.exit_code, 0)
            providers_payload = json.loads(providers_result.stdout)
            self.assertEqual(
                [item["name"] for item in providers_payload],
                ["local_builtin", "sample_api"],
            )

            discover_result = self.runner.invoke(
                app,
                ["tool", "discover", "--provider", "sample_api"],
                env=env,
            )
            self.assertEqual(discover_result.exit_code, 0)
            discover_payload = json.loads(discover_result.stdout)
            self.assertEqual(
                [item["id"] for item in discover_payload],
                ["sample_api.echo_message", "sample_api.search_docs"],
            )

            run_result = self.runner.invoke(
                app,
                [
                    "tool",
                    "run",
                    "sample_api.echo_message",
                    "--input",
                    '{"message":"cli","uppercase":true}',
                    "--environment",
                    "remote",
                ],
                env=env,
            )
            self.assertEqual(run_result.exit_code, 0)
            run_payload = json.loads(run_result.stdout)
            self.assertEqual(run_payload["status"], "succeeded")
            self.assertEqual(run_payload["output_payload"]["message"], "CLI")
            self.assertIn(
                "api_key=sample-api-key",
                run_payload["result"]["metadata"]["request"]["url"],
            )

            search_result = self.runner.invoke(
                app,
                [
                    "tool",
                    "run",
                    "sample_api.search_docs",
                    "--environment",
                    "remote",
                    "--input",
                    '{"body":{"query":"cli auth","limit":2}}',
                ],
                env=env,
            )
            self.assertEqual(search_result.exit_code, 0)
            search_payload = json.loads(search_result.stdout)
            self.assertEqual(search_payload["status"], "succeeded")
            self.assertEqual(
                search_payload["output_payload"]["query"],
                "cli auth",
            )
        finally:
            server.close()

    def test_tool_openapi_provider_commands_load_yaml_provider_configs(self) -> None:
        server = SampleApiServer()
        server.start()
        env = dict(self.env)
        env["SAMPLE_API_KEY"] = "sample-api-key"
        env["SAMPLE_BEARER_TOKEN"] = "sample-bearer-token"

        with tempfile.TemporaryDirectory() as tempdir:
            temp_root = Path(tempdir)
            providers_dir = temp_root / "tool_providers"
            specs_dir = temp_root / "specs"
            providers_dir.mkdir()
            specs_dir.mkdir()
            shutil.copy(
                openapi_fixture_path("sample_openapi.json"),
                specs_dir / "sample_openapi.json",
            )
            (providers_dir / "sample_api.yaml").write_text(
                "\n".join(
                    [
                        "name: sample_api",
                        "spec_location: ../specs/sample_openapi.json",
                        f"base_url: {server.base_url}",
                        "description: Sample OpenAPI provider loaded from YAML",
                        "timeout_seconds: 5",
                        "credentials:",
                        "  ApiKeyQuery: env:SAMPLE_API_KEY",
                        "  BearerAuth: env:SAMPLE_BEARER_TOKEN",
                        "",
                    ],
                ),
                encoding="utf-8",
            )
            env["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = str(providers_dir)

            try:
                providers_result = self.runner.invoke(
                    app,
                    ["tool", "providers"],
                    env=env,
                )
                self.assertEqual(providers_result.exit_code, 0)
                providers_payload = json.loads(providers_result.stdout)
                self.assertEqual(
                    [item["name"] for item in providers_payload],
                    ["local_builtin", "sample_api"],
                )

                discover_result = self.runner.invoke(
                    app,
                    ["tool", "discover", "--provider", "sample_api"],
                    env=env,
                )
                self.assertEqual(discover_result.exit_code, 0)
                discover_payload = json.loads(discover_result.stdout)
                self.assertEqual(
                    [item["id"] for item in discover_payload],
                    ["sample_api.echo_message", "sample_api.search_docs"],
                )

                run_result = self.runner.invoke(
                    app,
                    [
                        "tool",
                        "run",
                        "sample_api.search_docs",
                        "--environment",
                        "remote",
                        "--input",
                        '{"body":{"query":"yaml config","limit":2}}',
                    ],
                    env=env,
                )
                self.assertEqual(run_result.exit_code, 0)
                run_payload = json.loads(run_result.stdout)
                self.assertEqual(run_payload["status"], "succeeded")
                self.assertEqual(
                    run_payload["output_payload"]["query"],
                    "yaml config",
                )
                self.assertTrue(
                    run_payload["result"]["metadata"]["tool"].endswith(
                        "sample_api.search_docs",
                    ),
                )
            finally:
                server.close()

    def test_tool_mcp_provider_commands_discover_and_execute_remote_tools(self) -> None:
        env = dict(self.env)
        env["APP_TOOL_MCP_PROVIDERS"] = json.dumps(
            [
                {
                    "name": "sample_mcp",
                    "command": [sys.executable, fixture_path("mcp_sample_server.py")],
                    "description": "Sample MCP provider",
                    "timeout_seconds": 5,
                },
            ],
        )

        providers_result = self.runner.invoke(
            app,
            ["tool", "providers"],
            env=env,
        )
        self.assertEqual(providers_result.exit_code, 0)
        providers_payload = json.loads(providers_result.stdout)
        self.assertEqual(
            [item["name"] for item in providers_payload],
            ["local_builtin", "sample_mcp"],
        )

        discover_result = self.runner.invoke(
            app,
            ["tool", "discover", "--provider", "sample_mcp"],
            env=env,
        )
        self.assertEqual(discover_result.exit_code, 0)
        discover_payload = json.loads(discover_result.stdout)
        self.assertEqual(
            [item["id"] for item in discover_payload],
            ["sample_mcp.echo", "sample_mcp.sum"],
        )

        run_result = self.runner.invoke(
            app,
            [
                "tool",
                "run",
                "sample_mcp.echo",
                "--input",
                '{"message":"mcp cli","uppercase":true}',
                "--environment",
                "remote",
            ],
            env=env,
        )
        self.assertEqual(run_result.exit_code, 0)
        run_payload = json.loads(run_result.stdout)
        self.assertEqual(run_payload["status"], "succeeded")
        self.assertEqual(
            run_payload["output_payload"]["content"]["message"],
            "MCP CLI",
        )

    def test_tool_filesystem_provider_commands_discover_and_execute_local_tools(self) -> None:
        env = dict(self.env)
        env["APP_TOOL_LOCAL_PATHS"] = fixture_path("local_tools")

        providers_result = self.runner.invoke(
            app,
            ["tool", "providers"],
            env=env,
        )
        self.assertEqual(providers_result.exit_code, 0)
        providers_payload = json.loads(providers_result.stdout)
        self.assertEqual(
            [item["name"] for item in providers_payload],
            ["local_builtin", "local_filesystem"],
        )

        discover_result = self.runner.invoke(
            app,
            ["tool", "discover", "--provider", "local_filesystem"],
            env=env,
        )
        self.assertEqual(discover_result.exit_code, 0)
        discover_payload = json.loads(discover_result.stdout)
        self.assertEqual([item["id"] for item in discover_payload], ["greeter"])

        run_result = self.runner.invoke(
            app,
            [
                "tool",
                "run",
                "greeter",
                "--input",
                '{"name":"cli"}',
                "--strategy",
                "process",
            ],
            env=env,
        )
        self.assertEqual(run_result.exit_code, 0)
        run_payload = json.loads(run_result.stdout)
        self.assertEqual(run_payload["status"], "succeeded")
        self.assertEqual(run_payload["output_payload"]["message"], "hello cli")
        self.assertEqual(run_payload["result"]["metadata"]["environment"], "local")

    def test_tool_inline_process_run_returns_process_context(self) -> None:
        discover_result = self.runner.invoke(
            app,
            ["tool", "discover-local"],
            env=self.env,
        )
        self.assertEqual(discover_result.exit_code, 0)

        run_result = self.runner.invoke(
            app,
            [
                "tool",
                "run",
                "echo",
                "--strategy",
                "process",
                "--input",
                '{"message": "process cli"}',
            ],
            env=self.env,
        )

        self.assertEqual(run_result.exit_code, 0)
        run_payload = json.loads(run_result.stdout)
        self.assertEqual(run_payload["status"], "succeeded")
        self.assertEqual(run_payload["output_payload"]["message"], "process cli")
        self.assertNotEqual(run_payload["result"]["metadata"]["process_id"], os.getpid())

    def test_tool_background_run_eventually_succeeds(self) -> None:
        discover_result = self.runner.invoke(
            app,
            ["tool", "discover-local"],
            env=self.env,
        )
        self.assertEqual(discover_result.exit_code, 0)

        run_result = self.runner.invoke(
            app,
            [
                "tool",
                "run",
                "echo",
                "--mode",
                "background",
                "--input",
                '{"message": "queued hello"}',
            ],
            env=self.env,
        )

        self.assertEqual(run_result.exit_code, 0)
        run_payload = json.loads(run_result.stdout)
        self.assertEqual(run_payload["status"], "queued")

        deadline = time.monotonic() + 5
        fetched_run_payload = None
        while time.monotonic() < deadline:
            worker_result = self.runner.invoke(
                app,
                ["tool-worker", "once"],
                env=self.env,
            )
            self.assertEqual(worker_result.exit_code, 0)
            get_run_result = self.runner.invoke(
                app,
                ["tool", "get-run", run_payload["id"]],
                env=self.env,
            )
            self.assertEqual(get_run_result.exit_code, 0)
            fetched_run_payload = json.loads(get_run_result.stdout)
            if fetched_run_payload["status"] == "succeeded":
                break
            time.sleep(0.05)

        self.assertIsNotNone(fetched_run_payload)
        self.assertEqual(fetched_run_payload["status"], "succeeded")
        self.assertEqual(
            fetched_run_payload["output_payload"]["message"],
            "queued hello",
        )
        self.assertEqual(fetched_run_payload["result"]["metadata"]["environment"], "local")
        self.assertEqual(fetched_run_payload["attempt_count"], 1)
        self.assertIsNotNone(fetched_run_payload["worker_id"])

    def test_tool_background_process_run_eventually_succeeds(self) -> None:
        discover_result = self.runner.invoke(
            app,
            ["tool", "discover-local"],
            env=self.env,
        )
        self.assertEqual(discover_result.exit_code, 0)

        run_result = self.runner.invoke(
            app,
            [
                "tool",
                "run",
                "echo",
                "--mode",
                "background",
                "--strategy",
                "process",
                "--input",
                '{"message": "queued process hello"}',
            ],
            env=self.env,
        )

        self.assertEqual(run_result.exit_code, 0)
        run_payload = json.loads(run_result.stdout)
        self.assertEqual(run_payload["status"], "queued")
        self.assertEqual(run_payload["target"]["strategy"], "process")

        deadline = time.monotonic() + 5
        fetched_run_payload = None
        while time.monotonic() < deadline:
            worker_result = self.runner.invoke(
                app,
                ["tool-worker", "once", "--worker-id", "cli-process-worker"],
                env=self.env,
            )
            self.assertEqual(worker_result.exit_code, 0)
            get_run_result = self.runner.invoke(
                app,
                ["tool", "get-run", run_payload["id"]],
                env=self.env,
            )
            self.assertEqual(get_run_result.exit_code, 0)
            fetched_run_payload = json.loads(get_run_result.stdout)
            if fetched_run_payload["status"] == "succeeded":
                break
            time.sleep(0.05)

        self.assertIsNotNone(fetched_run_payload)
        self.assertEqual(fetched_run_payload["status"], "succeeded")
        self.assertEqual(
            fetched_run_payload["output_payload"]["message"],
            "queued process hello",
        )
        self.assertEqual(fetched_run_payload["target"]["strategy"], "process")
        self.assertEqual(fetched_run_payload["worker_id"], "cli-process-worker")
        self.assertNotEqual(
            fetched_run_payload["result"]["metadata"]["process_id"],
            os.getpid(),
        )

    def test_tool_cancel_run_command_returns_cancelled_payload(self) -> None:
        discover_result = self.runner.invoke(
            app,
            ["tool", "discover-local"],
            env=self.env,
        )
        self.assertEqual(discover_result.exit_code, 0)

        run_result = self.runner.invoke(
            app,
            [
                "tool",
                "run",
                "echo",
                "--mode",
                "background",
                "--input",
                '{"message": "cancel via cli"}',
            ],
            env=self.env,
        )
        self.assertEqual(run_result.exit_code, 0)
        run_payload = json.loads(run_result.stdout)

        cancel_result = self.runner.invoke(
            app,
            ["tool", "cancel-run", run_payload["id"]],
            env=self.env,
        )
        self.assertEqual(cancel_result.exit_code, 0)
        cancel_payload = json.loads(cancel_result.stdout)
        self.assertEqual(cancel_payload["status"], "cancelled")
        self.assertIsNotNone(cancel_payload["cancel_requested_at"])

    def test_tool_register_and_run_remote_runtime(self) -> None:
        register_result = self.runner.invoke(
            app,
            [
                "tool",
                "register",
                "remote_echo",
                "Remote Echo",
                "Executes through the remote adapter",
                "--environment",
                "remote",
                "--runtime-key",
                "remote.echo",
                "--source-kind",
                "remote_registry",
            ],
            env=self.env,
        )

        self.assertEqual(register_result.exit_code, 0)

        run_result = self.runner.invoke(
            app,
            [
                "tool",
                "run",
                "remote_echo",
                "--environment",
                "remote",
                "--input",
                '{"message": "remote cli"}',
            ],
            env=self.env,
        )

        self.assertEqual(run_result.exit_code, 0)
        run_payload = json.loads(run_result.stdout)
        self.assertEqual(run_payload["status"], "succeeded")
        self.assertEqual(run_payload["output_payload"]["message"], "remote cli")
        self.assertEqual(run_payload["result"]["metadata"]["environment"], "remote")


if __name__ == "__main__":
    unittest.main()
