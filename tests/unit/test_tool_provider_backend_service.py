from __future__ import annotations

import unittest

from crxzipple.modules.tool.application.provider_backend_service import (
    ToolProviderBackendReadinessEvaluator,
    ToolProviderBackendResolver,
    provider_backend_policy_from_metadata,
)
from crxzipple.modules.tool.application.ports import (
    ToolAccessReadiness,
    ToolAccessReadinessCheck,
)
from crxzipple.modules.tool.domain.entities import ToolFunction, ToolProviderBackend
from crxzipple.modules.tool.domain.exceptions import ToolExecutionNotAllowedError
from crxzipple.modules.tool.domain.value_objects import (
    ToolProviderBackendStatus,
    ToolProviderCapability,
)


class ToolProviderBackendResolverTestCase(unittest.TestCase):
    def test_policy_parser_includes_default_and_fallback_in_allowed_set(self) -> None:
        policy = provider_backend_policy_from_metadata(
            {
                "provider_backend_policy": {
                    "capability": "image_generation",
                    "default_backend_id": "image.primary",
                    "fallback_backend_ids": ["image.fallback"],
                },
            },
        )

        self.assertIsNotNone(policy)
        assert policy is not None
        self.assertEqual(policy.capability, ToolProviderCapability.IMAGE_GENERATION)
        self.assertEqual(policy.default_backend_id, "image.primary")
        self.assertEqual(policy.fallback_backend_ids, ("image.fallback",))
        self.assertEqual(
            policy.allowed_backend_ids,
            ("image.primary", "image.fallback"),
        )

    def test_resolver_uses_fallback_when_default_backend_is_disabled(self) -> None:
        resolver = ToolProviderBackendResolver()
        function = _function(
            {
                "capability": "image_generation",
                "default_backend_id": "image.primary",
                "fallback_backend_ids": ["image.fallback"],
            },
        )
        repository = _BackendRepository(
            _backend("image.primary", enabled=False),
            _backend("image.fallback", priority=20),
        )

        resolution = resolver.resolve_for_function(
            function=function,
            repository=repository,
        )

        self.assertIsNotNone(resolution)
        assert resolution is not None
        self.assertEqual(resolution.backend.backend_id, "image.fallback")
        self.assertEqual(
            resolution.to_payload()["credential_bindings"],
            {"openai_api_key": "openai-api-key"},
        )

    def test_resolver_reports_structured_error_when_no_backend_is_usable(self) -> None:
        resolver = ToolProviderBackendResolver()
        function = _function(
            {
                "capability": "image_generation",
                "default_backend_id": "image.primary",
            },
        )
        repository = _BackendRepository(
            _backend("image.primary", status=ToolProviderBackendStatus.DISABLED),
        )

        with self.assertRaises(ToolExecutionNotAllowedError) as raised:
            resolver.resolve_for_function(function=function, repository=repository)

        error = raised.exception
        self.assertEqual(error.code, "tool_provider_backend_not_available")
        self.assertEqual(error.detail["category"], "provider_backend")
        self.assertEqual(error.detail["function_id"], "image_generate")

    def test_readiness_evaluator_uses_tool_access_readiness_port(self) -> None:
        evaluator = ToolProviderBackendReadinessEvaluator()

        readiness = evaluator.check_backend_readiness(
            _backend("image.primary"),
            access_readiness=_ReadyAccessReadiness(),
        )

        payload = readiness.to_payload()
        self.assertTrue(payload["ready"])
        self.assertEqual(payload["status"], "ready")
        self.assertEqual(payload["parts"]["access"]["checks"][0]["binding_id"], "openai-api-key")


class _BackendRepository:
    def __init__(self, *backends: ToolProviderBackend) -> None:
        self._backends = {backend.backend_id: backend for backend in backends}

    def get(self, backend_id: str) -> ToolProviderBackend | None:
        return self._backends.get(backend_id)

    def list(
        self,
        *,
        capability,
        status,
    ) -> list[ToolProviderBackend]:
        return [
            backend
            for backend in sorted(
                self._backends.values(),
                key=lambda item: item.priority,
            )
            if backend.capability == capability and backend.status == status
        ]


class _ReadyAccessReadiness:
    def check_tool_access(self, tool) -> ToolAccessReadiness:  # noqa: ANN001
        self._assert_backend_tool(tool)
        return ToolAccessReadiness(
            ready=True,
            status="ready",
            reason="ready",
            checks=(
                ToolAccessReadinessCheck(
                    requirement="openai_api_key",
                    ready=True,
                    status="ready",
                    reason="ready",
                    binding_id="openai-api-key",
                    expected_kind="api_key",
                ),
            ),
        )

    def _assert_backend_tool(self, tool) -> None:  # noqa: ANN001
        assert tool.id == "image.primary"
        assert tool.credential_requirements
        slot = tool.credential_requirements[0].requirements[0].slot
        assert slot.binding_id == "openai-api-key"


def _function(policy: dict[str, object]) -> ToolFunction:
    return ToolFunction(
        id="image_generate",
        source_id="bundled.local_package.image",
        stable_key="local_package.image.image_generate",
        name="Image Generate",
        display_name="Image Generate",
        metadata={"provider_backend_policy": policy},
    )


def _backend(
    backend_id: str,
    *,
    priority: int = 10,
    enabled: bool = True,
    status: ToolProviderBackendStatus = ToolProviderBackendStatus.ACTIVE,
) -> ToolProviderBackend:
    return ToolProviderBackend(
        id=backend_id,
        source_id="bundled.local_package.image",
        capability=ToolProviderCapability.IMAGE_GENERATION,
        display_name=backend_id,
        credential_requirements=(
            {
                "requirement_set_id": "openai-image-credentials",
                "consumer": {
                    "consumer_id": "tool.provider_backend.image.primary",
                    "module": "tool",
                    "component": "provider_backend",
                },
                "requirements": [
                    {
                        "requirement_id": "openai-image-api-key",
                        "slot": {
                            "slot": "openai_api_key",
                            "binding_id": "openai-api-key",
                            "expected_kind": "api_key",
                        },
                    },
                ],
            },
        ),
        runtime_ref={"runtime_kind": "local", "ref": "image_generate"},
        priority=priority,
        enabled=enabled,
        status=status,
    )


if __name__ == "__main__":
    unittest.main()
