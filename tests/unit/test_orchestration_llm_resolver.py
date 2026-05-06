from __future__ import annotations

import unittest
from unittest.mock import patch

from crxzipple.modules.agent.domain import AgentLlmRoutingPolicy
from crxzipple.modules.access import AccessApplicationService
from crxzipple.modules.llm.domain import (
    LlmApiFamily,
    LlmCapability,
    LlmModelFamily,
    LlmProfile,
    LlmProviderKind,
)
from crxzipple.modules.llm.domain.exceptions import LlmNotFoundError
from crxzipple.modules.orchestration.application.llm_resolver import LlmResolver
from crxzipple.modules.orchestration.domain import OrchestrationValidationError


class _FakeLlmPort:
    def __init__(self, *profiles: LlmProfile) -> None:
        self._profiles = {profile.id: profile for profile in profiles}

    def get_profile(self, llm_id: str) -> LlmProfile:
        profile = self._profiles.get(llm_id)
        if profile is None:
            raise LlmNotFoundError(f"LLM profile '{llm_id}' was not found.")
        return profile


def _profile(
    profile_id: str,
    *,
    capabilities: tuple[LlmCapability, ...] = (),
    credential_binding: str | None = None,
    enabled: bool = True,
) -> LlmProfile:
    return LlmProfile(
        id=profile_id,
        provider=LlmProviderKind.OPENAI,
        api_family=LlmApiFamily.OPENAI_RESPONSES,
        model_name=profile_id,
        model_family=(
            LlmModelFamily.VISION
            if LlmCapability.VISION_INPUT in capabilities
            else LlmModelFamily.GENERAL
        ),
        capabilities=capabilities,
        credential_binding=credential_binding,
        enabled=enabled,
    )


