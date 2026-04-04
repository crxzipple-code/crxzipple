from __future__ import annotations

from crxzipple.modules.tool.domain import ToolRunResult, ToolValidationError

from tests.unit.tool_test_support import *  # noqa: F403


class ToolExecutionTestCase(ToolTestCaseBase):
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

    def test_execute_externalizes_inline_tool_attachments_to_artifact_refs(self) -> None:
        self.container.tool_service.discover_local_tools()

        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="inline_image_tool",
                name="Inline Image Tool",
                description="Returns an inline image block.",
                runtime_key="inline_image_tool",
            ),
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

        self.container.local_tool_catalog.register(tool, inline_image_tool)

        tool_run = asyncio.run(
            self.container.tool_service.execute(
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
        artifact = self.container.artifact_service.get_artifact(
            attachment_block["artifact_id"],
        )
        self.assertEqual(artifact.mime_type, "image/png")
        self.assertEqual(artifact.name, "generated.png")

    def test_execute_fails_when_tool_result_details_exceed_budget(self) -> None:
        self.container.tool_service.details_max_chars = 128
        self.container.tool_service.discover_local_tools()

        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="oversized_details_tool",
                name="Oversized Details Tool",
                description="Returns oversized details payload.",
                runtime_key="oversized_details_tool",
            ),
        )

        async def oversized_details_tool(_arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.structured(
                content=[{"type": "text", "text": "Generated output."}],
                details={"payload": "x" * 512},
            )

        self.container.local_tool_catalog.register(tool, oversized_details_tool)

        tool_run = asyncio.run(
            self.container.tool_service.execute(
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
        self.container.tool_service.discover_local_tools()

        tool_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="echo",
                    arguments={"message": "hello"},
                ),
            ),
        )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(tool_run.output_payload["message"], "hello")
        self.assertIsNotNone(tool_run.started_at)
        self.assertIsNotNone(tool_run.completed_at)

        with self.container.uow_factory() as uow:
            persisted = uow.tool_runs.get(tool_run.id)

        self.assertIsNotNone(persisted)
        self.assertEqual(persisted.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(persisted.output_payload["received"]["message"], "hello")

        event_names = [event.name for event in self.container.event_bus.published_events]
        self.assertIn("tool.run.created", event_names)
        self.assertIn("tool.run.started", event_names)
        self.assertIn("tool.run.succeeded", event_names)

    def test_executes_local_tool_with_generic_execution_context_without_persisting_it_in_input_payload(self) -> None:
        self.container.tool_service.discover_local_tools()

        tool_run = asyncio.run(
            self.container.tool_service.execute(
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
        self.assertEqual(
            tool_run.output_payload["execution_context"],
            {
                "run_id": "run-123",
                "agent_id": "assistant",
                "session_key": "agent:assistant:main",
                "surface": "interactive",
            },
        )

        with self.container.uow_factory() as uow:
            persisted = uow.tool_runs.get(tool_run.id)

        self.assertIsNotNone(persisted)
        assert persisted is not None
        self.assertEqual(persisted.input_payload, {"message": "scoped hello"})

    def test_executes_local_background_tool_with_generic_execution_context(self) -> None:
        self.container.tool_service.discover_local_tools()

        queued_run = asyncio.run(
            self.container.tool_service.execute(
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
                self.container.tool_service.process_next_queued_run(
                    worker_id="worker-background-context",
                )
            persisted = self.container.tool_service.get_tool_run(queued_run.id)
            if persisted.status is ToolRunStatus.SUCCEEDED:
                break
            time.sleep(0.05)

        self.assertIsNotNone(persisted)
        assert persisted is not None
        self.assertEqual(persisted.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(
            persisted.output_payload["execution_context"],
            {
                "run_id": "run-background-123",
                "agent_id": "assistant",
                "session_key": "agent:assistant:main",
            },
        )
        self.assertEqual(
            persisted.invocation_context_payload,
            {
                "run_id": "run-background-123",
                "agent_id": "assistant",
                "session_key": "agent:assistant:main",
            },
        )

    def test_executes_sandbox_inline_async_tool_via_runtime_router(self) -> None:
        self.container.tool_service.register(
            RegisterToolInput(
                id="sandbox_echo",
                name="Sandbox Echo",
                description="Executes through the sandbox adapter.",
                supported_environments=(ToolEnvironment.SANDBOX,),
                source_kind=ToolSourceKind.MANUAL,
                runtime_key="sandbox.echo",
            ),
        )

        tool_run = asyncio.run(
            self.container.tool_service.execute(
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
        self.container.tool_service.discover_local_tools()

        tool_run = asyncio.run(
            self.container.tool_service.execute(
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
        self.container.tool_service.discover_local_tools()

        tool_run = asyncio.run(
            self.container.tool_service.execute(
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
