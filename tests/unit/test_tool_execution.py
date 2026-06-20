from __future__ import annotations

import inspect
from unittest.mock import patch

import crxzipple.modules.tool as tool_module
import crxzipple.modules.tool.application as tool_application_module
from crxzipple.modules.tool.domain import (
    Tool,
    ToolExecutionNotAllowedError,
    ToolExecutionTarget,
    ToolRun,
    ToolRunResult,
    ToolValidationError,
)
from crxzipple.modules.tool.infrastructure import RemoteAsyncToolExecutor
from crxzipple.shared.runtime_metrics import RuntimeMetricsRegistry
from crxzipple.shared.domain.events import Event

from tests.unit.tool_test_support import *  # noqa: F403
from tests.unit.tool_runtime_test_support import process_next_background_tool_run


class ToolExecutionTestCase(ToolTestCaseBase):
    def test_tool_service_surface_prefers_assignment_runtime_over_queue_execution_helpers(
        self,
    ) -> None:
        self.assertFalse(hasattr(self.tool_service, "assign_next_available"))
        self.assertFalse(hasattr(self.tool_service, "process_next_assigned_run"))
        self.assertFalse(hasattr(self.tool_service, "register_worker"))
        self.assertFalse(hasattr(self.tool_service, "heartbeat_run"))
        self.assertFalse(hasattr(self.tool_service, "recover_abandoned_runs"))
        self.assertFalse(hasattr(self.tool_service, "handle_recovered_dispatch_task"))
        self.assertFalse(hasattr(self.tool_service, "_create_runs"))
        self.assertFalse(hasattr(self.tool_service, "_complete_run_results"))
        self.assertFalse(hasattr(self.tool_service, "claim_next_queued_run"))
        self.assertFalse(hasattr(self.tool_service, "process_next_queued_run"))
        self.assertFalse(hasattr(self.tool_service, "execute_background_run"))
        self.assertTrue(hasattr(self.tool_scheduler_service, "assign_next_available"))
        self.assertFalse(hasattr(self.tool_scheduler_service, "claim_next_queued_run"))
        self.assertTrue(hasattr(tool_application_module, "ToolSchedulerRuntimePort"))
        self.assertTrue(hasattr(tool_application_module, "ToolWorkerRuntimePort"))
        self.assertFalse(hasattr(tool_application_module, "ToolBackgroundSchedulerService"))
        self.assertFalse(hasattr(tool_application_module, "ToolWorkerService"))
        self.assertTrue(hasattr(tool_module, "ToolSchedulerRuntimePort"))
        self.assertTrue(hasattr(tool_module, "ToolWorkerRuntimePort"))
        self.assertFalse(hasattr(tool_module, "ToolBackgroundSchedulerService"))
        self.assertFalse(hasattr(tool_module, "ToolWorkerService"))
        self.assertFalse(hasattr(self.tool_service, "scheduler_service"))
        parameters = tuple(inspect.signature(self.tool_service.__class__).parameters)
        self.assertEqual(
            parameters,
            (
                "catalog_service",
                "worker_service",
                "submission_service",
                "runtime_pool_service",
                "surface_query_service",
            ),
        )

    def test_remote_runtime_limits_concurrency_by_provider_key(self) -> None:
        registry = ToolRuntimeRegistry()
        metrics = RuntimeMetricsRegistry()
        executor = RemoteAsyncToolExecutor(registry, metrics=metrics)
        active_count = 0
        max_active_count = 0

        async def slow_handler(arguments: dict[str, object]) -> ToolRunResult:
            nonlocal active_count, max_active_count
            active_count += 1
            max_active_count = max(max_active_count, active_count)
            await asyncio.sleep(0.02)
            active_count -= 1
            return ToolRunResult.text(str(arguments["name"]))

        registry.register(
            "remote.slow_one",
            slow_handler,
            concurrency_key="provider:slow",
            max_concurrency=1,
        )
        registry.register(
            "remote.slow_two",
            slow_handler,
            concurrency_key="provider:slow",
            max_concurrency=1,
        )
        tool_one = Tool(
            id="slow_one",
            name="Slow One",
            description="Slow remote tool one.",
            runtime_key="remote.slow_one",
        )
        tool_two = Tool(
            id="slow_two",
            name="Slow Two",
            description="Slow remote tool two.",
            runtime_key="remote.slow_two",
        )

        async def run_tools() -> None:
            await asyncio.gather(
                executor.execute_async(tool_one, {"name": "one"}),
                executor.execute_async(tool_two, {"name": "two"}),
            )

        asyncio.run(run_tools())

        self.assertEqual(max_active_count, 1)
        snapshot = metrics.snapshot(prefixes=("tool.remote_provider_limiter.",))
        self.assertIn(
            {
                "name": "tool.remote_provider_limiter.active",
                "labels": {"provider_key": "provider:slow"},
                "value": 0.0,
            },
            snapshot["gauges"],
        )
        wait_timing = next(
            item
            for item in snapshot["timings"]
            if item["name"] == "tool.remote_provider_limiter.wait_seconds"
        )
        self.assertEqual(wait_timing["labels"], {"provider_key": "provider:slow"})
        self.assertEqual(wait_timing["count"], 2)

    def test_tool_run_result_requires_non_empty_content_blocks(self) -> None:
        with self.assertRaisesRegex(
            ToolValidationError,
            "include at least one content block",
        ):
            ToolRunResult(content=[])

    def test_tool_run_result_rejects_non_block_content_shapes(self) -> None:
        with self.assertRaisesRegex(
            ToolValidationError,
            "non-empty content block sequence",
        ):
            ToolRunResult(content="hello")

    def test_tool_run_result_text_does_not_duplicate_text_into_details(self) -> None:
        result = ToolRunResult.text("Hello world.")

        self.assertIsNone(result.details)
        self.assertEqual(
            result.blocks,
            ({"type": "text", "text": "Hello world."},),
        )

    def test_tool_run_result_serializes_standard_content_blocks(self) -> None:
        result = ToolRunResult(
            content=[
                {"type": "text", "text": "Browser screenshot captured."},
                {"type": "image", "data": "aGVsbG8=", "mime_type": "image/png"},
            ],
            details={"ok": True},
            metadata={"tool": "browser"},
        )

        payload = result.to_payload()
        restored = ToolRunResult.from_payload(payload)

        self.assertEqual(restored.details, {"ok": True})
        self.assertEqual(
            restored.blocks,
            (
                {"type": "text", "text": "Browser screenshot captured."},
                {"type": "image", "data": "aGVsbG8=", "mime_type": "image/png"},
            ),
        )
        self.assertEqual(restored.metadata, {"tool": "browser"})

    def test_tool_run_result_rejects_legacy_unmarked_payloads(self) -> None:
        with self.assertRaisesRegex(
            ToolValidationError,
            "standardized serialized format",
        ):
            ToolRunResult.from_payload({"message": "legacy"})

    def test_tool_run_empty_persisted_error_payload_uses_fallback_message(self) -> None:
        tool_run = ToolRun(
            id="tool-run-empty-error",
            tool_id="empty_error_tool",
            target=ToolExecutionTarget(
                mode=ToolMode.INLINE,
                strategy=ToolExecutionStrategy.ASYNC,
                environment=ToolEnvironment.LOCAL,
            ),
            status=ToolRunStatus.FAILED,
            error_payload="",
        )

        self.assertIsNotNone(tool_run.error)
        assert tool_run.error is not None
        self.assertEqual(
            tool_run.error.message,
            "Tool run failed without an error message.",
        )

    def test_empty_exception_message_fails_tool_with_readable_error(self) -> None:
        tool = self.seed_tool(
            tool_id="empty_exception_tool",
            name="Empty Exception Tool",
            description="Raises an exception with no message.",
            runtime_key="empty_exception_tool",
        )

        async def empty_exception_tool(_arguments: dict[str, object]) -> ToolRunResult:
            raise RuntimeError()

        self.local_runtime_registry.register(tool, empty_exception_tool)

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="empty_exception_tool",
                    arguments={},
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.FAILED)
        self.assertIsNotNone(tool_run.error)
        assert tool_run.error is not None
        self.assertEqual(
            tool_run.error.message,
            "RuntimeError raised without an error message.",
        )

    def test_execute_externalizes_inline_tool_attachments_to_artifact_refs(self) -> None:

        tool = self.seed_tool(
            tool_id="inline_image_tool",
            name="Inline Image Tool",
            description="Returns an inline image block.",
            runtime_key="inline_image_tool",
        )

        async def inline_image_tool(_arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.structured(
                content=[
                    {"type": "text", "text": "Generated image."},
                    {
                        "type": "image",
                        "data": "ZmFrZS1wbmc=",
                        "mime_type": "image/png",
                        "name": "generated.png",
                    },
                ],
                details={"ok": True},
            )

        self.local_runtime_registry.register(tool, inline_image_tool)

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="inline_image_tool",
                    arguments={},
                ),
            ),
        )

        assert tool_run.result is not None
        self.assertEqual(tool_run.result.blocks[0], {"type": "text", "text": "Generated image."})
        attachment_block = tool_run.result.blocks[1]
        self.assertEqual(attachment_block["type"], "image_ref")
        artifact = self.artifact_service.get_artifact(
            attachment_block["artifact_id"],
        )
        self.assertEqual(artifact.mime_type, "image/png")
        self.assertEqual(artifact.name, "generated.png")

    def test_execute_externalizes_large_text_result_to_artifact_ref_metadata(self) -> None:
        tool = self.seed_tool(
            tool_id="large_text_tool",
            name="Large Text Tool",
            description="Returns a large text payload.",
            runtime_key="large_text_tool",
        )
        large_text = "header\n" + ("x" * 24_000)

        async def large_text_tool(_arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.text(large_text)

        self.local_runtime_registry.register(tool, large_text_tool)

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="large_text_tool",
                    arguments={},
                    call_id="call-large-text",
                    tool_surface_id="tool_surface:large-text",
                ),
            ),
        )

        self.assertEqual(tool_run.call_id, "call-large-text")
        self.assertEqual(tool_run.tool_surface_id, "tool_surface:large-text")
        assert tool_run.result is not None
        result_text = tool_run.result.blocks[0]["text"]
        self.assertIn("[large tool result externalized]", result_text)
        self.assertLess(len(result_text), len(large_text))
        artifact_ids = tool_run.result.metadata.get("artifact_ids")
        self.assertIsInstance(artifact_ids, list)
        assert isinstance(artifact_ids, list)
        self.assertEqual(tool_run.result.metadata.get("large_text_artifact_ids"), artifact_ids)
        envelope = tool_run.result.metadata.get("tool_result_envelope")
        self.assertIsInstance(envelope, dict)
        assert isinstance(envelope, dict)
        self.assertEqual(envelope["status"], "ok")
        self.assertTrue(envelope["truncated"])
        self.assertEqual(envelope["evidence_refs"], artifact_ids)
        self.assertEqual(
            [ref["artifact_id"] for ref in envelope["artifact_refs"]],
            artifact_ids,
        )
        self.assertEqual(envelope["omitted_count"], 1)
        self.assertGreater(envelope["omitted_chars"], 0)
        self.assertEqual(
            envelope["key_facts"]["externalized_text_block_count"],
            1,
        )
        self.assertEqual(
            envelope["provider_replay_payload"]["artifact_refs"],
            artifact_ids,
        )
        self.assertEqual(envelope["user_summary_payload"]["artifact_count"], 1)
        self.assertEqual(
            envelope["trace_payload"]["externalized_text_artifacts"][0]["artifact_id"],
            artifact_ids[0],
        )
        self.assertEqual(envelope["read_handles"][0]["kind"], "artifact")
        artifact = self.artifact_service.get_artifact(str(artifact_ids[0]))
        self.assertEqual(artifact.mime_type, "text/plain")
        self.assertEqual(artifact.metadata["source"], "tool.large_text_result")
        resolved = self.artifact_service.resolve_variant(artifact.id)
        self.assertEqual(resolved.path.read_text(), large_text)
        self.assertIsNotNone(tool_run.result_envelope_payload)
        assert tool_run.result_envelope_payload is not None
        self.assertEqual(
            tool_run.result_envelope_payload["provider_replay_payload"]["artifact_refs"],
            artifact_ids,
        )
        with self.uow_factory() as uow:
            persisted_large = uow.tool_runs.get(tool_run.id)
        self.assertIsNotNone(persisted_large)
        assert persisted_large is not None
        self.assertEqual(persisted_large.call_id, "call-large-text")
        self.assertEqual(persisted_large.tool_surface_id, "tool_surface:large-text")
        self.assertEqual(
            persisted_large.result_envelope_payload["artifact_refs"][0]["artifact_id"],
            artifact_ids[0],
        )

    def test_execute_fails_when_tool_result_details_exceed_budget(self) -> None:
        self.tool_service.details_max_chars = 128

        tool = self.seed_tool(
            tool_id="oversized_details_tool",
            name="Oversized Details Tool",
            description="Returns oversized details payload.",
            runtime_key="oversized_details_tool",
        )

        async def oversized_details_tool(_arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.structured(
                content=[{"type": "text", "text": "Generated output."}],
                details={"payload": "x" * 512},
            )

        self.local_runtime_registry.register(tool, oversized_details_tool)

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="oversized_details_tool",
                    arguments={},
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.FAILED)
        self.assertIsNone(tool_run.result)
        self.assertIsNotNone(tool_run.error)
        assert tool_run.error is not None
        self.assertIn("details exceed the allowed size budget", tool_run.error.message)

    def test_executes_local_inline_async_tool_and_persists_run(self) -> None:

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "hello"},
                    call_id="call-echo",
                    tool_surface_id="tool_surface:echo",
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(tool_run.call_id, "call-echo")
        self.assertEqual(tool_run.tool_surface_id, "tool_surface:echo")
        self.assertEqual(tool_run.output_payload["message"], "hello")
        self.assertIsNotNone(tool_run.started_at)
        self.assertIsNotNone(tool_run.completed_at)
        self.assertEqual(tool_run.function_id, "echo")
        self.assertEqual(tool_run.source_id, "bundled.local_package.debug")
        self.assertIsNotNone(tool_run.function_revision)
        self.assertIsNotNone(tool_run.source_revision)
        self.assertIsNotNone(tool_run.schema_hash)

        with self.uow_factory() as uow:
            persisted = uow.tool_runs.get(tool_run.id)

        self.assertIsNotNone(persisted)
        assert persisted is not None
        self.assertEqual(persisted.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(persisted.function_id, "echo")
        self.assertEqual(persisted.call_id, "call-echo")
        self.assertEqual(persisted.tool_surface_id, "tool_surface:echo")
        self.assertEqual(persisted.source_id, "bundled.local_package.debug")
        self.assertIsNotNone(persisted.schema_hash)
        self.assertEqual(persisted.output_payload["received"]["message"], "hello")

        event_names = [
            event.event_name
            for event in self.published_event_bus_events()
            if isinstance(event, Event) and bool(event.name)
        ]
        self.assertIn("tool.run.created", event_names)
        self.assertIn("tool.run.started", event_names)
        self.assertIn("tool.run.succeeded", event_names)

    def test_execution_gate_blocks_disabled_tool_source(self) -> None:
        source_commands = self.container.require(AppKey.TOOL_SOURCE_COMMAND_SERVICE)
        source_commands.disable_source("bundled.local_package.debug")

        with self.assertRaisesRegex(
            ToolExecutionNotAllowedError,
            "source 'bundled.local_package.debug' is disabled",
        ):
            asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="echo",
                        arguments={"message": "blocked"},
                    ),
                ),
            )

    def test_executes_local_tool_with_generic_execution_context_without_persisting_it_in_input_payload(self) -> None:

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "scoped hello"},
                    execution_context=ToolExecutionContext(
                        attrs={
                            "run_id": "run-123",
                            "agent_id": "assistant",
                            "session_key": "agent:assistant:main",
                            "surface": "interactive",
                        },
                    ),
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        execution_context_payload = tool_run.output_payload["execution_context"]
        self.assertEqual(execution_context_payload["run_id"], "run-123")
        self.assertEqual(execution_context_payload["agent_id"], "assistant")
        self.assertEqual(
            execution_context_payload["session_key"],
            "agent:assistant:main",
        )
        self.assertEqual(execution_context_payload["surface"], "interactive")
        self.assertEqual(execution_context_payload["tool_run_id"], tool_run.id)

        with self.uow_factory() as uow:
            persisted = uow.tool_runs.get(tool_run.id)

        self.assertIsNotNone(persisted)
        assert persisted is not None
        self.assertEqual(persisted.input_payload, {"message": "scoped hello"})

    def test_execute_many_batches_inline_run_creation_and_runs_concurrently(self) -> None:
        tool = self.seed_tool(
            tool_id="batch_inline_tool",
            name="Batch Inline Tool",
            description="Exercises batch inline tool creation.",
            runtime_key="batch_inline_tool",
        )
        active_count = 0
        max_active_count = 0
        active_lock = threading.Lock()
        both_entered = threading.Event()

        async def batch_inline_tool(arguments: dict[str, object]) -> ToolRunResult:
            nonlocal active_count, max_active_count
            with active_lock:
                active_count += 1
                max_active_count = max(max_active_count, active_count)
                if active_count == 2:
                    both_entered.set()
            try:
                if not await asyncio.to_thread(both_entered.wait, 1.0):
                    raise AssertionError(
                        "expected batched inline tool calls to run concurrently",
                    )
                return ToolRunResult.text(
                    str(arguments["message"]),
                    details={"message": arguments["message"]},
                )
            finally:
                with active_lock:
                    active_count -= 1

        self.local_runtime_registry.register(tool, batch_inline_tool)
        original_create_runs = self.tool_service.submission_service._create_runs
        original_complete_run_results = (
            self.tool_service.worker_service._complete_run_results
        )
        batch_sizes: list[int] = []
        completion_batch_sizes: list[int] = []

        def create_runs_spy(prepared_requests):  # noqa: ANN001, ANN202
            batch_sizes.append(len(prepared_requests))
            return original_create_runs(prepared_requests)

        def complete_run_results_spy(completions):  # noqa: ANN001, ANN202
            completion_batch_sizes.append(len(completions))
            return original_complete_run_results(completions)

        with patch.object(
            self.tool_service.dispatch_port,
            "complete",
            wraps=self.tool_service.dispatch_port.complete,
        ) as dispatch_complete_spy, patch.object(
            self.tool_service.submission_service,
            "_create_runs",
            side_effect=create_runs_spy,
        ), patch.object(
            self.tool_service.worker_service,
            "_complete_run_results",
            side_effect=complete_run_results_spy,
        ):
            runs = asyncio.run(
                self.tool_service.execute_many(
                    (
                        ExecuteToolInput(
                            tool_id="batch_inline_tool",
                            arguments={"message": "first"},
                        ),
                        ExecuteToolInput(
                            tool_id="batch_inline_tool",
                            arguments={"message": "second"},
                        ),
                    ),
                ),
            )

        self.assertEqual(batch_sizes, [2])
        self.assertEqual(completion_batch_sizes, [2])
        self.assertEqual(dispatch_complete_spy.call_count, 0)
        self.assertEqual(
            [run.status for run in runs],
            [ToolRunStatus.SUCCEEDED, ToolRunStatus.SUCCEEDED],
        )
        self.assertEqual(
            [run.output_payload["message"] for run in runs],
            ["first", "second"],
        )
        self.assertEqual(max_active_count, 2)

    def test_executes_local_background_tool_with_generic_execution_context(self) -> None:

        queued_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "background scoped hello"},
                    mode=ToolMode.BACKGROUND,
                    execution_context=ToolExecutionContext(
                        attrs={
                            "run_id": "run-background-123",
                            "agent_id": "assistant",
                            "session_key": "agent:assistant:main",
                        },
                    ),
                ),
            ),
        )

        self.assertEqual(queued_run.status, ToolRunStatus.QUEUED)

        deadline = time.monotonic() + 5
        persisted = None
        while time.monotonic() < deadline:
            if persisted is None or persisted.status is ToolRunStatus.QUEUED:
                process_next_background_tool_run(
                    self.container,
                    worker_id="worker-background-context",
                )
            persisted = self.tool_service.get_tool_run(queued_run.id)
            if persisted.status is ToolRunStatus.SUCCEEDED:
                break
            time.sleep(0.05)

        self.assertIsNotNone(persisted)
        assert persisted is not None
        self.assertEqual(persisted.status, ToolRunStatus.SUCCEEDED)
        execution_context_payload = persisted.output_payload["execution_context"]
        self.assertEqual(execution_context_payload["run_id"], "run-background-123")
        self.assertEqual(execution_context_payload["agent_id"], "assistant")
        self.assertEqual(
            execution_context_payload["session_key"],
            "agent:assistant:main",
        )
        self.assertEqual(execution_context_payload["tool_run_id"], persisted.id)
        self.assertEqual(persisted.invocation_context_payload["run_id"], "run-background-123")
        self.assertEqual(persisted.invocation_context_payload["agent_id"], "assistant")
        self.assertEqual(
            persisted.invocation_context_payload["session_key"],
            "agent:assistant:main",
        )
        self.assertEqual(persisted.invocation_context_payload["tool_run_id"], persisted.id)

    def test_executes_sandbox_inline_async_tool_via_runtime_router(self) -> None:
        self.seed_tool(
            tool_id="sandbox_echo",
            name="Sandbox Echo",
            description="Executes through the sandbox adapter.",
            supported_environments=(ToolEnvironment.SANDBOX,),
            definition_origin=ToolDefinitionOrigin.LOCAL_DISCOVERY,
            runtime_key="sandbox.echo",
        )

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="sandbox_echo",
                    arguments={"message": "sandbox hello"},
                    environment=ToolEnvironment.SANDBOX,
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(tool_run.output_payload["message"], "sandbox hello")
        self.assertEqual(tool_run.result.metadata["environment"], "sandbox")
        self.assertTrue(tool_run.result.metadata["sandboxed"])
        self.assertNotEqual(tool_run.result.metadata["process_id"], os.getpid())
        self.assertTrue(
            Path(tool_run.result.metadata["working_directory"]).name.startswith(
                "tool-sandbox-",
            ),
        )

    def test_executes_local_inline_thread_tool_and_reports_thread_context(self) -> None:

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "thread hello"},
                    strategy=ToolExecutionStrategy.THREAD,
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(tool_run.output_payload["message"], "thread hello")
        self.assertEqual(tool_run.result.metadata["process_id"], os.getpid())
        self.assertNotEqual(
            tool_run.result.metadata["thread_ident"],
            threading.get_ident(),
        )

    def test_executes_local_inline_process_tool_and_reports_process_context(self) -> None:

        tool_run = asyncio.run(
            self.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "process hello"},
                    strategy=ToolExecutionStrategy.PROCESS,
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(tool_run.output_payload["message"], "process hello")
        self.assertNotEqual(tool_run.result.metadata["process_id"], os.getpid())
