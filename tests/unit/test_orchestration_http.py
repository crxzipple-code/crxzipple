from __future__ import annotations

from crxzipple.modules.orchestration.interfaces.http_models import (
    IntakeOrchestrationRunRequest,
    OrchestrationRunResponse,
)
from crxzipple.modules.orchestration.interfaces.dto import (
    InboundInstructionDTO,
    OrchestrationRunDTO,
)
from tests.unit.http_test_support import *


class OrchestrationHttpTestCase(HttpModuleTestCase):
    def test_orchestration_http_models_only_expose_reply_target(self) -> None:
            intake_schema = IntakeOrchestrationRunRequest.model_json_schema()
            run_schema = OrchestrationRunResponse.model_json_schema()

            self.assertIn("reply_target", intake_schema["properties"])
            self.assertNotIn("delivery_target", intake_schema["properties"])
            self.assertIn("reply_target", run_schema["properties"])
            self.assertNotIn("delivery_target", run_schema["properties"])

    def test_orchestration_run_response_serializes_naive_datetimes_as_utc(self) -> None:
            dto = OrchestrationRunDTO(
                id="run-naive-time",
                status="completed",
                stage="done",
                session_key="session-1",
                active_session_id="session-instance-1",
                agent_id="agent-1",
                lane_key="session-1",
                queue_policy="normal",
                priority=0,
                current_step=1,
                max_steps=5,
                pending_tool_run_ids=(),
                waiting_reason=None,
                inbound_instruction=InboundInstructionDTO(
                    source="http",
                    content="hello",
                    metadata={},
                ),
                reply_target=None,
                result_payload=None,
                error=None,
                worker_id=None,
                metadata={},
                created_at=datetime(2026, 4, 18, 7, 0, 0),
                updated_at=datetime(2026, 4, 18, 7, 0, 1),
                queued_at=datetime(2026, 4, 18, 7, 0, 2),
                started_at=datetime(2026, 4, 18, 7, 0, 3),
                completed_at=datetime(2026, 4, 18, 7, 0, 4),
            )

            payload = OrchestrationRunResponse.from_dto(dto).model_dump()

            self.assertEqual(payload["created_at"], "2026-04-18T07:00:00+00:00")
            self.assertEqual(payload["started_at"], "2026-04-18T07:00:03+00:00")
            self.assertEqual(payload["completed_at"], "2026-04-18T07:00:04+00:00")

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
            run_id = turn_response.json()["run"]["id"]
            _ = self.client.app.state.container.orchestration_scheduler_service.process_run_request(
                run_id=run_id,
                worker_id="http-test-scheduler",
            )
            _ = process_next_orchestration_assignment(self.client.app.state.container, worker_id="http-test-worker")

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
                    "reply_target": {
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
            self.assertEqual(
                intake_payload["reply_target"],
                {
                    "interface_name": "http",
                    "address": "request:req-1",
                    "reply_to": None,
                    "metadata": {},
                },
            )
            self.assertNotIn("delivery_target", intake_payload)
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

    def test_orchestration_executor_and_scheduler_endpoints_drive_run_lifecycle(self) -> None:
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

            claimed = assign_next_orchestration_assignment(
                self.client.app.state.container,
                worker_id="worker-1",
            )
            self.assertIsNotNone(claimed)
            assert claimed is not None
            self.assertEqual(claimed.status.value, "running")

            heartbeat_response = self.client.post(
                "/orchestration/executor/runs/run-http-worker/heartbeat-assignment",
                json={"worker_id": "worker-1"},
            )
            self.assertEqual(heartbeat_response.status_code, 200)
            self.assertEqual(heartbeat_response.json()["status"], "running")

            advance_response = self.client.post(
                "/orchestration/executor/runs/run-http-worker/advance-assignment",
                json={"worker_id": "worker-1", "stage": "llm", "step_increment": 1},
            )
            self.assertEqual(advance_response.status_code, 200)
            self.assertEqual(advance_response.json()["stage"], "llm")
            self.assertEqual(advance_response.json()["current_step"], 1)

            wait_response = self.client.post(
                "/orchestration/executor/runs/run-http-worker/wait-assignment-on-tool",
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

            reclaimed = assign_next_orchestration_assignment(
                self.client.app.state.container,
                worker_id="worker-1",
            )
            self.assertIsNotNone(reclaimed)
            assert reclaimed is not None
            self.assertEqual(reclaimed.id, "run-http-worker")

            complete_response = self.client.post(
                "/orchestration/executor/runs/run-http-worker/complete-assignment",
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

    def test_orchestration_executor_process_next_completes_minimal_llm_run(self) -> None:
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

                assigned = assign_next_orchestration_assignment(
                    self.client.app.state.container,
                    worker_id="worker-1",
                )
                self.assertIsNotNone(assigned)

                process_response = self.client.post(
                    "/orchestration/executor/process-next-assigned-assignment",
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

    def test_orchestration_executor_process_assignment_inline_targets_requested_run(self) -> None:
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

            first_intake = self.client.post(
                "/orchestration/runs/intake",
                json={
                    "run_id": "run-http-inline-first",
                    "inbound_instruction": {"source": "http", "content": "first"},
                    "session": {
                        "agent_id": "assistant",
                        "llm_id": "openai.gpt-5.4-mini",
                        "channel": "webchat",
                    },
                    "priority": 50,
                    "enqueue": True,
                },
            )
            self.assertEqual(first_intake.status_code, 201)

            second_intake = self.client.post(
                "/orchestration/runs/intake",
                json={
                    "run_id": "run-http-inline-second",
                    "inbound_instruction": {"source": "http", "content": "second"},
                    "session": {
                        "agent_id": "assistant",
                        "llm_id": "openai.gpt-5.4-mini",
                        "channel": "webchat",
                    },
                    "priority": 5,
                    "enqueue": True,
                },
            )
            self.assertEqual(second_intake.status_code, 201)

            process_response = self.client.post(
                "/orchestration/executor/runs/run-http-inline-first/process-assignment-inline",
                json={"worker_id": "worker-inline-1"},
            )
            self.assertEqual(process_response.status_code, 200)
            self.assertEqual(process_response.json()["id"], "run-http-inline-first")

            first_response = self.client.get("/orchestration/runs/run-http-inline-first")
            second_response = self.client.get("/orchestration/runs/run-http-inline-second")
            self.assertEqual(first_response.status_code, 200)
            self.assertEqual(second_response.status_code, 200)
            self.assertNotEqual(first_response.json()["status"], "queued")
            self.assertEqual(second_response.json()["status"], "queued")

    def test_orchestration_executor_admit_assignment_targets_requested_run_without_processing(self) -> None:
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

            first_intake = self.client.post(
                "/orchestration/runs/intake",
                json={
                    "run_id": "run-http-admit-first",
                    "inbound_instruction": {"source": "http", "content": "first"},
                    "session": {
                        "agent_id": "assistant",
                        "llm_id": "openai.gpt-5.4-mini",
                        "channel": "webchat",
                    },
                    "priority": 50,
                    "enqueue": True,
                },
            )
            self.assertEqual(first_intake.status_code, 201)

            second_intake = self.client.post(
                "/orchestration/runs/intake",
                json={
                    "run_id": "run-http-admit-second",
                    "inbound_instruction": {"source": "http", "content": "second"},
                    "session": {
                        "agent_id": "assistant",
                        "llm_id": "openai.gpt-5.4-mini",
                        "channel": "webchat",
                    },
                    "priority": 5,
                    "enqueue": True,
                },
            )
            self.assertEqual(second_intake.status_code, 201)

            admit_response = self.client.post(
                "/orchestration/executor/runs/run-http-admit-first/admit-assignment",
                json={"worker_id": "worker-admit-1"},
            )
            self.assertEqual(admit_response.status_code, 200)
            admitted_payload = admit_response.json()
            self.assertEqual(admitted_payload["id"], "run-http-admit-first")
            self.assertEqual(admitted_payload["status"], "running")
            self.assertEqual(admitted_payload["worker_id"], "worker-admit-1")
            self.assertEqual(admitted_payload["current_step"], 0)

            first_response = self.client.get("/orchestration/runs/run-http-admit-first")
            second_response = self.client.get("/orchestration/runs/run-http-admit-second")
            self.assertEqual(first_response.status_code, 200)
            self.assertEqual(second_response.status_code, 200)
            self.assertEqual(first_response.json()["status"], "running")
            self.assertEqual(first_response.json()["worker_id"], "worker-admit-1")
            self.assertEqual(first_response.json()["current_step"], 0)
            self.assertEqual(second_response.json()["status"], "queued")

    def test_orchestration_intake_reports_access_setup_payload_for_missing_llm_token(self) -> None:
            llm_response = self.client.post(
                "/llms",
                json={
                    "id": "missing-access-chat",
                    "provider": "openai_compatible",
                    "api_family": "openai_chat_compatible",
                    "model_name": "llama3.2",
                    "base_url": "http://127.0.0.1:1/v1",
                    "credential_binding": "env:MISSING_HTTP_LLM_TOKEN",
                },
            )
            self.assertEqual(llm_response.status_code, 201)

            agent_response = self.client.post(
                "/agents",
                json={
                    "id": "missing-access-assistant",
                    "name": "Missing Access Assistant",
                    "llm_routing_policy": {"default_llm_id": "missing-access-chat"},
                },
            )
            self.assertEqual(agent_response.status_code, 201)

            with patch.dict("os.environ", {"MISSING_HTTP_LLM_TOKEN": ""}):
                intake_response = self.client.post(
                    "/orchestration/runs/intake",
                    json={
                        "run_id": "run-http-missing-access",
                        "inbound_instruction": {"source": "http", "content": "hello"},
                        "session": {
                            "agent_id": "missing-access-assistant",
                            "llm_id": "missing-access-chat",
                            "channel": "webchat",
                        },
                        "enqueue": True,
                    },
                )

            self.assertEqual(intake_response.status_code, 201)
            assigned = assign_next_orchestration_assignment(
                self.client.app.state.container,
                worker_id="worker-missing-access",
            )
            self.assertIsNotNone(assigned)

            process_response = self.client.post(
                "/orchestration/executor/process-next-assigned-assignment",
                json={"worker_id": "worker-missing-access"},
            )

            self.assertEqual(process_response.status_code, 200)
            payload = process_response.json()
            self.assertEqual(payload["status"], "failed")
            error = payload["error"]
            self.assertEqual(error["code"], "access_not_ready")
            self.assertEqual(error["details"]["resource_type"], "llm_profile")
            access = error["details"]["access"]
            self.assertEqual(access["requirement"], "env:MISSING_HTTP_LLM_TOKEN")
            self.assertEqual(access["status"], "setup_needed")
            self.assertEqual(access["setup_flow"]["kind"], "env")


if __name__ == "__main__":
    unittest.main()
