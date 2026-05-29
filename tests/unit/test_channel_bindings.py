from __future__ import annotations

import unittest

from crxzipple.modules.access import AccessApplicationService
from crxzipple.modules.channels.application.runtime import ChannelRuntimeBootstrapService
from crxzipple.modules.channels.application.services import (
    ChannelProfileApplicationService,
    ChannelRuntimeManager,
)
from crxzipple.modules.channels.application.bindings import (
    ChannelCredentialResolutionError,
    collect_channel_access_requirements,
    resolve_channel_metadata_binding,
)
from crxzipple.modules.channels.application.lark_messages import (
    should_accept_lark_message,
)
from crxzipple.modules.channels.domain import (
    ChannelAccountProfile,
    ChannelProfile,
    ChannelValidationError,
)
from crxzipple.modules.channels.infrastructure.stores import (
    InMemoryChannelRuntimeRegistryStore,
    InMemoryChannelSystemConfigStore,
)
from crxzipple.shared.access import AccessConsumerRef


class _FakeCredentialProvider:
    def __init__(self, credential: str = "provider-secret") -> None:
        self.credential = credential
        self.calls = []

    def resolve_credential(self, binding, *, consumer, trace_context=None):  # noqa: ANN001, ANN201
        self.calls.append((binding, consumer, trace_context))
        return self.credential


class _FailingCredentialProvider:
    def resolve_credential(self, binding, *, consumer, trace_context=None):  # noqa: ANN001, ANN201
        del binding, consumer, trace_context
        raise RuntimeError("credential binding missing")


def _channel_consumer() -> AccessConsumerRef:
    return AccessConsumerRef(
        consumer_id="channels.lark.account:default.lark_app_secret",
        module="channels",
        component="test",
        runtime_ref="lark",
    )


