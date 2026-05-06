from __future__ import annotations

from crxzipple.modules.tool.domain import ToolRunResult

from tests.unit.orchestration_test_support import *  # noqa: F403
from tests.unit.tool_runtime_test_support import process_next_background_tool_run


class OrchestrationApprovalTestCase(OrchestrationTestCaseBase):
    _BROWSER_TOOL_IDS = [
        "browser_action",
        "browser_control",
        "browser_profile",
        "browser_script",
        "browser_snapshot",
    ]
    _MOBILE_TOOL_IDS = [
        "mobile_devices",
        "mobile_press",
        "mobile_screenshot",
        "mobile_script",
        "mobile_snapshot",
        "mobile_swipe",
        "mobile_tap",
        "mobile_type",
        "mobile_wait",
    ]
    _OPENAI_IMAGE_TOOL_IDS = [
        "openai_image_edit",
        "openai_image_generate",
    ]
    _SESSION_TOOL_IDS = [
        "session_status",
        "sessions_history",
        "sessions_list",
        "sessions_send",
        "sessions_spawn",
        "sessions_stop",
        "sessions_yield",
    ]
    _POST_SKILL_SESSION_TOOL_IDS = ["subagents"]

    def test_tool_resolver_reuses_run_context_during_surface_filtering(self) -> None:
        self._register_agent_and_llm()
        call_count = 0

        def run_context_provider(_run: object) -> dict[str, object]:
            nonlocal call_count
            call_count += 1
            return {
                "available_scopes": [
                    "memory_context",
                    "session_context",
                    "workspace_bound",
                ],
                "workspace_dir": "/tmp",
            }

        self.container.orchestration_inspection_service.engine.tool_resolver.run_context_provider = (
            run_context_provider
        )
        run = self.container.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-tool-context-cache",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )

        resolved = self.container.orchestration_inspection_service.resolve_tools(
            self.container.orchestration_run_query_service.get_run(run.id),
        )

        self.assertGreater(len(resolved.tools), 1)
        self.assertEqual(call_count, 1)

    def test_tool_resolver_applies_authorized_tool_access_override(self) -> None:
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
                    instruction_policy=AgentInstructionPolicy(system_prompt="Be helpful."),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )
            container.tool_service.register(
                RegisterToolInput(
                    id="brave_search.news_search",
                    name="News Search",
                    description="Search news.",
                    supported_environments=(ToolEnvironment.REMOTE,),
                    required_effect_ids=("network_search",),
                ),
            )
            container.tool_service.register(
                RegisterToolInput(
                    id="open_meteo_weather.forecast_weather",
                    name="Forecast Weather",
                    description="Get weather data.",
                    supported_environments=(ToolEnvironment.REMOTE,),
                    required_effect_ids=("weather_data",),
                ),
            )
            container.authorization_service.grant_agent_tool_access(
                agent_id="assistant",
                tool_id="brave_search.news_search",
            )

            run = container.orchestration_intake_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-tool-access-allow",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.orchestration_intake_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )

            resolved = container.orchestration_inspection_service.resolve_tools(
                container.orchestration_run_query_service.get_run(run.id),
            )

            self.assertEqual(
                [item.tool.id for item in resolved.tools],
                [
                    "apply_patch",
                    "brave_search.news_search",
                    *self._BROWSER_TOOL_IDS,
                    "echo",
                    "edit",
                    "exec",
                    "memory_read",
                    "memory_search",
                    "memory_write_daily",
                    *self._MOBILE_TOOL_IDS,
                    "open_meteo_weather.forecast_weather",
                    *self._OPENAI_IMAGE_TOOL_IDS,
                    "process",
                    "read",
                    *self._SESSION_TOOL_IDS,
                    "skill_read",
                    *self._POST_SKILL_SESSION_TOOL_IDS,
                    "workspace_list",
                    "workspace_search",
                    "write",
                ],
            )
            weather_tool = resolved.by_name("open_meteo_weather.forecast_weather")
            self.assertIsNotNone(weather_tool)
            assert weather_tool is not None
            execution = container.orchestration_inspection_service.decide_tool_execution(
                container.orchestration_run_query_service.get_run(run.id),
                tool=weather_tool.tool,
                target=weather_tool.target,
            )
            self.assertEqual(execution.mode, "approval_required")
            self.assertIsNotNone(execution.approval)
            assert execution.approval is not None
            self.assertEqual(execution.approval.id, "weather_data")
        finally:
            custom_harness.close()

    def test_tool_resolver_applies_authorized_effect_access(self) -> None:
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
                    instruction_policy=AgentInstructionPolicy(system_prompt="Be helpful."),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )
            container.tool_service.register(
                RegisterToolInput(
                    id="brave_search.news_search",
                    name="News Search",
                    description="Search news.",
                    supported_environments=(ToolEnvironment.REMOTE,),
                    required_effect_ids=("network_search",),
                ),
            )
            container.tool_service.register(
                RegisterToolInput(
                    id="open_meteo_weather.forecast_weather",
                    name="Forecast Weather",
                    description="Get weather data.",
                    supported_environments=(ToolEnvironment.REMOTE,),
                    required_effect_ids=("weather_data",),
                ),
            )
            container.authorization_service.grant_agent_effect_access(
                agent_id="assistant",
                effect_id="network_search",
            )

            run = container.orchestration_intake_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-effect-access-allow",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.orchestration_intake_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )

            resolved = container.orchestration_inspection_service.resolve_tools(
                container.orchestration_run_query_service.get_run(run.id),
            )

            self.assertEqual(
                [item.tool.id for item in resolved.tools],
                [
                    "apply_patch",
                    "brave_search.news_search",
                    *self._BROWSER_TOOL_IDS,
                    "echo",
                    "edit",
                    "exec",
                    "memory_read",
                    "memory_search",
                    "memory_write_daily",
                    *self._MOBILE_TOOL_IDS,
                    "open_meteo_weather.forecast_weather",
                    *self._OPENAI_IMAGE_TOOL_IDS,
                    "process",
                    "read",
                    *self._SESSION_TOOL_IDS,
                    "skill_read",
                    *self._POST_SKILL_SESSION_TOOL_IDS,
                    "workspace_list",
                    "workspace_search",
                    "write",
                ],
            )
            search_tool = resolved.by_name("brave_search.news_search")
            weather_tool = resolved.by_name("open_meteo_weather.forecast_weather")
            self.assertIsNotNone(search_tool)
            self.assertIsNotNone(weather_tool)
            assert search_tool is not None
            assert weather_tool is not None
            search_execution = (
                container.orchestration_inspection_service.decide_tool_execution(
                    container.orchestration_run_query_service.get_run(run.id),
                    tool=search_tool.tool,
                    target=search_tool.target,
                )
            )
            weather_execution = (
                container.orchestration_inspection_service.decide_tool_execution(
                    container.orchestration_run_query_service.get_run(run.id),
                    tool=weather_tool.tool,
                    target=weather_tool.target,
                )
            )
            self.assertEqual(search_execution.mode, "allow")
            self.assertEqual(weather_execution.mode, "approval_required")
        finally:
            custom_harness.close()

    def test_tool_resolver_blocks_tool_when_authorization_explicitly_denies_tool_access(self) -> None:
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
                    instruction_policy=AgentInstructionPolicy(system_prompt="Be helpful."),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )
            container.tool_service.register(
                RegisterToolInput(
                    id="echo",
                    name="Echo",
                    description="Echo input.",
                ),
            )
            container.tool_service.register(
                RegisterToolInput(
                    id="filesystem.read_text",
                    name="Read Text",
                    description="Read a file.",
                ),
            )
            container.authorization_service.upsert_policy(
                AuthorizationPolicy(
                    id="deny_echo_tool_access",
                    description="Do not expose echo to this agent.",
                    effect=AuthorizationEffect.DENY,
                    actions=("tool.access_tool",),
                    resource_kind="tool",
                    resource_id="echo",
                    context_match={"agent_id": "assistant"},
                    priority=1000,
                ),
            )

            run = container.orchestration_intake_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-tool-access-deny",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.orchestration_intake_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )

            resolved = container.orchestration_inspection_service.resolve_tools(
                container.orchestration_run_query_service.get_run(run.id),
            )

            self.assertEqual(
                [item.tool.id for item in resolved.tools],
                [
                    "apply_patch",
                    *self._BROWSER_TOOL_IDS,
                    "edit",
                    "exec",
                    "filesystem.read_text",
                    "memory_read",
                    "memory_search",
                    "memory_write_daily",
                    *self._MOBILE_TOOL_IDS,
                    *self._OPENAI_IMAGE_TOOL_IDS,
                    "process",
                    "read",
                    *self._SESSION_TOOL_IDS,
                    "skill_read",
                    *self._POST_SKILL_SESSION_TOOL_IDS,
                    "workspace_list",
                    "workspace_search",
                    "write",
                ],
            )
        finally:
            custom_harness.close()

    def test_tool_resolver_blocks_tool_when_authorization_explicitly_denies_effect_access(self) -> None:
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
                    instruction_policy=AgentInstructionPolicy(system_prompt="Be helpful."),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )
            container.tool_service.register(
                RegisterToolInput(
                    id="brave_search.news_search",
                    name="News Search",
                    description="Search news.",
                    supported_environments=(ToolEnvironment.REMOTE,),
                    required_effect_ids=("network_search",),
                ),
            )
            container.authorization_service.upsert_policy(
                AuthorizationPolicy(
                    id="deny_network_search_effect_access",
                    description="Do not expose network search to this agent.",
                    effect=AuthorizationEffect.DENY,
                    actions=("tool.access_effect",),
                    resource_kind="tool",
                    resource_match={"authorization_effect_ids": ["network_search"]},
                    context_match={"agent_id": "assistant"},
                    priority=1000,
                ),
            )

            run = container.orchestration_intake_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-effect-access-deny",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.orchestration_intake_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )

            resolved = container.orchestration_inspection_service.resolve_tools(
                container.orchestration_run_query_service.get_run(run.id),
            )

            self.assertEqual(
                [item.tool.id for item in resolved.tools],
                [
                    "apply_patch",
                    *self._BROWSER_TOOL_IDS,
                    "echo",
                    "edit",
                    "exec",
                    "memory_read",
                    "memory_search",
                    "memory_write_daily",
                    *self._MOBILE_TOOL_IDS,
                    *self._OPENAI_IMAGE_TOOL_IDS,
                    "process",
                    "read",
                    *self._SESSION_TOOL_IDS,
                    "skill_read",
                    *self._POST_SKILL_SESSION_TOOL_IDS,
                    "workspace_list",
                    "workspace_search",
                    "write",
                ],
            )
        finally:
            custom_harness.close()

    def test_tool_resolver_includes_workspace_read_when_session_has_workspace(self) -> None:
        workspace_dir = tempfile.TemporaryDirectory()
        self.addCleanup(workspace_dir.cleanup)
        Path(workspace_dir.name, "README.md").write_text(
            "# Workspace\n\nhello\n",
            encoding="utf-8",
        )
        self._register_agent_and_llm(
            runtime_preferences=AgentRuntimePreferences(workspace=workspace_dir.name),
        )

        run = self.container.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-workspace-read-visible",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        self.container.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )

        resolved = self.container.orchestration_inspection_service.resolve_tools(
            self.container.orchestration_run_query_service.get_run(run.id),
        )

        tool_ids = [item.tool.id for item in resolved.tools]
        self.assertIn("apply_patch", tool_ids)
        self.assertIn("edit", tool_ids)
        self.assertIn("exec", tool_ids)
        self.assertIn("process", tool_ids)
        self.assertIn("read", tool_ids)
        self.assertIn("write", tool_ids)
        self.assertIn("workspace_list", tool_ids)
        self.assertIn("workspace_search", tool_ids)
        apply_patch_tool = resolved.by_name("apply_patch")
        edit_tool = resolved.by_name("edit")
        exec_tool = resolved.by_name("exec")
        process_tool = resolved.by_name("process")
        read_tool = resolved.by_name("read")
        write_tool = resolved.by_name("write")
        list_tool = resolved.by_name("workspace_list")
        search_tool = resolved.by_name("workspace_search")
        self.assertIsNotNone(apply_patch_tool)
        self.assertIsNotNone(edit_tool)
        self.assertIsNotNone(exec_tool)
        self.assertIsNotNone(process_tool)
        self.assertIsNotNone(read_tool)
        self.assertIsNotNone(write_tool)
        self.assertIsNotNone(list_tool)
        self.assertIsNotNone(search_tool)
        assert apply_patch_tool is not None
        assert edit_tool is not None
        assert exec_tool is not None
        assert process_tool is not None
        assert read_tool is not None
        assert write_tool is not None
        assert list_tool is not None
        assert search_tool is not None
        self.assertIn("scope:workspace_bound", apply_patch_tool.tool.tags)
        self.assertEqual(apply_patch_tool.tool.required_effect_ids, ("workspace_write",))
        self.assertIn("scope:workspace_bound", edit_tool.tool.tags)
        self.assertEqual(edit_tool.tool.required_effect_ids, ("workspace_write",))
        self.assertEqual(exec_tool.tool.required_effect_ids, ("command_execution",))
        self.assertEqual(process_tool.tool.required_effect_ids, ("command_execution",))
        self.assertIn("scope:workspace_bound", read_tool.tool.tags)
        self.assertEqual(read_tool.tool.required_effect_ids, ("workspace_read",))
        self.assertIn("scope:workspace_bound", write_tool.tool.tags)
        self.assertEqual(write_tool.tool.required_effect_ids, ("workspace_write",))
        self.assertIn("scope:workspace_bound", list_tool.tool.tags)
        self.assertEqual(list_tool.tool.required_effect_ids, ("workspace_read",))
        self.assertIn("scope:workspace_bound", search_tool.tool.tags)
        self.assertEqual(search_tool.tool.required_effect_ids, ("workspace_read",))
        exec_execution = self.container.orchestration_inspection_service.decide_tool_execution(
            self.container.orchestration_run_query_service.get_run(run.id),
            tool=exec_tool.tool,
            target=exec_tool.target,
        )
        self.assertEqual(exec_execution.mode, "approval_required")
        self.assertIsNotNone(exec_execution.approval)
        assert exec_execution.approval is not None
        self.assertEqual(exec_execution.approval.id, "command_execution")

    def test_effect_request_waits_for_confirmation_and_resumes_after_allow_once(self) -> None:
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="local-capability",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        self.container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="writer",
                name="Writer",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Use tools when needed.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="local-capability"),
            ),
        )

        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="echo",
                name="Echo",
                description="Echoes a message.",
                supported_modes=(ToolMode.INLINE,),
                runtime_key="echo",
                required_effect_ids=("local_tool_access",),
            ),
        )

        async def echo(arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={"echo": arguments.get("message")},
            )

        self.container.local_tool_catalog.register(tool, echo)
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _EffectApprovalAdapter(),
        )

        run = self.container.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-capability-approval",
                inbound_instruction=InboundInstruction(source="cli", content="complete the task"),
            ),
        )
        self.container.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="writer",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        waiting = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert waiting is not None
        self.assertEqual(waiting.status, OrchestrationRunStatus.WAITING)
        self.assertEqual(waiting.stage, OrchestrationRunStage.WAITING_FOR_CONFIRMATION)
        pending_request = waiting.pending_approval_request()
        self.assertIsNotNone(pending_request)
        assert pending_request is not None
        self.assertEqual(pending_request.effect_id, "local_tool_access")
        self.assertEqual(pending_request.tool_ids, ("echo",))
        self.assertEqual(pending_request.tool_name, "echo")

        resumed = self.container.orchestration_approval_control_service.resolve_approval_request(
            ResolveApprovalRequestInput(
                run_id=run.id,
                request_id=pending_request.request_id,
                decision=ApprovalDecision.ALLOW_ONCE,
            ),
        )
        self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)

        completed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert completed is not None
        self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
        assert completed.result_payload is not None
        self.assertEqual(completed.result_payload.get("output_text"), "approval flow complete")

    def test_process_next_orchestration_assignment_includes_approval_resume_flow_prompt(self) -> None:
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="local-capability",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        self.container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="writer",
                name="Writer",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Write carefully.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(
                    default_llm_id="local-capability",
                ),
            ),
        )
        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="echo",
                name="Echo",
                description="Returns the input payload for local inline execution tests.",
                supported_modes=(ToolMode.INLINE,),
                runtime_key="echo",
                required_effect_ids=("local_tool_access",),
            ),
        )

        async def echo(arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={"echo": arguments.get("message")},
            )

        self.container.local_tool_catalog.register(tool, echo)
        adapter = _EffectApprovalAdapter()
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )

        run = self.container.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-approval-resume-flow-prompt",
                inbound_instruction=InboundInstruction(source="cli", content="complete the task"),
            ),
        )
        self.container.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="writer",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        waiting = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert waiting is not None
        pending_request = waiting.pending_approval_request()
        assert pending_request is not None

        self.container.orchestration_approval_control_service.resolve_approval_request(
            ResolveApprovalRequestInput(
                run_id=run.id,
                request_id=pending_request.request_id,
                decision=ApprovalDecision.ALLOW_ONCE,
            ),
        )
        completed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
        self.assertGreaterEqual(len(adapter.requests), 2)
        resume_system_messages = [
            message
            for message in adapter.requests[1].messages
            if message.role is LlmMessageRole.SYSTEM
        ]
        self.assertTrue(
            any(
                "# Approval Update" in str(message.content)
                and "approved the requested additional access" in str(message.content)
                and "valid only for the current turn" in str(message.content)
                for message in resume_system_messages
            ),
        )
        refreshed_run = self.container.orchestration_run_query_service.get_run(run.id)
        session_messages = self.container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key=str(refreshed_run.metadata["session_key"]),
            ),
        )
        self.assertTrue(
            any(
                message.kind is SessionMessageKind.TOOL_RESULT
                and message.source_kind == "approval_request"
                and str(message.content_payload).find("running echo") >= 0
                and str(message.content_payload).find("must be requested again later") >= 0
                for message in session_messages
            ),
        )

    def test_approval_does_not_persist_unprocessed_tool_calls_from_same_invocation(self) -> None:
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="local-capability",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        self.container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="writer",
                name="Writer",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Use tools when needed.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="local-capability"),
            ),
        )

        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="echo",
                name="Echo",
                description="Echoes a message.",
                supported_modes=(ToolMode.INLINE,),
                runtime_key="echo",
                required_effect_ids=("local_tool_access",),
            ),
        )

        async def echo(arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={"echo": arguments.get("message")},
            )

        self.container.local_tool_catalog.register(tool, echo)
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _MultiToolApprovalAdapter(),
        )

        run = self.container.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-multi-tool-approval",
                inbound_instruction=InboundInstruction(source="cli", content="complete the task"),
            ),
        )
        self.container.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="writer",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        waiting = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert waiting is not None
        pending_request = waiting.pending_approval_request()
        assert pending_request is not None
        self.assertEqual(pending_request.request_id, "call-echo-1")

        session_messages = self.container.session_service.list_messages(
            ListSessionMessagesInput(
                session_key=str(waiting.metadata["session_key"]),
            ),
        )
        function_call_ids = [
            str(message.metadata.get("tool_call_id", "")).strip()
            for message in session_messages
            if message.role == "assistant"
            and message.content_payload.get("type") == "function_call"
        ]
        self.assertEqual(function_call_ids, ["call-echo-1"])

    def test_recover_abandoned_runs_continues_resolved_approval_recovery(self) -> None:
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="local-capability",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        self.container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="writer",
                name="Writer",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Use tools when needed.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="local-capability"),
            ),
        )

        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="echo",
                name="Echo",
                description="Echoes a message.",
                supported_modes=(ToolMode.INLINE,),
                runtime_key="echo",
                required_effect_ids=("local_tool_access",),
            ),
        )

        async def echo(arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={"echo": arguments.get("message")},
            )

        self.container.local_tool_catalog.register(tool, echo)
        adapter = _EffectApprovalAdapter()
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )

        run = self.container.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-approval-recovery-contract",
                inbound_instruction=InboundInstruction(source="cli", content="complete the task"),
            ),
        )
        self.container.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="writer",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        waiting = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert waiting is not None
        pending_request = waiting.pending_approval_request()
        assert pending_request is not None

        wait_coordinator = (
            self.container.orchestration_approval_control_service.resolve_approval_request_fn.__self__
        )
        with patch.object(
            wait_coordinator,
            "continue_recovery_contract_fn",
            lambda run_id: self.container.orchestration_run_query_service.get_run(run_id),
        ):
            stalled = self.container.orchestration_approval_control_service.resolve_approval_request(
                ResolveApprovalRequestInput(
                    run_id=run.id,
                    request_id=pending_request.request_id,
                    decision=ApprovalDecision.ALLOW_ONCE,
                ),
            )

        self.assertEqual(stalled.status, OrchestrationRunStatus.WAITING)
        self.assertEqual(stalled.stage, OrchestrationRunStage.WAITING_FOR_CONFIRMATION)
        recovery_contract = stalled.metadata.get("recovery_contract")
        assert isinstance(recovery_contract, dict)
        self.assertEqual(recovery_contract.get("kind"), "approval")
        self.assertEqual(recovery_contract.get("state"), "resolved_allow_pending_replay")

        recovered = (
            self.container.orchestration_scheduler_service.recover_abandoned_runs()
        )
        self.assertTrue(any(item.id == run.id for item in recovered))

        resumed = self.container.orchestration_run_query_service.get_run(run.id)
        self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)
        self.assertEqual(resumed.stage, OrchestrationRunStage.QUEUED)

        completed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert completed is not None
        self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(completed.result_payload.get("output_text"), "approval flow complete")

    def test_process_next_orchestration_assignment_includes_approval_denied_flow_prompt(self) -> None:
        self.container.llm_service.register_profile(
            RegisterLlmProfileInput(
                id="local-capability",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )
        self.container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="writer",
                name="Writer",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Write carefully.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(
                    default_llm_id="local-capability",
                ),
            ),
        )
        tool = self.container.tool_service.register(
            RegisterToolInput(
                id="echo",
                name="Echo",
                description="Returns the input payload for local inline execution tests.",
                supported_modes=(ToolMode.INLINE,),
                runtime_key="echo",
                required_effect_ids=("local_tool_access",),
            ),
        )

        async def echo(arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={"echo": arguments.get("message")},
            )

        self.container.local_tool_catalog.register(tool, echo)
        adapter = _EffectDeniedFallbackAdapter()
        self.container.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )

        run = self.container.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-approval-denied-flow-prompt",
                inbound_instruction=InboundInstruction(source="cli", content="complete the task"),
            ),
        )
        self.container.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="writer",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.container.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        waiting = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert waiting is not None
        pending_request = waiting.pending_approval_request()
        assert pending_request is not None

        resumed = self.container.orchestration_approval_control_service.resolve_approval_request(
            ResolveApprovalRequestInput(
                run_id=run.id,
                request_id=pending_request.request_id,
                decision=ApprovalDecision.DENY,
            ),
        )
        self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)

        completed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )

        self.assertIsNotNone(completed)
        assert completed is not None
        self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(completed.result_payload["output_text"], "fallback after denial")
        denied_system_messages = [
            message
            for message in adapter.requests[1].messages
            if message.role is LlmMessageRole.SYSTEM
        ]
        self.assertTrue(
            any(
                "# Approval Update" in str(message.content)
                and "denied the requested additional access" in str(message.content)
                for message in denied_system_messages
            ),
        )

    def test_allow_for_agent_persists_auth_rule_without_mutating_agent_profile(self) -> None:
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
            container.llm_service.register_profile(
                RegisterLlmProfileInput(
                    id="local-capability",
                    provider=LlmProviderKind.OPENAI,
                    api_family=LlmApiFamily.OPENAI_RESPONSES,
                    model_name="gpt-5.4-mini",
                ),
            )
            container.agent_service.register_profile(
                RegisterAgentProfileInput(
                    id="writer",
                    name="Writer",
                    instruction_policy=AgentInstructionPolicy(
                        system_prompt="Use tools when needed.",
                    ),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="local-capability",
                    ),
                ),
            )

            tool = container.tool_service.register(
                RegisterToolInput(
                    id="echo",
                    name="Echo",
                    description="Echoes a message.",
                    supported_modes=(ToolMode.INLINE,),
                    runtime_key="echo",
                    required_effect_ids=("local_tool_access",),
                ),
            )

            async def echo(arguments: dict[str, object]) -> ToolRunResult:
                return ToolRunResult.text(
                    str(arguments.get("message") or ""),
                    details={"echo": arguments.get("message")},
                )

            container.local_tool_catalog.register(tool, echo)
            container.llm_adapter_registry.register(
                LlmApiFamily.OPENAI_RESPONSES,
                _EffectApprovalOrVisibleAdapter(),
            )

            run = container.orchestration_intake_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-effect-agent-approval",
                    inbound_instruction=InboundInstruction(
                        source="cli",
                        content="complete the task",
                    ),
                ),
            )
            container.orchestration_intake_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="writer",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.orchestration_intake_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            waiting = process_next_orchestration_assignment(container,
                worker_id="worker-1",
            )
            assert waiting is not None
            pending_request = waiting.pending_approval_request()
            assert pending_request is not None

            resumed = container.orchestration_approval_control_service.resolve_approval_request(
                ResolveApprovalRequestInput(
                    run_id=run.id,
                    request_id=pending_request.request_id,
                    decision=ApprovalDecision.ALWAYS_FOR_AGENT,
                ),
            )
            self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)

            policies = container.authorization_service.list_policies()
            self.assertTrue(
                any(policy.actions == ("tool.access_effect",) for policy in policies),
            )

            completed = process_next_orchestration_assignment(container,
                worker_id="worker-1",
            )
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)

            followup = container.orchestration_intake_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-effect-agent-followup",
                    inbound_instruction=InboundInstruction(
                        source="cli",
                        content="complete the follow-up task",
                    ),
                ),
            )
            followup = container.orchestration_intake_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=followup.id,
                    context=SessionRouteContext(
                        agent_id="writer",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            resolved = container.orchestration_inspection_service.resolve_tools(followup)

            self.assertIsNotNone(resolved.by_name("echo"))
        finally:
            custom_harness.close()

    def test_background_tool_call_can_wait_for_approval_then_transition_to_tool_wait(self) -> None:
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

            run = container.orchestration_intake_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-background-approval",
                    inbound_instruction=InboundInstruction(source="cli", content="search"),
                ),
            )
            container.orchestration_intake_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.orchestration_intake_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            waiting_for_approval = process_next_orchestration_assignment(container,
                worker_id="worker-1",
            )
            self.assertIsNotNone(waiting_for_approval)
            assert waiting_for_approval is not None
            self.assertEqual(
                waiting_for_approval.stage,
                OrchestrationRunStage.WAITING_FOR_CONFIRMATION,
            )
            pending_request = waiting_for_approval.pending_approval_request()
            self.assertIsNotNone(pending_request)
            assert pending_request is not None
            self.assertEqual(pending_request.effect_id, "background_execution")
            self.assertEqual(pending_request.tool_name, "background_echo")

            waiting_on_tool = container.orchestration_approval_control_service.resolve_approval_request(
                ResolveApprovalRequestInput(
                    run_id=run.id,
                    request_id=pending_request.request_id,
                    decision=ApprovalDecision.ALLOW_ONCE,
                ),
            )
            self.assertEqual(waiting_on_tool.status, OrchestrationRunStatus.WAITING)
            self.assertEqual(waiting_on_tool.stage, OrchestrationRunStage.WAITING_ON_TOOL)
            self.assertEqual(waiting_on_tool.waiting_reason, "tool_background_wait")
            self.assertEqual(len(waiting_on_tool.pending_tool_run_ids), 1)

            finished_tool_run = process_next_background_tool_run(
                container,
                worker_id="tool-worker-1",
            )
            self.assertIsNotNone(finished_tool_run)
            assert finished_tool_run is not None
            self.assertEqual(finished_tool_run.status, ToolRunStatus.SUCCEEDED)
            container.orchestration_scheduler_service.process_runtime_events(
                limit_per_subscription=10,
            )
            processed_signal = container.orchestration_scheduler_service.process_next_signal(
                worker_id="scheduler-1",
            )
            self.assertIsNotNone(processed_signal)

            resumed = container.orchestration_run_query_service.get_run(run.id)
            self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)
            self.assertEqual(resumed.stage, OrchestrationRunStage.QUEUED)

            completed = process_next_orchestration_assignment(container,
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

    def test_approval_replay_fails_if_stored_target_is_no_longer_supported(self) -> None:
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

            run = container.orchestration_intake_service.accept(
                AcceptOrchestrationRunInput(
                    run_id="run-background-approval-target-mismatch",
                    inbound_instruction=InboundInstruction(source="cli", content="search"),
                ),
            )
            container.orchestration_intake_service.prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.orchestration_intake_service.enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            waiting_for_approval = process_next_orchestration_assignment(container,
                worker_id="worker-1",
            )
            self.assertIsNotNone(waiting_for_approval)
            assert waiting_for_approval is not None
            pending_request = waiting_for_approval.pending_approval_request()
            self.assertIsNotNone(pending_request)
            assert pending_request is not None
            self.assertEqual(pending_request.tool_name, "background_echo")
            self.assertEqual(pending_request.execution_mode, ToolMode.BACKGROUND.value)

            container.tool_service.catalog_service._manual_tools["background_echo"] = replace(
                tool,
                execution_support=ToolExecutionSupport(
                    supported_modes=(ToolMode.INLINE,),
                    supported_strategies=tool.execution_support.supported_strategies,
                    supported_environments=tool.execution_support.supported_environments,
                ),
            )

            with self.assertRaises(OrchestrationValidationError) as exc_info:
                container.orchestration_approval_control_service.resolve_approval_request(
                    ResolveApprovalRequestInput(
                        run_id=run.id,
                        request_id=pending_request.request_id,
                        decision=ApprovalDecision.ALLOW_ONCE,
                    ),
                )
            self.assertIn(
                "Approved tool replay target is no longer supported",
                str(exc_info.exception),
            )
        finally:
            custom_harness.close()
