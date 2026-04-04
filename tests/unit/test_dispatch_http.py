from __future__ import annotations

from tests.unit.http_test_support import *


class DispatchHttpTestCase(HttpModuleTestCase):
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


if __name__ == "__main__":
    unittest.main()
