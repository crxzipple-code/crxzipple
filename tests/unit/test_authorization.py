from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
import unittest

from crxzipple.core.config import load_settings
from crxzipple.interfaces.runtime_container import AppKey
from crxzipple.interfaces.authorization import (
    authorize_llm_action,
    authorize_tool_run,
)
from crxzipple.modules.authorization.domain import (
    AuthorizationContext,
    AuthorizationDeniedError,
    AuthorizationDecisionCode,
    AuthorizationEffect,
    AuthorizationPolicy,
    AuthorizationRequest,
    AuthorizationResource,
    AuthorizationSubject,
    ToolExecutionAuthorizationRequest,
)
from crxzipple.modules.authorization.infrastructure.persistence import (
    AuthorizationAuditModel,
    AuthorizationPolicyModel,
    TemporaryAuthorizationGrantModel,
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
from crxzipple.modules.tool.application import ExecuteToolInput
from crxzipple.modules.tool.domain import (
    ToolEnvironment,
    ToolExecutionStrategy,
    ToolMode,
)
from tests.unit.support import SqliteTestHarness
from tests.unit.tool_catalog_seed import seed_catalog_tool


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
        container = self.harness.build_runtime_container(settings=settings)

        policies = container.require(AppKey.AUTHORIZATION_SERVICE).list_policies()
        self.assertEqual(
            [item.id for item in policies],
            [
                "allow_browser_local_tool_access_effect",
                "allow_browser_tool_execution",
                "allow_cli_source_cancel_from_cli_interface",
                "allow_llm_invocation",
                "allow_safe_tool_execution",
                "allow_session_context_tool_execution",
                "allow_session_context_tool_mutation_effect",
                "allow_skill_authoring_draft_lifecycle_effects",
                "allow_skill_authoring_draft_tool_execution",
                "deny_tool_access_when_required_scope_missing",
                "deny_tool_access_when_surface_mismatch",
                "deny_tool_access_when_surface_requires_explicit_declaration",
            ],
        )

        llm_decision = container.require(AppKey.AUTHORIZATION_SERVICE).check(
            AuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                action="llm.invoke",
                resource=AuthorizationResource(kind="llm_profile", id="writer"),
                context=AuthorizationContext(attrs={"interface": "http"}),
            ),
        )
        denied_decision = container.require(AppKey.AUTHORIZATION_SERVICE).check(
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

    def test_default_policy_allows_configured_browser_source_execution(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(self.policy_path,),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        container = self.harness.build_runtime_container(settings=settings)

        decision = container.require(AppKey.AUTHORIZATION_SERVICE).check_tool_execution(
            ToolExecutionAuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                resource=AuthorizationResource(
                    kind="tool",
                    id="browser.navigate",
                    attrs={
                        "source_id": "bundled.local_package.browser",
                        "mutates_state": True,
                        "required_effect_ids": ["local_tool_access"],
                        "authorization_effect_ids": ["local_tool_access"],
                        "capability_ids": ["browser.control", "browser.page_action"],
                    },
                ),
                context=AuthorizationContext(attrs={"interface": "http"}),
                required_effect_ids=("local_tool_access",),
            ),
        )

        self.assertTrue(decision.allowed)
        self.assertIn("allow_browser_tool_execution", decision.matched_policy_ids)
        self.assertIn(
            "allow_browser_local_tool_access_effect",
            decision.matched_policy_ids,
        )

    def test_tool_run_authorization_exposes_browser_profile_context(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(self.policy_path,),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        container = self.harness.build_runtime_container(settings=settings)
        seed_catalog_tool(
            container,
            tool_id="browser.navigate",
            name="Browser Navigate",
            mutates_state=True,
            source_id="bundled.local_package.browser",
        )
        container.require(AppKey.AUTHORIZATION_SERVICE).upsert_policy(
            AuthorizationPolicy(
                id="deny_user_browser_profile",
                description="Block direct execution against the user's browser profile.",
                effect=AuthorizationEffect.DENY,
                actions=("tool.run",),
                resource_kind="tool",
                resource_match={"source_id": "bundled.local_package.browser"},
                context_match={"browser_profile": "user"},
                priority=1000,
                source_kind="local_managed",
            ),
        )

        with self.assertRaises(AuthorizationDeniedError):
            authorize_tool_run(
                container,
                tool_id="browser.navigate",
                mode=ToolMode.INLINE,
                strategy=ToolExecutionStrategy.ASYNC,
                environment=ToolEnvironment.LOCAL,
                interface_name="http",
                arguments={"profile": "user"},
            )

        authorize_tool_run(
            container,
            tool_id="browser.navigate",
            mode=ToolMode.INLINE,
            strategy=ToolExecutionStrategy.ASYNC,
            environment=ToolEnvironment.LOCAL,
            interface_name="http",
            arguments={"profile": "crxzipple"},
        )

    def test_default_policy_allows_skill_draft_lifecycle_but_requires_apply_approval(
        self,
    ) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(self.policy_path,),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        container = self.harness.build_runtime_container(settings=settings)

        create_decision = container.require(
            AppKey.AUTHORIZATION_SERVICE,
        ).check_tool_execution(
            ToolExecutionAuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                resource=AuthorizationResource(
                    kind="tool",
                    id="skill_draft_create",
                    attrs={
                        "mutates_state": True,
                        "required_effect_ids": ["skill_authoring.create"],
                        "authorization_effect_ids": ["skill_authoring.create"],
                        "tags": ["skill", "authoring"],
                    },
                ),
                context=AuthorizationContext(attrs={"interface": "http"}),
                required_effect_ids=("skill_authoring.create",),
            ),
        )
        apply_decision = container.require(
            AppKey.AUTHORIZATION_SERVICE,
        ).check_tool_execution(
            ToolExecutionAuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                resource=AuthorizationResource(
                    kind="tool",
                    id="skill_draft_apply",
                    attrs={
                        "mutates_state": True,
                        "required_effect_ids": ["skill_authoring.apply"],
                        "authorization_effect_ids": ["skill_authoring.apply"],
                        "tags": ["skill", "authoring", "approval:required"],
                    },
                ),
                context=AuthorizationContext(attrs={"interface": "http"}),
                required_effect_ids=("skill_authoring.apply",),
            ),
        )

        self.assertTrue(create_decision.allowed)
        self.assertIn(
            "allow_skill_authoring_draft_lifecycle_effects",
            create_decision.matched_policy_ids,
        )
        self.assertFalse(apply_decision.allowed)
        self.assertEqual(apply_decision.code, AuthorizationDecisionCode.APPROVAL_REQUIRED)
        self.assertEqual(
            apply_decision.details["missing_effect_ids"],
            ["skill_authoring.apply"],
        )

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
        container = self.harness.build_runtime_container(settings=settings)

        seed_catalog_tool(
            container,
            tool_id="dangerous_write",
            name="Dangerous Write",
            description="Mutates external state.",
            mutates_state=True,
        )

        direct_run = asyncio.run(
            container.require(AppKey.TOOL_SERVICE).execute(
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

    def test_default_policy_allows_cli_source_cancel_only_from_cli_interface(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(self.policy_path,),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        container = self.harness.build_runtime_container(settings=settings)
        seed_catalog_tool(
            container,
            tool_id="configured_cli_cancel",
            name="Configured CLI Cancel",
            description="Cancel a governed CLI source process.",
            required_effect_ids=("tool.cli.cancel",),
            mutates_state=True,
            supported_environments=(ToolEnvironment.REMOTE,),
        )

        authorize_tool_run(
            container,
            tool_id="configured_cli_cancel",
            mode=ToolMode.INLINE,
            strategy=ToolExecutionStrategy.ASYNC,
            environment=ToolEnvironment.REMOTE,
            interface_name="cli",
        )

        with self.assertRaises(AuthorizationDeniedError):
            authorize_tool_run(
                container,
                tool_id="configured_cli_cancel",
                mode=ToolMode.INLINE,
                strategy=ToolExecutionStrategy.ASYNC,
                environment=ToolEnvironment.REMOTE,
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
        allowed_container = self.harness.build_runtime_container(settings=allowed_settings)
        registry = LlmAdapterRegistry()
        registry.register(LlmApiFamily.OPENAI_RESPONSES, _FakeLlmAdapter())
        service = LlmApplicationService(
            allowed_container.require(AppKey.UNIT_OF_WORK_FACTORY),
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

        denied_harness = SqliteTestHarness()
        try:
            denied_settings = replace(
                load_settings(),
                database_url=denied_harness.database_url,
                authorization_enabled=True,
                authorization_policy_paths=(),
                tool_openapi_providers=(),
                tool_mcp_providers=(),
                llm_profiles=(),
            )
            denied_harness.initialize_schema(settings=denied_settings)
            denied_container = denied_harness.build_runtime_container(settings=denied_settings)
            denied_registry = LlmAdapterRegistry()
            denied_registry.register(LlmApiFamily.OPENAI_RESPONSES, _FakeLlmAdapter())
            denied_service = LlmApplicationService(
                denied_container.require(AppKey.UNIT_OF_WORK_FACTORY),
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
        finally:
            denied_harness.close()

    def test_grant_agent_effect_authorization_persists_policy_and_allows_effect(self) -> None:
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
        container = self.harness.build_runtime_container(settings=settings)

        policy = container.require(AppKey.AUTHORIZATION_SERVICE).grant_agent_effect_authorization(
            agent_id="assistant",
            effect_id="network_search",
        )

        self.assertEqual(policy.actions, ("tool.effect.authorize",))
        self.assertFalse(runtime_policy_path.exists())
        with container.require(AppKey.DATABASE_SESSION_FACTORY)() as session:
            stored = session.get(AuthorizationPolicyModel, policy.id)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.policy_id, policy.id)
        self.assertEqual(stored.actions_payload, ["tool.effect.authorize"])
        self.assertEqual(
            stored.resource_match_payload["authorization_effect_ids"],
            ["network_search"],
        )

        allowed = container.require(AppKey.AUTHORIZATION_SERVICE).check(
            AuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                action="tool.effect.authorize",
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
        denied = container.require(AppKey.AUTHORIZATION_SERVICE).check(
            AuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                action="tool.effect.authorize",
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

    def test_grant_agent_tool_authorization_persists_policy_and_allows_tool(self) -> None:
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
        container = self.harness.build_runtime_container(settings=settings)

        policy = container.require(AppKey.AUTHORIZATION_SERVICE).grant_agent_tool_authorization(
            agent_id="assistant",
            tool_id="filesystem.read_text",
        )

        self.assertFalse(runtime_policy_path.exists())
        with container.require(AppKey.DATABASE_SESSION_FACTORY)() as session:
            stored = session.get(AuthorizationPolicyModel, policy.id)
        self.assertIsNotNone(stored)
        assert stored is not None
        self.assertEqual(stored.policy_id, policy.id)
        self.assertEqual(stored.actions_payload, ["tool.authorize"])
        self.assertEqual(stored.resource_id, "filesystem.read_text")

        allowed = container.require(AppKey.AUTHORIZATION_SERVICE).check(
            AuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                action="tool.authorize",
                resource=AuthorizationResource(
                    kind="tool",
                    id="filesystem.read_text",
                ),
                context=AuthorizationContext(
                    attrs={"interface": "http", "agent_id": "assistant"},
                ),
            ),
        )
        denied = container.require(AppKey.AUTHORIZATION_SERVICE).check(
            AuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                action="tool.authorize",
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

    def test_authorization_governance_manages_policies_and_records_audit(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        container = self.harness.build_runtime_container(settings=settings)

        policy = AuthorizationPolicy(
            id="local_allow_echo",
            effect=AuthorizationEffect.ALLOW,
            actions=("tool.run",),
            resource_kind="tool",
            resource_id="echo",
            priority=50,
            source_kind="local_managed",
        )
        container.require(AppKey.AUTHORIZATION_SERVICE).create_policy(
            policy,
            actor_type="test",
            actor_id="operator",
            reason="unit test",
        )
        allowed = container.require(AppKey.AUTHORIZATION_SERVICE).dry_run(
            AuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                action="tool.run",
                resource=AuthorizationResource(kind="tool", id="echo"),
                context=AuthorizationContext(attrs={"interface": "http"}),
            ),
            actor_type="test",
            actor_id="operator",
        )
        disabled = container.require(AppKey.AUTHORIZATION_SERVICE).set_policy_enabled(
            "local_allow_echo",
            enabled=False,
            actor_type="test",
            actor_id="operator",
        )
        denied = container.require(AppKey.AUTHORIZATION_SERVICE).dry_run(
            AuthorizationRequest(
                subject=AuthorizationSubject(type="interface", id="http"),
                action="tool.run",
                resource=AuthorizationResource(kind="tool", id="echo"),
                context=AuthorizationContext(attrs={"interface": "http"}),
            ),
        )
        imported = container.require(AppKey.AUTHORIZATION_SERVICE).import_policies(
            (
                AuthorizationPolicy(
                    id="local_allow_llm",
                    effect=AuthorizationEffect.ALLOW,
                    actions=("llm.invoke",),
                    resource_kind="llm_profile",
                    source_kind="local_managed",
                ),
            ),
            actor_type="test",
            actor_id="operator",
            source="unit",
        )
        bundle = container.require(AppKey.AUTHORIZATION_SERVICE).export_policy_bundle()
        deleted = container.require(AppKey.AUTHORIZATION_SERVICE).delete_policy(
            "local_allow_llm",
            actor_type="test",
            actor_id="operator",
        )

        self.assertTrue(allowed.allowed)
        self.assertFalse(disabled.enabled)
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.code, AuthorizationDecisionCode.NO_MATCH)
        self.assertEqual(imported[0].id, "local_allow_llm")
        self.assertIn(
            "local_allow_llm",
            [item["id"] for item in bundle["policies"]],
        )
        self.assertEqual(deleted.id, "local_allow_llm")

        audit_records = container.require(AppKey.AUTHORIZATION_SERVICE).list_audit_records(limit=20)
        actions = {record.action for record in audit_records}
        self.assertTrue(
            {
                "policy.create",
                "policy.disable",
                "policy.import",
                "policy.delete",
                "decision.dry_run",
            }.issubset(actions),
        )
        with container.require(AppKey.DATABASE_SESSION_FACTORY)() as session:
            stored_audit = session.get(AuthorizationAuditModel, audit_records[0].id)
        self.assertIsNotNone(stored_audit)

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
        container = self.harness.build_runtime_container(settings=settings)

        decision = container.require(AppKey.AUTHORIZATION_SERVICE).check_tool_execution(
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
        container = self.harness.build_runtime_container(settings=settings)
        container.require(AppKey.AUTHORIZATION_SERVICE).grant_run_authorization(
            run_id="run-weather-1",
            agent_id="assistant",
            approval_request_id="approval-weather-1",
            effect_ids=("weather_data",),
            tool_ids=("open_meteo_weather.forecast_weather",),
        )
        with container.require(AppKey.DATABASE_SESSION_FACTORY)() as session:
            stored_grant = session.get(
                TemporaryAuthorizationGrantModel,
                "run:run-weather-1:approval-weather-1",
            )
        self.assertIsNotNone(stored_grant)

        decision = container.require(AppKey.AUTHORIZATION_SERVICE).check_tool_execution(
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

    def test_tool_execution_requires_effect_when_tool_authorization_allows_tool(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        container = self.harness.build_runtime_container(settings=settings)
        container.require(AppKey.AUTHORIZATION_SERVICE).grant_agent_tool_authorization(
            agent_id="assistant",
            tool_id="open_meteo_weather.forecast_weather",
        )

        decision = container.require(AppKey.AUTHORIZATION_SERVICE).check_tool_execution(
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
        container = self.harness.build_runtime_container(settings=settings)

        decision = container.require(AppKey.AUTHORIZATION_SERVICE).check_tool_execution(
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

    def test_tool_execution_returns_policy_denied_when_required_scope_is_missing(self) -> None:
        settings = replace(
            load_settings(),
            database_url=self.harness.database_url,
            authorization_enabled=True,
            authorization_policy_paths=(self.policy_path,),
            tool_openapi_providers=(),
            tool_mcp_providers=(),
            llm_profiles=(),
        )
        container = self.harness.build_runtime_container(settings=settings)

        decision = container.require(AppKey.AUTHORIZATION_SERVICE).check_tool_execution(
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
        container = self.harness.build_runtime_container(settings=settings)

        decision = container.require(AppKey.AUTHORIZATION_SERVICE).check_tool_execution(
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
        container = self.harness.build_runtime_container(settings=settings)

        decision = container.require(AppKey.AUTHORIZATION_SERVICE).check_tool_execution(
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