class ChannelBindingsTestCase(unittest.TestCase):
    def test_resolves_access_binding_through_injected_credential_provider(self) -> None:
        provider = _FakeCredentialProvider("secret-value")

        resolved = resolve_channel_metadata_binding(
            {"app_secret_binding": "lark-app-secret"},
            key="app_secret",
            description="Lark app secret",
            required=True,
            credential_provider=provider,
            consumer=_channel_consumer(),
        )

        self.assertEqual(resolved, "secret-value")
        binding, _consumer, _trace_context = provider.calls[0]
        self.assertEqual(binding.source_type, "binding")
        self.assertEqual(binding.source_ref, "lark-app-secret")

    def test_resolves_bindings_through_injected_credential_provider(self) -> None:
        provider = _FakeCredentialProvider("injected-lark-secret")
        consumer = _channel_consumer()

        resolved = resolve_channel_metadata_binding(
            {"lark_app_secret_binding": "lark-app-secret"},
            key="lark_app_secret",
            description="Lark app secret",
            required=True,
            credential_provider=provider,
            consumer=consumer,
        )

        self.assertEqual(resolved, "injected-lark-secret")
        self.assertEqual(len(provider.calls), 1)
        binding, actual_consumer, trace_context = provider.calls[0]
        self.assertEqual(binding.source_ref, "lark-app-secret")
        self.assertEqual(binding.source_type, "binding")
        self.assertEqual(binding.masked_preview, "la***et")
        self.assertIs(actual_consumer, consumer)
        self.assertIsNone(trace_context)

    def test_lark_group_mention_acceptance_uses_injected_access_provider(self) -> None:
        provider = _FakeCredentialProvider("ou_bot")
        consumer = AccessConsumerRef(
            consumer_id="channels.lark.account:default.lark_bot_open_id",
            module="channels",
            component="message_ingress",
            runtime_ref="lark",
        )

        accepted = should_accept_lark_message(
            account_metadata={
                "lark_group_require_bot_mention": True,
                "lark_bot_open_id_binding": "lark-bot-open-id",
            },
            chat_type="group",
            mentions=[{"open_id": "ou_bot"}],
            credential_provider=provider,
            consumer=consumer,
        )

        self.assertTrue(accepted)
        self.assertEqual(len(provider.calls), 1)
        binding, actual_consumer, _trace_context = provider.calls[0]
        self.assertEqual(binding.source_ref, "lark-bot-open-id")
        self.assertIs(actual_consumer, consumer)

    def test_binding_resolution_requires_injected_provider(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "injected credential provider"):
            resolve_channel_metadata_binding(
                {"lark_app_secret_binding": "lark-app-secret"},
                key="lark_app_secret",
                description="Lark app secret",
                required=True,
                consumer=_channel_consumer(),
            )

    def test_direct_credential_sources_are_rejected(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "direct credential source"):
            resolve_channel_metadata_binding(
                {"lark_app_secret_binding": "env:LARK_APP_SECRET"},
                key="lark_app_secret",
                description="Lark app secret",
                required=True,
                credential_provider=_FakeCredentialProvider(),
                consumer=_channel_consumer(),
            )

        with self.assertRaisesRegex(RuntimeError, "inline metadata value"):
            resolve_channel_metadata_binding(
                {"lark_app_secret": "literal-secret"},
                key="lark_app_secret",
                description="Lark app secret",
                required=True,
                credential_provider=_FakeCredentialProvider(),
                consumer=_channel_consumer(),
            )

    def test_binding_resolution_failure_reports_access_not_ready(self) -> None:
        with self.assertRaises(ChannelCredentialResolutionError) as caught:
            resolve_channel_metadata_binding(
                {"lark_app_secret_binding": "access-binding:lark-secret"},
                key="lark_app_secret",
                description="Lark app secret",
                required=True,
                credential_provider=_FailingCredentialProvider(),
                consumer=_channel_consumer(),
            )

        self.assertEqual(caught.exception.code, "access_not_ready")
        self.assertEqual(caught.exception.binding_id, "access-binding:lark-secret")
        self.assertEqual(
            caught.exception.to_payload()["reason"],
            "credential binding missing",
        )

    def test_preserves_literal_channel_metadata_values(self) -> None:
        resolved = resolve_channel_metadata_binding(
            {"display_name": "Lark Production"},
            key="display_name",
            description="display name",
            required=True,
        )

        self.assertEqual(resolved, "Lark Production")

    def test_collects_explicit_channel_access_requirements(self) -> None:
        requirements = collect_channel_access_requirements(
            {
                "access_requirements": ["github:oauth_connector(repo_read)"],
                "lark_app_id_binding": "lark-app-id",
                "lark_bot_open_id_binding": "lark-bot-open-id",
            },
            binding_keys=("lark_app_id",),
        )

        self.assertEqual(
            requirements,
            ("github:oauth_connector(repo_read)", "lark-app-id"),
        )

    def test_channel_runtime_registration_requires_ready_access(self) -> None:
        profile_service = ChannelProfileApplicationService(
            system_config_store=InMemoryChannelSystemConfigStore(),
        )
        profile_service.upsert_profile(
            ChannelProfile(
                channel_type="webhook",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        metadata={"access_requirements": ["webhook-token"]},
                    ),
                ),
            ),
        )
        runtime = ChannelRuntimeBootstrapService(
            profile_service=profile_service,
            runtime_manager=ChannelRuntimeManager(
                registry_store=InMemoryChannelRuntimeRegistryStore(),
            ),
            access_service=AccessApplicationService(),
        )

        with self.assertRaises(ChannelValidationError) as caught:
            runtime.ensure_registered("webhook")
        self.assertEqual(caught.exception.code, "access_not_ready")
        access = caught.exception.details["access"]
        self.assertIsInstance(access, list)
        assert isinstance(access, list)
        self.assertEqual(access[0]["requirement"], "webhook-token")
        self.assertEqual(access[0]["setup_flow"]["kind"], "unsupported")

        runtime.access_service.ready_auth_requirements = ("webhook-token",)
        registration = runtime.ensure_registered("webhook")

        self.assertEqual(registration.channel_type, "webhook")

    def test_runtime_account_binding_metadata_masks_secret_values(self) -> None:
        profile_service = ChannelProfileApplicationService(
            system_config_store=InMemoryChannelSystemConfigStore(),
        )
        profile_service.upsert_profile(
            ChannelProfile(
                channel_type="lark",
                accounts=(
                    ChannelAccountProfile(
                        account_id="default",
                        credential_bindings={
                            "lark_verification_token": "lark-verify",
                        },
                        metadata={
                            "lark_app_id": "cli_app",
                            "lark_app_secret": "literal-super-secret",
                            "agent_id": "assistant",
                        },
                    ),
                ),
            ),
        )
        runtime_manager = ChannelRuntimeManager(
            registry_store=InMemoryChannelRuntimeRegistryStore(),
        )
        runtime = ChannelRuntimeBootstrapService(
            profile_service=profile_service,
            runtime_manager=runtime_manager,
        )

        runtime.ensure_registered("lark")
        bindings = runtime_manager.list_account_bindings(
            runtime_id="lark-runtime-1",
            channel_type="lark",
        )

        self.assertEqual(len(bindings), 1)
        metadata = bindings[0].metadata
        self.assertEqual(metadata["lark_app_id"], "cli_app")
        self.assertEqual(metadata["lark_verification_token_binding"], "lark-verify")
        self.assertNotIn("lark_app_secret", metadata)
        self.assertIn("lark_app_secret_masked_preview", metadata)
        self.assertNotIn("literal-super-secret", str(metadata))


if __name__ == "__main__":
    unittest.main()
