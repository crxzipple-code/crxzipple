from __future__ import annotations

from crxzipple.modules.authorization.domain import (
    AuthorizationContext,
    AuthorizationResource,
    AuthorizationSubject,
    ToolExecutionAuthorizationRequest,
)
from crxzipple.modules.orchestration.application.approval import ApprovalResolutionService
from crxzipple.modules.orchestration.infrastructure.adapters import (
    AuthorizationServiceAdapter,
)
from crxzipple.modules.tool.domain import ToolExecutionNotAllowedError, ToolRunResult

from tests.unit.orchestration_test_support import *  # noqa: F403
from tests.unit.tool_runtime_test_support import process_next_background_tool_run


class OrchestrationApprovalTestCase(OrchestrationTestCaseBase):
    def _register_test_openai_profile(self, container, *, profile_id: str) -> None:
        credential_binding_id = self._install_default_llm_access_binding(container)
        container.require(AppKey.LLM_SERVICE).register_profile(
            RegisterLlmProfileInput(
                id=profile_id,
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
                credential_binding_id=credential_binding_id,
            ),
        )

    def test_approval_session_grant_writes_temporary_authorization(self) -> None:
        self._register_agent_and_llm()
        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-session-access-grant",
                inbound_instruction=InboundInstruction(source="cli", content="hello"),
            ),
        )
        prepared = self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        session_key = str(prepared.metadata.get("session_key") or "")
        approval_service = ApprovalResolutionService(
            authorization_port=AuthorizationServiceAdapter(
                self.authorization_service,
            ),
            session_service=None,
            get_run=self.orchestration_run_query_service.get_run,
        )

        approval_service.grant_session_tool_authorization(
            run_id=run.id,
            approval_request_id="approval-session",
            effect_ids=("local_tool_access",),
            tool_ids=("echo",),
        )

        decision = self.authorization_service.check_tool_execution(
            ToolExecutionAuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="llm"),
                resource=AuthorizationResource(
                    kind="tool",
                    id="echo",
                    attrs={"authorization_effect_ids": ["local_tool_access"]},
                ),
                context=AuthorizationContext(
                    attrs={"agent_id": "assistant", "session_key": session_key},
                ),
                required_effect_ids=("local_tool_access",),
            ),
        )
        self.assertTrue(decision.allowed)
        self.assertIn("local_tool_access", decision.details["granted_effect_ids"])

    def test_tool_execution_decision_uses_browser_profile_argument_context(self) -> None:
        self._register_agent_and_llm()
        self.authorization_service.upsert_policy(
            AuthorizationPolicy(
                id="deny_orchestration_user_browser_profile",
                description="Block orchestration browser tool calls against user profile.",
                effect=AuthorizationEffect.DENY,
                actions=("tool.run",),
                resource_kind="tool",
                resource_match={"source_id": "bundled.local_package.browser"},
                context_match={"browser_profile": "user"},
                priority=1000,
            ),
        )
        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-browser-profile-deny",
                inbound_instruction=InboundInstruction(source="cli", content="open page"),
            ),
        )
        prepared = self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="assistant",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        bound_run = self.orchestration_run_query_service.get_run(run.id)
        resolved_tools = self.orchestration_inspection_service.resolve_tools(bound_run)
        self.assertIsNotNone(resolved_tools.by_name("browser.navigate"))

        with self.assertRaises(OrchestrationValidationError):
            asyncio.run(
                self.orchestration_inspection_service.engine.tool_executor.execute_tool_calls_async(
                    bound_run,
                    session_key=str(prepared.metadata.get("session_key") or ""),
                    active_session_id=bound_run.active_session_id or "",
                    resolved_tools=resolved_tools,
                    tool_calls=(
                        ToolCallIntent(
                            id="call-browser-profile-deny",
                            name="browser.navigate",
                            arguments={
                                "profile": "user",
                                "url": "https://example.com",
                            },
                        ),
                    ),
                    append_tool_call_messages=False,
                    append_tool_result_messages=False,
                ),
            )

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

        self.orchestration_inspection_service.engine.tool_resolver.run_context_provider = (
            run_context_provider
        )
        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-tool-context-cache",
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

        resolved = self.orchestration_inspection_service.resolve_tools(
            self.orchestration_run_query_service.get_run(run.id),
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
        container = custom_harness.build_runtime_container(settings=settings)
        try:
            self._register_test_openai_profile(
                container,
                profile_id="openai.gpt-5.4-mini",
            )
            container.require(AppKey.AGENT_SERVICE).register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(system_prompt="Be helpful."),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )
            seed_catalog_tool(
                container,
                tool_id="brave_search.news_search",
                name="News Search",
                description="Search news.",
                supported_environments=(ToolEnvironment.REMOTE,),
                required_effect_ids=("network_search",),
            )
            seed_catalog_tool(
                container,
                tool_id="open_meteo_weather.forecast_weather",
                name="Forecast Weather",
                description="Get weather data.",
                supported_environments=(ToolEnvironment.REMOTE,),
                required_effect_ids=("weather_data",),
            )
            AuthorizationServiceAdapter(
                container.require(AppKey.AUTHORIZATION_SERVICE),
            ).grant_agent_tool_authorization(
                agent_id="assistant",
                tool_id="brave_search.news_search",
            )

            run = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-tool-access-allow",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )

            resolved = container.require(AppKey.ORCHESTRATION_INSPECTION_SERVICE).resolve_tools(
                container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).get_run(run.id),
            )

            resolved_tool_ids = {item.tool.id for item in resolved.tools}
            self.assertIn("brave_search.news_search", resolved_tool_ids)
            self.assertIn("open_meteo_weather.forecast_weather", resolved_tool_ids)
            self.assertIn("read", resolved_tool_ids)
            weather_tool = resolved.by_name("open_meteo_weather.forecast_weather")
            self.assertIsNotNone(weather_tool)
            assert weather_tool is not None
            execution = container.require(AppKey.ORCHESTRATION_INSPECTION_SERVICE).decide_tool_execution(
                container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).get_run(run.id),
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
        container = custom_harness.build_runtime_container(settings=settings)
        try:
            self._register_test_openai_profile(
                container,
                profile_id="openai.gpt-5.4-mini",
            )
            container.require(AppKey.AGENT_SERVICE).register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(system_prompt="Be helpful."),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )
            seed_catalog_tool(
                container,
                tool_id="brave_search.news_search",
                name="News Search",
                description="Search news.",
                supported_environments=(ToolEnvironment.REMOTE,),
                required_effect_ids=("network_search",),
            )
            seed_catalog_tool(
                container,
                tool_id="open_meteo_weather.forecast_weather",
                name="Forecast Weather",
                description="Get weather data.",
                supported_environments=(ToolEnvironment.REMOTE,),
                required_effect_ids=("weather_data",),
            )
            AuthorizationServiceAdapter(
                container.require(AppKey.AUTHORIZATION_SERVICE),
            ).grant_agent_effect_authorization(
                agent_id="assistant",
                effect_id="network_search",
            )

            run = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-effect-access-allow",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )

            resolved = container.require(AppKey.ORCHESTRATION_INSPECTION_SERVICE).resolve_tools(
                container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).get_run(run.id),
            )

            resolved_tool_ids = {item.tool.id for item in resolved.tools}
            self.assertIn("brave_search.news_search", resolved_tool_ids)
            self.assertIn("open_meteo_weather.forecast_weather", resolved_tool_ids)
            self.assertIn("read", resolved_tool_ids)
            search_tool = resolved.by_name("brave_search.news_search")
            weather_tool = resolved.by_name("open_meteo_weather.forecast_weather")
            self.assertIsNotNone(search_tool)
            self.assertIsNotNone(weather_tool)
            assert search_tool is not None
            assert weather_tool is not None
            search_execution = (
                container.require(AppKey.ORCHESTRATION_INSPECTION_SERVICE).decide_tool_execution(
                    container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).get_run(run.id),
                    tool=search_tool.tool,
                    target=search_tool.target,
                )
            )
            weather_execution = (
                container.require(AppKey.ORCHESTRATION_INSPECTION_SERVICE).decide_tool_execution(
                    container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).get_run(run.id),
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
        container = custom_harness.build_runtime_container(settings=settings)
        try:
            self._register_test_openai_profile(
                container,
                profile_id="openai.gpt-5.4-mini",
            )
            container.require(AppKey.AGENT_SERVICE).register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(system_prompt="Be helpful."),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )
            seed_catalog_tool(
                container,
                tool_id="echo",
                name="Echo",
                description="Echo input.",
            )
            seed_catalog_tool(
                container,
                tool_id="filesystem.read_text",
                name="Read Text",
                description="Read a file.",
            )
            container.require(AppKey.AUTHORIZATION_SERVICE).upsert_policy(
                AuthorizationPolicy(
                    id="deny_echo_tool_access",
                    description="Do not expose echo to this agent.",
                    effect=AuthorizationEffect.DENY,
                    actions=("tool.authorize",),
                    resource_kind="tool",
                    resource_id="echo",
                    context_match={"agent_id": "assistant"},
                    priority=1000,
                ),
            )

            run = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-tool-access-deny",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )

            resolved = container.require(AppKey.ORCHESTRATION_INSPECTION_SERVICE).resolve_tools(
                container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).get_run(run.id),
            )

            resolved_tool_ids = {item.tool.id for item in resolved.tools}
            self.assertNotIn("echo", resolved_tool_ids)
            self.assertIn("filesystem.read_text", resolved_tool_ids)
            self.assertIn("read", resolved_tool_ids)
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
        container = custom_harness.build_runtime_container(settings=settings)
        try:
            self._register_test_openai_profile(
                container,
                profile_id="openai.gpt-5.4-mini",
            )
            container.require(AppKey.AGENT_SERVICE).register_profile(
                RegisterAgentProfileInput(
                    id="assistant",
                    name="Assistant",
                    instruction_policy=AgentInstructionPolicy(system_prompt="Be helpful."),
                    llm_routing_policy=AgentLlmRoutingPolicy(
                        default_llm_id="openai.gpt-5.4-mini",
                    ),
                ),
            )
            seed_catalog_tool(
                container,
                tool_id="brave_search.news_search",
                name="News Search",
                description="Search news.",
                supported_environments=(ToolEnvironment.REMOTE,),
                required_effect_ids=("network_search",),
            )
            container.require(AppKey.AUTHORIZATION_SERVICE).upsert_policy(
                AuthorizationPolicy(
                    id="deny_network_search_effect_access",
                    description="Do not expose network search to this agent.",
                    effect=AuthorizationEffect.DENY,
                    actions=("tool.effect.authorize",),
                    resource_kind="tool",
                    resource_match={"authorization_effect_ids": ["network_search"]},
                    context_match={"agent_id": "assistant"},
                    priority=1000,
                ),
            )

            run = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-effect-access-deny",
                    inbound_instruction=InboundInstruction(source="cli", content="hello"),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )

            resolved = container.require(AppKey.ORCHESTRATION_INSPECTION_SERVICE).resolve_tools(
                container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).get_run(run.id),
            )

            resolved_tool_ids = {item.tool.id for item in resolved.tools}
            self.assertNotIn("brave_search.news_search", resolved_tool_ids)
            self.assertIn("read", resolved_tool_ids)
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

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-workspace-read-visible",
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

        resolved = self.orchestration_inspection_service.resolve_tools(
            self.orchestration_run_query_service.get_run(run.id),
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
        exec_execution = self.orchestration_inspection_service.decide_tool_execution(
            self.orchestration_run_query_service.get_run(run.id),
            tool=exec_tool.tool,
            target=exec_tool.target,
        )
        self.assertEqual(exec_execution.mode, "approval_required")
        self.assertIsNotNone(exec_execution.approval)
        assert exec_execution.approval is not None
        self.assertEqual(exec_execution.approval.id, "command_execution")

    def test_effect_request_waits_for_confirmation_and_resumes_after_allow_once(self) -> None:
        self._register_test_openai_profile(
            self.container,
            profile_id="local-capability",
        )
        self.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="writer",
                name="Writer",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Use tools when needed.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="local-capability"),
            ),
        )

        tool = self.seed_tool(
            tool_id="echo",
            name="Echo",
            description="Echoes a message.",
            supported_modes=(ToolMode.INLINE,),
            runtime_key="echo",
            required_effect_ids=("local_tool_access",),
        )

        async def echo(arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={"echo": arguments.get("message")},
            )

        self.local_runtime_registry.register(tool, echo)
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _EffectApprovalAdapter(),
        )

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-capability-approval",
                inbound_instruction=InboundInstruction(source="cli", content="complete the task"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="writer",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
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

        resumed = self.orchestration_approval_control_service.resolve_approval_request(
            ResolveApprovalRequestInput(
                run_id=run.id,
                request_id=pending_request.request_id,
                decision=ApprovalDecision.ALLOW_ONCE,
            ),
        )
        self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)

        decision = self.authorization_service.check_tool_execution(
            ToolExecutionAuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="llm"),
                resource=AuthorizationResource(
                    kind="tool",
                    id="echo",
                    attrs={"authorization_effect_ids": ["local_tool_access"]},
                ),
                context=AuthorizationContext(
                    attrs={"agent_id": "writer", "run_id": run.id},
                ),
                required_effect_ids=("local_tool_access",),
            ),
        )
        self.assertTrue(decision.allowed)
        self.assertIn("local_tool_access", decision.details["granted_effect_ids"])

        completed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert completed is not None
        self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
        assert completed.result_payload is not None
        self.assertEqual(completed.result_payload.get("output_text"), "approval flow complete")

    def test_process_next_orchestration_assignment_includes_approval_resume_flow_node(self) -> None:
        self._register_test_openai_profile(
            self.container,
            profile_id="local-capability",
        )
        self.agent_service.register_profile(
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
        tool = self.seed_tool(
            tool_id="echo",
            name="Echo",
            description="Returns the input payload for local inline execution tests.",
            supported_modes=(ToolMode.INLINE,),
            runtime_key="echo",
            required_effect_ids=("local_tool_access",),
        )

        async def echo(arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={"echo": arguments.get("message")},
            )

        self.local_runtime_registry.register(tool, echo)
        adapter = _EffectApprovalAdapter()
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-approval-resume-flow-prompt",
                inbound_instruction=InboundInstruction(source="cli", content="complete the task"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="writer",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        waiting = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert waiting is not None
        pending_request = waiting.pending_approval_request()
        assert pending_request is not None

        self.orchestration_approval_control_service.resolve_approval_request(
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
        self.assertGreaterEqual(len(adapter.requests), 3)
        resume_system_messages = [
            message
            for message in adapter.requests[-1].messages
            if message.role is LlmMessageRole.SYSTEM
        ]
        context_tree_message = next(
            message
            for message in resume_system_messages
            if message.metadata.get("prompt_block_kind") == "context_workspace"
        )
        self.assertIn("run.flow", str(context_tree_message.content))
        self.assertIn("Flow: Approval Resume", str(context_tree_message.content))
        self.assertIn("approved the requested additional access", str(context_tree_message.content))
        self.assertIn("valid only for the current turn", str(context_tree_message.content))
        self.assertFalse(
            any("# Approval Update" in str(message.content) for message in resume_system_messages),
        )
        refreshed_run = self.orchestration_run_query_service.get_run(run.id)
        session_messages = self.session_service.list_messages(
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
        self._register_test_openai_profile(
            self.container,
            profile_id="local-capability",
        )
        self.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="writer",
                name="Writer",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Use tools when needed.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="local-capability"),
            ),
        )

        tool = self.seed_tool(
            tool_id="echo",
            name="Echo",
            description="Echoes a message.",
            supported_modes=(ToolMode.INLINE,),
            runtime_key="echo",
            required_effect_ids=("local_tool_access",),
        )

        async def echo(arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={"echo": arguments.get("message")},
            )

        self.local_runtime_registry.register(tool, echo)
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _MultiToolApprovalAdapter(),
        )

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-multi-tool-approval",
                inbound_instruction=InboundInstruction(source="cli", content="complete the task"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="writer",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        waiting = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert waiting is not None
        pending_request = waiting.pending_approval_request()
        assert pending_request is not None
        self.assertEqual(pending_request.request_id, "call-echo-1")

        session_messages = self.session_service.list_messages(
            ListSessionMessagesInput(
                session_key=str(waiting.metadata["session_key"]),
            ),
        )
        function_call_ids = [
            str(message.metadata.get("tool_call_id", "")).strip()
            for message in session_messages
            if message.role == "assistant"
            and message.content_payload.get("type") == "function_call"
            and message.metadata.get("tool_name") == "echo"
        ]
        self.assertEqual(function_call_ids, ["call-echo-1"])

    def test_recover_abandoned_runs_continues_resolved_approval_recovery(self) -> None:
        self._register_test_openai_profile(
            self.container,
            profile_id="local-capability",
        )
        self.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="writer",
                name="Writer",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Use tools when needed.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="local-capability"),
            ),
        )

        tool = self.seed_tool(
            tool_id="echo",
            name="Echo",
            description="Echoes a message.",
            supported_modes=(ToolMode.INLINE,),
            runtime_key="echo",
            required_effect_ids=("local_tool_access",),
        )

        async def echo(arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={"echo": arguments.get("message")},
            )

        self.local_runtime_registry.register(tool, echo)
        adapter = _EffectApprovalAdapter()
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-approval-recovery-contract",
                inbound_instruction=InboundInstruction(source="cli", content="complete the task"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="writer",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        waiting = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert waiting is not None
        pending_request = waiting.pending_approval_request()
        assert pending_request is not None

        wait_coordinator = (
            self.orchestration_approval_control_service.resolve_approval_request_fn.__self__
        )
        with patch.object(
            wait_coordinator,
            "continue_recovery_contract_fn",
            lambda run_id: self.orchestration_run_query_service.get_run(run_id),
        ):
            stalled = self.orchestration_approval_control_service.resolve_approval_request(
                ResolveApprovalRequestInput(
                    run_id=run.id,
                    request_id=pending_request.request_id,
                    decision=ApprovalDecision.ALLOW_ONCE,
                ),
            )

        self.assertEqual(stalled.status, OrchestrationRunStatus.WAITING)
        self.assertEqual(stalled.stage, OrchestrationRunStage.WAITING_FOR_CONFIRMATION)
        recovery_contract = stalled.recovery_contract_payload
        assert isinstance(recovery_contract, dict)
        self.assertEqual(recovery_contract.get("kind"), "approval")
        self.assertEqual(recovery_contract.get("state"), "resolved_allow_pending_replay")

        recovered = (
            self.orchestration_scheduler_service.recover_abandoned_runs()
        )
        self.assertTrue(any(item.id == run.id for item in recovered))

        resumed = self.orchestration_run_query_service.get_run(run.id)
        self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)
        self.assertEqual(resumed.stage, OrchestrationRunStage.QUEUED)

        completed = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert completed is not None
        self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)
        self.assertEqual(completed.result_payload.get("output_text"), "approval flow complete")

    def test_recover_abandoned_runs_fails_resolved_approval_when_replay_fails(self) -> None:
        self._register_test_openai_profile(
            self.container,
            profile_id="local-capability",
        )
        self.agent_service.register_profile(
            RegisterAgentProfileInput(
                id="writer",
                name="Writer",
                instruction_policy=AgentInstructionPolicy(
                    system_prompt="Use tools when needed.",
                ),
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="local-capability"),
            ),
        )

        self.seed_tool(
            tool_id="echo",
            name="Echo",
            description="Echoes a message.",
            supported_modes=(ToolMode.INLINE,),
            runtime_key="echo",
            required_effect_ids=("local_tool_access",),
        )
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            _EffectApprovalAdapter(),
        )

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-approval-replay-fails",
                inbound_instruction=InboundInstruction(source="cli", content="complete the task"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="writer",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        waiting = process_next_orchestration_assignment(
            self.container,
            worker_id="worker-1",
        )
        assert waiting is not None
        pending_request = waiting.pending_approval_request()
        assert pending_request is not None

        wait_coordinator = (
            self.orchestration_approval_control_service.resolve_approval_request_fn.__self__
        )
        with patch.object(
            wait_coordinator,
            "continue_recovery_contract_fn",
            lambda run_id: self.orchestration_run_query_service.get_run(run_id),
        ):
            self.orchestration_approval_control_service.resolve_approval_request(
                ResolveApprovalRequestInput(
                    run_id=run.id,
                    request_id=pending_request.request_id,
                    decision=ApprovalDecision.ALLOW_ONCE,
                ),
            )

        assert wait_coordinator.engine is not None
        with patch.object(
            type(wait_coordinator.engine.tool_executor),
            "replay_approved_tool_call",
            side_effect=ToolExecutionNotAllowedError(
                "Tool requires setup.",
                code="credential_kind_mismatch",
                detail={"credential_binding_id": "bad-binding"},
            ),
        ):
            recovered = self.orchestration_scheduler_service.recover_abandoned_runs()

        self.assertTrue(any(item.id == run.id for item in recovered))
        failed = self.orchestration_run_query_service.get_run(run.id)
        self.assertEqual(failed.status, OrchestrationRunStatus.FAILED)
        self.assertEqual(failed.stage, OrchestrationRunStage.FAILED)
        self.assertIsNone(failed.pending_approval_request_payload)
        assert failed.error is not None
        self.assertEqual(failed.error.code, "credential_kind_mismatch")
        self.assertEqual(
            failed.recovery_contract_payload.get("state"),
            "replay_failed",
        )

    def test_process_next_orchestration_assignment_includes_approval_denied_flow_node(self) -> None:
        self._register_test_openai_profile(
            self.container,
            profile_id="local-capability",
        )
        self.agent_service.register_profile(
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
        tool = self.seed_tool(
            tool_id="echo",
            name="Echo",
            description="Returns the input payload for local inline execution tests.",
            supported_modes=(ToolMode.INLINE,),
            runtime_key="echo",
            required_effect_ids=("local_tool_access",),
        )

        async def echo(arguments: dict[str, object]) -> ToolRunResult:
            return ToolRunResult.text(
                str(arguments.get("message") or ""),
                details={"echo": arguments.get("message")},
            )

        self.local_runtime_registry.register(tool, echo)
        adapter = _EffectDeniedFallbackAdapter()
        self.llm_adapter_registry.register(
            LlmApiFamily.OPENAI_RESPONSES,
            adapter,
        )

        run = self.orchestration_intake_service.accept(
            AcceptOrchestrationRunInput(
                run_id="run-approval-denied-flow-prompt",
                inbound_instruction=InboundInstruction(source="cli", content="complete the task"),
            ),
        )
        self.orchestration_intake_service.prepare_session_run(
            PrepareSessionRunInput(
                run_id=run.id,
                context=SessionRouteContext(
                    agent_id="writer",
                    channel="webchat",
                    direct_scope=DirectSessionScope.MAIN,
                ),
            ),
        )
        self.orchestration_intake_service.enqueue(
            EnqueueOrchestrationRunInput(run_id=run.id),
        )

        waiting = process_next_orchestration_assignment(self.container,
            worker_id="worker-1",
        )
        assert waiting is not None
        pending_request = waiting.pending_approval_request()
        assert pending_request is not None

        resumed = self.orchestration_approval_control_service.resolve_approval_request(
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
            for message in adapter.requests[-1].messages
            if message.role is LlmMessageRole.SYSTEM
        ]
        context_tree_message = next(
            message
            for message in denied_system_messages
            if message.metadata.get("prompt_block_kind") == "context_workspace"
        )
        self.assertIn("run.flow", str(context_tree_message.content))
        self.assertIn("Flow: Approval Denied", str(context_tree_message.content))
        self.assertIn("denied the requested additional access", str(context_tree_message.content))
        self.assertFalse(
            any("# Approval Update" in str(message.content) for message in denied_system_messages),
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
        container = custom_harness.build_runtime_container(settings=settings)
        try:
            self._register_test_openai_profile(
                container,
                profile_id="local-capability",
            )
            container.require(AppKey.AGENT_SERVICE).register_profile(
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

            tool = seed_catalog_tool(
                container,
                tool_id="echo",
                name="Echo",
                description="Echoes a message.",
                supported_modes=(ToolMode.INLINE,),
                runtime_key="echo",
                required_effect_ids=("local_tool_access",),
            )

            async def echo(arguments: dict[str, object]) -> ToolRunResult:
                return ToolRunResult.text(
                    str(arguments.get("message") or ""),
                    details={"echo": arguments.get("message")},
                )

            container.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY).register(tool, echo)
            container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
                LlmApiFamily.OPENAI_RESPONSES,
                _EffectApprovalOrVisibleAdapter(),
            )

            run = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-effect-agent-approval",
                    inbound_instruction=InboundInstruction(
                        source="cli",
                        content="complete the task",
                    ),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="writer",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).enqueue(
                EnqueueOrchestrationRunInput(run_id=run.id),
            )

            waiting = process_next_orchestration_assignment(container,
                worker_id="worker-1",
            )
            assert waiting is not None
            pending_request = waiting.pending_approval_request()
            assert pending_request is not None

            resumed = container.require(AppKey.ORCHESTRATION_APPROVAL_CONTROL_SERVICE).resolve_approval_request(
                ResolveApprovalRequestInput(
                    run_id=run.id,
                    request_id=pending_request.request_id,
                    decision=ApprovalDecision.ALWAYS_FOR_AGENT,
                ),
            )
            self.assertEqual(resumed.status, OrchestrationRunStatus.QUEUED)

            policies = container.require(AppKey.AUTHORIZATION_SERVICE).list_policies()
            self.assertTrue(
                any(
                    policy.context_match == {"agent_id": "writer"}
                    and policy.resource_match == {
                        "authorization_effect_ids": ["local_tool_access"],
                    }
                    for policy in policies
                ),
            )
            completed = process_next_orchestration_assignment(container,
                worker_id="worker-1",
            )
            assert completed is not None
            self.assertEqual(completed.status, OrchestrationRunStatus.COMPLETED)

            followup = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-effect-agent-followup",
                    inbound_instruction=InboundInstruction(
                        source="cli",
                        content="complete the follow-up task",
                    ),
                ),
            )
            followup = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=followup.id,
                    context=SessionRouteContext(
                        agent_id="writer",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            resolved = container.require(AppKey.ORCHESTRATION_INSPECTION_SERVICE).resolve_tools(followup)

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
        container = custom_harness.build_runtime_container(settings=settings)
        try:
            adapter = _BackgroundApprovalAdapter()
            container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            self._register_test_openai_profile(
                container,
                profile_id="openai.gpt-5.4-mini",
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

            tool = seed_catalog_tool(
                container,
                tool_id="background_echo",
                name="Background Echo",
                description="Only runs in the background.",
                supported_modes=(ToolMode.BACKGROUND,),
                runtime_key="background_echo",
            )

            async def background_echo(arguments: dict[str, object]) -> ToolRunResult:
                return ToolRunResult.text(
                    str(arguments.get("message") or ""),
                    details={"message": arguments.get("message")},
                )

            container.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY).register(tool, background_echo)

            run = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-background-approval",
                    inbound_instruction=InboundInstruction(source="cli", content="search"),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).enqueue(
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

            waiting_on_tool = container.require(AppKey.ORCHESTRATION_APPROVAL_CONTROL_SERVICE).resolve_approval_request(
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
            publish_outbox_events(container)
            container.require(AppKey.ORCHESTRATION_SCHEDULER_SERVICE).process_runtime_events(
                limit_per_subscription=10,
            )
            processed_continuation = container.require(
                AppKey.ORCHESTRATION_SCHEDULER_SERVICE,
            ).process_next_continuation(
                worker_id="scheduler-1",
            )
            self.assertIsNotNone(processed_continuation)

            resumed = container.require(AppKey.ORCHESTRATION_RUN_QUERY_SERVICE).get_run(run.id)
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
        container = custom_harness.build_runtime_container(settings=settings)
        try:
            adapter = _BackgroundApprovalAdapter()
            container.require(AppKey.LLM_ADAPTER_REGISTRY).register(
                LlmApiFamily.OPENAI_RESPONSES,
                adapter,
            )
            self._register_test_openai_profile(
                container,
                profile_id="openai.gpt-5.4-mini",
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

            tool = seed_catalog_tool(
                container,
                tool_id="background_echo",
                name="Background Echo",
                description="Only runs in the background.",
                supported_modes=(ToolMode.BACKGROUND,),
                runtime_key="background_echo",
            )

            async def background_echo(arguments: dict[str, object]) -> ToolRunResult:
                return ToolRunResult.text(
                    str(arguments.get("message") or ""),
                    details={"message": arguments.get("message")},
                )

            container.require(AppKey.TOOL_LOCAL_RUNTIME_REGISTRY).register(tool, background_echo)

            run = container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).accept(
                AcceptOrchestrationRunInput(
                    run_id="run-background-approval-target-mismatch",
                    inbound_instruction=InboundInstruction(source="cli", content="search"),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).prepare_session_run(
                PrepareSessionRunInput(
                    run_id=run.id,
                    context=SessionRouteContext(
                        agent_id="assistant",
                        channel="webchat",
                        direct_scope=DirectSessionScope.MAIN,
                    ),
                ),
            )
            container.require(AppKey.ORCHESTRATION_INTAKE_SERVICE).enqueue(
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

            with container.require(AppKey.UNIT_OF_WORK_FACTORY)() as uow:
                function = uow.tool_functions.get("background_echo")
                assert function is not None
                function.execution_support = ToolExecutionSupport(
                    supported_modes=(ToolMode.INLINE,),
                    supported_strategies=tool.execution_support.supported_strategies,
                    supported_environments=tool.execution_support.supported_environments,
                )
                function.metadata = {
                    **function.metadata,
                    "execution_support": {
                        **dict(function.metadata.get("execution_support", {})),
                        "supported_modes": (ToolMode.INLINE.value,),
                    },
                }
                uow.tool_functions.upsert(function)
                uow.commit()

            failed = container.require(
                AppKey.ORCHESTRATION_APPROVAL_CONTROL_SERVICE,
            ).resolve_approval_request(
                ResolveApprovalRequestInput(
                    run_id=run.id,
                    request_id=pending_request.request_id,
                    decision=ApprovalDecision.ALLOW_ONCE,
                ),
            )
            self.assertEqual(failed.status, OrchestrationRunStatus.FAILED)
            self.assertEqual(failed.stage, OrchestrationRunStage.FAILED)
            assert failed.error is not None
            self.assertEqual(failed.error.code, "approval_replay_failed")
            self.assertIn(
                "Approved tool replay target is no longer supported",
                failed.error.message,
            )
        finally:
            custom_harness.close()
