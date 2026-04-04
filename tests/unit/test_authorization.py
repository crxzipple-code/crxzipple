from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
import unittest
import yaml

from crxzipple.core.config import load_settings
from crxzipple.interfaces.authorization import (
    authorize_llm_action,
    authorize_tool_run,
)
from crxzipple.modules.authorization.domain import (
    AuthorizationContext,
    AuthorizationDeniedError,
    AuthorizationDecisionCode,
    AuthorizationRequest,
    AuthorizationResource,
    AuthorizationSubject,
    ToolExecutionAuthorizationRequest,
)
from crxzipple.modules.llm.application import (
    InvokeLlmInput,
    LlmAdapterRequest,
    LlmAdapterResponse,
    LlmApplicationService,
    RegisterLlmProfileInput,
)
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmDefaults,
    LlmMessage,
    LlmMessageRole,
    LlmProviderKind,
    LlmResult,
)
from crxzipple.modules.llm.infrastructure import LlmAdapterRegistry
from crxzipple.modules.tool.application import ExecuteToolInput, RegisterToolInput
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolMode,
)
from tests.unit.support import SqliteTestHarness


class _FakeLlmAdapter:
    def invoke(self, profile, request: LlmAdapterRequest) -> LlmAdapterResponse:  # noqa: ANN001
        self.last_profile = profile
        self.last_request = request
        return LlmAdapterResponse(
            result=LlmResult(
                text="authorized llm response",
                finish_reason="stop",
                metadata={"adapter": "fake"},
            ),
            provider_request_id="fake-authorization-request",
        )


class AuthorizationTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = SqliteTestHarness()
        self.harness.initialize_schema()
        self.policy_path = str(
            Path(__file__).resolve().parents[2]
            / "config"
            / "authorization_policies"
            / "default.yaml"
        )

    def tearDown(self) -> None:
        self.harness.close()

    def test_authorization_service_lists_policies_and_evaluates_allow_and_deny(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(self.policy_path,),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        container = self.harness.build_container(settings=settings)

        policies = container.authorization_service.list_policies()
        self.assertEqual(
            [item.id for item in policies],
            [
                "allow_llm_invocation",
                "allow_safe_tool_execution",
                "deny_tool_access_when_required_scope_missing",
                "deny_tool_access_when_surface_mismatch",
                "deny_tool_access_when_surface_requires_explicit_declaration",
            ],
        )

        llm_decision = container.authorization_service.check(
            AuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                action="llm.invoke",
                resource=AuthorizationResource(kind="llm_profile", id="writer"),
                context=AuthorizationContext(attrs={"interface": "http"}),
            ),
        )
        denied_decision = container.authorization_service.check(
            AuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="cli"),
                action="tool.run",
                resource=AuthorizationResource(
                    kind="tool",
                    id="dangerous_write",
                    attrs={"mutates_state": True},
                ),
                context=AuthorizationContext(attrs={"interface": "cli"}),
            ),
        )

        self.assertTrue(llm_decision.allowed)
        self.assertIn("allow_llm_invocation", llm_decision.matched_policy_ids)
        self.assertFalse(denied_decision.allowed)
        self.assertEqual(denied_decision.matched_policy_ids, ())

    def test_tool_service_is_decoupled_and_interface_guard_denies_mutating_tool(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(self.policy_path,),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        container = self.harness.build_container(settings=settings)

        container.tool_service.register(
            RegisterToolInput(
                id="dangerous_write",
                name="Dangerous Write",
                description="Mutates external state.",
                mutates_state=True,
            ),
        )

        direct_run = asyncio.run(
            container.tool_service.execute(
                ExecuteToolInput(
                    tool_id="dangerous_write",
                    arguments={},
                ),
            ),
        )
        self.assertEqual(direct_run.status.value, "failed")
        self.assertNotIn("Authorization denied", direct_run.error_message or "")

        with self.assertRaises(AuthorizationDeniedError):
            authorize_tool_run(
                container,
                tool_id="dangerous_write",
                mode=ToolMode.INLINE,
                strategy=ToolExecutionStrategy.ASYNC,
                environment=ToolEnvironment.LOCAL,
                interface_name="http",
            )

    def test_llm_service_is_decoupled_and_interface_guard_denies_without_policy(self) -> None:
        allowed_settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(self.policy_path,),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        allowed_container = self.harness.build_container(settings=allowed_settings)
        registry = LlmAdapterRegistry()
        registry.register(LlmApiFamily.OPENAI_RESPONSES, _FakeLlmAdapter())
        service = LlmApplicationService(
            allowed_container.uow_factory,
            registry,
        )

        service.register_profile(
            RegisterLlmProfileInput(
                id="writer",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
                default_params=LlmDefaults(temperature=0.2),
            ),
        )
        invocation = service.invoke(
            InvokeLlmInput(
                llm_id="writer",
                messages=(
                    LlmMessage(role=LlmMessageRole.USER, content="hello"),
                ),
            ),
        )
        self.assertEqual(invocation.status.value, "succeeded")
        authorize_llm_action(
            allowed_container,
            llm_id="writer",
            action="llm.invoke",
            interface_name="http",
        )

        denied_settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        denied_container = self.harness.build_container(settings=denied_settings)
        denied_registry = LlmAdapterRegistry()
        denied_registry.register(LlmApiFamily.OPENAI_RESPONSES, _FakeLlmAdapter())
        denied_service = LlmApplicationService(
            denied_container.uow_factory,
            denied_registry,
        )
        denied_service.register_profile(
            RegisterLlmProfileInput(
                id="blocked",
                provider=LlmProviderKind.OPENAI,
                api_family=LlmApiFamily.OPENAI_RESPONSES,
                model_name="gpt-5.4-mini",
            ),
        )

        direct_invocation = denied_service.invoke(
            InvokeLlmInput(
                llm_id="blocked",
                messages=(
                    LlmMessage(role=LlmMessageRole.USER, content="hello"),
                ),
            ),
        )
        self.assertEqual(direct_invocation.status.value, "succeeded")

        with self.assertRaises(AuthorizationDeniedError):
            authorize_llm_action(
                denied_container,
                llm_id="blocked",
                action="llm.invoke",
                interface_name="http",
            )

    def test_grant_agent_effect_access_persists_runtime_policy_and_allows_effect_access(self) -> None:
        runtime_policy_path = Path(self.harness.authorization_runtime_policy_path)
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(self.policy_path,),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        container = self.harness.build_container(settings=settings)

        policy = container.authorization_service.grant_agent_effect_access(
            agent_id="assistant",
            effect_id="network_search",
        )

        self.assertEqual(policy.actions, ("tool.access_effect",))
        self.assertTrue(runtime_policy_path.exists())
        payload = yaml.safe_load(runtime_policy_path.read_text(encoding="utf-8"))
        self.assertEqual(payload[0]["id"], policy.id)
        self.assertEqual(payload[0]["actions"], ["tool.access_effect"])
        self.assertEqual(
            payload[0]["resource"]["match"]["authorization_effect_ids"],
            ["network_search"],
        )

        allowed = container.authorization_service.check(
            AuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                action="tool.access_effect",
                resource=AuthorizationResource(
                    kind="tool",
                    id="brave_search.news_search",
                    attrs={"authorization_effect_ids": ["network_search"]},
                ),
                context=AuthorizationContext(
                    attrs={"interface": "http", "agent_id": "assistant"},
                ),
            ),
        )
        denied = container.authorization_service.check(
            AuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                action="tool.access_effect",
                resource=AuthorizationResource(
                    kind="tool",
                    id="brave_search.news_search",
                    attrs={"authorization_effect_ids": ["network_search"]},
                ),
                context=AuthorizationContext(
                    attrs={"interface": "http", "agent_id": "other-agent"},
                ),
            ),
        )

        self.assertTrue(allowed.allowed)
        self.assertIn(policy.id, allowed.matched_policy_ids)
        self.assertFalse(denied.allowed)

    def test_grant_agent_tool_access_persists_runtime_policy_and_allows_tool_access(self) -> None:
        runtime_policy_path = Path(self.harness.authorization_runtime_policy_path)
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(self.policy_path,),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        container = self.harness.build_container(settings=settings)

        policy = container.authorization_service.grant_agent_tool_access(
            agent_id="assistant",
            tool_id="filesystem.read_text",
        )

        payload = yaml.safe_load(runtime_policy_path.read_text(encoding="utf-8"))
        self.assertEqual(payload[0]["id"], policy.id)
        self.assertEqual(payload[0]["actions"], ["tool.access_tool"])
        self.assertEqual(payload[0]["resource"]["id"], "filesystem.read_text")

        allowed = container.authorization_service.check(
            AuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                action="tool.access_tool",
                resource=AuthorizationResource(
                    kind="tool",
                    id="filesystem.read_text",
                ),
                context=AuthorizationContext(
                    attrs={"interface": "http", "agent_id": "assistant"},
                ),
            ),
        )
        denied = container.authorization_service.check(
            AuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                action="tool.access_tool",
                resource=AuthorizationResource(
                    kind="tool",
                    id="filesystem.read_text",
                ),
                context=AuthorizationContext(
                    attrs={"interface": "http", "agent_id": "other-agent"},
                ),
            ),
        )

        self.assertTrue(allowed.allowed)
        self.assertIn(policy.id, allowed.matched_policy_ids)
        self.assertFalse(denied.allowed)

    def test_check_tool_execution_returns_approval_required_when_effect_is_missing(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=False,
            authorization_policy_paths=(),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        container = self.harness.build_container(settings=settings)

        decision = container.authorization_service.check_tool_execution(
            ToolExecutionAuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                resource=AuthorizationResource(
                    kind="tool",
                    id="open_meteo_weather.forecast_weather",
                    attrs={
                        "environment": "remote",
                        "mode": "inline",
                        "strategy": "async",
                        "required_effect_ids": ["weather_data"],
                        "authorization_effect_ids": ["weather_data"],
                        "mutates_state": False,
                        "tags": [],
                    },
                ),
                context=AuthorizationContext(
                    attrs={"interface": "http", "agent_id": "assistant"},
                ),
                required_effect_ids=("weather_data",),
            ),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, AuthorizationDecisionCode.APPROVAL_REQUIRED)
        self.assertEqual(decision.details["missing_effect_ids"], ["weather_data"])

    def test_check_tool_execution_allows_run_grant_recorded_in_authorization_store(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=False,
            authorization_policy_paths=(),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        container = self.harness.build_container(settings=settings)
        container.authorization_service.grant_run_access(
            run_id="run-weather-1",
            agent_id="assistant",
            approval_request_id="approval-weather-1",
            effect_ids=("weather_data",),
            tool_ids=("open_meteo_weather.forecast_weather",),
        )

        decision = container.authorization_service.check_tool_execution(
            ToolExecutionAuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                resource=AuthorizationResource(
                    kind="tool",
                    id="open_meteo_weather.forecast_weather",
                    attrs={
                        "environment": "remote",
                        "mode": "inline",
                        "strategy": "async",
                        "required_effect_ids": ["weather_data"],
                        "authorization_effect_ids": ["weather_data"],
                        "mutates_state": False,
                        "tags": [],
                    },
                ),
                context=AuthorizationContext(
                    attrs={
                        "interface": "http",
                        "agent_id": "assistant",
                        "run_id": "run-weather-1",
                    },
                ),
                required_effect_ids=("weather_data",),
            ),
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.code, AuthorizationDecisionCode.ALLOW)

    def test_check_tool_execution_still_requires_effect_when_tool_access_policy_allows_tool(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        container = self.harness.build_container(settings=settings)
        container.authorization_service.grant_agent_tool_access(
            agent_id="assistant",
            tool_id="open_meteo_weather.forecast_weather",
        )

        decision = container.authorization_service.check_tool_execution(
            ToolExecutionAuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                resource=AuthorizationResource(
                    kind="tool",
                    id="open_meteo_weather.forecast_weather",
                    attrs={
                        "environment": "remote",
                        "mode": "inline",
                        "strategy": "async",
                        "required_effect_ids": ["weather_data"],
                        "authorization_effect_ids": ["weather_data"],
                        "mutates_state": False,
                        "tags": [],
                    },
                ),
                context=AuthorizationContext(
                    attrs={"interface": "http", "agent_id": "assistant"},
                ),
                required_effect_ids=("weather_data",),
            ),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, AuthorizationDecisionCode.APPROVAL_REQUIRED)
        self.assertEqual(decision.details["missing_effect_ids"], ["weather_data"])

    def test_check_tool_execution_returns_policy_denied_when_mode_policy_blocks_tool(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(self.policy_path,),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        container = self.harness.build_container(settings=settings)

        decision = container.authorization_service.check_tool_execution(
            ToolExecutionAuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                resource=AuthorizationResource(
                    kind="tool",
                    id="memory_search",
                    attrs={
                        "environment": "local",
                        "mode": "inline",
                        "strategy": "async",
                        "required_effect_ids": [],
                        "authorization_effect_ids": ["local_tool_access"],
                        "mutates_state": False,
                        "tags": ["system-managed", "surface:interactive"],
                        "surface_mode": "interactive",
                    },
                ),
                context=AuthorizationContext(
                    attrs={
                        "interface": "http",
                        "agent_id": "assistant",
                        "prompt_mode": "heartbeat",
                        "surface": "maintenance",
                    },
                ),
                required_effect_ids=("local_tool_access",),
            ),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, AuthorizationDecisionCode.POLICY_DENIED)

    def test_check_tool_execution_returns_policy_denied_when_required_scope_is_missing(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(self.policy_path,),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        container = self.harness.build_container(settings=settings)

        decision = container.authorization_service.check_tool_execution(
            ToolExecutionAuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                resource=AuthorizationResource(
                    kind="tool",
                    id="read",
                    attrs={
                        "environment": "local",
                        "mode": "inline",
                        "strategy": "async",
                        "required_effect_ids": ["workspace_read"],
                        "authorization_effect_ids": ["workspace_read"],
                        "mutates_state": False,
                        "tags": ["system-managed", "scope:workspace_bound"],
                        "scope_required": "workspace_bound",
                    },
                ),
                context=AuthorizationContext(
                    attrs={
                        "interface": "http",
                        "agent_id": "assistant",
                        "available_scopes": ["memory_context"],
                    },
                ),
                required_effect_ids=("workspace_read",),
            ),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, AuthorizationDecisionCode.POLICY_DENIED)
        self.assertIn(
            "deny_tool_access_when_required_scope_missing",
            decision.matched_policy_ids,
        )

    def test_declared_only_surface_hides_unscoped_tools_when_auth_is_enabled(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(self.policy_path,),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        container = self.harness.build_container(settings=settings)

        decision = container.authorization_service.check_tool_execution(
            ToolExecutionAuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                resource=AuthorizationResource(
                    kind="tool",
                    id="echo",
                    attrs={
                        "environment": "local",
                        "mode": "inline",
                        "strategy": "async",
                        "required_effect_ids": [],
                        "authorization_effect_ids": [],
                        "mutates_state": False,
                        "tags": ["builtin"],
                    },
                ),
                context=AuthorizationContext(
                    attrs={
                        "interface": "http",
                        "agent_id": "assistant",
                        "prompt_mode": "memory_flush",
                        "surface": "maintenance_write",
                        "surface_contract": "declared_only",
                    },
                ),
                required_effect_ids=(),
            ),
        )

        self.assertFalse(decision.allowed)
        self.assertEqual(decision.code, AuthorizationDecisionCode.POLICY_DENIED)
        self.assertIn(
            "deny_tool_access_when_surface_requires_explicit_declaration",
            decision.matched_policy_ids,
        )

    def test_declared_only_surface_allows_tool_with_matching_supported_surfaces(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(self.policy_path,),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        container = self.harness.build_container(settings=settings)

        decision = container.authorization_service.check_tool_execution(
            ToolExecutionAuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                resource=AuthorizationResource(
                    kind="tool",
                    id="memory_write_daily",
                    attrs={
                        "environment": "local",
                        "mode": "inline",
                        "strategy": "async",
                        "required_effect_ids": [],
                        "authorization_effect_ids": [],
                        "mutates_state": False,
                        "tags": [
                            "system-managed",
                            "surface:interactive",
                            "surface:maintenance_write",
                        ],
                        "surface_mode": "interactive",
                        "supported_surfaces": ["interactive", "maintenance_write"],
                    },
                ),
                context=AuthorizationContext(
                    attrs={
                        "interface": "http",
                        "agent_id": "assistant",
                        "prompt_mode": "memory_flush",
                        "surface": "maintenance_write",
                        "surface_contract": "declared_only",
                    },
                ),
                required_effect_ids=(),
            ),
        )

        self.assertTrue(decision.allowed)
        self.assertEqual(decision.code, AuthorizationDecisionCode.ALLOW)
