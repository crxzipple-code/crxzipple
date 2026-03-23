from __future__ import annotations

import asyncio
from dataclasses import replace
from pathlib import Path
import unittest

from crxzipple.core.config import load_settings
from crxzipple.interfaces.authorization import (
    authorize_llm_action,
    authorize_tool_run,
)
from crxzipple.modules.authorization.domain import (
    AuthorizationContext,
    AuthorizationDeniedError,
    AuthorizationRequest,
    AuthorizationResource,
    AuthorizationSubject,
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
        self.assertEqual([item.id for item in policies], ["allow_llm_invocation", "allow_safe_tool_execution"])

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
