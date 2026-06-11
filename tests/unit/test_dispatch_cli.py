from __future__ import annotations

from crxzipple.interfaces.runtime_container import AppKey
from tests.unit.cli_test_support import (
    CliModuleTestCase,
    CreateDispatchTaskInput,
    EnqueueDispatchTaskInput,
    app,
    json,
    unittest,
)


class DispatchCliTestCase(CliModuleTestCase):
    def test_dispatch_cli_manages_task_lifecycle(self) -> None:
            create_result = self.runner.invoke(
                app,
                [
                    "dispatch",
                    "create",
                    "orchestration_step",
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
                    "orchestration_step",
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
                    "orchestration_step",
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
            container = self.harness.build_runtime_container()
            dispatch_service = container.require(AppKey.DISPATCH_SERVICE)
            uow_factory = container.require(AppKey.UNIT_OF_WORK_FACTORY)
            first = dispatch_service.create_task(
                CreateDispatchTaskInput(
                    task_id="dispatch-cli-tool",
                    owner_kind="tool_run",
                    owner_id="tool-run-cli",
                ),
            )
            second = dispatch_service.create_task(
                CreateDispatchTaskInput(
                    task_id="dispatch-cli-orch",
                    owner_kind="orchestration_step",
                    owner_id="orch-run-cli",
                ),
            )
            dispatch_service.enqueue_task(EnqueueDispatchTaskInput(task_id=first.id))
            dispatch_service.enqueue_task(EnqueueDispatchTaskInput(task_id=second.id))
            dispatch_service.claim_next_queued_task(
                owner_kind="tool_run",
                worker_id="tool-worker",
                lease_seconds=5,
            )
            dispatch_service.claim_next_queued_task(
                owner_kind="orchestration_step",
                worker_id="orch-worker",
                lease_seconds=5,
            )
            with uow_factory() as uow:
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


if __name__ == "__main__":
    unittest.main()
