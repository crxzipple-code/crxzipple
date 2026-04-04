from __future__ import annotations

from tests.unit.cli_test_support import *


class OrchestrationCliTestCase(CliModuleTestCase):
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


if __name__ == "__main__":
    unittest.main()