class LlmResolverTestCase(unittest.TestCase):
    def test_explicit_llm_id_wins_over_auto_routing(self) -> None:
        resolver = LlmResolver(
            _FakeLlmPort(
                _profile("text-default"),
                _profile("image-special", capabilities=(LlmCapability.VISION_INPUT,)),
            ),
        )
        routing_policy = AgentLlmRoutingPolicy(
            default_llm_id="text-default",
            image_llm_id="image-special",
        )

        resolved = resolver.resolve(
            requested_llm_id="text-default",
            routing_policy=routing_policy,
            input_content={
                "blocks": [
                    {
                        "type": "image",
                        "data": "aGVsbG8=",
                        "mime_type": "image/png",
                    },
                ],
            },
        )

        self.assertEqual(resolved.resolved_llm_id, "text-default")
        self.assertEqual(resolved.strategy, "explicit")

    def test_auto_routes_image_input_to_image_llm(self) -> None:
        resolver = LlmResolver(
            _FakeLlmPort(
                _profile("text-default"),
                _profile("image-special", capabilities=(LlmCapability.VISION_INPUT,)),
            ),
        )
        routing_policy = AgentLlmRoutingPolicy(
            default_llm_id="text-default",
            image_llm_id="image-special",
        )

        resolved = resolver.resolve(
            requested_llm_id="auto",
            routing_policy=routing_policy,
            input_content={
                "blocks": [
                    {
                        "type": "image",
                        "data": "aGVsbG8=",
                        "mime_type": "image/png",
                    },
                ],
            },
        )

        self.assertEqual(resolved.resolved_llm_id, "image-special")
        self.assertEqual(resolved.strategy, "auto-image")
        self.assertTrue(resolved.input_has_image)

    def test_auto_routes_image_ref_input_to_image_llm(self) -> None:
        resolver = LlmResolver(
            _FakeLlmPort(
                _profile("text-default"),
                _profile("image-special", capabilities=(LlmCapability.VISION_INPUT,)),
            ),
        )
        routing_policy = AgentLlmRoutingPolicy(
            default_llm_id="text-default",
            image_llm_id="image-special",
        )

        resolved = resolver.resolve(
            requested_llm_id="auto",
            routing_policy=routing_policy,
            input_content={
                "blocks": [
                    {
                        "type": "image_ref",
                        "artifact_id": "img_123",
                        "mime_type": "image/png",
                    },
                ],
            },
        )

        self.assertEqual(resolved.resolved_llm_id, "image-special")
        self.assertEqual(resolved.strategy, "auto-image")
        self.assertTrue(resolved.input_has_image)

    def test_auto_routes_file_input_to_document_llm(self) -> None:
        resolver = LlmResolver(
            _FakeLlmPort(
                _profile("text-default"),
                _profile("doc-special"),
            ),
        )
        routing_policy = AgentLlmRoutingPolicy(
            default_llm_id="text-default",
            document_llm_id="doc-special",
        )

        resolved = resolver.resolve(
            requested_llm_id="AUTO",
            routing_policy=routing_policy,
            input_content={
                "blocks": [
                    {
                        "type": "file",
                        "data": "aGVsbG8=",
                        "mime_type": "application/pdf",
                        "name": "brief.pdf",
                    },
                ],
            },
        )

        self.assertEqual(resolved.resolved_llm_id, "doc-special")
        self.assertEqual(resolved.strategy, "auto-document")
        self.assertTrue(resolved.input_has_file)

    def test_auto_falls_back_to_vision_capable_fallback(self) -> None:
        resolver = LlmResolver(
            _FakeLlmPort(
                _profile("text-default"),
                _profile("vision-fallback", capabilities=(LlmCapability.VISION_INPUT,)),
            ),
        )
        routing_policy = AgentLlmRoutingPolicy(
            default_llm_id="text-default",
            image_llm_id="missing-image",
            fallback_llm_ids=("vision-fallback",),
        )

        resolved = resolver.resolve(
            requested_llm_id="auto",
            routing_policy=routing_policy,
            input_content={
                "blocks": [
                    {
                        "type": "image",
                        "data": "aGVsbG8=",
                        "mime_type": "image/png",
                    },
                ],
            },
        )

        self.assertEqual(resolved.resolved_llm_id, "vision-fallback")
        self.assertEqual(resolved.strategy, "auto-image")

    def test_auto_raises_when_no_vision_capable_model_exists(self) -> None:
        resolver = LlmResolver(
            _FakeLlmPort(
                _profile("text-default"),
                _profile("image-special"),
            ),
        )
        routing_policy = AgentLlmRoutingPolicy(
            default_llm_id="text-default",
            image_llm_id="image-special",
        )

        with self.assertRaises(OrchestrationValidationError):
            resolver.resolve(
                requested_llm_id="auto",
                routing_policy=routing_policy,
                input_content={
                    "blocks": [
                        {
                            "type": "image",
                            "data": "aGVsbG8=",
                            "mime_type": "image/png",
                        },
                    ],
                },
            )

    def test_auto_skips_models_without_ready_access(self) -> None:
        resolver = LlmResolver(
            _FakeLlmPort(
                _profile("missing-access", credential_binding="env:MISSING_LLM_TOKEN"),
                _profile("ready-fallback", credential_binding="env:READY_LLM_TOKEN"),
            ),
            access_port=AccessApplicationService(),
        )
        routing_policy = AgentLlmRoutingPolicy(
            default_llm_id="missing-access",
            fallback_llm_ids=("ready-fallback",),
        )

        with patch.dict("os.environ", {"READY_LLM_TOKEN": "token"}):
            resolved = resolver.resolve(
                requested_llm_id="auto",
                routing_policy=routing_policy,
                input_content="hello",
            )

        self.assertEqual(resolved.resolved_llm_id, "ready-fallback")
        self.assertEqual(resolved.strategy, "auto-default")

    def test_explicit_model_with_missing_access_is_rejected(self) -> None:
        resolver = LlmResolver(
            _FakeLlmPort(
                _profile("missing-access", credential_binding="env:MISSING_LLM_TOKEN"),
            ),
            access_port=AccessApplicationService(),
        )
        routing_policy = AgentLlmRoutingPolicy(default_llm_id="missing-access")

        with self.assertRaises(OrchestrationValidationError) as caught:
            resolver.resolve(
                requested_llm_id="missing-access",
                routing_policy=routing_policy,
                input_content="hello",
            )
        self.assertEqual(caught.exception.code, "access_not_ready")
        self.assertEqual(caught.exception.details["resource_type"], "llm_profile")
        access = caught.exception.details["access"]
        self.assertIsInstance(access, dict)
        assert isinstance(access, dict)
        self.assertEqual(access["requirement"], "env:MISSING_LLM_TOKEN")
        self.assertEqual(access["status"], "setup_needed")
        setup_flow = access["setup_flow"]
        self.assertIsInstance(setup_flow, dict)
        assert isinstance(setup_flow, dict)
        self.assertEqual(setup_flow["kind"], "env")


if __name__ == "__main__":
    unittest.main()
