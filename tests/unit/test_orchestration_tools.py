from __future__ import annotations

from crxzipple.modules.tool.domain import ToolRunResult

from tests.unit.orchestration_test_support import *  # noqa: F403


class OrchestrationToolsTestCase(OrchestrationTestCaseBase):
    def test_wait_on_tool_reconciles_when_tool_finished_before_wait_mapping(self) -> None:
        self._register_agent_and_llm()

        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="background_echo",
                name="Background Echo",
                description="Only runs in the background.",
                supported_modes=(ToolMode.BACKGROUND,),
                runtime_key="background_echo",
            ),
        )

        async def background_echo(arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={"message": arguments.get("message")},
            )

        self.container.local_tool_catalog.register(tool, background_echo)

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-early-tool-finish",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )
        claimed = self.container.orchestration_service.claim_next_queued_run(
            worker_id="worker-1",
        )
        assert claimed is not None

        queued_tool_run = asyncio.run(
            self.container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="background_echo",
                    arguments={"message": "background hello"},
                    mode=ToolMode.BACKGROUND,
                ),
            ),
        )
        finished_tool_run = self.container.tool_service.process_next_queued_run(
            worker_id="tool-worker-1",
        )

        self.assertEqual(queued_tool_run.status, ToolRunStatus.QUEUED)
        self.assertIsNotNone(finished_tool_run)
        assert finished_tool_run is not None
        self.assertEqual(finished_tool_run.status, ToolRunStatus.SUCCEEDED)

        reconciled = self.container.orchestration_service.wait_on_tool(
            WaitOnToolInput(
                run_id=run.id,
                worker_id="worker-1",
                pending_tool_run_ids=(queued_tool_run.id,),
                reason="tool_background_wait",
            ),
        )

        self.assertEqual(reconciled.status, OrchestrationRunStatus.QUEUED)
        self.assertEqual(reconciled.stage, OrchestrationRunStage.QUEUED)
        self.assertEqual(reconciled.pending_tool_run_ids, ())
        self.assertEqual(reconciled.queue_policy, OrchestrationQueuePolicy.RESUME_FIRST)

    def test_process_next_queued_run_heartbeats_dispatch_during_long_execution(self) -> None:
        custom_harness = SqliteTestHarness()
        custom_settings = replace(
            load_settings(),
            orchestration_run_lease_seconds=1,
            orchestration_run_heartbeat_seconds=0.05,
        )
        custom_harness.initialize_schema(settings=custom_settings)
        container = custom_harness.build_container(settings=custom_settings)
        try:
            adapter = _SlowStaticTextAdapter(
                text="slow llm response",
                delay_seconds=0.15,
            )
            container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                ),
            )
            container.agent_service.register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )

            run = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-heartbeat-loop",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            processed = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )

            self.assertIsNotNone(processed)
            assert processed is not None
            self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
            self.assertIn(
                "dispatch.task.heartbeated",
                [event.name for event in container.event_bus.published_events],
            )
        finally:
            custom_harness.close()

    def test_process_next_queued_run_injects_available_skills_catalog(self) -> None:
        adapter = _StaticTextAdapter(text="hello with skill catalog")
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            workspace.mkdir()
            _write_skill_package(
                workspace / ".crxzipple" / "skills" / "repo-review",
                name="repo-review",
                description="Use this skill when reviewing repository changes.",
                instructions=(
                    "# Repo Review\n\nUse this skill when reviewing repository changes.\n"
                ),
            )
            self._register_agent_and_llm(
                runtime_preferences=AgentRuntimePreferences(workspace=str(workspace)),
            )

            with patch(
                "crxzipple.modules.skills.infrastructure.filesystem.repository.DEFAULT_GLOBAL_SKILLS_DIR",
                root / "global",
            ), patch(
                "crxzipple.modules.skills.infrastructure.filesystem.repository.DEFAULT_SYSTEM_SKILLS_DIR",
                root / "system",
            ):
                run = self.container.orchestration_service.accept(
                    AcceptOrchestrationRunInput(
                        run_id="run-skill-catalog",
                        inbound_instruction=InboundInstruction(source="cli", content="hello"),
                    ),
                )
                self.container.orchestration_service.prepare_session_run(
                    PrepareSessionRunInput(
                        run_id=run.id,
                        context=SessionRouteContext(
                            agent_id="assistant",
                            channel="webchat",
                            direct_scope=DirectSessionScope.MAIN,
                        ),
                    ),
                )
                self.container.orchestration_service.enqueue(
                    EnqueueOrchestrationRunInput(run_id=run.id),
                )

                processed = self.container.orchestration_service.process_next_queued_run(
                    worker_id="worker-1",
                )

            self.assertIsNotNone(processed)
            assert processed is not None
            self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
            system_messages = [
                message
                for message in adapter.requests[0].messages
                if message.role is LlmMessageRole.SYSTEM
            ]
            self.assertTrue(
                any(
                    "# Available Skills" in str(message.content)
                    and "repo-review" in str(message.content)
                    and "SKILL.md" in str(message.content)
                    for message in system_messages
                ),
            )
            self.assertIn(
                "skills_catalog",
                [
                    block["kind"]
                    for block in processed.metadata["prompt_report"]["system_blocks"]
                ],
            )

    def test_process_next_queued_run_can_read_skill_and_continue(self) -> None:
        adapter = _SkillReadingAdapter()
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            workspace.mkdir()
            _write_skill_package(
                workspace / ".crxzipple" / "skills" / "repo-review",
                name="repo-review",
                description="Review changes carefully and cite concrete findings.",
                version="1",
                tags=("review", "repository"),
                allowed_tools=("memory_search",),
                instructions=(
                    "# Repo Review\n\n"
                    "Review changes carefully and cite concrete findings.\n"
                ),
            )
            self._register_agent_and_llm(
                runtime_preferences=AgentRuntimePreferences(workspace=str(workspace)),
            )

            run = self.container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-read-skill",
                    inbound_instruction=InboundInstruction(source="cli", content="review the repo"),
                ),
            )
            self.container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            self.container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            completed = self.container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )

            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
            assert completed.result_payload is not None
            self.assertEqual(completed.result_payload["output_text"], "used repo-review skill")
            self.assertEqual(len(adapter.requests), 2)
            skill_tool_messages = [
                message
                for message in adapter.requests[1].messages
                if message.role is LlmMessageRole.TOOL and message.name == "skill_read"
            ]
            self.assertEqual(len(skill_tool_messages), 1)
            self.assertIn(
                "# Skill: repo-review",
                str(skill_tool_messages[0].content),
            )
            self.assertIn("- Version: 1", str(skill_tool_messages[0].content))
            self.assertIn("- Tags: review, repository", str(skill_tool_messages[0].content))
            self.assertIn("- Suggested tools: memory_search", str(skill_tool_messages[0].content))
            self.assertIn(
                "Review changes carefully and cite concrete findings.",
                str(skill_tool_messages[0].content),
            )
            session_messages = self.container.session_service.list_messages(
                ListSessionMessagesInput(
                    session_key="agent:assistant:main",
                    active_session_only=True,
                ),
            )
            skill_results = [
                message
                for message in session_messages
                if message.source_kind == "tool_run"
                and message.metadata.get("tool_name") == "skill_read"
            ]
            self.assertEqual(len(skill_results), 1)
            self.assertEqual(skill_results[0].metadata["tool_name"], "skill_read")
            self.assertIn(
                "# Skill: repo-review",
                str(skill_results[0].content_payload.get("content")),
            )

    def test_process_next_queued_run_allows_skill_read_alongside_other_tools(self) -> None:
        adapter = _SkillReadAndEchoAdapter()
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            workspace.mkdir()
            _write_skill_package(
                workspace / ".crxzipple" / "skills" / "repo-review",
                name="repo-review",
                description="Review changes carefully and cite concrete findings.",
                instructions=(
                    "# Repo Review\n\n"
                    "Review changes carefully and cite concrete findings.\n"
                ),
            )
            self._register_agent_and_llm(
                runtime_preferences=AgentRuntimePreferences(workspace=str(workspace)),
            )
            tool = self.container.tool_service.register(
                RegisterToolInput(
                    id="echo",
                    name="Echo",
                    description="Returns the input payload for local inline execution tests.",
                    supported_modes=(ToolMode.INLINE,),
                    runtime_key="echo",
                ),
            )

            async def echo(arguments: dict[str, object]) -> ToolRunResult:
                return ToolRunResult.text(
                    str(arguments.get("message") or ""),
                    details={"echo": arguments.get("message")},
                )

            self.container.local_tool_catalog.register(tool, echo)

            run = self.container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-read-skill-and-echo",
                    inbound_instruction=InboundInstruction(source="cli", content="review the repo"),
                ),
            )
            self.container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            self.container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            completed = self.container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )

            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
            assert completed.result_payload is not None
            self.assertEqual(
                completed.result_payload["output_text"],
                "used skill guidance without mode switch",
            )
            self.assertEqual(len(adapter.requests), 2)
            second_request_tool_names = [
                message.name
                for message in adapter.requests[1].messages
                if message.role is LlmMessageRole.TOOL
            ]
            self.assertIn("skill_read", second_request_tool_names)
            self.assertIn("echo", second_request_tool_names)

    def test_process_next_queued_run_can_read_multiple_skills_before_deciding(self) -> None:
        adapter = _MultiSkillReadAdapter()
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            workspace.mkdir()
            _write_skill_package(
                workspace / ".crxzipple" / "skills" / "repo-review",
                name="repo-review",
                description="Review changes carefully and cite concrete findings.",
                instructions="# Repo Review\n\nReview changes carefully.\n",
            )
            _write_skill_package(
                workspace / ".crxzipple" / "skills" / "memory-recall",
                name="memory-recall",
                description="Recall durable memory before answering.",
                instructions="# Memory Recall\n\nUse durable memory.\n",
            )
            self._register_agent_and_llm(
                runtime_preferences=AgentRuntimePreferences(workspace=str(workspace)),
            )

            run = self.container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-read-multiple-skills",
                    inbound_instruction=InboundInstruction(source="cli", content="decide how to answer"),
                ),
            )
            self.container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            self.container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            completed = self.container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )

            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
            assert completed.result_payload is not None
            self.assertEqual(
                completed.result_payload["output_text"],
                "compared multiple skills before deciding",
            )
            second_request_tool_names = [
                message.name
                for message in adapter.requests[1].messages
                if message.role is LlmMessageRole.TOOL
            ]
            self.assertEqual(second_request_tool_names.count("skill_read"), 2)

    def test_process_next_queued_run_completes_inline_tool_loop(self) -> None:
        adapter = _InlineToolLoopAdapter()
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()
        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="echo",
                name="Echo",
                description="Returns the input payload for local inline execution tests.",
                supported_modes=(ToolMode.INLINE,),
                runtime_key="echo",
            ),
        )

        async def echo(arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={"echo": arguments.get("message")},
            )

        self.container.local_tool_catalog.register(tool, echo)

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-process-inline-tool",
                inbound_instruction=InboundInstruction(source="cli", content="search"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(processed.stage, OrchestrationRunStage.COMPLETED)
        self.assertEqual(processed.current_step, 2)
        assert processed.result_payload is not None
        self.assertEqual(processed.result_payload["output_text"], "tool loop complete")
        self.assertEqual(processed.result_payload["llm_id"], "openai.gpt-5.4-mini")
        self.assertEqual(len(adapter.requests), 2)
        first_schema_names = [schema.name for schema in adapter.requests[0].tool_schemas]
        self.assertIn("echo", first_schema_names)
        self.assertIn("memory_read", first_schema_names)
        self.assertIn("memory_search", first_schema_names)
        self.assertIn("memory_write_daily", first_schema_names)
        self.assertIn("skill_read", first_schema_names)
        self.assertEqual(
            [message.role for message in adapter.requests[1].messages[:2]],
            [
                LlmMessageRole.SYSTEM,
                LlmMessageRole.SYSTEM,
            ],
        )
        self.assertEqual(
            [message.role for message in adapter.requests[1].messages[-3:]],
            [
                LlmMessageRole.USER,
                LlmMessageRole.ASSISTANT,
                LlmMessageRole.TOOL,
            ],
        )
        self.assertEqual(adapter.requests[1].messages[-2].tool_call_id, "call-echo-1")
        self.assertEqual(adapter.requests[1].messages[-1].tool_call_id, "call-echo-1")
        self.assertEqual(adapter.requests[1].messages[-1].name, "echo")

        session_messages = self.container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        self.assertEqual(
            [message.role for message in session_messages],
            ["user", "assistant", "tool", "assistant"],
        )
        self.assertEqual(session_messages[1].metadata["tool_call_id"], "call-echo-1")
        self.assertEqual(session_messages[2].metadata["tool_call_id"], "call-echo-1")

    def test_process_next_queued_run_waits_when_tool_is_background(self) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
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
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_container(settings=settings)
        try:
            container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                _BackgroundToolAdapter(),
            )
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                ),
            )
            container.agent_service.register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )

            tool = container.tool_service.register(
                RegisterToolInput(
                    id="background_echo",
                    name="Background Echo",
                    description="Only runs in the background.",
                    supported_modes=(ToolMode.BACKGROUND,),
                    runtime_key="background_echo",
                ),
            )

            async def background_echo(arguments: dict[str, object]) -> ToolRunResult:
                return ToolRunResult.text(
                    str(arguments.get("message") or ""),
                    details={"message": arguments.get("message")},
                )

            container.local_tool_catalog.register(tool, background_echo)
            container.authorization_service.grant_agent_effect_access(
                agent_id="assistant",
                effect_id="background_execution",
            )

            run = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-process-tool",
                    inbound_instruction=InboundInstruction(source="cli", content="search"),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            processed = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )

            self.assertIsNotNone(processed)
            assert processed is not None
            self.assertEqual(processed.status, OrchestrationRunStatus.WAITING)
            self.assertEqual(processed.stage, OrchestrationRunStage.WAITING_ON_TOOL)
            self.assertEqual(processed.current_step, 1)
            self.assertEqual(processed.waiting_reason, "tool_background_wait")
            self.assertEqual(len(processed.pending_tool_run_ids), 1)

            tool_run = container.tool_service.get_tool_run(
                processed.pending_tool_run_ids[0],
            )
            self.assertEqual(tool_run.status, ToolRunStatus.QUEUED)

            session_messages = container.session_service.list_messages(
                ListSessionMessagesInput(
                    session_key="agent:assistant:main",
                    active_session_only=True,
                ),
            )
            self.assertEqual([message.role for message in session_messages], ["user", "assistant"])
            self.assertEqual(session_messages[1].metadata["tool_call_id"], "call-bg-1")
        finally:
            custom_harness.close()

    def test_background_tool_execution_receives_orchestration_context(self) -> None:
        workspace_dir = tempfile.TemporaryDirectory()
        self.addCleanup(workspace_dir.cleanup)
        Path(workspace_dir.name, "README.md").write_text(
            "# Workspace\n\nbackground context\n",
            encoding="utf-8",
        )
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
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
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_container(settings=settings)
        try:
            adapter = _BackgroundToolAdapter()
            container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                ),
            )
            container.agent_service.register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                    runtime_preferences=AgentRuntimePreferences(
                        workspace=workspace_dir.name,
                    ),
                ),
            )

            tool = container.tool_service.register(
                RegisterToolInput(
                    id="background_echo",
                    name="Background Echo",
                    description="Only runs in the background.",
                    supported_modes=(ToolMode.BACKGROUND,),
                    runtime_key="background_echo",
                ),
            )

            async def background_echo(
                arguments: dict[str, object],
                execution_context=None,
            ) -> ToolRunResult:
                return ToolRunResult.text(
                    str(arguments.get("message") or ""),
                    details={
                        "message": arguments.get("message"),
                        "execution_context": (
                            execution_context.to_payload() if execution_context is not None else None
                        ),
                    },
                )

            container.local_tool_catalog.register(tool, background_echo)
            container.authorization_service.grant_agent_effect_access(
                agent_id="assistant",
                effect_id="background_execution",
            )

            run = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-background-context",
                    inbound_instruction=InboundInstruction(source="cli", content="search"),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            waiting = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )

            self.assertIsNotNone(waiting)
            assert waiting is not None
            self.assertEqual(waiting.status, OrchestrationRunStatus.WAITING)
            self.assertEqual(len(waiting.pending_tool_run_ids), 1)

            queued_tool_run = container.tool_service.get_tool_run(
                waiting.pending_tool_run_ids[0],
            )
            self.assertEqual(
                queued_tool_run.invocation_context_payload["session_key"],
                "agent:assistant:main",
            )
            self.assertEqual(
                queued_tool_run.invocation_context_payload["workspace_dir"],
                workspace_dir.name,
            )
            self.assertIn(
                "workspace_bound",
                queued_tool_run.invocation_context_payload["available_scopes"],
            )

            finished_tool_run = container.tool_service.process_next_queued_run(
                worker_id="tool-worker-1",
            )

            self.assertIsNotNone(finished_tool_run)
            assert finished_tool_run is not None
            self.assertEqual(finished_tool_run.status, ToolRunStatus.SUCCEEDED)
            self.assertEqual(
                finished_tool_run.output_payload["execution_context"]["session_key"],
                "agent:assistant:main",
            )
            self.assertEqual(
                finished_tool_run.output_payload["execution_context"]["workspace_dir"],
                workspace_dir.name,
            )
            self.assertIn(
                "workspace_bound",
                finished_tool_run.output_payload["execution_context"]["available_scopes"],
            )
        finally:
            custom_harness.close()

    def test_background_tool_completion_event_resumes_run_and_allows_next_turn(self) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
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
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_container(settings=settings)
        try:
            adapter = _BackgroundResumeAdapter()
            container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                ),
            )
            container.agent_service.register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )

            tool = container.tool_service.register(
                RegisterToolInput(
                    id="background_echo",
                    name="Background Echo",
                    description="Only runs in the background.",
                    supported_modes=(ToolMode.BACKGROUND,),
                    runtime_key="background_echo",
                ),
            )

            async def background_echo(arguments: dict[str, object]) -> ToolRunResult:
                return ToolRunResult.text(
                    str(arguments.get("message") or ""),
                    details={"message": arguments.get("message")},
                )

            container.local_tool_catalog.register(tool, background_echo)
            container.authorization_service.grant_agent_effect_access(
                agent_id="assistant",
                effect_id="background_execution",
            )

            run = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-process-background-resume",
                    inbound_instruction=InboundInstruction(source="cli", content="search"),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            waiting = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )
            assert waiting is not None
            self.assertEqual(waiting.status, OrchestrationRunStatus.WAITING)
            self.assertEqual(len(waiting.pending_tool_run_ids), 1)
            background_tool_run_id = waiting.pending_tool_run_ids[0]

            finished_tool_run = container.tool_service.process_next_queued_run(
                worker_id="tool-worker-1",
            )
            self.assertIsNotNone(finished_tool_run)
            assert finished_tool_run is not None
            self.assertEqual(finished_tool_run.id, background_tool_run_id)
            self.assertEqual(finished_tool_run.status, ToolRunStatus.SUCCEEDED)

            resumed = container.orchestration_service.get_run(run.id)
            self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)
            self.assertEqual(resumed.stage, OrchestrationRunStage.QUEUED)
            self.assertEqual(resumed.pending_tool_run_ids, ())
            self.assertEqual(resumed.waiting_reason, None)
            self.assertEqual(
                resumed.queue_policy,
                OrchestrationQueuePolicy.RESUME_FIRST,
            )

            session_messages = container.session_service.list_messages(
                ListSessionMessagesInput(
                    session_key="agent:assistant:main",
                    active_session_only=True,
                ),
            )
            self.assertEqual(
                [message.role for message in session_messages],
                ["user", "assistant", "tool"],
            )
            self.assertEqual(session_messages[2].source_id, background_tool_run_id)
            self.assertEqual(session_messages[2].metadata["tool_call_id"], "call-bg-1")

            completed = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )
            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
            self.assertEqual(completed.stage, OrchestrationRunStage.COMPLETED)
            self.assertEqual(completed.current_step, 2)
            assert completed.result_payload is not None
            self.assertEqual(
                completed.result_payload["output_text"],
                "background loop complete",
            )
            self.assertEqual(len(adapter.requests), 2)
            self.assertEqual(
                [message.role for message in adapter.requests[1].messages[:2]],
                [
                    LlmMessageRole.SYSTEM,
                    LlmMessageRole.SYSTEM,
                ],
            )
            self.assertEqual(
                [message.role for message in adapter.requests[1].messages[-3:]],
                [
                    LlmMessageRole.USER,
                    LlmMessageRole.ASSISTANT,
                    LlmMessageRole.TOOL,
                ],
            )
            self.assertEqual(completed.metadata["prompt_mode"], "recovery_resume")
            recovery_system_messages = [
                message
                for message in adapter.requests[1].messages
                if message.role is LlmMessageRole.SYSTEM
            ]
            self.assertTrue(
                any(
                    "# Recovery Update" in str(message.content)
                    and "resuming after background work completed" in str(message.content)
                    for message in recovery_system_messages
                ),
            )
            self.assertFalse(
                any(
                    "Durable memory is available for this run." in str(message.content)
                    for message in recovery_system_messages
                ),
            )
            self.assertFalse(
                any("# Recalled Memory" in str(message.content) for message in recovery_system_messages),
            )
        finally:
            custom_harness.close()

    def test_recover_abandoned_runs_recovers_tool_wait_when_wait_mapping_is_lost(self) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
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
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_container(settings=settings)
        try:
            adapter = _BackgroundApprovalAdapter()
            container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                ),
            )
            container.agent_service.register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Be helpful and concise.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )

            tool = container.tool_service.register(
                RegisterToolInput(
                    id="background_echo",
                    name="Background Echo",
                    description="Only runs in the background.",
                    supported_modes=(ToolMode.BACKGROUND,),
                    runtime_key="background_echo",
                ),
            )

            async def background_echo(arguments: dict[str, object]) -> ToolRunResult:
                return ToolRunResult.text(
                    str(arguments.get("message") or ""),
                    details={"message": arguments.get("message")},
                )

            container.local_tool_catalog.register(tool, background_echo)

            run = container.orchestration_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-background-tool-wait-recovery",
                    inbound_instruction=InboundInstruction(source="cli", content="search"),
                ),
            )
            container.orchestration_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.orchestration_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            waiting_for_approval = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )
            assert waiting_for_approval is not None
            pending_request = waiting_for_approval.pending_approval_request()
            assert pending_request is not None

            waiting_on_tool = container.orchestration_service.resolve_approval_request(
                ResolveApprovalRequestInput(
                    run_id=run.id,
                    request_id=pending_request.request_id,
                    decision=ApprovalDecision.ALLOW_ONCE,
                ),
            )
            self.assertEqual(waiting_on_tool.stage, OrchestrationRunStage.WAITING_ON_TOOL)

            with container.orchestration_service.uow_factory() as uow:
                uow.orchestration_waits.delete_for_run(run.id)
                uow.commit()

            finished_tool_run = container.tool_service.process_next_queued_run(
                worker_id="tool-worker-1",
            )
            self.assertIsNotNone(finished_tool_run)
            assert finished_tool_run is not None
            self.assertEqual(finished_tool_run.status, ToolRunStatus.SUCCEEDED)

            recovered = container.orchestration_service.recover_abandoned_runs()
            self.assertTrue(any(item.id == run.id for item in recovered))

            resumed = container.orchestration_service.get_run(run.id)
            self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)
            self.assertEqual(resumed.stage, OrchestrationRunStage.QUEUED)

            completed = container.orchestration_service.process_next_queued_run(
                worker_id="worker-1",
            )
            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
            self.assertEqual(
                completed.result_payload["output_text"],
                "background approval flow complete",
            )
        finally:
            custom_harness.close()

    def test_process_next_queued_run_fails_when_llm_requests_unknown_tool(self) -> None:
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _ToolCallAdapter(),
        )
        self._register_agent_and_llm()

        run = self.container.orchestration_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-process-tool",
                inbound_instruction=InboundInstruction(source="cli", content="search"),
            ),
        )
        self.container.orchestration_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = self.container.orchestration_service.process_next_queued_run(
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.FAILED)
        self.assertEqual(processed.stage, OrchestrationRunStage.FAILED)
        self.assertEqual(processed.current_step, 1)
        assert processed.error is not None
        self.assertEqual(processed.error.code, "engine_failed")
        self.assertIn("search_docs", processed.error.message)

        session_messages = self.container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        self.assertEqual(
            [message.role for message in session_messages],
            ["user", "assistant"],
        )
