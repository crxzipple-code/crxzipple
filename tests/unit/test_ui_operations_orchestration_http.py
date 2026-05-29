from __future__ import annotations

from crxzipple.interfaces.runtime_container import (
    AssemblyTarget,
    build_runtime_container,
)
from crxzipple.modules.events import Event
from tests.unit.http_test_support import AppKey, HttpModuleTestCase


class UiOperationsOrchestrationHttpTestCase(HttpModuleTestCase):
    def _target_container(self, target: AssemblyTarget):
        return build_runtime_container(
            self.client.app.state.container.require(AppKey.CORE_SETTINGS),
            target=target,
        )

    def _process_operations_events(self) -> None:
        observer_container = self._target_container(AssemblyTarget.OPERATIONS_OBSERVER)
        try:
            observer_container.require(
                AppKey.OPERATIONS_OBSERVER_RUNTIME_EVENT_SERVICE,
            ).process_available_events()
        finally:
            observer_container.close()

    def _materialize_operations(self, *modules: str) -> None:
        materializer = self.client.app.state.container.require(
            AppKey.OPERATIONS_PROJECTION_MATERIALIZER,
        )
        materializer.materialize_modules(modules)

    def _register_agent_and_llm(self) -> None:
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

    def test_overview_uses_owner_runtime_state(self) -> None:
        self._register_agent_and_llm()
        self.client.app.state.container.require(
            AppKey.ORCHESTRATION_EXECUTOR_CONTROL_SERVICE,
        ).heartbeat_executor(
            worker_id="worker-ui",
            max_inflight_assignments=3,
            inflight_assignment_count=1,
        )
        intake_response = self.client.post(
            "/orchestration/runs/intake",
            json={
                "run_id": "run-ui-ops",
                "inbound_instruction": {"source": "http", "content": "queue me"},
                "session": {
                    "agent_id": "assistant",
                    "llm_id": "openai.gpt-5.4-mini",
                    "channel": "webchat",
                },
                "priority": 4,
                "enqueue": True,
            },
        )
        self.assertEqual(intake_response.status_code, 201)

        self._materialize_operations("orchestration")
        response = self.client.get("/operations/orchestration/overview")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["module"], "orchestration")
        self.assertEqual(payload["title"], "Orchestration")
        self.assertIn(
            {
                "Priority": "P4",
                "Run ID": "run-ui-ops",
                "Lane Key": "session:agent:assistant:main",
                "Wait Reason": "fifo",
                "Wait Time": payload["queue"][0]["Wait Time"],
            },
            payload["queue"],
        )
        self.assertEqual(payload["executor"][0]["Worker ID"], "worker-ui")
        self.assertEqual(payload["executor"][0]["Load"], "33%")

    def test_page_uses_owner_runtime_state(self) -> None:
        self._register_agent_and_llm()
        self.client.app.state.container.require(
            AppKey.ORCHESTRATION_EXECUTOR_CONTROL_SERVICE,
        ).heartbeat_executor(
            worker_id="worker-ui-page",
            max_inflight_assignments=3,
            inflight_assignment_count=1,
        )
        intake_response = self.client.post(
            "/orchestration/runs/intake",
            json={
                "run_id": "run-ui-ops-page",
                "inbound_instruction": {"source": "http", "content": "page queue me"},
                "session": {
                    "agent_id": "assistant",
                    "llm_id": "openai.gpt-5.4-mini",
                    "channel": "webchat",
                },
                "metadata": {"trace_id": "trace-ui-ops-page"},
                "priority": 4,
                "enqueue": True,
            },
        )
        self.assertEqual(intake_response.status_code, 201)

        container = self.client.app.state.container
        self._process_operations_events()
        container.require(AppKey.EVENTS_SERVICE).publish(
            Event(
                name="orchestration.run.queued",
                kind="observe",
                payload={
                    "event_name": "orchestration.run.queued",
                    "run_id": "run-ui-ops-direct-event",
                    "status": "queued",
                    "stage": "queued",
                    "current_step": 0,
                    "source_event_name": "orchestration.run.accepted",
                },
                trace={"trace_id": "trace-ui-ops-direct-event"},
                ordering_key="run-ui-ops-direct-event",
            ),
        )
        self._process_operations_events()

        self._materialize_operations("orchestration")
        response = self.client.get("/operations/orchestration")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["module"], "orchestration")
        self.assertNotIn("sections", payload)
        self.assertEqual(payload["role"]["scope"], "orchestration")
        self.assertTrue(payload["role"]["can_operate"])
        self.assertEqual(payload["scheduler_status"]["id"], "scheduler_status")
        self.assertEqual(payload["backpressure"]["kind"], "donut")
        self.assertEqual(payload["backpressure"]["total"], 1)
        metrics = {item["id"]: item for item in payload["metrics"]}
        self.assertEqual(metrics["approval_waiting"]["value"], "0")
        self.assertEqual(metrics["approval_waiting"]["tone"], "success")
        queue_row = payload["run_queue"]["rows"][0]
        self.assertEqual(queue_row["cells"]["run_id"], "run-ui-ops-page")
        self.assertEqual(queue_row["cells"]["lane_key"], "session:agent:assistant:main")
        self.assertEqual(queue_row["cells"]["trace"], "trace-ui-ops-page")
        executor_row = payload["executor_overview"]["rows"][0]
        self.assertEqual(executor_row["cells"]["worker_id"], "worker-ui-page")
        self.assertEqual(executor_row["cells"]["load"], "33%")
        self.assertEqual(executor_row["cells"]["available_slots"], "2")
        action_by_id = {item["id"]: item for item in payload["actions"]}
        self.assertEqual(action_by_id["cancel_run"]["method"], "POST")
        self.assertEqual(
            action_by_id["cancel_run"]["audit_event"],
            "orchestration.run.cancel",
        )
        self.assertEqual(
            action_by_id["cancel_run"]["endpoint"],
            "/operations/orchestration/runs/{run_id}/cancel",
        )
        self.assertEqual(action_by_id["force_release_lane"]["risk"], "dangerous")
        self.assertFalse(action_by_id["force_release_lane"]["allowed"])
        self.assertTrue(action_by_id["force_release_lane"]["requires_confirmation"])
        self.assertTrue(action_by_id["force_release_lane"]["reason_required"])
        event_run_ids = {
            item["cells"]["run_id"] for item in payload["ops_event_log"]["rows"]
        }
        self.assertIn("run-ui-ops-page", event_run_ids)
        self.assertIn("run-ui-ops-direct-event", event_run_ids)

    def test_page_uses_ingress_signal_and_event_sources(self) -> None:
        self._register_agent_and_llm()
        intake_response = self.client.post(
            "/orchestration/runs/intake",
            json={
                "run_id": "run-ui-ingress-page",
                "inbound_instruction": {"source": "http", "content": "hold in ingress"},
                "session": {
                    "agent_id": "assistant",
                    "llm_id": "openai.gpt-5.4-mini",
                    "channel": "webchat",
                },
                "priority": 7,
                "enqueue": False,
            },
        )
        self.assertEqual(intake_response.status_code, 201)

        self.client.app.state.container.require(
            AppKey.ORCHESTRATION_SCHEDULER_MAINTENANCE_SERVICE,
        ).queue_tool_terminal_signal(tool_run_id="tool-ui-signal")
        self._process_operations_events()
        self._materialize_operations("orchestration")
        response = self.client.get("/operations/orchestration")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        metrics = {item["id"]: item for item in payload["metrics"]}
        self.assertEqual(metrics["ingress"]["value"], "1")
        self.assertEqual(metrics["ingress"]["delta"], "ingress requests")
        ingress_row = payload["ingress_queue"]["rows"][0]
        self.assertEqual(ingress_row["cells"]["run_id"], "run-ui-ingress-page")
        self.assertEqual(ingress_row["cells"]["status"], "queued")
        self.assertNotEqual(
            ingress_row["cells"]["intake_key"],
            ingress_row["cells"]["run_id"],
        )
        scheduler_items = {
            item["label"]: item["value"] for item in payload["scheduler_status"]["items"]
        }
        self.assertEqual(scheduler_items["Scheduler Signals"], "1 queued / 0 processing")
        policy_items = {
            item["label"]: item["value"] for item in payload["policy_limits"]["items"]
        }
        self.assertEqual(policy_items["Lease Timeout"], "30s")
        self.assertNotEqual(policy_items["Lane Lock TTL"], "60s")
        self.assertEqual(policy_items["Executor Max Assignments"], "4")
        self.assertEqual(policy_items["Auto Compaction"], "enabled")
        event_rows = payload["ops_event_log"]["rows"]
        self.assertTrue(event_rows)
        self.assertIn(
            "run-ui-ingress-page",
            {item["cells"]["run_id"] for item in event_rows},
        )
        self.assertTrue(
            any(item["cells"]["source"] == "Ingress" for item in event_rows),
        )
