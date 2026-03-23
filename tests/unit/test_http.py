from __future__ import annotations

from dataclasses import replace
import json
import os
from pathlib import Path
import sys
import threading
import time
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from crxzipple.core.config import (
    AgentProfileSettings,
    LlmProfileSettings,
    McpProviderSettings,
    OpenApiCredentialBinding,
    OpenApiProviderSettings,
    load_settings,
)
from crxzipple.interfaces.http.app import create_app
from tests.unit.support import (
    SampleApiServer,
    SampleLlmApiServer,
    SqliteTestHarness,
    fixture_path,
    openapi_fixture_path,
)


class _FakeStreamResponse:
    def __init__(
        self,
        *,
        status_code: int = 200,
        events: tuple[tuple[str, dict[str, object]], ...] = (),
        text: str = "",
    ) -> None:
        self.status_code = status_code
        self._events = events
        self.text = text

    def iter_lines(self, decode_unicode: bool = False):  # noqa: ANN001
        del decode_unicode
        for event_name, payload in self._events:
            yield f"event: {event_name}".encode("utf-8")
            yield f"data: {json.dumps(payload)}".encode("utf-8")
            yield b""

    def close(self) -> None:
        return None


class HttpTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.previous_openapi_provider_paths = os.environ.get(
            "APP_TOOL_OPENAPI_PROVIDER_PATHS",
        )
        os.environ["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = os.pathsep
        self.harness = SqliteTestHarness()
        self.harness.initialize_schema()
        self.client = TestClient(create_app(database_url=self.harness.database_url))

    def tearDown(self) -> None:
        self.client.close()
        self.client.app.state.container.engine.dispose()
        self.harness.close()
        if self.previous_openapi_provider_paths is None:
            os.environ.pop("APP_TOOL_OPENAPI_PROVIDER_PATHS", None)
        else:
            os.environ["APP_TOOL_OPENAPI_PROVIDER_PATHS"] = (
                self.previous_openapi_provider_paths
            )

    def test_health_endpoint(self) -> None:
        response = self.client.get("/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "ok"})

    def test_dispatch_endpoints_manage_task_lifecycle(self) -> None:
        create_response = self.client.post(
            "/dispatch/tasks",
            json={
                "task_id": "dispatch-http-1",
                "owner_kind": "orchestration_run",
                "owner_id": "run-http-1",
                "lane_key": "bulk:http",
                "metadata": {"source": "http"},
            },
        )
        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["status"], "created")

        enqueue_response = self.client.post(
            "/dispatch/tasks/dispatch-http-1/enqueue",
            json={"policy": "jump_queue", "priority": 5},
        )
        self.assertEqual(enqueue_response.status_code, 200)
        self.assertEqual(enqueue_response.json()["status"], "queued")
        self.assertEqual(enqueue_response.json()["policy"], "jump_queue")

        claim_response = self.client.post(
            "/dispatch/tasks/claim-next",
            json={
                "owner_kind": "orchestration_run",
                "worker_id": "http-worker",
                "lease_seconds": 30,
            },
        )
        self.assertEqual(claim_response.status_code, 200)
        claim_payload = claim_response.json()
        self.assertEqual(claim_payload["id"], "dispatch-http-1")
        self.assertEqual(claim_payload["status"], "claimed")
        self.assertEqual(claim_payload["claimed_by"], "http-worker")
        self.assertIsNotNone(claim_payload["heartbeat_at"])
        self.assertIsNotNone(claim_payload["lease_expires_at"])

        heartbeat_response = self.client.post(
            "/dispatch/tasks/dispatch-http-1/heartbeat",
            json={
                "worker_id": "http-worker",
                "claim_token": claim_payload["claim_token"],
                "lease_seconds": 45,
            },
        )
        self.assertEqual(heartbeat_response.status_code, 200)
        self.assertEqual(heartbeat_response.json()["status"], "claimed")

        wait_response = self.client.post(
            "/dispatch/tasks/dispatch-http-1/wait",
            json={"reason": "waiting_for_event"},
        )
        self.assertEqual(wait_response.status_code, 200)
        self.assertEqual(wait_response.json()["status"], "waiting")
        self.assertEqual(
            wait_response.json()["waiting_reason"],
            "waiting_for_event",
        )

        requeue_response = self.client.post(
            "/dispatch/tasks/dispatch-http-1/requeue",
            json={"policy": "resume_first", "reason": "event_ready"},
        )
        self.assertEqual(requeue_response.status_code, 200)
        self.assertEqual(requeue_response.json()["status"], "queued")
        self.assertEqual(requeue_response.json()["policy"], "resume_first")

        get_response = self.client.get("/dispatch/tasks/dispatch-http-1")
        list_response = self.client.get(
            "/dispatch/tasks",
            params={"owner_kind": "orchestration_run", "status": "queued"},
        )
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["id"], "dispatch-http-1")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual([item["id"] for item in list_response.json()], ["dispatch-http-1"])

        complete_response = self.client.post("/dispatch/tasks/dispatch-http-1/complete")
        self.assertEqual(complete_response.status_code, 200)
        self.assertEqual(complete_response.json()["status"], "completed")

    def test_dispatch_recover_abandoned_endpoint_filters_owner_kind(self) -> None:
        create_tool = self.client.post(
            "/dispatch/tasks",
            json={
                "task_id": "dispatch-http-tool",
                "owner_kind": "tool_run",
                "owner_id": "tool-run-http",
            },
        )
        create_orch = self.client.post(
            "/dispatch/tasks",
            json={
                "task_id": "dispatch-http-orch",
                "owner_kind": "orchestration_run",
                "owner_id": "orch-run-http",
            },
        )
        self.assertEqual(create_tool.status_code, 201)
        self.assertEqual(create_orch.status_code, 201)
        self.client.post("/dispatch/tasks/dispatch-http-tool/enqueue", json={})
        self.client.post("/dispatch/tasks/dispatch-http-orch/enqueue", json={})
        self.client.post(
            "/dispatch/tasks/claim-next",
            json={"owner_kind": "tool_run", "worker_id": "tool-worker", "lease_seconds": 5},
        )
        self.client.post(
            "/dispatch/tasks/claim-next",
            json={
                "owner_kind": "orchestration_run",
                "worker_id": "orch-worker",
                "lease_seconds": 5,
            },
        )

        with self.client.app.state.container.uow_factory() as uow:
            tool_task = uow.dispatch_tasks.get("dispatch-http-tool")
            orch_task = uow.dispatch_tasks.get("dispatch-http-orch")
            assert tool_task is not None
            assert orch_task is not None
            tool_task.lease_expires_at = tool_task.claimed_at
            orch_task.lease_expires_at = orch_task.claimed_at
            uow.dispatch_tasks.add(tool_task)
            uow.dispatch_tasks.add(orch_task)
            uow.commit()

        recover_response = self.client.post(
            "/dispatch/tasks/recover-abandoned",
            json={"owner_kind": "tool_run", "reason": "lease_expired"},
        )
        self.assertEqual(recover_response.status_code, 200)
        self.assertEqual([item["id"] for item in recover_response.json()], ["dispatch-http-tool"])

        tool_task = self.client.get("/dispatch/tasks/dispatch-http-tool").json()
        orch_task = self.client.get("/dispatch/tasks/dispatch-http-orch").json()
        self.assertEqual(tool_task["status"], "queued")
        self.assertEqual(orch_task["status"], "claimed")

    def test_session_endpoints_manage_history_and_reset_instances(self) -> None:
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

        create_response = self.client.post(
            "/sessions",
            json={
                "key": "agent:assistant:main",
                "runtime_binding": {
                    "agent_id": "assistant",
                    "llm_id": "openai.gpt-5.4-mini",
                },
                "channel": "webchat",
                "chat_type": "direct",
                "origin": {"provider": "webchat", "surface": "browser"},
                "delivery": {"channel": "webchat", "to": "user:1"},
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
                "llm_id": "openai.gpt-5.4-mini",
            },
        )
        self.assertEqual(create_payload["channel"], "webchat")
        first_active_session_id = create_payload["active_session_id"]

        get_response = self.client.get("/sessions/agent:assistant:main")
        list_response = self.client.get("/sessions")

        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["active_session_id"], first_active_session_id)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual([item["key"] for item in list_response.json()], ["agent:assistant:main"])

        first_message = self.client.post(
            "/sessions/agent:assistant:main/messages",
            json={"role": "user", "content": "hello"},
        )
        second_message = self.client.post(
            "/sessions/agent:assistant:main/messages",
            json={"role": "assistant", "content": "hi there"},
        )

        self.assertEqual(first_message.status_code, 201)
        self.assertEqual(second_message.status_code, 201)
        self.assertEqual(first_message.json()["session_id"], first_active_session_id)
        self.assertEqual(second_message.json()["session_id"], first_active_session_id)
        self.assertEqual(first_message.json()["sequence_no"], 1)
        self.assertEqual(first_message.json()["kind"], "message")
        self.assertEqual(first_message.json()["content_payload"], {"text": "hello"})
        self.assertEqual(second_message.json()["sequence_no"], 2)

        history_response = self.client.get("/sessions/agent:assistant:main/messages")
        active_history_response = self.client.get(
            "/sessions/agent:assistant:main/messages",
            params={"active_session_only": True},
        )

        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(
            [item["content"] for item in history_response.json()],
            ["hello", "hi there"],
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
                "llm_id": "openai.gpt-5.4-mini",
            },
        )
        self.assertEqual(instances_payload[0]["kind"], "main")
        self.assertEqual(instances_payload[0]["status"], "closed")
        self.assertEqual(instances_payload[0]["reset_reason"], "manual")
        self.assertEqual(instances_payload[1]["id"], reset_payload["active_session_id"])
        self.assertEqual(instances_payload[1]["status"], "active")

        active_history_after_reset = self.client.get(
            "/sessions/agent:assistant:main/messages",
            params={"active_session_only": True},
        )
        self.assertEqual(active_history_after_reset.status_code, 200)
        self.assertEqual(active_history_after_reset.json(), [])

        third_message = self.client.post(
            "/sessions/agent:assistant:main/messages",
            json={"role": "user", "content": "fresh start"},
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
            [item["content"] for item in latest_active_history.json()],
            ["fresh start"],
        )

    def test_session_message_endpoint_accepts_structured_payload_only_messages(self) -> None:
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

        create_response = self.client.post(
            "/sessions",
            json={
                "key": "agent:assistant:main",
                "runtime_binding": {
                    "agent_id": "assistant",
                    "llm_id": "openai.gpt-5.4-mini",
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
        self.assertEqual(message_payload["content"], None)
        self.assertEqual(message_payload["content_payload"]["tool"], "search")
        self.assertEqual(message_payload["source_kind"], "tool_run")
        self.assertEqual(message_payload["source_id"], "run-1")
        self.assertEqual(message_payload["visibility"], "internal")

    def test_session_create_endpoint_accepts_runtime_binding_payload(self) -> None:
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

        create_response = self.client.post(
            "/sessions",
            json={
                "key": "agent:assistant:main",
                "runtime_binding": {
                    "agent_id": "assistant",
                    "llm_id": "openai.gpt-5.4-mini",
                },
            },
        )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(
            create_response.json()["runtime_binding"],
            {
                "agent_id": "assistant",
                "llm_id": "openai.gpt-5.4-mini",
            },
        )

    def test_session_resolve_endpoint_routes_and_ensures_main_session(self) -> None:
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

        resolve_response = self.client.post(
            "/sessions/resolve",
            json={
                "agent_id": "assistant",
                "llm_id": "openai.gpt-5.4-mini",
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

        instances_response = self.client.get("/sessions/agent:assistant:main/instances")
        self.assertEqual(instances_response.status_code, 200)
        instances_payload = instances_response.json()
        self.assertEqual(len(instances_payload), 1)
        self.assertEqual(instances_payload[0]["kind"], "main")
        self.assertEqual(instances_payload[0]["status"], "active")

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

    def test_agent_profile_endpoints_register_fetch_and_list(self) -> None:
        create_response = self.client.post(
            "/agents",
            json={
                "id": "writer",
                "name": "Writer",
                "description": "Writes concise summaries.",
                "identity": {"display_name": "Writer Agent", "emoji": ":memo:"},
                "instruction_policy": {
                    "system_prompt": "Be concise.",
                    "stream_by_default": True,
                },
                "llm_routing_policy": {
                    "default_llm_id": "openai.gpt-5.4-mini",
                    "fallback_llm_ids": ["openai.gpt-5.4"],
                },
                "execution_policy": {"timeout_seconds": 90, "max_turns": 8},
                "runtime_preferences": {
                    "workspace": "/tmp/agent-writer",
                    "sandbox_mode": "sandbox",
                },
            },
        )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["id"], "writer")
        self.assertEqual(
            create_response.json()["llm_routing_policy"]["default_llm_id"],
            "openai.gpt-5.4-mini",
        )

        get_response = self.client.get("/agents/writer")
        list_response = self.client.get("/agents")

        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["identity"]["display_name"], "Writer Agent")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)
        self.assertTrue(list_response.json()[0]["instruction_policy"]["stream_by_default"])

    def test_agent_sync_profiles_endpoint_uses_configured_profiles(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            agent_profiles=(
                AgentProfileSettings(
                    id="writer",
                    name="Writer",
                    description="Default writer profile.",
                    identity={"display_name": "Writer Agent"},
                    instruction_policy={
                        "system_prompt": "Be concise.",
                        "stream_by_default": True,
                    },
                    llm_routing_policy={"default_llm_id": "openai.gpt-5.4-mini"},
                    execution_policy={"timeout_seconds": 75, "max_turns": 7},
                    runtime_preferences={"sandbox_mode": "sandbox"},
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        client = TestClient(create_app(settings=settings))
        try:
            sync_response = client.post("/agents/sync-profiles")
            self.assertEqual(sync_response.status_code, 200)
            self.assertEqual([item["id"] for item in sync_response.json()], ["writer"])
            self.assertEqual(
                sync_response.json()[0]["identity"]["display_name"],
                "Writer Agent",
            )

            get_response = client.get("/agents/writer")
            self.assertEqual(get_response.status_code, 200)
            self.assertEqual(
                get_response.json()["execution_policy"]["timeout_seconds"],
                75,
            )
        finally:
            client.close()

    def test_authorization_endpoints_list_policies_and_check(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(
                str(
                    Path(__file__).resolve().parents[2]
                    / "config"
                    / "authorization_policies"
                    / "default.yaml"
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        client = TestClient(create_app(settings=settings))
        try:
            policies_response = client.get("/authorization/policies")
            self.assertEqual(policies_response.status_code, 200)
            self.assertEqual(
                [item["id"] for item in policies_response.json()],
                ["allow_llm_invocation", "allow_safe_tool_execution"],
            )

            check_response = client.post(
                "/authorization/check",
                json={
                    "action": "tool.run",
                    "resource": {
                        "kind": "tool",
                        "id": "echo",
                        "attrs": {"mutates_state": False},
                    },
                    "context": {"attrs": {"interface": "http"}},
                },
            )
            self.assertEqual(check_response.status_code, 200)
            self.assertTrue(check_response.json()["allowed"])
        finally:
            client.close()

    def test_http_guard_returns_403_when_abac_blocks_tool_run(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(
                str(
                    Path(__file__).resolve().parents[2]
                    / "config"
                    / "authorization_policies"
                    / "default.yaml"
                ),
            ),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        client = TestClient(create_app(settings=settings))
        try:
            create_response = client.post(
                "/tools",
                json={
                    "id": "dangerous_write",
                    "name": "Dangerous Write",
                    "description": "Mutates external state.",
                    "mutates_state": True,
                },
            )
            self.assertEqual(create_response.status_code, 201)

            run_response = client.post(
                "/tools/dangerous_write/runs",
                json={"arguments": {}},
            )
            self.assertEqual(run_response.status_code, 403)
            self.assertIn("Authorization denied", run_response.json()["detail"])
        finally:
            client.close()

    def test_llm_profile_endpoints_register_fetch_and_list(self) -> None:
        create_response = self.client.post(
            "/llms",
            json={
                "id": "writer",
                "provider": "openai",
                "api_family": "openai_responses",
                "model_name": "gpt-5",
                "model_family": "reasoning",
                "capabilities": ["tool_calling"],
                "default_params": {"temperature": 0.2, "max_output_tokens": 512},
                "credential_binding": "env:OPENAI_API_KEY",
            },
        )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["id"], "writer")
        self.assertEqual(create_response.json()["api_family"], "openai_responses")

        get_response = self.client.get("/llms/writer")
        list_response = self.client.get("/llms")

        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_response.json()["model_name"], "gpt-5")
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)
        self.assertEqual(list_response.json()[0]["credential_binding"], "env:OPENAI_API_KEY")

    def test_llm_invoke_endpoint_uses_openai_compatible_adapter(self) -> None:
        server = SampleLlmApiServer()
        previous_token = os.environ.get("OPENAI_COMPATIBLE_TOKEN")
        os.environ["OPENAI_COMPATIBLE_TOKEN"] = "sample-compat-token"
        server.start()

        try:
            create_response = self.client.post(
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

            self.assertEqual(create_response.status_code, 201)

            invoke_response = self.client.post(
                "/llms/local-chat/invoke",
                json={
                    "messages": [{"role": "user", "content": "hello"}],
                    "tool_schemas": [
                        {
                            "name": "search_docs",
                            "description": "Search docs",
                            "input_schema": {
                                "type": "object",
                                "properties": {"query": {"type": "string"}},
                            },
                        },
                    ],
                },
            )

            self.assertEqual(invoke_response.status_code, 201)
            payload = invoke_response.json()
            self.assertEqual(payload["status"], "succeeded")
            self.assertEqual(payload["provider_request_id"], "chatcmpl_sample_1")
            self.assertEqual(payload["result"]["text"], "hello from sample llm")
            self.assertEqual(payload["result"]["tool_calls"][0]["name"], "search_docs")

            list_response = self.client.get("/llms/local-chat/invocations")
            self.assertEqual(list_response.status_code, 200)
            self.assertEqual(len(list_response.json()), 1)
            self.assertEqual(list_response.json()[0]["id"], payload["id"])
        finally:
            if previous_token is None:
                os.environ.pop("OPENAI_COMPATIBLE_TOKEN", None)
            else:
                os.environ["OPENAI_COMPATIBLE_TOKEN"] = previous_token
            server.close()

    def test_llm_stream_endpoint_returns_sse_events_for_codex(self) -> None:
        create_response = self.client.post(
            "/llms",
            json={
                "id": "codex-profile",
                "provider": "openai_codex",
                "api_family": "openai_codex_responses",
                "model_name": "gpt-5-codex",
                "model_family": "codex",
                "credential_binding": "codex-inline-token",
            },
        )

        self.assertEqual(create_response.status_code, 201)

        with patch(
            "crxzipple.modules.llm.infrastructure.adapters.openai_codex_responses.requests.post",
            return_value=_FakeStreamResponse(
                events=(
                    (
                        "response.output_text.delta",
                        {
                            "type": "response.output_text.delta",
                            "delta": "codex-",
                        },
                    ),
                    (
                        "response.completed",
                        {
                            "type": "response.completed",
                            "response": {
                                "id": "resp_http_codex_1",
                                "status": "completed",
                                "model": "gpt-5.1-codex",
                                "output": [
                                    {
                                        "type": "message",
                                        "content": [
                                            {
                                                "type": "output_text",
                                                "text": "codex-http-ok",
                                            },
                                        ],
                                    },
                                ],
                                "usage": {
                                    "input_tokens": 5,
                                    "output_tokens": 3,
                                    "total_tokens": 8,
                                },
                            },
                        },
                    ),
                ),
            ),
        ):
            with self.client.stream(
                "POST",
                "/llms/codex-profile/stream",
                json={
                    "messages": [
                        {"role": "system", "content": "You are a concise coding assistant."},
                        {"role": "user", "content": "Reply with codex-http-ok."},
                    ],
                },
            ) as response:
                body = response.read().decode("utf-8")
                content_type = response.headers["content-type"]
                status_code = response.status_code

        self.assertEqual(status_code, 200)
        self.assertIn("text/event-stream", content_type)
        self.assertIn("event: invocation_started", body)
        self.assertIn("event: text_delta", body)
        self.assertIn("event: completed", body)
        self.assertIn("codex-http-ok", body)

    def test_llm_sync_profiles_endpoint_loads_configured_profiles(self) -> None:
        harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            database_url=harness.database_url,
            llm_profiles=(
                LlmProfileSettings(
                    id="openai.gpt-5.4",
                    provider="openai",
                    api_family="openai_responses",
                    model_name="gpt-5.4",
                    model_family="reasoning",
                    capabilities=("tool_calling", "structured_output"),
                    default_params={"reasoning_effort": "medium"},
                    credential_binding="env:OPENAI_API_KEY",
                    timeout_seconds=120,
                ),
            ),
        )

        harness.initialize_schema(settings=settings)
        client = TestClient(
            create_app(
                settings=settings,
                database_url=harness.database_url,
            ),
        )

        try:
            sync_response = client.post("/llms/sync-profiles")
            self.assertEqual(sync_response.status_code, 200)
            sync_payload = sync_response.json()
            self.assertEqual([item["id"] for item in sync_payload], ["openai.gpt-5.4"])
            self.assertEqual(
                sync_payload[0]["default_params"]["reasoning_effort"],
                "medium",
            )

            list_response = client.get("/llms")
            self.assertEqual(list_response.status_code, 200)
            self.assertEqual(
                [item["id"] for item in list_response.json()],
                ["openai.gpt-5.4"],
            )
        finally:
            client.close()
            client.app.state.container.engine.dispose()
            harness.close()

    def test_tool_endpoints_register_and_list(self) -> None:
        create_response = self.client.post(
            "/tools",
            json={
                "id": "search",
                "name": "Search",
                "description": "Query external knowledge",
            },
        )

        self.assertEqual(create_response.status_code, 201)
        self.assertEqual(create_response.json()["id"], "search")

        list_response = self.client.get("/tools")

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)
        self.assertEqual(list_response.json()[0]["name"], "Search")

    def test_tool_runtime_endpoints_discover_execute_and_fetch_runs(self) -> None:
        discover_response = self.client.post("/tools/discover-local")

        self.assertEqual(discover_response.status_code, 200)
        self.assertEqual(discover_response.json()[0]["id"], "echo")

        execute_response = self.client.post(
            "/tools/echo/runs",
            json={"arguments": {"message": "from http"}},
        )

        self.assertEqual(execute_response.status_code, 201)
        run_payload = execute_response.json()
        self.assertEqual(run_payload["tool_id"], "echo")
        self.assertEqual(run_payload["status"], "succeeded")
        self.assertEqual(run_payload["output_payload"]["message"], "from http")

        list_runs_response = self.client.get("/tools/echo/runs")

        self.assertEqual(list_runs_response.status_code, 200)
        list_payload = list_runs_response.json()
        self.assertEqual(len(list_payload), 1)
        self.assertEqual(list_payload[0]["id"], run_payload["id"])

        get_run_response = self.client.get(f"/tools/runs/{run_payload['id']}")

        self.assertEqual(get_run_response.status_code, 200)
        self.assertEqual(get_run_response.json()["id"], run_payload["id"])

    def test_tool_provider_endpoints_list_and_discover_tools(self) -> None:
        providers_response = self.client.get("/tools/providers")

        self.assertEqual(providers_response.status_code, 200)
        providers_payload = providers_response.json()
        self.assertEqual(len(providers_payload), 1)
        self.assertEqual(providers_payload[0]["name"], "local_builtin")

        discover_response = self.client.post(
            "/tools/discover",
            params={"provider": "local_builtin"},
        )

        self.assertEqual(discover_response.status_code, 200)
        discover_payload = discover_response.json()
        self.assertEqual([item["id"] for item in discover_payload], ["echo"])

    def test_openapi_provider_endpoints_discover_and_execute_remote_tools(self) -> None:
        server = SampleApiServer()
        server.start()
        harness = SqliteTestHarness()
        previous_api_key = os.environ.get("SAMPLE_API_KEY")
        previous_bearer_token = os.environ.get("SAMPLE_BEARER_TOKEN")
        os.environ["SAMPLE_API_KEY"] = "sample-api-key"
        os.environ["SAMPLE_BEARER_TOKEN"] = "sample-bearer-token"
        settings = replace(
            load_settings(),
            database_url=harness.database_url,
            tool_openapi_providers=(
                OpenApiProviderSettings(
                    name="sample_api",
                    spec_location=openapi_fixture_path("sample_openapi.json"),
                    base_url=server.base_url,
                    description="Sample OpenAPI provider",
                    timeout_seconds=5,
                    credential_bindings=(
                        OpenApiCredentialBinding(
                            scheme_name="ApiKeyQuery",
                            source="env:SAMPLE_API_KEY",
                        ),
                        OpenApiCredentialBinding(
                            scheme_name="BearerAuth",
                            source="env:SAMPLE_BEARER_TOKEN",
                        ),
                    ),
                ),
            ),
        )

        harness.initialize_schema(settings=settings)
        client = TestClient(
            create_app(
                settings=settings,
                database_url=harness.database_url,
            ),
        )

        try:
            providers_response = client.get("/tools/providers")
            self.assertEqual(providers_response.status_code, 200)
            self.assertEqual(
                [item["name"] for item in providers_response.json()],
                ["local_builtin", "sample_api"],
            )

            discover_response = client.post(
                "/tools/discover",
                params={"provider": "sample_api"},
            )
            self.assertEqual(discover_response.status_code, 200)
            self.assertEqual(
                [item["id"] for item in discover_response.json()],
                ["sample_api.echo_message", "sample_api.search_docs"],
            )

            echo_response = client.post(
                "/tools/sample_api.echo_message/runs",
                json={
                    "arguments": {"message": "http", "uppercase": True},
                    "environment": "remote",
                },
            )
            self.assertEqual(echo_response.status_code, 201)
            self.assertEqual(
                echo_response.json()["output_payload"]["message"],
                "HTTP",
            )
            self.assertIn(
                "api_key=sample-api-key",
                echo_response.json()["result"]["metadata"]["request"]["url"],
            )

            execute_response = client.post(
                "/tools/sample_api.search_docs/runs",
                json={
                    "arguments": {"body": {"query": "tooling", "limit": 3}},
                    "environment": "remote",
                },
            )
            self.assertEqual(execute_response.status_code, 201)
            self.assertEqual(
                execute_response.json()["output_payload"]["query"],
                "tooling",
            )
        finally:
            if previous_api_key is None:
                os.environ.pop("SAMPLE_API_KEY", None)
            else:
                os.environ["SAMPLE_API_KEY"] = previous_api_key
            if previous_bearer_token is None:
                os.environ.pop("SAMPLE_BEARER_TOKEN", None)
            else:
                os.environ["SAMPLE_BEARER_TOKEN"] = previous_bearer_token
            client.close()
            client.app.state.container.engine.dispose()
            harness.close()
            server.close()

    def test_mcp_provider_endpoints_discover_and_execute_remote_tools(self) -> None:
        harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            database_url=harness.database_url,
            tool_mcp_providers=(
                McpProviderSettings(
                    name="sample_mcp",
                    command=(sys.executable, fixture_path("mcp_sample_server.py")),
                    description="Sample MCP provider",
                    timeout_seconds=5,
                ),
            ),
        )

        harness.initialize_schema(settings=settings)
        client = TestClient(
            create_app(
                settings=settings,
                database_url=harness.database_url,
            ),
        )

        try:
            providers_response = client.get("/tools/providers")
            self.assertEqual(providers_response.status_code, 200)
            self.assertEqual(
                [item["name"] for item in providers_response.json()],
                ["local_builtin", "sample_mcp"],
            )

            discover_response = client.post(
                "/tools/discover",
                params={"provider": "sample_mcp"},
            )
            self.assertEqual(discover_response.status_code, 200)
            self.assertEqual(
                [item["id"] for item in discover_response.json()],
                ["sample_mcp.echo", "sample_mcp.sum"],
            )

            execute_response = client.post(
                "/tools/sample_mcp.sum/runs",
                json={
                    "arguments": {"left": 6, "right": 4},
                    "environment": "remote",
                },
            )
            self.assertEqual(execute_response.status_code, 201)
            self.assertEqual(
                execute_response.json()["output_payload"]["content"]["total"],
                10,
            )
        finally:
            client.close()
            client.app.state.container.engine.dispose()
            harness.close()

    def test_filesystem_local_provider_endpoints_discover_and_execute_tools(self) -> None:
        harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            database_url=harness.database_url,
            tool_local_paths=(fixture_path("local_tools"),),
        )

        harness.initialize_schema(settings=settings)
        client = TestClient(
            create_app(
                settings=settings,
                database_url=harness.database_url,
            ),
        )

        try:
            providers_response = client.get("/tools/providers")
            self.assertEqual(providers_response.status_code, 200)
            self.assertEqual(
                [item["name"] for item in providers_response.json()],
                ["local_builtin", "local_filesystem"],
            )

            discover_response = client.post(
                "/tools/discover",
                params={"provider": "local_filesystem"},
            )
            self.assertEqual(discover_response.status_code, 200)
            self.assertEqual(
                [item["id"] for item in discover_response.json()],
                ["greeter"],
            )

            execute_response = client.post(
                "/tools/greeter/runs",
                json={
                    "arguments": {"name": "http"},
                    "strategy": "process",
                },
            )
            self.assertEqual(execute_response.status_code, 201)
            self.assertEqual(
                execute_response.json()["output_payload"]["message"],
                "hello http",
            )
            self.assertEqual(
                execute_response.json()["result"]["metadata"]["environment"],
                "local",
            )
        finally:
            client.close()
            client.app.state.container.engine.dispose()
            harness.close()

    def test_tool_runtime_endpoint_executes_thread_strategy(self) -> None:
        discover_response = self.client.post("/tools/discover-local")
        self.assertEqual(discover_response.status_code, 200)

        execute_response = self.client.post(
            "/tools/echo/runs",
            json={
                "arguments": {"message": "thread http"},
                "strategy": "thread",
            },
        )

        self.assertEqual(execute_response.status_code, 201)
        run_payload = execute_response.json()
        self.assertEqual(run_payload["status"], "succeeded")
        self.assertEqual(run_payload["output_payload"]["message"], "thread http")
        self.assertEqual(run_payload["result"]["metadata"]["process_id"], os.getpid())
        self.assertNotEqual(
            run_payload["result"]["metadata"]["thread_ident"],
            threading.get_ident(),
        )

    def test_tool_background_runtime_endpoint_eventually_succeeds(self) -> None:
        discover_response = self.client.post("/tools/discover-local")

        self.assertEqual(discover_response.status_code, 200)

        execute_response = self.client.post(
            "/tools/echo/runs",
            json={
                "arguments": {"message": "background http"},
                "mode": "background",
            },
        )

        self.assertEqual(execute_response.status_code, 201)
        run_payload = execute_response.json()
        self.assertEqual(run_payload["status"], "queued")

        deadline = time.monotonic() + 5
        fetched = None
        while time.monotonic() < deadline:
            worker_response = self.client.app.state.container.tool_service.process_next_queued_run(
                worker_id="http-test-worker",
            )
            get_run_response = self.client.get(f"/tools/runs/{run_payload['id']}")
            self.assertEqual(get_run_response.status_code, 200)
            fetched = get_run_response.json()
            if fetched["status"] == "succeeded" or worker_response is not None:
                if fetched["status"] == "succeeded":
                    break
            if fetched["status"] == "succeeded":
                break
            time.sleep(0.05)

        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["status"], "succeeded")
        self.assertEqual(fetched["output_payload"]["message"], "background http")
        self.assertEqual(fetched["result"]["metadata"]["environment"], "local")
        self.assertEqual(fetched["attempt_count"], 1)
        self.assertEqual(fetched["worker_id"], "http-test-worker")

    def test_tool_background_thread_runtime_endpoint_eventually_succeeds(self) -> None:
        discover_response = self.client.post("/tools/discover-local")
        self.assertEqual(discover_response.status_code, 200)

        execute_response = self.client.post(
            "/tools/echo/runs",
            json={
                "arguments": {"message": "background thread http"},
                "mode": "background",
                "strategy": "thread",
            },
        )

        self.assertEqual(execute_response.status_code, 201)
        run_payload = execute_response.json()
        self.assertEqual(run_payload["status"], "queued")
        self.assertEqual(run_payload["target"]["strategy"], "thread")

        deadline = time.monotonic() + 5
        fetched = None
        while time.monotonic() < deadline:
            self.client.app.state.container.tool_service.process_next_queued_run(
                worker_id="http-thread-worker",
            )
            get_run_response = self.client.get(f"/tools/runs/{run_payload['id']}")
            self.assertEqual(get_run_response.status_code, 200)
            fetched = get_run_response.json()
            if fetched["status"] == "succeeded":
                break
            time.sleep(0.05)

        self.assertIsNotNone(fetched)
        self.assertEqual(fetched["status"], "succeeded")
        self.assertEqual(
            fetched["output_payload"]["message"],
            "background thread http",
        )
        self.assertEqual(fetched["target"]["strategy"], "thread")
        self.assertEqual(fetched["worker_id"], "http-thread-worker")
        self.assertEqual(fetched["result"]["metadata"]["process_id"], os.getpid())
        self.assertNotEqual(
            fetched["result"]["metadata"]["thread_ident"],
            threading.get_ident(),
        )

    def test_tool_run_can_be_cancelled_via_http(self) -> None:
        discover_response = self.client.post("/tools/discover-local")
        self.assertEqual(discover_response.status_code, 200)

        execute_response = self.client.post(
            "/tools/echo/runs",
            json={
                "arguments": {"message": "cancel http"},
                "mode": "background",
            },
        )
        self.assertEqual(execute_response.status_code, 201)
        run_payload = execute_response.json()

        cancel_response = self.client.post(f"/tools/runs/{run_payload['id']}/cancel")
        self.assertEqual(cancel_response.status_code, 200)
        cancel_payload = cancel_response.json()
        self.assertEqual(cancel_payload["status"], "cancelled")
        self.assertIsNotNone(cancel_payload["cancel_requested_at"])

    def test_tool_runtime_endpoint_executes_sandbox_adapter(self) -> None:
        register_response = self.client.post(
            "/tools",
            json={
                "id": "sandbox_echo",
                "name": "Sandbox Echo",
                "description": "Executes through the sandbox adapter",
                "supported_environments": ["sandbox"],
                "runtime_key": "sandbox.echo",
            },
        )

        self.assertEqual(register_response.status_code, 201)

        execute_response = self.client.post(
            "/tools/sandbox_echo/runs",
            json={
                "arguments": {"message": "sandbox http"},
                "environment": "sandbox",
            },
        )

        self.assertEqual(execute_response.status_code, 201)
        run_payload = execute_response.json()
        self.assertEqual(run_payload["status"], "succeeded")
        self.assertEqual(run_payload["output_payload"]["message"], "sandbox http")
        self.assertEqual(run_payload["result"]["metadata"]["environment"], "sandbox")
        self.assertTrue(run_payload["result"]["metadata"]["sandboxed"])
        self.assertTrue(
            Path(run_payload["result"]["metadata"]["working_directory"]).name.startswith(
                "tool-sandbox-",
            ),
        )


if __name__ == "__main__":
    unittest.main()
