from __future__ import annotations

from tests.unit.orchestration_test_support import *  # noqa: F403


class OrchestrationMemoryTestCase(OrchestrationTestCaseBase):
    def _write_memory_file(
        self,
        scope_ref: str,
        content: str,
        *,
        path: str = "MEMORY.md",
    ) -> None:
        context = self.memory_context_resolver.resolve(scope_ref)
        self.assertIsNotNone(context)
        assert context is not None
        root = Path(context.storage_root)
        root.mkdir(parents=True, exist_ok=True)
        (root / path).write_text(content, encoding="utf-8")

    def test_memory_context_resolver_uses_agent_memory_scope_ref(self) -> None:
        workspace_dir = tempfile.TemporaryDirectory()
        self.addCleanup(workspace_dir.cleanup)
        self._register_agent_and_llm(
            runtime_preferences=AgentRuntimePreferences(
                workspace=workspace_dir.name,
            ),
            memory=AgentMemoryBinding(scope_ref="shared-memory"),
        )

        context = self.memory_context_resolver.resolve("shared-memory")

        assert context is not None
        self.assertEqual(context.space_id, "shared-memory")
        self.assertNotEqual(context.storage_root, workspace_dir.name)
        self.assertTrue(context.storage_root.endswith("shared-memory"))

    def test_process_next_orchestration_assignment_does_not_implicitly_write_memory(self) -> None:
        adapter = _StaticTextAdapter(
            text=(
                "Use effect-based approvals as the default human-facing approval unit, "
                "and keep tool-level overrides only for explicit exceptions."
            ),
        )
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-memory-candidate",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="What should our approval model look like?",
                ),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertNotIn("inline_tool_run_ids", processed.result_payload or {})

    def test_process_next_orchestration_assignment_exposes_memory_node_without_auto_recall(self) -> None:
        adapter = _StaticTextAdapter(text="approval answer without implicit recall")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        workspace_dir = tempfile.TemporaryDirectory()
        self.addCleanup(workspace_dir.cleanup)
        Path(workspace_dir.name, "MEMORY.md").write_text(
            "# Approval model\nUse effect-based approvals as the default human-facing approval unit.\n",
            encoding="utf-8",
        )
        self._register_agent_and_llm(
            runtime_preferences=AgentRuntimePreferences(workspace=workspace_dir.name),
        )
        self._write_memory_file(
            "assistant",
            "# Approval model\nUse effect-based approvals as the default human-facing approval unit.\n",
        )

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-memory-recall",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="How should our approval model work?",
                ),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        assert processed is not None
        self.assertEqual(len(adapter.requests), 1)
        system_messages = [
            message
            for message in adapter.requests[0].messages
            if message.role is LlmMessageRole.SYSTEM
        ]
        context_tree_message = next(
            message for message in system_messages
            if message.metadata.get("prompt_block_kind") == "context_workspace"
        )
        self.assertIn("skills.available", str(context_tree_message.content))
        self.assertIn("memory.visible", str(context_tree_message.content))
        self.assertFalse(
            any("# Available Skills" in str(message.content) for message in system_messages),
        )
        self.assertFalse(
            any("# Recalled Memory" in str(message.content) for message in system_messages),
        )
        self.assertFalse(
            any("# Workspace Context" in str(message.content) for message in system_messages),
        )
        system_block_kinds = [
            block["kind"] for block in processed.metadata["prompt_report"]["context_blocks"]
        ]
        self.assertEqual(
            system_block_kinds,
            [
                "agent_instruction",
                "runtime_context",
            ],
        )
        context_workspace = self.container.require(
            AppKey.CONTEXT_WORKSPACE_SERVICE,
        ).get_by_session("agent:assistant:main")
        self.assertEqual(
            context_workspace.metadata["available_skill_names"],
            ["memory-recall"],
        )

    def test_process_next_orchestration_assignment_includes_memory_recall_skill_without_auto_recall_on_normal_turn(
        self,
    ) -> None:
        workspace_dir = tempfile.TemporaryDirectory()
        self.addCleanup(workspace_dir.cleanup)
        Path(workspace_dir.name, "MEMORY.md").write_text(
            "# Approval model\nUse effect-based approvals as the default human-facing approval unit.\n",
            encoding="utf-8",
        )

        adapter = _SequentialTextAdapter("hello from session start", "normal turn answer")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm(
            runtime_preferences=AgentRuntimePreferences(workspace=workspace_dir.name),
        )

        first_run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-memory-normal-turn-initial",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=first_run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=first_run.id),
        )
        process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-memory-normal-turn-followup",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="How should our approval model work?",
                ),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        assert processed is not None
        self.assertEqual(processed.metadata["prompt_mode"], "normal_turn")
        self.assertEqual(
            [block["kind"] for block in processed.metadata["prompt_report"]["context_blocks"]],
            [
                "agent_instruction",
                "runtime_context",
            ],
        )

    def test_process_next_orchestration_assignment_can_search_and_get_memory_then_continue(
        self,
    ) -> None:
        workspace_dir = tempfile.TemporaryDirectory()
        self.addCleanup(workspace_dir.cleanup)
        self._register_agent_and_llm(
            runtime_preferences=AgentRuntimePreferences(workspace=workspace_dir.name),
        )
        self._write_memory_file(
            "assistant",
            "# Approval model\nUse effect-based approvals as the default human-facing approval unit.\n",
        )

        adapter = _MemorySearchAndReadAdapter(
            path="MEMORY.md",
            start_line=1,
            line_count=6,
        )
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-memory-search-get",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="Remind me how our approval model should work.",
                ),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        completed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
        assert completed.result_payload is not None
        self.assertEqual(completed.result_payload["output_text"], "memory-guided answer")
        self.assertEqual(len(adapter.requests), 3)

        search_tool_messages = [
            message
            for message in adapter.requests[1].messages
            if message.role is LlmMessageRole.TOOL and message.name == "memory_search"
        ]
        self.assertEqual(len(search_tool_messages), 1)
        self.assertIn(
            "# Memory Search Results",
            str(search_tool_messages[0].content),
        )
        self.assertIn("MEMORY.md", str(search_tool_messages[0].content))
        self.assertIn("- citation: MEMORY.md:", str(search_tool_messages[0].content))
        self.assertIn("- snippet:", str(search_tool_messages[0].content))

        read_tool_messages = [
            message
            for message in adapter.requests[2].messages
            if message.role is LlmMessageRole.TOOL and message.name == "memory_read"
        ]
        self.assertEqual(len(read_tool_messages), 1)
        self.assertIn(
            "# Memory Excerpt",
            str(read_tool_messages[0].content),
        )
        self.assertIn("Citation: MEMORY.md:", str(read_tool_messages[0].content))
        self.assertIn(
            "effect-based approvals",
            str(read_tool_messages[0].content).lower(),
        )

        session_messages = self.session_service.list_messages(
            ListSessionMessagesInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        memory_results = [
            message
            for message in session_messages
            if message.source_kind == "tool_run"
            and message.metadata.get("tool_name") in {"memory_search", "memory_read"}
        ]
        self.assertEqual(len(memory_results), 2)
        self.assertEqual(memory_results[0].metadata["tool_name"], "memory_search")
        self.assertEqual(memory_results[1].metadata["tool_name"], "memory_read")

    def test_process_next_orchestration_assignment_includes_session_start_flow_node(self) -> None:
        adapter = _StaticTextAdapter(text="hello from new session")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-session-start-flow-prompt",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(processed.metadata["prompt_mode"], "session_start")
        session_start_system_messages = [
            message
            for message in adapter.requests[0].messages
            if message.role is LlmMessageRole.SYSTEM
        ]
        context_tree_message = next(
            message
            for message in session_start_system_messages
            if message.metadata.get("prompt_block_kind") == "context_workspace"
        )
        self.assertIn("run.flow", str(context_tree_message.content))
        self.assertIn("Flow: Session Start", str(context_tree_message.content))
        self.assertIn("new active session", str(context_tree_message.content))
        self.assertFalse(
            any("# Session Start" in str(message.content) for message in session_start_system_messages),
        )

    def test_process_next_orchestration_assignment_includes_compaction_flow_node(self) -> None:
        adapter = _StaticTextAdapter(text="compacted summary")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-compaction-flow-prompt",
                inbound_instruction=InboundInstruction(
                    source="cli",
                    content="compact the current session",
                ),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        with self.uow_factory() as uow:
            current = uow.orchestration_runs.get(run.id)
            assert current is not None
            current.metadata["prompt_flow_hint"] = {
                "mode": "compaction",
                "reason": "context budget exceeded",
                "preserve": "open tasks, approvals, and user preferences",
            }
            uow.orchestration_runs.add(current)
            uow.commit()
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        processed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(processed.metadata["prompt_mode"], "compaction")
        compaction_system_messages = [
            message
            for message in adapter.requests[0].messages
            if message.role is LlmMessageRole.SYSTEM
        ]
        context_tree_message = next(
            message
            for message in compaction_system_messages
            if message.metadata.get("prompt_block_kind") == "context_workspace"
        )
        self.assertIn("run.flow", str(context_tree_message.content))
        self.assertIn("Flow: Compaction", str(context_tree_message.content))
        self.assertIn("compacting the current session context", str(context_tree_message.content))
        self.assertIn(
            "Preserve explicitly: open tasks, approvals, and user preferences",
            str(context_tree_message.content),
        )
        self.assertFalse(
            any("# Compaction" in str(message.content) for message in compaction_system_messages),
        )

    def test_request_heartbeat_processes_with_heartbeat_flow_node(self) -> None:
        adapter = _SequentialTextAdapter("initial answer", "HEARTBEAT_OK")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        initial = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-initial-for-heartbeat",
                inbound_instruction=InboundInstruction(source="cli", content="first task"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=initial.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=initial.id),
        )
        process_next_orchestration_assignment(self.container, worker_id="worker-1")

        heartbeat = self.orchestration_scheduler_service.request_heartbeat(
            RequestHeartbeatInput(
                anchor_run_id=initial.id,
                reason="scheduled_check",
            ),
        )
        self.assertEqual(heartbeat.inbound_instruction.source, "heartbeat")
        self.assertEqual(heartbeat.metadata["prompt_flow_hint"]["mode"], "heartbeat")
        self.assertEqual(heartbeat.metadata["heartbeat_request"]["basis"], "manual")

        processed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(processed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(processed.metadata["prompt_mode"], "heartbeat")
        heartbeat_system_messages = [
            message
            for message in adapter.requests[-1].messages
            if message.role is LlmMessageRole.SYSTEM
        ]
        context_tree_message = next(
            message
            for message in heartbeat_system_messages
            if message.metadata.get("prompt_block_kind") == "context_workspace"
        )
        self.assertIn("run.flow", str(context_tree_message.content))
        self.assertIn("Flow: Heartbeat", str(context_tree_message.content))
        self.assertIn("lightweight heartbeat check", str(context_tree_message.content))
        self.assertIn("Default idle reply: HEARTBEAT_OK", str(context_tree_message.content))
        self.assertFalse(
            any("# Heartbeat" in str(message.content) for message in heartbeat_system_messages),
        )
        self.assertEqual(
            [schema.name for schema in adapter.requests[-1].tool_schemas],
            [],
        )

    def test_heartbeat_prompt_mode_policy_hides_memory_tools_when_auth_is_enabled(
        self,
    ) -> None:
        harness = SqliteTestHarness()
        settings = replace(load_settings(), authorization_enabled=True)
        container = harness.build_runtime_container(settings=settings)
        self.addCleanup(container.close)
        self.addCleanup(harness.close)

        adapter = _SequentialTextAdapter("initial answer", "HEARTBEAT_OK")
        container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        credential_binding_id = self._install_default_llm_access_binding(container)
        container.require(AppKey.LLM_SERVICE).register_profile(
            RegisterLlmProfileInput(
                id="openai.gpt-5.4-mini",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
                credential_binding_id=credential_binding_id,
            ),
        )
        workspace_dir = tempfile.TemporaryDirectory()
        self.addCleanup(workspace_dir.cleanup)
        container.require(AppKey.AGENT_SERVICE).register_profile(
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
        initial = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
            AcceptOrchestrationRunInput(
                run_id="run-auth-heartbeat-initial",
                inbound_instruction=InboundInstruction(source="cli", content="first task"),
            ),
        )
        container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
            PrepareSessionRunInput(
                run_id=initial.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).enqueue(
            EnqueueOrchestrationRunInput(run_id=initial.id),
        )
        process_next_orchestration_assignment(container, worker_id="worker-1")

        heartbeat = container.require(AppKey.ORCHESTRATION_SCHEDULER_SERVICE).request_heartbeat(
            RequestHeartbeatInput(
                anchor_run_id=initial.id,
                reason="scheduled_check",
            ),
        )
        processed = process_next_orchestration_assignment(container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(processed)
        assert processed is not None
        self.assertEqual(heartbeat.metadata["prompt_flow_hint"]["mode"], "heartbeat")
        self.assertEqual(processed.metadata["prompt_mode"], "heartbeat")
        self.assertEqual(
            [schema.name for schema in adapter.requests[-1].tool_schemas],
            [],
        )

    def test_request_memory_flush_records_durable_memory_without_transcript_reply(
        self,
    ) -> None:
        adapter = _SequentialResultAdapter(
            "initial answer",
            LlmResult(
                tool_calls=(
                    ToolCallIntent(
                        id="call-memory-write-1",
                        name="memory_write_daily",
                        arguments={
                            "content": (
                                "# Durable Memory\n\n"
                                "Keep effect approvals as the default path for risky actions."
                            ),
                        },
                    ),
                ),
            ),
        )
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        workspace_dir = tempfile.TemporaryDirectory()
        self.addCleanup(workspace_dir.cleanup)
        self._register_agent_and_llm(
            runtime_preferences=AgentRuntimePreferences(workspace=workspace_dir.name),
        )

        initial = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-initial-for-memory-flush",
                inbound_instruction=InboundInstruction(source="cli", content="first task"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=initial.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=initial.id),
        )
        initial_completed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert initial_completed is not None

        session_key = str(initial_completed.metadata["session_key"])
        messages_before = self.session_service.list_messages(
            ListSessionMessagesInput(
                session_key=session_key,
                active_session_only=True,
            ),
        )

        flush = self.orchestration_scheduler_service.request_memory_flush(
            RequestMemoryFlushInput(
                anchor_run_id=initial.id,
                reason="manual memory flush",
            ),
        )
        self.assertEqual(flush.inbound_instruction.source, "memory_flush")
        self.assertEqual(flush.metadata["prompt_flow_hint"]["mode"], "memory_flush")
        self.assertEqual(flush.metadata["memory_flush_request"]["basis"], "manual")

        flushed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        self.assertIsNotNone(flushed)
        assert flushed is not None
        self.assertEqual(flushed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(flushed.metadata["prompt_mode"], "memory_flush")
        self.assertNotIn("assistant_message_id", flushed.result_payload or {})
        self.assertNotIn("memory_flush_result", flushed.metadata)
        inline_tool_run_ids = flushed.result_payload.get("inline_tool_run_ids")
        self.assertIsInstance(inline_tool_run_ids, list)
        assert isinstance(inline_tool_run_ids, list)
        self.assertEqual(len(inline_tool_run_ids), 1)
        tool_run = self.tool_service.get_tool_run(inline_tool_run_ids[0])
        self.assertEqual(tool_run.tool_id, "memory_write_daily")
        self.assertEqual(
            _memory_flush_tool_schema_names(adapter.requests[-1]),
            ["memory_flush_skip", "memory_write_daily"],
        )
        self.assertEqual(adapter.requests[-1].overrides.get("tool_choice"), "required")

        messages_after = self.session_service.list_messages(
            ListSessionMessagesInput(
                session_key=session_key,
                active_session_only=True,
            ),
        )
        self.assertEqual([item.id for item in messages_after], [item.id for item in messages_before])
        memory_file_path = str(tool_run.result.metadata["path"])
        context = self.memory_context_resolver.resolve("assistant")
        self.assertIsNotNone(context)
        assert context is not None
        excerpt = self.file_memory_service.get(
            context=context,
            path=memory_file_path,
        )
        self.assertIsNotNone(excerpt)
        assert excerpt is not None
        self.assertIn("effect approvals", excerpt.text.lower())
        self.assertFalse(Path(workspace_dir.name, "MEMORY.md").exists())
        self.assertFalse(Path(workspace_dir.name, "memory").exists())

    def test_memory_flush_skip_tool_does_not_record_durable_memory(self) -> None:
        adapter = _SequentialResultAdapter("initial answer", _memory_flush_skip_result())
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        workspace_dir = tempfile.TemporaryDirectory()
        self.addCleanup(workspace_dir.cleanup)
        self._register_agent_and_llm(
            runtime_preferences=AgentRuntimePreferences(workspace=workspace_dir.name),
        )

        initial = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-initial-for-memory-flush-skip",
                inbound_instruction=InboundInstruction(source="cli", content="first task"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=initial.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=initial.id),
        )
        process_next_orchestration_assignment(self.container, worker_id="worker-1")

        self.orchestration_scheduler_service.request_memory_flush(
            RequestMemoryFlushInput(anchor_run_id=initial.id),
        )
        context = self.memory_context_resolver.resolve("assistant")
        self.assertIsNotNone(context)
        assert context is not None
        files_before = [
            item.path
            for item in self.file_memory_service.list_files(context=context)
        ]
        flushed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        assert flushed is not None
        self.assertNotIn("memory_flush_result", flushed.metadata)
        self.assertIn("inline_tool_run_ids", flushed.result_payload)
        tool_run = self.tool_service.get_tool_run(
            flushed.result_payload["inline_tool_run_ids"][0],
        )
        self.assertEqual(tool_run.tool_id, "memory_flush_skip")
        self.assertEqual(adapter.requests[-1].overrides.get("tool_choice"), "required")
        self.assertEqual(
            [
                item.path
                for item in self.file_memory_service.list_files(
                    context=context,
                )
            ],
            files_before,
        )

    def test_memory_flush_text_reply_without_tool_is_rejected(self) -> None:
        adapter = _SequentialTextAdapter("initial answer", "plain reply instead of tool")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        initial = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-memory-flush-protocol-initial",
                inbound_instruction=InboundInstruction(source="cli", content="first task"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=initial.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=initial.id),
        )
        process_next_orchestration_assignment(self.container, worker_id="worker-1")

        self.orchestration_scheduler_service.request_memory_flush(
            RequestMemoryFlushInput(anchor_run_id=initial.id),
        )
        flushed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        assert flushed is not None
        self.assertEqual(flushed.status, OrchestrationRunStatus.FAILED)
        assert flushed.error is not None
        self.assertEqual(flushed.error.code, "memory_flush_protocol_violation")
        self.assertEqual(adapter.requests[-1].overrides.get("tool_choice"), "required")

    def test_memory_flush_surface_excludes_unscoped_tools(self) -> None:
        def echo(arguments: dict[str, object], _execution_context=None):
            return {"message": arguments.get("message")}

        tool = Tool(
            id="echo",
            name="Echo",
            description="debug echo",
            kind=ToolKind.FUNCTION,
            parameters=(
                ToolParameter(
                    name="message",
                    data_type="string",
                    description="message",
                    required=True,
                ),
            ),
            runtime_key="echo",
            enabled=True,
        )
        self.local_runtime_registry.register(tool, echo)

        self._register_agent_and_llm()
        initial = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-memory-flush-surface-initial",
                inbound_instruction=InboundInstruction(source="cli", content="first task"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=initial.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=initial.id),
        )
        process_next_orchestration_assignment(self.container, worker_id="worker-1")

        flush = self.orchestration_scheduler_service.request_memory_flush(
            RequestMemoryFlushInput(anchor_run_id=initial.id),
        )
        resolved = self.orchestration_inspection_service.resolve_tools(flush)
        self.assertEqual(
            sorted(item.tool.id for item in resolved.tools),
            ["memory_flush_skip", "memory_write_daily"],
        )

    def test_request_due_heartbeats_enqueues_idle_session_once(self) -> None:
        adapter = _SequentialTextAdapter("initial answer", "HEARTBEAT_OK")
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        initial = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-initial-for-due-heartbeat",
                inbound_instruction=InboundInstruction(source="cli", content="first task"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=initial.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=initial.id),
        )
        process_next_orchestration_assignment(self.container, worker_id="worker-1")

        with self.session_service.uow_factory() as uow:
            session = uow.sessions.get("agent:assistant:main")
            assert session is not None
            session.updated_at = datetime.now(timezone.utc) - timedelta(minutes=10)
            uow.sessions.add(session)
            uow.commit()

        requested = self.orchestration_scheduler_service.request_due_heartbeats(
            RequestDueHeartbeatsInput(
                idle_seconds=60,
                limit=5,
            ),
        )
        self.assertEqual(len(requested), 1)
        self.assertEqual(requested[0].metadata["prompt_flow_hint"]["mode"], "heartbeat")
        self.assertEqual(requested[0].metadata["heartbeat_request"]["basis"], "idle_session")
        self.assertEqual(
            requested[0].metadata["heartbeat_request"]["details"]["idle_seconds"],
            60,
        )

        requested_again = self.orchestration_scheduler_service.request_due_heartbeats(
            RequestDueHeartbeatsInput(
                idle_seconds=60,
                limit=5,
            ),
        )
        self.assertEqual(requested_again, [])

    def test_request_compaction_archives_prior_messages_and_future_prompt_uses_summary(self) -> None:
        adapter = _SequentialTextAdapter(
            "initial answer",
            "compacted summary",
            "follow-up answer",
        )
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )
        self._register_agent_and_llm()

        initial = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-initial-for-compaction",
                inbound_instruction=InboundInstruction(source="cli", content="first task"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=initial.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=initial.id),
        )
        initial_completed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert initial_completed is not None

        compaction = self.orchestration_scheduler_service.request_compaction(
            RequestCompactionInput(
                anchor_run_id=initial.id,
                reason="manual compaction",
                preserve="open tasks and constraints",
            ),
        )
        compaction_completed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(compaction_completed)
        assert compaction_completed is not None
        self.assertEqual(compaction_completed.metadata["prompt_mode"], "compaction")
        self.assertGreaterEqual(
            int(compaction_completed.result_payload["archived_message_count"]),
            2,
        )

        session_messages = self.session_service.list_messages(
            ListSessionMessagesInput(
                session_key="agent:assistant:main",
                active_session_only=True,
            ),
        )
        archived_messages = [
            message for message in session_messages if message.visibility.value == "archived"
        ]
        visible_messages = [
            message for message in session_messages if message.visibility.value != "archived"
        ]
        self.assertGreaterEqual(len(archived_messages), 2)
        visible_assistant_messages = [
            message for message in visible_messages if message.role == "assistant"
        ]
        self.assertEqual(
            visible_assistant_messages[-1].content_payload["blocks"],
            [{"type": "text", "text": "compacted summary"}],
        )

        followup = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-followup-after-compaction",
                inbound_instruction=InboundInstruction(source="cli", content="what next?"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=followup.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=followup.id),
        )
        process_next_orchestration_assignment(self.container, worker_id="worker-1")

        followup_request = adapter.requests[-1]
        transcript_contents = [
            str(message.content)
            for message in followup_request.messages
            if message.role in {LlmMessageRole.USER, LlmMessageRole.ASSISTANT}
        ]
        self.assertTrue(
            any("compacted summary" in content for content in transcript_contents),
        )
        self.assertTrue(
            any("what next?" in content for content in transcript_contents),
        )
        self.assertNotIn("first task", transcript_contents)
        self.assertNotIn("initial answer", transcript_contents)
        self.assertEqual(adapter.requests[1].tool_schemas, ())

    def test_preflight_maintenance_runs_inline_before_followup_when_prompt_budget_is_exceeded(
        self,
    ) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
            orchestration_auto_compaction_enabled=True,
            orchestration_auto_compaction_reserve_tokens=200,
            orchestration_auto_compaction_soft_threshold_tokens=100,
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_runtime_container(settings=settings)
        try:
            adapter = _SequentialResultAdapter(
                "A" * 3_200,
                _memory_flush_skip_result(),
                "compacted summary",
                "follow-up answer after inline maintenance",
            )
            container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            credential_binding_id = self._install_default_llm_access_binding(container)
            container.require(AppKey.LLM_SERVICE).register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                    context_window_tokens=1_000,
                    credential_binding_id=credential_binding_id,
                ),
            )
            container.require(AppKey.AGENT_SERVICE).register_profile(
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

            initial = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-auto-compaction-initial",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=initial.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).enqueue(
                EnqueueOrchestrationRunInput(run_id=initial.id),
            )
            process_next_orchestration_assignment(container, worker_id="worker-1")

            followup = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-auto-compaction-followup",
                    inbound_instruction=InboundInstruction(
                        source="cli",
                        content="continue",
                    ),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=followup.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).enqueue(
                EnqueueOrchestrationRunInput(run_id=followup.id),
            )

            completed = process_next_orchestration_assignment(container,
                worker_id="worker-1",
            )
            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertEqual(completed.metadata["prompt_mode"], "normal_turn")
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
            self.assertEqual(
                completed.result_payload["output_text"],
                "follow-up answer after inline maintenance",
            )
            self.assertEqual(
                _memory_flush_tool_schema_names(adapter.requests[1]),
                ["memory_flush_skip", "memory_write_daily"],
            )
            self.assertEqual(adapter.requests[1].overrides.get("tool_choice"), "required")
            self.assertEqual(adapter.requests[2].tool_schemas, ())

            completed_runs = container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).list_runs(
                status=OrchestrationRunStatus.COMPLETED,
            )
            self.assertEqual(
                len(
                    [
                        run
                        for run in completed_runs
                        if run.inbound_instruction.source == "memory_flush"
                    ]
                ),
                1,
            )
            self.assertEqual(
                len(
                    [
                        run
                        for run in completed_runs
                        if run.inbound_instruction.source == "compaction"
                    ]
                ),
                1,
            )

            refreshed_session = container.require(AppKey.SESSION_SERVICE).get_session("agent:assistant:main")
            self.assertIn("run_id", refreshed_session.metadata["compaction"])
            self.assertNotIn("pending_run_id", refreshed_session.metadata["compaction"])
            self.assertNotIn(
                "pending_memory_flush_run_id",
                refreshed_session.metadata["compaction"],
            )
            self.assertEqual(
                adapter.requests[-1].messages[-1].content,
                [{"type": "text", "text": "continue"}],
            )
        finally:
            custom_harness.close()

    def test_preflight_maintenance_fails_run_when_compaction_cannot_recover_prompt_budget(
        self,
    ) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
            orchestration_auto_compaction_enabled=True,
            orchestration_auto_compaction_reserve_tokens=200,
            orchestration_auto_compaction_soft_threshold_tokens=100,
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_runtime_container(settings=settings)
        try:
            adapter = _SequentialResultAdapter(
                "hello start",
                _memory_flush_skip_result(),
                "compacted summary",
            )
            container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            credential_binding_id = self._install_default_llm_access_binding(container)
            container.require(AppKey.LLM_SERVICE).register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                    context_window_tokens=1_000,
                    credential_binding_id=credential_binding_id,
                ),
            )
            container.require(AppKey.AGENT_SERVICE).register_profile(
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

            initial = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-auto-prompt-threshold-initial",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=initial.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).enqueue(
                EnqueueOrchestrationRunInput(run_id=initial.id),
            )
            process_next_orchestration_assignment(container, worker_id="worker-1")

            followup = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-auto-prompt-threshold-followup",
                    inbound_instruction=InboundInstruction(
                        source="cli",
                        content="B" * 3_200,
                    ),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=followup.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).enqueue(
                EnqueueOrchestrationRunInput(run_id=followup.id),
            )

            completed = process_next_orchestration_assignment(container,
                worker_id="worker-1",
            )
            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.FAILED)
            self.assertEqual(completed.current_step, 0)
            assert completed.error is not None
            self.assertEqual(completed.error.code, "context_budget_unrecoverable")
            self.assertIn("preflight_maintenance", completed.metadata)

            completed_runs = container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).list_runs(
                status=OrchestrationRunStatus.COMPLETED,
            )
            self.assertEqual(
                len(
                    [
                        run
                        for run in completed_runs
                        if run.inbound_instruction.source == "memory_flush"
                    ]
                ),
                1,
            )
            self.assertEqual(
                len(
                    [
                        run
                        for run in completed_runs
                        if run.inbound_instruction.source == "compaction"
                    ]
                ),
                1,
            )
            self.assertEqual(
                _memory_flush_tool_schema_names(adapter.requests[1]),
                ["memory_flush_skip", "memory_write_daily"],
            )
            self.assertEqual(adapter.requests[1].overrides.get("tool_choice"), "required")
            self.assertEqual(adapter.requests[2].tool_schemas, ())
        finally:
            custom_harness.close()

    def test_context_limit_error_triggers_preflight_maintenance_and_retries_same_step(
        self,
    ) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
            orchestration_auto_compaction_enabled=True,
            orchestration_auto_compaction_reserve_tokens=200,
            orchestration_auto_compaction_soft_threshold_tokens=100,
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_runtime_container(settings=settings)
        try:
            adapter = _SequentialFailureAdapter(
                "initial answer",
                RuntimeError(
                    "LLM invocation failed [context_length_exceeded]: prompt too long",
                ),
                _memory_flush_skip_result(),
                "compacted summary",
                "answer after context recovery",
            )
            container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            credential_binding_id = self._install_default_llm_access_binding(container)
            container.require(AppKey.LLM_SERVICE).register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                    context_window_tokens=1_000,
                    credential_binding_id=credential_binding_id,
                ),
            )
            container.require(AppKey.AGENT_SERVICE).register_profile(
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

            initial = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-context-limit-initial",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=initial.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).enqueue(
                EnqueueOrchestrationRunInput(run_id=initial.id),
            )
            process_next_orchestration_assignment(container, worker_id="worker-1")

            followup = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-context-limit-followup",
                    inbound_instruction=InboundInstruction(source="cli", content="continue"),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=followup.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).enqueue(
                EnqueueOrchestrationRunInput(run_id=followup.id),
            )

            completed = process_next_orchestration_assignment(container,
                worker_id="worker-1",
            )
            self.assertIsNotNone(completed)
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
            self.assertEqual(completed.current_step, 1)
            self.assertEqual(
                completed.result_payload["output_text"],
                "answer after context recovery",
            )

            completed_runs = container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).list_runs(
                status=OrchestrationRunStatus.COMPLETED,
            )
            self.assertEqual(
                len(
                    [
                        run
                        for run in completed_runs
                        if run.inbound_instruction.source == "memory_flush"
                    ]
                ),
                1,
            )
            self.assertEqual(
                len(
                    [
                        run
                        for run in completed_runs
                        if run.inbound_instruction.source == "compaction"
                    ]
                ),
                1,
            )
            self.assertEqual(
                _memory_flush_tool_schema_names(adapter.requests[2]),
                ["memory_flush_skip", "memory_write_daily"],
            )
            self.assertEqual(adapter.requests[2].overrides.get("tool_choice"), "required")
            self.assertEqual(adapter.requests[3].tool_schemas, ())
        finally:
            custom_harness.close()

    def test_preflight_memory_flush_caps_transcript_for_maintenance_run(self) -> None:
        custom_harness = SqliteTestHarness()
        settings = replace(
            load_settings(),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
            orchestration_auto_compaction_enabled=True,
            orchestration_auto_compaction_reserve_tokens=200,
            orchestration_auto_compaction_soft_threshold_tokens=100,
        )
        custom_harness.initialize_schema(settings=settings)
        container = custom_harness.build_runtime_container(settings=settings)
        container.require(AppKey.ORCHESTRATION_INSPECTION_SERVICE).set_memory_flush_transcript_max_chars(
            1_000
        )
        try:
            adapter = _SequentialResultAdapter(
                "A" * 12_000,
                _memory_flush_skip_result(),
                "compacted summary",
                "follow-up answer after capped flush",
            )
            container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            credential_binding_id = self._install_default_llm_access_binding(container)
            container.require(AppKey.LLM_SERVICE).register_profile(
                RegisterLlmProfileInput(
                    id="openai.gpt-5.4-mini",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                    context_window_tokens=1_000,
                    credential_binding_id=credential_binding_id,
                ),
            )
            container.require(AppKey.AGENT_SERVICE).register_profile(
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

            initial = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-memory-flush-cap-initial",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=initial.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).enqueue(
                EnqueueOrchestrationRunInput(run_id=initial.id),
            )
            process_next_orchestration_assignment(container, worker_id="worker-1")

            followup = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-memory-flush-cap-followup",
                    inbound_instruction=InboundInstruction(
                        source="cli",
                        content="continue",
                    ),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=followup.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).enqueue(
                EnqueueOrchestrationRunInput(run_id=followup.id),
            )

            completed = process_next_orchestration_assignment(container,
                worker_id="worker-1",
            )

            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
            self.assertEqual(
                completed.result_payload["output_text"],
                "follow-up answer after capped flush",
            )

            memory_flush_request = adapter.requests[1]
            transcript_text = "\n".join(
                str(message.content)
                for message in memory_flush_request.messages
                if message.role is not LlmMessageRole.SYSTEM
            )
            self.assertLess(len(transcript_text), 5_000)
            self.assertLess(
                sum(
                    len(str(message.content))
                    for message in memory_flush_request.messages
                    if message.role is not LlmMessageRole.SYSTEM
                ),
                5_000,
            )
        finally:
            custom_harness.close()
