from __future__ import annotations

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from crxzipple.interfaces.runtime_container import AppKey
from crxzipple.modules.orchestration.domain import (
    OrchestrationExecutorLease,
)
from tests.unit.cli_test_support import *


class _RuntimeCliFakeContainer:
    def __init__(self, values: dict[AppKey, object]) -> None:
        self._values = values

    def require(self, key: AppKey) -> object:
        return self._values[key]


class OrchestrationCliTestCase(CliModuleTestCase):
    def setUp(self) -> None:
            super().setUp()
            self.env["APP_LLM_PROFILE_PATHS"] = os.pathsep

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
                    "--credential-binding-id",
                    "openai-api-key",
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
            self.assertEqual(intake_payload["session_key"], "agent:assistant:main")
            self.assertEqual(
                intake_payload["lane_key"],
                "session:agent:assistant:main",
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

    def test_orchestration_executor_and_scheduler_commands_drive_run_lifecycle(self) -> None:
            llm_result = self.runner.invoke(
                app,
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

            heartbeat_executor_result = self.runner.invoke(
                app,
                [
                    "orchestration-executor",
                    "heartbeat-executor",
                    "--worker-id",
                    "worker-1",
                ],
                env=self.env,
            )
            self.assertEqual(heartbeat_executor_result.exit_code, 0)

            assign_result = self.runner.invoke(
                app,
                [
                    "orchestration-scheduler",
                    "assign-next-assignment",
                    "--worker-id",
                    "scheduler-1",
                ],
                env=self.env,
            )
            self.assertEqual(assign_result.exit_code, 0)
            self.assertEqual(json.loads(assign_result.stdout)["status"], "running")

            heartbeat_result = self.runner.invoke(
                app,
                [
                    "orchestration-executor",
                    "heartbeat-assignment",
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
                    "orchestration-executor",
                    "advance-assignment",
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
                    "orchestration-executor",
                    "wait-assignment-on-tool",
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
                ["orchestration-scheduler", "resume", "run-cli-worker"],
                env=self.env,
            )
            self.assertEqual(resume_result.exit_code, 0)
            self.assertEqual(json.loads(resume_result.stdout)["status"], "queued")

            reassign_result = self.runner.invoke(
                app,
                [
                    "orchestration-scheduler",
                    "assign-next-assignment",
                    "--worker-id",
                    "scheduler-1",
                ],
                env=self.env,
            )
            self.assertEqual(reassign_result.exit_code, 0)
            self.assertEqual(json.loads(reassign_result.stdout)["id"], "run-cli-worker")

            complete_result = self.runner.invoke(
                app,
                [
                    "orchestration-executor",
                    "complete-assignment",
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

    def test_orchestration_scheduler_process_next_request_reports_idle(self) -> None:
            result = self.runner.invoke(
                app,
                [
                    "orchestration-scheduler",
                    "process-next-request",
                    "--worker-id",
                    "scheduler-1",
                ],
                env=self.env,
            )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(
                json.loads(result.stdout),
                {"status": "idle", "worker_id": "scheduler-1"},
            )

    def test_orchestration_executor_process_next_completes_minimal_llm_run(self) -> None:
            server = SampleLlmApiServer()
            previous_token = os.environ.get("OPENAI_API_KEY")
            os.environ["OPENAI_API_KEY"] = "sample-compat-token"
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
                        "--credential-binding-id",
                        "openai-api-key",
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

                heartbeat_executor_result = self.runner.invoke(
                    app,
                    [
                        "orchestration-executor",
                        "heartbeat-executor",
                        "--worker-id",
                        "worker-1",
                    ],
                    env=self.env,
                )
                self.assertEqual(heartbeat_executor_result.exit_code, 0)

                assign_result = self.runner.invoke(
                    app,
                    [
                        "orchestration-scheduler",
                        "assign-next-assignment",
                        "--worker-id",
                        "scheduler-1",
                    ],
                    env=self.env,
                )
                self.assertEqual(assign_result.exit_code, 0)

                process_result = self.runner.invoke(
                    app,
                    [
                        "orchestration-executor",
                        "process-next-assigned-assignment",
                        "--worker-id",
                        "worker-1",
                    ],
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

                preview_result = self.runner.invoke(
                    app,
                    ["orchestration", "prompt-preview", "run-cli-process"],
                    env=self.env,
                )
                self.assertEqual(preview_result.exit_code, 0)
                preview_payload = json.loads(preview_result.stdout)
                self.assertEqual(preview_payload["run_id"], "run-cli-process")
                self.assertEqual(preview_payload["llm_id"], "local-chat")
                self.assertEqual(preview_payload["mode"], "normal_turn")
                self.assertIsNotNone(preview_payload["prompt_report"])
                self.assertTrue(
                    any(
                        item["role"] == "user"
                        and item["content"] == [{"type": "text", "text": "hello"}]
                        for item in preview_payload["messages"]
                    ),
                )
            finally:
                if previous_token is None:
                    os.environ.pop("OPENAI_API_KEY", None)
                else:
                    os.environ["OPENAI_API_KEY"] = previous_token
                server.close()

    def test_orchestration_executor_heartbeat_command_records_executor_lease(self) -> None:
            heartbeat_result = self.runner.invoke(
                app,
                [
                    "orchestration-executor",
                    "heartbeat-executor",
                    "--worker-id",
                    "executor-cli-1",
                    "--max-inflight-assignments",
                    "4",
                    "--inflight-assignment-count",
                    "1",
                    "--metadata",
                    '{"pool":"io"}',
                ],
                env=self.env,
            )

            self.assertEqual(heartbeat_result.exit_code, 0)
            heartbeat_payload = json.loads(heartbeat_result.stdout)
            self.assertEqual(heartbeat_payload["worker_id"], "executor-cli-1")
            self.assertEqual(heartbeat_payload["status"], "online")
            self.assertEqual(heartbeat_payload["max_inflight_assignments"], 4)
            self.assertEqual(heartbeat_payload["inflight_assignment_count"], 1)
            self.assertEqual(heartbeat_payload["metadata"], {"pool": "io"})

            list_result = self.runner.invoke(
                app,
                [
                    "orchestration-executor",
                    "list-executor-leases",
                    "--status",
                    "online",
                ],
                env=self.env,
            )
            self.assertEqual(list_result.exit_code, 0)
            self.assertEqual(
                [item["worker_id"] for item in json.loads(list_result.stdout)],
                ["executor-cli-1"],
            )

    def test_orchestration_intake_command_accepts_reply_target_options(self) -> None:
            llm_result = self.runner.invoke(
                app,
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
                    "--reply-interface",
                    "webhook",
                    "--reply-address",
                    "https://example.test/reply",
                    "--reply-to",
                    "thread-1",
                    "--reply-metadata",
                    '{"reply_address":{"channel_type":"webhook"}}',
                ],
                env=self.env,
            )

            self.assertEqual(intake_result.exit_code, 0)
            intake_payload = json.loads(intake_result.stdout)
            self.assertEqual(intake_payload["reply_target"]["interface_name"], "webhook")
            self.assertEqual(
                intake_payload["reply_target"]["address"],
                "https://example.test/reply",
            )
            self.assertEqual(intake_payload["reply_target"]["reply_to"], "thread-1")
            self.assertEqual(
                intake_payload["reply_target"]["metadata"]["reply_address"]["channel_type"],
                "webhook",
            )
            self.assertNotIn("delivery_target", intake_payload)

    def test_orchestration_executor_run_processes_assignments_until_limit(self) -> None:
            server = SampleLlmApiServer()
            previous_token = os.environ.get("OPENAI_API_KEY")
            os.environ["OPENAI_API_KEY"] = "sample-compat-token"
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
                        "--credential-binding-id",
                        "openai-api-key",
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

                heartbeat_result = self.runner.invoke(
                    app,
                    [
                        "orchestration-executor",
                        "heartbeat-executor",
                        "--worker-id",
                        "worker-loop-1",
                    ],
                    env=self.env,
                )
                self.assertEqual(heartbeat_result.exit_code, 0)

                assign_result = self.runner.invoke(
                    app,
                    [
                        "orchestration-scheduler",
                        "assign-next-assignment",
                        "--worker-id",
                        "scheduler-loop-1",
                    ],
                    env=self.env,
                )
                self.assertEqual(assign_result.exit_code, 0)
                self.assertEqual(
                    json.loads(assign_result.stdout)["worker_id"],
                    "worker-loop-1",
                )

                run_result = self.runner.invoke(
                    app,
                    [
                        "orchestration-executor",
                        "run-executor",
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
                    os.environ.pop("OPENAI_API_KEY", None)
                else:
                    os.environ["OPENAI_API_KEY"] = previous_token
                server.close()

    def test_orchestration_scheduler_help_only_exposes_scheduler_commands(self) -> None:
            result = self.runner.invoke(
                app,
                ["orchestration-scheduler", "--help"],
                env=self.env,
            )

            self.assertEqual(result.exit_code, 0)
            self.assertIn("assign-next-assignment", result.stdout)
            self.assertIn("process-next-request", result.stdout)
            self.assertIn("process-next-signal", result.stdout)
            self.assertIn("run-scheduler", result.stdout)
            self.assertIn("resume", result.stdout)
            self.assertNotIn("claim-next", result.stdout)
            self.assertNotIn("wait-tool", result.stdout)
            self.assertNotIn("run-executor", result.stdout)

    def test_orchestration_executor_help_only_exposes_executor_commands(self) -> None:
            result = self.runner.invoke(
                app,
                ["orchestration-executor", "--help"],
                env=self.env,
            )

            self.assertEqual(result.exit_code, 0)
            self.assertIn("process-next-assigned-assignment", result.stdout)
            self.assertNotIn("claim-next", result.stdout)
            self.assertIn("admit-assignment", result.stdout)
            self.assertIn("heartbeat-executor", result.stdout)
            self.assertIn("list-executor-leases", result.stdout)
            self.assertIn("heartbeat-assignment", result.stdout)
            self.assertIn("advance-assignment", result.stdout)
            self.assertIn("wait-assignment-on-tool", result.stdout)
            self.assertIn("complete-assignment", result.stdout)
            self.assertIn("fail-assignment", result.stdout)
            self.assertIn("process-assignment-inline", result.stdout)
            self.assertIn("run-executor", result.stdout)
            self.assertNotIn("claim-next-" "assignment", result.stdout)
            self.assertNotIn("process-next-" "assignment", result.stdout)
            self.assertNotIn("claim-next\n", result.stdout)
            self.assertNotIn("process-next\n", result.stdout)
            self.assertNotIn("heartbeat\n", result.stdout)
            self.assertNotIn("advance\n", result.stdout)
            self.assertNotIn("complete\n", result.stdout)
            self.assertNotIn("fail\n", result.stdout)
            self.assertNotIn("wait-tool", result.stdout)
            self.assertNotIn("process-next-request", result.stdout)
            self.assertNotIn("process-next-signal", result.stdout)
            self.assertNotIn("run-scheduler", result.stdout)
            self.assertNotIn("resume", result.stdout)

    def test_operations_observation_help_exposes_observer_commands(self) -> None:
            result = self.runner.invoke(
                app,
                ["operations-observer", "--help"],
                env=self.env,
            )

            self.assertEqual(result.exit_code, 0)
            self.assertIn("process", result.stdout)
            self.assertIn("rebuild", result.stdout)
            self.assertIn("run", result.stdout)
            self.assertNotIn("run-scheduler", result.stdout)
            self.assertNotIn("run-executor", result.stdout)
            self.assertNotIn("assign-next-assignment", result.stdout)
            self.assertNotIn("claim-next-" "assignment", result.stdout)

    def test_process_assignment_inline_command_targets_requested_run(self) -> None:
            server = SampleLlmApiServer()
            previous_token = os.environ.get("OPENAI_API_KEY")
            os.environ["OPENAI_API_KEY"] = "sample-compat-token"
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
                        "--credential-binding-id",
                        "openai-api-key",
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

                first_intake = self.runner.invoke(
                    app,
                    [
                        "orchestration",
                        "intake",
                        "assistant",
                        "local-chat",
                        "first",
                        "--run-id",
                        "run-cli-inline-first",
                        "--channel",
                        "webchat",
                        "--priority",
                        "50",
                        "--enqueue",
                    ],
                    env=self.env,
                )
                self.assertEqual(first_intake.exit_code, 0)

                second_intake = self.runner.invoke(
                    app,
                    [
                        "orchestration",
                        "intake",
                        "assistant",
                        "local-chat",
                        "second",
                        "--run-id",
                        "run-cli-inline-second",
                        "--channel",
                        "webchat",
                        "--priority",
                        "5",
                        "--enqueue",
                    ],
                    env=self.env,
                )
                self.assertEqual(second_intake.exit_code, 0)

                process_result = self.runner.invoke(
                    app,
                    [
                        "orchestration-executor",
                        "process-assignment-inline",
                        "run-cli-inline-first",
                        "--worker-id",
                        "worker-inline-1",
                    ],
                    env=self.env,
                )
                self.assertEqual(process_result.exit_code, 0)
                self.assertEqual(
                    json.loads(process_result.stdout)["id"],
                    "run-cli-inline-first",
                )

                first_get = self.runner.invoke(
                    app,
                    ["orchestration", "get", "run-cli-inline-first"],
                    env=self.env,
                )
                second_get = self.runner.invoke(
                    app,
                    ["orchestration", "get", "run-cli-inline-second"],
                    env=self.env,
                )
                self.assertEqual(first_get.exit_code, 0)
                self.assertEqual(second_get.exit_code, 0)
                self.assertNotEqual(json.loads(first_get.stdout)["status"], "queued")
                self.assertEqual(json.loads(second_get.stdout)["status"], "queued")
            finally:
                if previous_token is None:
                    os.environ.pop("OPENAI_API_KEY", None)
                else:
                    os.environ["OPENAI_API_KEY"] = previous_token
                server.close()

    def test_admit_assignment_command_targets_requested_run_without_processing(self) -> None:
            llm_result = self.runner.invoke(
                app,
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

            first_intake = self.runner.invoke(
                app,
                [
                    "orchestration",
                    "intake",
                    "assistant",
                    "openai.gpt-5.4-mini",
                    "first",
                    "--run-id",
                    "run-cli-admit-first",
                    "--channel",
                    "webchat",
                    "--priority",
                    "50",
                    "--enqueue",
                ],
                env=self.env,
            )
            self.assertEqual(first_intake.exit_code, 0)

            second_intake = self.runner.invoke(
                app,
                [
                    "orchestration",
                    "intake",
                    "assistant",
                    "openai.gpt-5.4-mini",
                    "second",
                    "--run-id",
                    "run-cli-admit-second",
                    "--channel",
                    "webchat",
                    "--priority",
                    "5",
                    "--enqueue",
                ],
                env=self.env,
            )
            self.assertEqual(second_intake.exit_code, 0)

            admit_result = self.runner.invoke(
                app,
                [
                    "orchestration-executor",
                    "admit-assignment",
                    "run-cli-admit-first",
                    "--worker-id",
                    "worker-admit-1",
                ],
                env=self.env,
            )
            self.assertEqual(admit_result.exit_code, 0)
            admitted_payload = json.loads(admit_result.stdout)
            self.assertEqual(admitted_payload["id"], "run-cli-admit-first")
            self.assertEqual(admitted_payload["status"], "running")
            self.assertEqual(admitted_payload["worker_id"], "worker-admit-1")
            self.assertEqual(admitted_payload["current_step"], 0)

            first_get = self.runner.invoke(
                app,
                ["orchestration", "get", "run-cli-admit-first"],
                env=self.env,
            )
            second_get = self.runner.invoke(
                app,
                ["orchestration", "get", "run-cli-admit-second"],
                env=self.env,
            )
            self.assertEqual(first_get.exit_code, 0)
            self.assertEqual(second_get.exit_code, 0)
            self.assertEqual(json.loads(first_get.stdout)["status"], "running")
            self.assertEqual(json.loads(first_get.stdout)["worker_id"], "worker-admit-1")
            self.assertEqual(json.loads(first_get.stdout)["current_step"], 0)
            self.assertEqual(json.loads(second_get.stdout)["status"], "queued")

    def test_run_executor_command_uses_service_owned_run_loop(self) -> None:
            calls: list[dict[str, object]] = []

            class _FakeExecutorService:
                def __init__(self) -> None:
                    self.heartbeats: list[dict[str, object]] = []

                def run_until_stopped(
                    self,
                    *,
                    worker_id: str,
                    poll_interval_seconds: float,
                    max_runs: int | None = None,
                    max_idle_cycles: int | None = None,
                    stop_event=None,
                    max_concurrent_assignments: int = 1,
                ) -> int:
                    calls.append(
                        {
                            "worker_id": worker_id,
                            "poll_interval_seconds": poll_interval_seconds,
                            "max_runs": max_runs,
                            "max_idle_cycles": max_idle_cycles,
                            "stop_event": stop_event,
                            "max_concurrent_assignments": max_concurrent_assignments,
                        },
                    )
                    return 0

                def heartbeat_executor(
                    self,
                    *,
                    worker_id: str,
                    max_inflight_assignments: int | None = None,
                    inflight_assignment_count: int | None = None,
                    draining: bool | None = None,
                    metadata: dict[str, object] | None = None,
                ):  # noqa: ANN201
                    self.heartbeats.append(
                        {
                            "worker_id": worker_id,
                            "max_inflight_assignments": max_inflight_assignments,
                            "inflight_assignment_count": inflight_assignment_count,
                            "draining": draining,
                            "metadata": metadata,
                        },
                    )
                    return object()

                def runtime_metrics_snapshot(self) -> dict[str, object]:
                    return {}

            class _FakeContainerContext:
                def __enter__(self):
                    return _RuntimeCliFakeContainer(
                        {AppKey.ORCHESTRATION_EXECUTOR_SERVICE: _FakeExecutorService()},
                    )

                def __exit__(self, exc_type, exc, tb):
                    return False

            with patch(
                "crxzipple.modules.orchestration.interfaces.worker_cli._executor_container",
                return_value=_FakeContainerContext(),
            ):
                result = self.runner.invoke(
                    app,
                    [
                        "orchestration-executor",
                        "run-executor",
                        "--worker-id",
                        "executor-service-1",
                        "--max-runs",
                        "2",
                        "--max-idle-cycles",
                        "3",
                        "--poll-interval-seconds",
                        "0.25",
                        "--max-concurrent-assignments",
                        "4",
                    ],
                    env=self.env,
                )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(
                calls,
                [
                    {
                        "worker_id": "executor-service-1",
                        "poll_interval_seconds": 0.25,
                        "max_runs": 2,
                        "max_idle_cycles": 3,
                        "stop_event": calls[0]["stop_event"],
                        "max_concurrent_assignments": 4,
                    },
                ],
            )
            self.assertIsNotNone(calls[0]["stop_event"])

    def test_run_executor_rejects_sqlite_without_explicit_runtime_fallback(self) -> None:
            result = self.runner.invoke(
                app,
                [
                    "orchestration-executor",
                    "run-executor",
                    "--max-idle-cycles",
                    "1",
                ],
                env=self.env_without_sqlite_runtime_fallback(),
            )

            self.assertEqual(result.exit_code, 1)
            self.assertIn(
                "Refusing to start orchestration executor with SQLite",
                result.stderr,
            )
            self.assertIn("APP_ALLOW_SQLITE_RUNTIME_FALLBACK=1", result.stderr)

    def test_run_scheduler_command_uses_service_owned_run_loop(self) -> None:
            calls: list[dict[str, object]] = []

            class _FakeSchedulerService:
                def run_until_stopped(
                    self,
                    *,
                    worker_id: str,
                    poll_interval_seconds: float,
                    max_runs: int | None = None,
                    max_idle_cycles: int | None = None,
                    stop_event=None,
                ) -> int:
                    calls.append(
                        {
                            "worker_id": worker_id,
                            "poll_interval_seconds": poll_interval_seconds,
                            "max_runs": max_runs,
                            "max_idle_cycles": max_idle_cycles,
                            "stop_event": stop_event,
                        },
                    )
                    return 0

            class _FakeContainerContext:
                def __enter__(self):
                    return _RuntimeCliFakeContainer(
                        {
                            AppKey.ORCHESTRATION_SCHEDULER_SERVICE: (
                                _FakeSchedulerService()
                            ),
                        },
                    )

                def __exit__(self, exc_type, exc, tb):
                    return False

            with patch(
                "crxzipple.modules.orchestration.interfaces.worker_cli._scheduler_container",
                return_value=_FakeContainerContext(),
            ):
                result = self.runner.invoke(
                    app,
                    [
                        "orchestration-scheduler",
                        "run-scheduler",
                        "--worker-id",
                        "scheduler-service-1",
                        "--max-runs",
                        "4",
                        "--max-idle-cycles",
                        "5",
                        "--poll-interval-seconds",
                        "0.75",
                    ],
                    env=self.env,
                )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(
                calls,
                [
                    {
                        "worker_id": "scheduler-service-1",
                        "poll_interval_seconds": 0.75,
                        "max_runs": 4,
                        "max_idle_cycles": 5,
                        "stop_event": None,
                    },
                ],
            )

    def test_run_scheduler_rejects_sqlite_without_explicit_runtime_fallback(self) -> None:
            result = self.runner.invoke(
                app,
                [
                    "orchestration-scheduler",
                    "run-scheduler",
                    "--max-idle-cycles",
                    "1",
                ],
                env=self.env_without_sqlite_runtime_fallback(),
            )

            self.assertEqual(result.exit_code, 1)
            self.assertIn(
                "Refusing to start orchestration scheduler with SQLite",
                result.stderr,
            )
            self.assertIn("APP_ALLOW_SQLITE_RUNTIME_FALLBACK=1", result.stderr)

    def test_operations_observation_run_command_uses_runtime_owned_run_loop(self) -> None:
            calls: list[dict[str, object]] = []

            class _FakeOperationsObserverRuntime:
                def run_until_stopped(
                    self,
                    *,
                    worker_id: str,
                    poll_interval_seconds: float,
                    max_events: int | None = None,
                    max_idle_cycles: int | None = None,
                    limit_per_subscription: int = 100,
                    stop_event=None,
                ) -> int:
                    calls.append(
                        {
                            "worker_id": worker_id,
                            "poll_interval_seconds": poll_interval_seconds,
                            "max_events": max_events,
                            "max_idle_cycles": max_idle_cycles,
                            "limit_per_subscription": limit_per_subscription,
                            "stop_event": stop_event,
                        },
                    )
                    return 7

            class _FakeContainer:
                def __init__(self) -> None:
                    self._values = {
                        AppKey.OPERATIONS_OBSERVER_RUNTIME_EVENT_SERVICE: (
                            _FakeOperationsObserverRuntime()
                        ),
                        AppKey.OPERATIONS_PROJECTION_MATERIALIZER: None,
                    }

                def require(self, key):
                    return self._values[key]

                def close(self) -> None:
                    pass

            class _FakeRuntimeContainer:
                def __enter__(self):
                    return _FakeContainer()

                def __exit__(self, exc_type, exc, traceback) -> None:
                    return None

            with patch(
                "crxzipple.modules.operations.interfaces.worker_cli.runtime_container",
                return_value=_FakeRuntimeContainer(),
            ):
                result = self.runner.invoke(
                    app,
                    [
                        "operations-observer",
                        "run",
                        "--worker-id",
                        "operations-observer-1",
                        "--max-events",
                        "7",
                        "--max-idle-cycles",
                        "5",
                        "--poll-interval-seconds",
                        "0.75",
                        "--limit-per-subscription",
                        "11",
                    ],
                    env=self.env,
                )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(
                calls,
                [
                    {
                        "worker_id": "operations-observer-1",
                        "poll_interval_seconds": 0.75,
                        "max_events": 7,
                        "max_idle_cycles": 5,
                        "limit_per_subscription": 11,
                        "stop_event": None,
                    },
                ],
            )
            self.assertEqual(
                json.loads(result.stdout),
                {
                    "processed_events": 7,
                    "worker_id": "operations-observer-1",
                },
            )

    def test_operations_observer_rebuild_only_rebuilds_projections(self) -> None:
            calls: list[str] = []

            class _FakeProjectionStore:
                def clear(self, **kwargs):  # noqa: ANN001
                    calls.append(f"clear:{kwargs}")
                    return 3

            class _FakeMaterializer:
                def materialize_all(self) -> int:
                    calls.append("materialize_all")
                    return 10

            class _FakeContainer:
                def __init__(self) -> None:
                    self._values = {
                        AppKey.OPERATIONS_PROJECTION_STORE: _FakeProjectionStore(),
                        AppKey.OPERATIONS_PROJECTION_MATERIALIZER: _FakeMaterializer(),
                    }

                def require(self, key):
                    return self._values[key]

                def close(self) -> None:
                    pass

            class _FakeRuntimeContainer:
                def __enter__(self):
                    return _FakeContainer()

                def __exit__(self, exc_type, exc, traceback) -> None:
                    return None

            with patch(
                "crxzipple.modules.operations.interfaces.worker_cli.runtime_container",
                return_value=_FakeRuntimeContainer(),
            ):
                result = self.runner.invoke(
                    app,
                    [
                        "operations-observer",
                        "rebuild",
                        "--worker-id",
                        "operations-observer-1",
                    ],
                    env=self.env,
                )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(calls, ["clear:{}", "materialize_all"])
            self.assertEqual(
                json.loads(result.stdout),
                {
                    "processed_events": 0,
                    "materialized_modules": 10,
                    "worker_id": "operations-observer-1",
                    "observation_reset": False,
                    "projection_reset": True,
                },
            )

    def test_operations_observer_run_rejects_sqlite_without_explicit_runtime_fallback(self) -> None:
            result = self.runner.invoke(
                app,
                [
                    "operations-observer",
                    "run",
                    "--max-idle-cycles",
                    "1",
                ],
                env=self.env_without_sqlite_runtime_fallback(),
            )

            self.assertEqual(result.exit_code, 1)
            self.assertIn(
                "Refusing to start operations observer with SQLite",
                result.stderr,
            )
            self.assertIn("APP_ALLOW_SQLITE_RUNTIME_FALLBACK=1", result.stderr)

    def test_operations_observer_process_rejects_sqlite_without_explicit_runtime_fallback(self) -> None:
            result = self.runner.invoke(
                app,
                ["operations-observer", "process"],
                env=self.env_without_sqlite_runtime_fallback(),
            )

            self.assertEqual(result.exit_code, 1)
            self.assertIn(
                "Refusing to start operations observer with SQLite",
                result.stderr,
            )
            self.assertIn("APP_ALLOW_SQLITE_RUNTIME_FALLBACK=1", result.stderr)

    def test_operations_observer_rebuild_rejects_sqlite_without_explicit_runtime_fallback(self) -> None:
            result = self.runner.invoke(
                app,
                ["operations-observer", "rebuild"],
                env=self.env_without_sqlite_runtime_fallback(),
            )

            self.assertEqual(result.exit_code, 1)
            self.assertIn(
                "Refusing to start operations observer rebuild with SQLite",
                result.stderr,
            )
            self.assertIn("APP_ALLOW_SQLITE_RUNTIME_FALLBACK=1", result.stderr)

    def test_orchestration_executor_runtime_metrics_command_summarizes_leases(self) -> None:
            class _FakeStatus:
                value = "online"

            class _FakeLease:
                worker_id = "executor-metrics-1"
                status = _FakeStatus()
                max_inflight_assignments = 4
                inflight_assignment_count = 2
                metadata = {
                    "runtime_state": {
                        "active_run_ids": ["run-1", "run-2"],
                        "active_assignment_count": 2,
                    },
                    "runtime_metrics": {
                        "gauges": [
                            {
                                "name": "orchestration.executor.active_assignments",
                                "labels": {"worker_id": "executor-metrics-1"},
                                "value": 2.0,
                            },
                        ],
                    },
                }

            class _FakeExecutorService:
                def list_executor_leases(self, *, status=None):  # noqa: ANN001, ANN201
                    self.status = status
                    return [_FakeLease()]

            class _FakeContainerContext:
                def __enter__(self):
                    return _RuntimeCliFakeContainer(
                        {AppKey.ORCHESTRATION_EXECUTOR_SERVICE: _FakeExecutorService()},
                    )

                def __exit__(self, exc_type, exc, tb):
                    return False

            with patch(
                "crxzipple.modules.orchestration.interfaces.worker_cli._executor_container",
                return_value=_FakeContainerContext(),
            ):
                result = self.runner.invoke(
                    app,
                    ["orchestration-executor", "runtime-metrics"],
                    env=self.env,
                )

            self.assertEqual(result.exit_code, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["executor_count"], 1)
            self.assertEqual(payload["online_executor_count"], 1)
            self.assertEqual(payload["capacity_executor_count"], 1)
            self.assertEqual(payload["total_max_inflight_assignments"], 4)
            self.assertEqual(payload["total_inflight_assignment_count"], 2)
            self.assertEqual(payload["total_available_assignment_slots"], 2)
            self.assertTrue(payload["leases"][0]["counts_toward_capacity"])
            self.assertEqual(payload["leases"][0]["worker_id"], "executor-metrics-1")
            self.assertEqual(
                payload["leases"][0]["runtime_state"]["active_run_ids"],
                ["run-1", "run-2"],
            )
            self.assertEqual(payload["leases"][0]["effective_status"], "online")

    def test_orchestration_executor_list_leases_reports_effective_status(self) -> None:
            expired_lease = OrchestrationExecutorLease.register(
                worker_id="executor-expired-display",
                max_inflight_assignments=4,
                inflight_assignment_count=1,
                lease_seconds=30,
            )
            expired_lease.lease_expires_at = datetime.now(timezone.utc) - timedelta(
                seconds=1,
            )

            class _FakeExecutorService:
                def list_executor_leases(self, *, status=None):  # noqa: ANN001, ANN201
                    self.status = status
                    return [expired_lease]

            class _FakeContainerContext:
                def __enter__(self):
                    return _RuntimeCliFakeContainer(
                        {AppKey.ORCHESTRATION_EXECUTOR_SERVICE: _FakeExecutorService()},
                    )

                def __exit__(self, exc_type, exc, tb):
                    return False

            with patch(
                "crxzipple.modules.orchestration.interfaces.worker_cli._executor_container",
                return_value=_FakeContainerContext(),
            ):
                result = self.runner.invoke(
                    app,
                    ["orchestration-executor", "list-executor-leases"],
                    env=self.env,
                )

            self.assertEqual(result.exit_code, 0)
            [payload] = json.loads(result.stdout)
            self.assertEqual(payload["status"], "online")
            self.assertEqual(payload["effective_status"], "offline")
            self.assertTrue(payload["expired"])
            self.assertFalse(payload["counts_toward_capacity"])
            self.assertEqual(payload["available_assignment_slots"], 0)

    def test_orchestration_scheduler_expire_executor_leases_command(self) -> None:
            expired_lease = OrchestrationExecutorLease.register(
                worker_id="executor-expire-cli",
                max_inflight_assignments=2,
                inflight_assignment_count=0,
                lease_seconds=30,
            )
            expired_lease.lease_expires_at = datetime.now(timezone.utc) - timedelta(
                seconds=1,
            )
            expired_lease.mark_offline()

            class _FakeSchedulerService:
                def expire_executor_leases(self):  # noqa: ANN201
                    return [expired_lease]

            class _FakeContainerContext:
                def __enter__(self):
                    return _RuntimeCliFakeContainer(
                        {
                            AppKey.ORCHESTRATION_SCHEDULER_SERVICE: (
                                _FakeSchedulerService()
                            ),
                        },
                    )

                def __exit__(self, exc_type, exc, tb):
                    return False

            with patch(
                "crxzipple.modules.orchestration.interfaces.worker_cli._scheduler_container",
                return_value=_FakeContainerContext(),
            ):
                result = self.runner.invoke(
                    app,
                    ["orchestration-scheduler", "expire-executor-leases"],
                    env=self.env,
                )

            self.assertEqual(result.exit_code, 0)
            [payload] = json.loads(result.stdout)
            self.assertEqual(payload["worker_id"], "executor-expire-cli")
            self.assertEqual(payload["status"], "offline")
            self.assertEqual(payload["effective_status"], "offline")

    def test_orchestration_executor_runtime_metrics_excludes_draining_capacity(self) -> None:
            class _OnlineStatus:
                value = "online"

            class _DrainingStatus:
                value = "draining"

            class _OnlineLease:
                worker_id = "executor-online"
                status = _OnlineStatus()
                max_inflight_assignments = 4
                inflight_assignment_count = 1
                metadata = {}

                def is_expired(self) -> bool:
                    return False

            class _DrainingLease:
                worker_id = "executor-draining"
                status = _DrainingStatus()
                max_inflight_assignments = 8
                inflight_assignment_count = 0
                metadata = {}

                def is_expired(self) -> bool:
                    return False

            class _FakeExecutorService:
                def list_executor_leases(self, *, status=None):  # noqa: ANN001, ANN201
                    self.status = status
                    return [_OnlineLease(), _DrainingLease()]

            class _FakeContainerContext:
                def __enter__(self):
                    return _RuntimeCliFakeContainer(
                        {AppKey.ORCHESTRATION_EXECUTOR_SERVICE: _FakeExecutorService()},
                    )

                def __exit__(self, exc_type, exc, tb):
                    return False

            with patch(
                "crxzipple.modules.orchestration.interfaces.worker_cli._executor_container",
                return_value=_FakeContainerContext(),
            ):
                result = self.runner.invoke(
                    app,
                    ["orchestration-executor", "runtime-metrics"],
                    env=self.env,
                )

            self.assertEqual(result.exit_code, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["executor_count"], 2)
            self.assertEqual(payload["online_executor_count"], 1)
            self.assertEqual(payload["capacity_executor_count"], 1)
            self.assertEqual(payload["total_max_inflight_assignments"], 4)
            self.assertEqual(payload["total_inflight_assignment_count"], 1)
            self.assertEqual(payload["total_available_assignment_slots"], 3)
            leases_by_id = {lease["worker_id"]: lease for lease in payload["leases"]}
            self.assertTrue(leases_by_id["executor-online"]["counts_toward_capacity"])
            self.assertFalse(leases_by_id["executor-draining"]["counts_toward_capacity"])
            self.assertEqual(
                leases_by_id["executor-draining"]["available_assignment_slots"],
                0,
            )

    def test_orchestration_executor_probe_runtime_runs_bounded_loop_and_emits_metrics(self) -> None:
            calls: list[dict[str, object]] = []

            class _FakeExecutorService:
                def run_until_stopped(
                    self,
                    *,
                    worker_id: str,
                    poll_interval_seconds: float,
                    max_runs: int | None = None,
                    max_idle_cycles: int | None = None,
                    max_concurrent_assignments: int = 1,
                    stop_event=None,
                ) -> int:
                    calls.append(
                        {
                            "worker_id": worker_id,
                            "poll_interval_seconds": poll_interval_seconds,
                            "max_runs": max_runs,
                            "max_idle_cycles": max_idle_cycles,
                            "max_concurrent_assignments": max_concurrent_assignments,
                            "stop_event": stop_event,
                        },
                    )
                    return 12

                def runtime_metrics_snapshot(self) -> dict[str, object]:
                    return {
                        "counters": [
                            {
                                "name": "orchestration.executor.assignment_completions",
                                "labels": {"worker_id": "executor-probe-1"},
                                "value": 12,
                            },
                        ],
                    }

            class _FakeContainerContext:
                def __enter__(self):
                    return _RuntimeCliFakeContainer(
                        {AppKey.ORCHESTRATION_EXECUTOR_SERVICE: _FakeExecutorService()},
                    )

                def __exit__(self, exc_type, exc, tb):
                    return False

            with patch(
                "crxzipple.modules.orchestration.interfaces.worker_cli._executor_container",
                return_value=_FakeContainerContext(),
            ):
                result = self.runner.invoke(
                    app,
                    [
                        "orchestration-executor",
                        "probe-runtime",
                        "--worker-id",
                        "executor-probe-1",
                        "--max-runs",
                        "12",
                        "--max-idle-cycles",
                        "2",
                        "--poll-interval-seconds",
                        "0.25",
                        "--max-concurrent-assignments",
                        "4",
                    ],
                    env=self.env,
                )

            self.assertEqual(result.exit_code, 0)
            self.assertEqual(
                calls,
                [
                    {
                        "worker_id": "executor-probe-1",
                        "poll_interval_seconds": 0.25,
                        "max_runs": 12,
                        "max_idle_cycles": 2,
                        "max_concurrent_assignments": 4,
                        "stop_event": None,
                    },
                ],
            )
            payload = json.loads(result.stdout)
            self.assertEqual(payload["processed_runs"], 12)
            self.assertEqual(payload["max_concurrent_assignments"], 4)
            self.assertEqual(
                payload["runtime_metrics"]["counters"][0]["name"],
                "orchestration.executor.assignment_completions",
            )

    def test_orchestration_executor_benchmark_runtime_builds_runs_and_reports_throughput(self) -> None:
            class _FakeStatus:
                value = "completed"

            class _FakeRun:
                status = _FakeStatus()

                def __init__(self, run_id: str) -> None:
                    self.id = run_id

            class _FakeSchedulerService:
                def __init__(self) -> None:
                    self.accepted_content: list[str] = []
                    self.main_keys: list[str] = []
                    self.enqueued_run_ids: list[str] = []
                    self._assignable_run_ids: list[str] = []
                    self.run_calls: list[dict[str, object]] = []

                def submit_turn(self, data, *, inline_worker_id=None):  # noqa: ANN001, ANN201
                    del inline_worker_id
                    self.accepted_content.append(data.accept_input.inbound_instruction.content)
                    self.main_keys.append(data.context.main_key)
                    run_id = data.accept_input.run_id
                    self.enqueued_run_ids.append(run_id)
                    self._assignable_run_ids.append(run_id)
                    return _FakeRun(run_id)

                def assign_next_assignment(self):  # noqa: ANN201
                    if not self._assignable_run_ids:
                        return None
                    return _FakeRun(self._assignable_run_ids.pop(0))

                def run_until_stopped(
                    self,
                    *,
                    worker_id: str,
                    poll_interval_seconds: float,
                    max_runs: int | None = None,
                    max_idle_cycles: int | None = None,
                    stop_event=None,
                ) -> int:
                    del stop_event
                    assigned_count = min(
                        len(self._assignable_run_ids),
                        max_runs or len(self._assignable_run_ids),
                    )
                    self.run_calls.append(
                        {
                            "worker_id": worker_id,
                            "poll_interval_seconds": poll_interval_seconds,
                            "max_runs": max_runs,
                            "max_idle_cycles": max_idle_cycles,
                            "assigned_count": assigned_count,
                        },
                    )
                    del self._assignable_run_ids[:assigned_count]
                    return assigned_count

            class _FakeExecutorService:
                def __init__(self) -> None:
                    self.heartbeats: list[dict[str, object]] = []
                    self.run_calls: list[dict[str, object]] = []

                def heartbeat_executor(
                    self,
                    *,
                    worker_id: str,
                    max_inflight_assignments: int | None = None,
                    inflight_assignment_count: int | None = None,
                    draining: bool | None = None,
                    metadata: dict[str, object] | None = None,
                ):  # noqa: ANN201
                    self.heartbeats.append(
                        {
                            "worker_id": worker_id,
                            "max_inflight_assignments": max_inflight_assignments,
                            "inflight_assignment_count": inflight_assignment_count,
                            "draining": draining,
                            "metadata": metadata,
                        },
                    )
                    return object()

                def run_until_stopped(
                    self,
                    *,
                    worker_id: str,
                    poll_interval_seconds: float,
                    max_runs: int | None = None,
                    max_idle_cycles: int | None = None,
                    max_concurrent_assignments: int = 1,
                    stop_event=None,
                ) -> int:
                    del stop_event
                    self.run_calls.append(
                        {
                            "worker_id": worker_id,
                            "poll_interval_seconds": poll_interval_seconds,
                            "max_runs": max_runs,
                            "max_idle_cycles": max_idle_cycles,
                            "max_concurrent_assignments": max_concurrent_assignments,
                        },
                    )
                    time.sleep(0.02)
                    return max_runs or 0

                def runtime_metrics_snapshot(self) -> dict[str, object]:
                    return {
                        "counters": [
                            {
                                "name": "orchestration.executor.assignment_completions",
                                "labels": {"worker_id": "executor-bench-1"},
                                "value": 3,
                            },
                        ],
                    }

            class _FakeRunQueryService:
                def list_runs(self, *, status=None):  # noqa: ANN001, ANN201
                    del status
                    return []

                def get_run(self, run_id: str) -> _FakeRun:
                    return _FakeRun(run_id)

            fake_scheduler = _FakeSchedulerService()
            fake_executor = _FakeExecutorService()

            class _FakeContainerContext:
                def __enter__(self):
                    container = _RuntimeCliFakeContainer(
                        {
                            AppKey.ORCHESTRATION_SCHEDULER_SERVICE: fake_scheduler,
                            AppKey.ORCHESTRATION_EXECUTOR_SERVICE: fake_executor,
                            AppKey.ORCHESTRATION_RUN_QUERY_SERVICE: (
                                _FakeRunQueryService()
                            ),
                        },
                    )
                    return container, container

                def __exit__(self, exc_type, exc, tb):
                    return False

            with patch(
                "crxzipple.modules.orchestration.interfaces.worker_cli._linked_runtime_containers",
                return_value=_FakeContainerContext(),
            ):
                result = self.runner.invoke(
                    app,
                    [
                        "orchestration-executor",
                        "benchmark-runtime",
                        "assistant",
                        "local-chat",
                        "hello benchmark",
                        "--run-count",
                        "3",
                        "--run-id-prefix",
                        "bench-cli",
                        "--main-key",
                        "lane",
                        "--worker-id",
                        "executor-bench-1",
                        "--scheduler-worker-id",
                        "scheduler-bench-1",
                        "--max-concurrent-assignments",
                        "2",
                        "--poll-interval-seconds",
                        "0.01",
                        "--scheduler-poll-interval-seconds",
                        "0.01",
                    ],
                    env=self.env,
                )

            self.assertEqual(result.exit_code, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["benchmark_id"], "bench-cli")
            self.assertEqual(payload["created_run_count"], 3)
            self.assertEqual(payload["assigned_run_count"], 3)
            self.assertEqual(payload["assignment_waves"], 2)
            self.assertEqual(payload["scheduler_processed_items"], 3)
            self.assertEqual(payload["runtime_mode"], "linked_scheduler_executor")
            self.assertEqual(payload["processed_runs"], 3)
            self.assertEqual(payload["lane_mode"], "unique")
            self.assertEqual(
                payload["run_ids"],
                ["bench-cli-0001", "bench-cli-0002", "bench-cli-0003"],
            )
            self.assertEqual(
                payload["assigned_run_ids"],
                ["bench-cli-0001", "bench-cli-0002", "bench-cli-0003"],
            )
            self.assertEqual(payload["status_counts"], {"completed": 3})
            self.assertEqual(payload["other_online_executor_ids"], [])
            self.assertEqual(payload["executor"]["worker_id"], "executor-bench-1")
            self.assertEqual(payload["executor"]["max_concurrent_assignments"], 2)
            self.assertEqual(payload["scheduler"]["worker_id"], "scheduler-bench-1")
            self.assertEqual(
                fake_scheduler.main_keys,
                ["lane-0001", "lane-0002", "lane-0003"],
            )
            self.assertIn("benchmark_run index=1", fake_scheduler.accepted_content[0])
            self.assertEqual(
                fake_executor.heartbeats[0]["inflight_assignment_count"],
                0,
            )
            self.assertEqual(
                fake_scheduler.run_calls,
                [
                    {
                        "worker_id": "scheduler-bench-1",
                        "poll_interval_seconds": 0.01,
                        "max_runs": 3,
                        "max_idle_cycles": None,
                        "assigned_count": 3,
                    },
                ],
            )
            self.assertEqual(
                [call["max_runs"] for call in fake_executor.run_calls],
                [3],
            )
            self.assertEqual(
                payload["runtime_metrics"]["counters"][0]["name"],
                "orchestration.executor.assignment_completions",
            )

    def _invoke_benchmark_tool_io_with_fakes(
        self,
        *,
        same_lane: bool = False,
        max_active_tool_calls: int,
    ):
            class _FakeStatus:
                value = "completed"

            class _FakeRun:
                status = _FakeStatus()
                worker_id = "executor-tool-io-1"

                def __init__(self, run_id: str) -> None:
                    self.id = run_id

            class _FakeSchedulerService:
                def __init__(self) -> None:
                    self.main_keys: list[str] = []
                    self.run_calls: list[dict[str, object]] = []

                def submit_turn(self, data, *, inline_worker_id=None):  # noqa: ANN001, ANN201
                    del inline_worker_id
                    self.main_keys.append(data.context.main_key)
                    return _FakeRun(data.accept_input.run_id)

                def run_until_stopped(
                    self,
                    *,
                    worker_id: str,
                    poll_interval_seconds: float,
                    max_runs: int | None = None,
                    max_idle_cycles: int | None = None,
                    stop_event=None,
                ) -> int:
                    del stop_event
                    self.run_calls.append(
                        {
                            "worker_id": worker_id,
                            "poll_interval_seconds": poll_interval_seconds,
                            "max_runs": max_runs,
                            "max_idle_cycles": max_idle_cycles,
                        },
                    )
                    return max_runs or 0

            class _FakeExecutorService:
                def __init__(self) -> None:
                    self.heartbeats: list[dict[str, object]] = []
                    self.run_calls: list[dict[str, object]] = []

                def heartbeat_executor(
                    self,
                    *,
                    worker_id: str,
                    max_inflight_assignments: int | None = None,
                    inflight_assignment_count: int | None = None,
                    draining: bool | None = None,
                    metadata: dict[str, object] | None = None,
                ):  # noqa: ANN201
                    self.heartbeats.append(
                        {
                            "worker_id": worker_id,
                            "max_inflight_assignments": max_inflight_assignments,
                            "inflight_assignment_count": inflight_assignment_count,
                            "draining": draining,
                            "metadata": metadata,
                        },
                    )
                    return object()

                def list_executor_leases(self, *, status=None):  # noqa: ANN001, ANN201
                    del status
                    return []

                def run_until_stopped(
                    self,
                    *,
                    worker_id: str,
                    poll_interval_seconds: float,
                    max_runs: int | None = None,
                    max_idle_cycles: int | None = None,
                    max_concurrent_assignments: int = 1,
                    stop_event=None,
                ) -> int:
                    del stop_event
                    self.run_calls.append(
                        {
                            "worker_id": worker_id,
                            "poll_interval_seconds": poll_interval_seconds,
                            "max_runs": max_runs,
                            "max_idle_cycles": max_idle_cycles,
                            "max_concurrent_assignments": max_concurrent_assignments,
                        },
                    )
                    return max_runs or 0

                def runtime_metrics_snapshot(self) -> dict[str, object]:
                    return {
                        "timings": [
                            {
                                "name": "orchestration.executor.advance_phase_seconds",
                                "labels": {"phase": "engine"},
                                "count": 2,
                            },
                            {
                                "name": "orchestration.engine.phase_seconds",
                                "labels": {"phase": "tool_execution"},
                                "count": 2,
                            },
                        ],
                    }

            class _FakeRunQueryService:
                def list_runs(self, *, status=None):  # noqa: ANN001, ANN201
                    del status
                    return []

                def get_run(self, run_id: str) -> _FakeRun:
                    return _FakeRun(run_id)

            class _FakeStats:
                def snapshot(self) -> dict[str, int]:
                    return {
                        "started_tool_calls": 4,
                        "completed_tool_calls": 4,
                        "active_tool_calls": 0,
                        "max_active_tool_calls": max_active_tool_calls,
                        "started_llm_invocations": 2,
                        "completed_llm_invocations": 2,
                    }

            fake_scheduler = _FakeSchedulerService()
            fake_executor = _FakeExecutorService()

            class _FakeContainerContext:
                def __enter__(self):
                    container = _RuntimeCliFakeContainer(
                        {
                            AppKey.ORCHESTRATION_SCHEDULER_SERVICE: fake_scheduler,
                            AppKey.ORCHESTRATION_EXECUTOR_SERVICE: fake_executor,
                            AppKey.ORCHESTRATION_RUN_QUERY_SERVICE: (
                                _FakeRunQueryService()
                            ),
                        },
                    )
                    return container, container

                def __exit__(self, exc_type, exc, tb):
                    return False

            command = [
                "orchestration-executor",
                "benchmark-tool-io",
                "--agent-id",
                "tool-io-single-lane-agent" if same_lane else "tool-io-agent",
                "--run-count",
                "2",
                "--tool-calls-per-run",
                "2",
                "--tool-sleep-seconds",
                "0.2",
                "--run-id-prefix",
                "tool-io-single-lane-cli" if same_lane else "tool-io-cli",
                "--main-key",
                "tool-io-single-lane-cli" if same_lane else "tool-io-cli",
                "--max-concurrent-assignments",
                "2",
                "--poll-interval-seconds",
                "0.01",
                "--scheduler-poll-interval-seconds",
                "0.01",
            ]
            if same_lane:
                command.append("--same-lane")

            with (
                patch(
                    "crxzipple.modules.orchestration.interfaces.worker_cli._linked_runtime_containers",
                    return_value=_FakeContainerContext(),
                ),
                patch(
                    "crxzipple.modules.orchestration.interfaces.worker_cli._register_tool_io_benchmark_runtime",
                    return_value=(
                        "benchmark.tool_io.fake",
                        "benchmark_tool_io_sleep_fake",
                        _FakeStats(),
                    ),
                ),
            ):
                result = self.runner.invoke(app, command, env=self.env)

            return result, fake_scheduler, fake_executor

    def test_orchestration_executor_benchmark_tool_io_reports_cross_run_concurrency(self) -> None:
            result, fake_scheduler, fake_executor = (
                self._invoke_benchmark_tool_io_with_fakes(
                    max_active_tool_calls=4,
                )
            )

            self.assertEqual(result.exit_code, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(
                payload["runtime_mode"],
                "linked_scheduler_executor_synthetic_tool_io",
            )
            self.assertEqual(payload["processed_runs"], 2)
            self.assertEqual(payload["status_counts"], {"completed": 2})
            self.assertEqual(payload["tool_calls_per_run"], 2)
            self.assertEqual(payload["expected_tool_call_count"], 4)
            self.assertEqual(payload["completed_tool_call_count"], 4)
            self.assertGreaterEqual(payload["max_active_tool_calls"], 3)
            self.assertEqual(payload["executor"]["max_concurrent_assignments"], 2)
            self.assertEqual(
                fake_scheduler.main_keys,
                [
                    "tool-io-cli-tool-io-cli-0001",
                    "tool-io-cli-tool-io-cli-0002",
                ],
            )
            self.assertEqual(
                [call["max_concurrent_assignments"] for call in fake_executor.run_calls],
                [2],
            )
            timing_phases = {
                (item["name"], item.get("labels", {}).get("phase"))
                for item in payload["runtime_metrics"]["timings"]
            }
            self.assertIn(
                ("orchestration.executor.advance_phase_seconds", "engine"),
                timing_phases,
            )
            self.assertIn(
                ("orchestration.engine.phase_seconds", "tool_execution"),
                timing_phases,
            )

    def test_orchestration_executor_benchmark_tool_io_same_lane_counts_each_run(self) -> None:
            result, fake_scheduler, fake_executor = (
                self._invoke_benchmark_tool_io_with_fakes(
                    same_lane=True,
                    max_active_tool_calls=2,
                )
            )

            self.assertEqual(result.exit_code, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["processed_runs"], 2)
            self.assertEqual(payload["status_counts"], {"completed": 2})
            self.assertEqual(payload["lane_mode"], "single")
            self.assertEqual(payload["expected_tool_call_count"], 4)
            self.assertEqual(payload["completed_tool_call_count"], 4)
            self.assertLessEqual(payload["max_active_tool_calls"], 2)
            self.assertEqual(
                fake_scheduler.main_keys,
                [
                    "tool-io-single-lane-cli-tool-io-single-lane-cli",
                    "tool-io-single-lane-cli-tool-io-single-lane-cli",
                ],
            )
            self.assertEqual(
                [call["max_concurrent_assignments"] for call in fake_executor.run_calls],
                [1],
            )

    def test_orchestration_executor_benchmark_daemon_runtime_waits_for_daemons(self) -> None:
            class _FakeStatus:
                value = "completed"

            class _FakeRun:
                status = _FakeStatus()
                worker_id = "worker-orchestration-1"

                def __init__(self, run_id: str) -> None:
                    self.id = run_id

            class _FakeSchedulerService:
                def __init__(self) -> None:
                    self.accepted_content: list[str] = []
                    self.main_keys: list[str] = []

                def submit_turn(self, data, *, inline_worker_id=None):  # noqa: ANN001, ANN201
                    del inline_worker_id
                    self.accepted_content.append(data.accept_input.inbound_instruction.content)
                    self.main_keys.append(data.context.main_key)
                    return _FakeRun(data.accept_input.run_id)

            class _FakeRunQueryService:
                def list_runs(self, *, status=None):  # noqa: ANN001, ANN201
                    del status
                    return []

                def get_run(self, run_id: str) -> _FakeRun:
                    return _FakeRun(run_id)

            class _FakeDaemonManager:
                def __init__(self) -> None:
                    self.service_keys: list[str] = []

                def list_instances(self, *, service_key: str, refresh: bool = True):  # noqa: ANN201
                    self.service_keys.append(service_key)
                    return (
                        SimpleNamespace(
                            id=f"inst-{service_key}",
                            status="ready",
                            worker_id=f"{service_key.replace(':', '-')}-1",
                            pid=1234,
                        ),
                    )

            fake_scheduler = _FakeSchedulerService()
            fake_daemon_manager = _FakeDaemonManager()

            class _FakeContainerContext:
                def __enter__(self):
                    return _RuntimeCliFakeContainer(
                        {
                            AppKey.ORCHESTRATION_SCHEDULER_SERVICE: fake_scheduler,
                            AppKey.ORCHESTRATION_RUN_QUERY_SERVICE: (
                                _FakeRunQueryService()
                            ),
                            AppKey.DAEMON_MANAGER: fake_daemon_manager,
                        },
                    )

                def __exit__(self, exc_type, exc, tb):
                    return False

            with patch(
                "crxzipple.modules.orchestration.interfaces.worker_cli._admin_container",
                return_value=_FakeContainerContext(),
            ):
                result = self.runner.invoke(
                    app,
                    [
                        "orchestration-executor",
                        "benchmark-daemon-runtime",
                        "assistant",
                        "local-chat",
                        "hello daemon benchmark",
                        "--run-count",
                        "2",
                        "--run-id-prefix",
                        "daemon-bench-cli",
                        "--main-key",
                        "daemon-lane",
                        "--timeout-seconds",
                        "1",
                        "--poll-interval-seconds",
                        "0.01",
                    ],
                    env=self.env,
                )

            self.assertEqual(result.exit_code, 0)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["benchmark_id"], "daemon-bench-cli")
            self.assertEqual(payload["runtime_mode"], "daemon_scheduler_executor")
            self.assertEqual(payload["created_run_count"], 2)
            self.assertEqual(payload["processed_runs"], 2)
            self.assertTrue(payload["completed_before_timeout"])
            self.assertEqual(payload["status_counts"], {"completed": 2})
            self.assertEqual(
                payload["run_ids"],
                ["daemon-bench-cli-0001", "daemon-bench-cli-0002"],
            )
            self.assertEqual(
                payload["assigned_run_ids"],
                ["daemon-bench-cli-0001", "daemon-bench-cli-0002"],
            )
            self.assertEqual(
                fake_scheduler.main_keys,
                ["daemon-lane-0001", "daemon-lane-0002"],
            )
            self.assertEqual(
                fake_daemon_manager.service_keys,
                [
                    "worker:orchestration-scheduler",
                    "worker:orchestration",
                ],
            )

    def test_orchestration_executor_benchmark_daemon_runtime_requires_ready_daemons(self) -> None:
            class _FakeSchedulerService:
                def submit_turn(self, data, *, inline_worker_id=None):  # noqa: ANN001, ANN201
                    del inline_worker_id
                    raise AssertionError("benchmark should not create runs before daemon readiness")

            class _FakeRunQueryService:
                def list_runs(self, *, status=None):  # noqa: ANN001, ANN201
                    del status
                    return []

            class _FakeDaemonManager:
                def list_instances(self, *, service_key: str, refresh: bool = True):  # noqa: ANN201
                    del service_key, refresh
                    return ()

            class _FakeContainerContext:
                def __enter__(self):
                    return _RuntimeCliFakeContainer(
                        {
                            AppKey.ORCHESTRATION_SCHEDULER_SERVICE: (
                                _FakeSchedulerService()
                            ),
                            AppKey.ORCHESTRATION_RUN_QUERY_SERVICE: (
                                _FakeRunQueryService()
                            ),
                            AppKey.DAEMON_MANAGER: _FakeDaemonManager(),
                        },
                    )

                def __exit__(self, exc_type, exc, tb):
                    return False

            with patch(
                "crxzipple.modules.orchestration.interfaces.worker_cli._admin_container",
                return_value=_FakeContainerContext(),
            ):
                result = self.runner.invoke(
                    app,
                    [
                        "orchestration-executor",
                        "benchmark-daemon-runtime",
                        "assistant",
                        "local-chat",
                        "hello daemon benchmark",
                        "--run-count",
                        "1",
                    ],
                    env=self.env,
                )

            self.assertEqual(result.exit_code, 1)
            self.assertIn("requires ready orchestration runtime services", result.stderr)

    def test_orchestration_executor_benchmark_runtime_rejects_existing_queued_runs(self) -> None:
            class _FakeStatus:
                value = "queued"

            class _FakeRun:
                status = _FakeStatus()

                def __init__(self, run_id: str) -> None:
                    self.id = run_id

            class _FakeSchedulerService:
                def __init__(self) -> None:
                    self.submit_turn_calls = 0

                def submit_turn(self, data, *, inline_worker_id=None):  # noqa: ANN001, ANN201
                    del data, inline_worker_id
                    self.submit_turn_calls += 1
                    return _FakeRun("unexpected")

            class _FakeExecutorService:
                pass

            class _FakeRunQueryService:
                def list_runs(self, *, status=None):  # noqa: ANN001, ANN201
                    del status
                    return [_FakeRun("queued-before-benchmark")]

            fake_scheduler = _FakeSchedulerService()

            class _FakeContainerContext:
                def __enter__(self):
                    container = _RuntimeCliFakeContainer(
                        {
                            AppKey.ORCHESTRATION_SCHEDULER_SERVICE: fake_scheduler,
                            AppKey.ORCHESTRATION_EXECUTOR_SERVICE: (
                                _FakeExecutorService()
                            ),
                            AppKey.ORCHESTRATION_RUN_QUERY_SERVICE: (
                                _FakeRunQueryService()
                            ),
                        },
                    )
                    return container, container

                def __exit__(self, exc_type, exc, tb):
                    return False

            with patch(
                "crxzipple.modules.orchestration.interfaces.worker_cli._linked_runtime_containers",
                return_value=_FakeContainerContext(),
            ):
                result = self.runner.invoke(
                    app,
                    [
                        "orchestration-executor",
                        "benchmark-runtime",
                        "assistant",
                        "local-chat",
                        "hello benchmark",
                        "--run-count",
                        "1",
                    ],
                    env=self.env,
                )

            self.assertEqual(result.exit_code, 1)
            self.assertIn("existing queued orchestration runs", result.stderr)
            self.assertEqual(fake_scheduler.submit_turn_calls, 0)


if __name__ == "__main__":
    unittest.main()
