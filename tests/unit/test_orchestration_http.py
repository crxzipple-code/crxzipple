from __future__ import annotations

from tests.unit.http_test_support import *


class OrchestrationHttpTestCase(HttpModuleTestCase):
    def test_orchestration_request_due_heartbeats_endpoint_queues_idle_session(self) -> None:
            adapter = _SequentialTextAdapter("initial answer", "HEARTBEAT_OK")
            self.client.app.state.container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )

            llm_response = self.client.post(
                "/llms",
                json={
                    "id": "local-chat",
                    "provider": "openai",
                    "api_family": "openai_responses",
                    "model_name": "gpt-5.4-mini",
                },
            )
            self.assertEqual(llm_response.status_code, 201)
            agent_response = self.client.post(
                "/agents",
                json={
                    "id": "crxzipple",
                    "name": "crxzipple",
                    "llm_routing_policy": {"default_llm_id": "local-chat"},
                    "instruction_policy": {"system_prompt": "Be helpful."},
                },
            )
            self.assertEqual(agent_response.status_code, 201)

            turn_response = self.client.post(
                "/turns",
                json={
                    "content": "hello",
                    "agent_id": "crxzipple",
                },
            )
            self.assertEqual(turn_response.status_code, 202)
            _ = self.client.app.state.container.orchestration_service.process_next_queued_run(
                worker_id="http-test-worker",
            )

            with self.client.app.state.container.session_service.uow_factory() as uow:
                session = uow.sessions.get("agent:crxzipple:main")
                assert session is not None
                session.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
                uow.sessions.add(session)
                uow.commit()

            due_response = self.client.post(
                "/orchestration/heartbeats/request-due",
                json={
                    "idle_seconds": 60,
                    "limit": 5,
                },
            )
            self.assertEqual(due_response.status_code, 200)
            payload = due_response.json()
            self.assertEqual(len(payload), 1)
            self.assertEqual(payload[0]["metadata"]["prompt_flow_hint"]["mode"], "heartbeat")
            self.assertEqual(payload[0]["metadata"]["heartbeat_request"]["basis"], "idle_session")

    def test_orchestration_intake_endpoint_accepts_prepares_and_enqueues_run(self) -> None:
            llm_response = self.client.post(
                "/llms",
                json={
                    "id": "openai.gpt-5.4-mini",
                    "provider": "openai",
                    "api_family": "openai_responses",
                    "model_name": "gpt-5.4-mini",
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

            intake_response = self.client.post(
                "/orchestration/runs/intake",
                json={
                    "inbound_instruction": {
                        "source": "http",
                        "content": "draft a reply",
                        "metadata": {"request_id": "req-1"},
                    },
                    "session": {
                        "agent_id": "assistant",
                        "llm_id": "openai.gpt-5.4-mini",
                        "channel": "webchat",
                        "label": "browser",
                        "surface": "chat",
                        "metadata": {"scope": "main"},
                    },
                    "delivery_target": {
                        "interface_name": "http",
                        "address": "request:req-1",
                    },
                    "metadata": {"correlation_id": "corr-1"},
                    "queue_policy": "lane_jump_queue",
                    "priority": 9,
                    "enqueue": True,
                },
            )

            self.assertEqual(intake_response.status_code, 201)
            intake_payload = intake_response.json()
            self.assertEqual(intake_payload["status"], "queued")
            self.assertEqual(intake_payload["stage"], "queued")
            self.assertEqual(intake_payload["session_key"], "agent:assistant:main")
            self.assertEqual(
                intake_payload["lane_key"],
                "session:agent:assistant:main",
            )
            self.assertEqual(intake_payload["queue_policy"], "lane_jump_queue")
            self.assertEqual(intake_payload["agent_id"], "assistant")
            self.assertTrue(intake_payload["active_session_id"])
            self.assertEqual(intake_payload["metadata"]["session_key"], "agent:assistant:main")
            self.assertEqual(intake_payload["metadata"]["session_kind"], "main")
            self.assertEqual(intake_payload["metadata"]["correlation_id"], "corr-1")

            get_response = self.client.get(
                f"/orchestration/runs/{intake_payload['id']}",
            )
            list_response = self.client.get(
                "/orchestration/runs",
                params={"status": "queued"},
            )

            self.assertEqual(get_response.status_code, 200)
            self.assertEqual(get_response.json()["id"], intake_payload["id"])
            self.assertEqual(list_response.status_code, 200)
            self.assertEqual([item["id"] for item in list_response.json()], [intake_payload["id"]])

    def test_orchestration_worker_endpoints_drive_run_lifecycle(self) -> None:
            llm_response = self.client.post(
                "/llms",
                json={
                    "id": "openai.gpt-5.4-mini",
                    "provider": "openai",
                    "api_family": "openai_responses",
                    "model_name": "gpt-5.4-mini",
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

            intake_response = self.client.post(
                "/orchestration/runs/intake",
                json={
                    "run_id": "run-http-worker",
                    "inbound_instruction": {"source": "http", "content": "hello"},
                    "session": {
                        "agent_id": "assistant",
                        "llm_id": "openai.gpt-5.4-mini",
                        "channel": "webchat",
                    },
                    "enqueue": True,
                },
            )
            self.assertEqual(intake_response.status_code, 201)

            claim_response = self.client.post(
                "/orchestration/worker/claim-next",
                json={"worker_id": "worker-1"},
            )
            self.assertEqual(claim_response.status_code, 200)
            self.assertEqual(claim_response.json()["status"], "running")

            heartbeat_response = self.client.post(
                "/orchestration/runs/run-http-worker/heartbeat",
                json={"worker_id": "worker-1"},
            )
            self.assertEqual(heartbeat_response.status_code, 200)
            self.assertEqual(heartbeat_response.json()["status"], "running")

            advance_response = self.client.post(
                "/orchestration/runs/run-http-worker/advance",
                json={"worker_id": "worker-1", "stage": "llm", "step_increment": 1},
            )
            self.assertEqual(advance_response.status_code, 200)
            self.assertEqual(advance_response.json()["stage"], "llm")
            self.assertEqual(advance_response.json()["current_step"], 1)

            wait_response = self.client.post(
                "/orchestration/runs/run-http-worker/wait-on-tool",
                json={
                    "worker_id": "worker-1",
                    "pending_tool_run_ids": ["tool-run-1"],
                    "reason": "tool_background_wait",
                },
            )
            self.assertEqual(wait_response.status_code, 200)
            self.assertEqual(wait_response.json()["status"], "waiting")
            self.assertEqual(wait_response.json()["stage"], "waiting_on_tool")

            resume_response = self.client.post(
                "/orchestration/runs/run-http-worker/resume",
                json={"reason": "tool_results_ready"},
            )
            self.assertEqual(resume_response.status_code, 200)
            self.assertEqual(resume_response.json()["status"], "queued")
            self.assertEqual(resume_response.json()["pending_tool_run_ids"], [])

            reclaim_response = self.client.post(
                "/orchestration/worker/claim-next",
                json={"worker_id": "worker-1"},
            )
            self.assertEqual(reclaim_response.status_code, 200)
            self.assertEqual(reclaim_response.json()["id"], "run-http-worker")

            complete_response = self.client.post(
                "/orchestration/runs/run-http-worker/complete",
                json={
                    "worker_id": "worker-1",
                    "result_payload": {"output": "done"},
                },
            )
            self.assertEqual(complete_response.status_code, 200)
            self.assertEqual(complete_response.json()["status"], "completed")
            self.assertEqual(complete_response.json()["stage"], "completed")
            self.assertEqual(
                complete_response.json()["result_payload"],
                {"output": "done"},
            )

    def test_orchestration_worker_process_next_completes_minimal_llm_run(self) -> None:
            server = SampleLlmApiServer()
            previous_token = os.environ.get("OPENAI_COMPATIBLE_TOKEN")
            os.environ["OPENAI_COMPATIBLE_TOKEN"] = "sample-compat-token"
            server.start()

            try:
                llm_response = self.client.post(
                    "/llms",
                    json={
                        "id": "local-chat",
                        "provider": "openai_compatible",
                        "api_family": "openai_chat_compatible",
                        "model_name": "llama3.2",
                        "base_url": f"{server.base_url}/v1",
                        "credential_binding": "env:OPENAI_COMPATIBLE_TOKEN",
                    },
                )
                self.assertEqual(llm_response.status_code, 201)

                agent_response = self.client.post(
                    "/agents",
                    json={
                        "id": "assistant",
                        "name": "Assistant",
                        "instruction_policy": {"system_prompt": "Be helpful."},
                        "llm_routing_policy": {"default_llm_id": "local-chat"},
                    },
                )
                self.assertEqual(agent_response.status_code, 201)

                intake_response = self.client.post(
                    "/orchestration/runs/intake",
                    json={
                        "run_id": "run-http-process",
                        "inbound_instruction": {"source": "http", "content": "hello"},
                        "session": {
                            "agent_id": "assistant",
                            "llm_id": "local-chat",
                            "channel": "webchat",
                        },
                        "enqueue": True,
                    },
                )
                self.assertEqual(intake_response.status_code, 201)

                process_response = self.client.post(
                    "/orchestration/worker/process-next",
                    json={"worker_id": "worker-1"},
                )

                self.assertEqual(process_response.status_code, 200)
                payload = process_response.json()
                self.assertEqual(payload["id"], "run-http-process")
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


if __name__ == "__main__":
    unittest.main()
