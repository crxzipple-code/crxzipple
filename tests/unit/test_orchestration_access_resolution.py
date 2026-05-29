from __future__ import annotations

import unittest
from unittest.mock import patch

from crxzipple.modules.access import AccessApplicationService
from crxzipple.modules.authorization.domain import (
    AuthorizationDecision,
    AuthorizationRequest,
    ToolExecutionAuthorizationRequest,
)
from crxzipple.modules.orchestration.application.tool_resolver import ToolResolver
from crxzipple.modules.orchestration.domain import InboundInstruction, OrchestrationRun
from crxzipple.modules.tool.domain import Tool


class _FakeToolCatalog:
    def __init__(self, *tools: Tool) -> None:
        self._tools = list(tools)

    def ensure_local_system_tools_registered(self) -> tuple[Tool, ...]:
        return ()

    def list_enabled_tools(self, *, runtime_context=None) -> list[Tool]:
        del runtime_context
        return [tool for tool in self._tools if tool.enabled]


class _DisabledAuthorizationPort:
    def is_enabled(self) -> bool:
        return False

    def check(self, request: AuthorizationRequest) -> AuthorizationDecision:
        del request
        return AuthorizationDecision(allowed=True, reason="authorization disabled")

    def check_tool_execution(
        self,
        request: ToolExecutionAuthorizationRequest,
    ) -> AuthorizationDecision:
        del request
        return AuthorizationDecision(allowed=True, reason="authorization disabled")


class OrchestrationAccessResolutionTestCase(unittest.TestCase):
    def test_tool_resolver_filters_tools_without_ready_access(self) -> None:
        resolver = ToolResolver(
            tool_catalog=_FakeToolCatalog(
                Tool(
                    id="missing_remote",
                    name="Missing Remote",
                    description="Requires a missing token.",
                    access_requirements=("env:MISSING_TOOL_TOKEN",),
                ),
                Tool(
                    id="ready_remote",
                    name="Ready Remote",
                    description="Requires a configured token.",
                    access_requirements=("env:READY_TOOL_TOKEN",),
                ),
            ),
            authorization_port=_DisabledAuthorizationPort(),
            access_port=AccessApplicationService(),
        )
        run = OrchestrationRun.accept(
            run_id="run-access-tools",
            inbound_instruction=InboundInstruction(source="cli", content="hello"),
        )

        with patch.dict("os.environ", {"READY_TOOL_TOKEN": "token"}):
            resolved = resolver.resolve(run)

        self.assertEqual([item.tool.id for item in resolved.tools], ["ready_remote"])
        blocked_access = resolved.blocked_access_by_name("missing_remote")
        self.assertIsNotNone(blocked_access)
        assert blocked_access is not None
        payload = blocked_access.to_payload()
        self.assertEqual(payload["resource_type"], "tool")
        self.assertEqual(payload["resource_id"], "missing_remote")
        requirement_sets = payload["requirement_sets"]
        self.assertIsInstance(requirement_sets, list)
        assert isinstance(requirement_sets, list)
        check = requirement_sets[0]["checks"][0]
        self.assertEqual(check["requirement"], "env:MISSING_TOOL_TOKEN")
        self.assertEqual(check["status"], "setup_needed")
        self.assertEqual(check["setup_flow"]["kind"], "env")

    def test_tool_resolver_accepts_any_ready_access_requirement_set(self) -> None:
        resolver = ToolResolver(
            tool_catalog=_FakeToolCatalog(
                Tool(
                    id="either_remote",
                    name="Either Remote",
                    description="Can use either credential set.",
                    access_requirement_sets=(
                        ("env:MISSING_TOOL_TOKEN",),
                        ("env:READY_TOOL_TOKEN",),
                    ),
                ),
            ),
            authorization_port=_DisabledAuthorizationPort(),
            access_port=AccessApplicationService(),
        )
        run = OrchestrationRun.accept(
            run_id="run-access-tool-alternative",
            inbound_instruction=InboundInstruction(source="cli", content="hello"),
        )

        with patch.dict("os.environ", {"READY_TOOL_TOKEN": "token"}):
            resolved = resolver.resolve(run)

        self.assertEqual([item.tool.id for item in resolved.tools], ["either_remote"])
        self.assertIsNone(resolved.blocked_access_by_name("either_remote"))


if __name__ == "__main__":
    unittest.main()
