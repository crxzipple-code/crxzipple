from __future__ import annotations

import unittest

from crxzipple.modules.channels.application.runtime import ChannelRuntimeBootstrapService
from crxzipple.modules.channels.application.services import ChannelProfileApplicationService
from crxzipple.modules.channels.application.services import ChannelRuntimeManager
from crxzipple.modules.channels.application.settings_integration import (
    channel_profile_from_settings,
)
from crxzipple.modules.channels.domain import ChannelAccountProfile, ChannelProfile
from crxzipple.modules.channels.infrastructure import InMemoryChannelSystemConfigStore
from crxzipple.modules.channels.infrastructure import InMemoryChannelRuntimeRegistryStore
from crxzipple.shared.access import AccessCredentialKind


class ChannelAccessCredentialRequirementTestCase(unittest.TestCase):
    def test_lark_profile_declares_credential_slots_from_bindings(self) -> None:
        profile = channel_profile_from_settings(
            {
                "channel_type": "lark",
                "accounts": [
                    {
                        "account_id": "default",
                        "credential_bindings": {
                            "lark_app_id": "access-binding:lark-app-id",
                            "lark_app_secret": "access-binding:lark-app-secret",
                            "lark_verification_token": "access-binding:lark-token",
                            "lark_encrypt_key": "access-binding:lark-encrypt-key",
                            "lark_bot_open_id": "access-binding:lark-bot-open-id",
                        },
                    },
                ],
            },
        )

        account = profile.accounts[0]
        self.assertEqual(
            account.metadata["lark_app_id_binding"],
            "access-binding:lark-app-id",
        )
        requirement_set = account.credential_requirements
        self.assertIsNotNone(requirement_set)
        assert requirement_set is not None
        requirements_by_slot = {
            requirement.slot.slot: requirement for requirement in requirement_set.requirements
        }

        self.assertEqual(set(requirements_by_slot), set(account.credential_bindings))
        self.assertEqual(
            requirements_by_slot["lark_app_secret"].slot.expected_kind,
            AccessCredentialKind.APP_SECRET,
        )
        self.assertEqual(
            requirements_by_slot["lark_verification_token"].slot.expected_kind,
            AccessCredentialKind.WEBHOOK_SECRET,
        )
        self.assertEqual(
            requirements_by_slot["lark_bot_open_id"].slot.binding_id,
            "access-binding:lark-bot-open-id",
        )

        payload = profile.to_payload()
        payload_requirements = payload["accounts"][0]["credential_requirements"]
        self.assertEqual(
            payload_requirements["requirements"][0]["consumer"]["module"],
            "channels",
        )
        self.assertEqual(
            {
                item["slot"]["slot"]: item["slot"]["binding_id"]
                for item in payload_requirements["requirements"]
            },
            account.credential_bindings,
        )

    def test_lark_metadata_binding_fields_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "credential_bindings"):
            channel_profile_from_settings(
                {
                    "channel_type": "lark",
                    "accounts": [
                        {
                            "account_id": "legacy",
                            "metadata": {
                                "lark_app_id_binding": "access-binding:legacy-app-id",
                                "lark_app_secret_binding": "access-binding:legacy-secret",
                            },
                        },
                    ],
                },
            )

    def test_webhook_profile_declares_signing_secret_slot_from_binding(self) -> None:
        profile = channel_profile_from_settings(
            {
                "channel_type": "webhook",
                "accounts": [
                    {
                        "account_id": "default",
                        "transport_mode": "webhook",
                        "credential_bindings": {
                            "webhook_signing_secret": "access-binding:webhook-secret",
                        },
                    },
                ],
            },
        )

        account = profile.accounts[0]
        self.assertEqual(
            account.metadata["webhook_signing_secret_binding"],
            "access-binding:webhook-secret",
        )
        requirement_set = account.credential_requirements
        self.assertIsNotNone(requirement_set)
        assert requirement_set is not None
        self.assertEqual(len(requirement_set.requirements), 1)
        requirement = requirement_set.requirements[0]
        self.assertEqual(requirement.provider, "webhook")
        self.assertEqual(requirement.slot.slot, "webhook_signing_secret")
        self.assertEqual(
            requirement.slot.expected_kind,
            AccessCredentialKind.WEBHOOK_SECRET,
        )
        self.assertEqual(
            requirement.slot.binding_id,
            "access-binding:webhook-secret",
        )

    def test_webhook_metadata_binding_field_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "credential_bindings"):
            channel_profile_from_settings(
                {
                    "channel_type": "webhook",
                    "accounts": [
                        {
                            "account_id": "legacy",
                            "metadata": {
                                "webhook_signing_secret_binding": (
                                    "access-binding:webhook-secret"
                                ),
                            },
                        },
                    ],
                },
            )

    def test_wecom_profile_declares_app_credential_slots_without_oauth_flow(self) -> None:
        profile = channel_profile_from_settings(
            {
                "channel_type": "wecom",
                "accounts": [
                    {
                        "account_id": "default",
                        "credential_bindings": {
                            "wecom_corp_id": "access-binding:wecom-corp-id",
                            "wecom_agent_id": "access-binding:wecom-agent-id",
                            "wecom_corp_secret": "access-binding:wecom-corp-secret",
                            "wecom_token": "access-binding:wecom-token",
                            "wecom_encoding_aes_key": "access-binding:wecom-aes-key",
                        },
                    },
                ],
            },
        )

        account = profile.accounts[0]
        self.assertEqual(
            account.metadata["wecom_corp_secret_binding"],
            "access-binding:wecom-corp-secret",
        )
        requirement_set = account.credential_requirements
        self.assertIsNotNone(requirement_set)
        assert requirement_set is not None
        requirements_by_slot = {
            requirement.slot.slot: requirement for requirement in requirement_set.requirements
        }

        self.assertEqual(set(requirements_by_slot), set(account.credential_bindings))
        self.assertEqual(
            requirements_by_slot["wecom_corp_id"].slot.expected_kind,
            AccessCredentialKind.API_KEY,
        )
        self.assertEqual(
            requirements_by_slot["wecom_agent_id"].slot.expected_kind,
            AccessCredentialKind.API_KEY,
        )
        self.assertEqual(
            requirements_by_slot["wecom_corp_secret"].slot.expected_kind,
            AccessCredentialKind.APP_SECRET,
        )
        self.assertEqual(
            requirements_by_slot["wecom_token"].slot.expected_kind,
            AccessCredentialKind.WEBHOOK_SECRET,
        )
        self.assertEqual(
            requirements_by_slot["wecom_encoding_aes_key"].slot.expected_kind,
            AccessCredentialKind.WEBHOOK_SECRET,
        )
        self.assertTrue(
            all(
                requirement.setup_flow_hint.flow_kind.value == "manual"
                for requirement in requirements_by_slot.values()
            ),
        )
        self.assertTrue(
            all(
                requirement.slot.expected_kind is not AccessCredentialKind.OAUTH2_ACCOUNT
                for requirement in requirements_by_slot.values()
            ),
        )

    def test_wecom_metadata_binding_fields_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "credential_bindings"):
            channel_profile_from_settings(
                {
                    "channel_type": "wecom",
                    "accounts": [
                        {
                            "account_id": "legacy",
                            "metadata": {
                                "wecom_corp_secret_binding": (
                                    "access-binding:wecom-secret"
                                ),
                            },
                        },
                    ],
                },
            )

    def test_profile_metadata_binding_field_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "account credential_bindings"):
            ChannelProfile(
                channel_type="webhook",
                metadata={
                    "webhook_signing_secret_binding": "access-binding:webhook-secret",
                },
            )

    def test_profile_metadata_secret_field_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "profile metadata credential fields"):
            ChannelProfile(
                channel_type="webhook",
                metadata={
                    "webhook_signing_secret": "inline-webhook-secret",
                },
                accounts=(ChannelAccountProfile(account_id="default"),),
            )

    def test_non_lark_channel_reports_empty_requirement_list(self) -> None:
        profile = channel_profile_from_settings(
            {
                "channel_type": "web",
                "accounts": [{"account_id": "browser"}],
            },
        )

        requirement_set = profile.accounts[0].credential_requirements
        self.assertIsNotNone(requirement_set)
        assert requirement_set is not None
        self.assertEqual(requirement_set.requirements, ())
        self.assertEqual(
            profile.to_payload()["accounts"][0]["credential_requirements"]["requirements"],
            [],
        )

    def test_runtime_access_requirements_include_credential_binding_slots(self) -> None:
        profile = ChannelProfile(
            channel_type="lark",
            accounts=(
                ChannelAccountProfile(
                    account_id="default",
                    credential_bindings={
                        "lark_app_id": "access-binding:lark-app-id",
                        "lark_app_secret": "access-binding:lark-app-secret",
                    },
                ),
            ),
        )
        runtime = ChannelRuntimeBootstrapService(
            profile_service=ChannelProfileApplicationService(
                system_config_store=InMemoryChannelSystemConfigStore(),
            ),
            runtime_manager=ChannelRuntimeManager(
                registry_store=InMemoryChannelRuntimeRegistryStore(),
            ),
        )

        self.assertEqual(
            runtime.profile_access_requirements(profile),
            (
                "access-binding:lark-app-id",
                "access-binding:lark-app-secret",
            ),
        )

    def test_runtime_access_requirements_include_wecom_credential_slots(self) -> None:
        profile = ChannelProfile(
            channel_type="wecom",
            accounts=(
                ChannelAccountProfile(
                    account_id="default",
                    credential_bindings={
                        "wecom_corp_id": "access-binding:wecom-corp-id",
                        "wecom_agent_id": "access-binding:wecom-agent-id",
                        "wecom_corp_secret": "access-binding:wecom-corp-secret",
                    },
                ),
            ),
        )
        runtime = ChannelRuntimeBootstrapService(
            profile_service=ChannelProfileApplicationService(
                system_config_store=InMemoryChannelSystemConfigStore(),
            ),
            runtime_manager=ChannelRuntimeManager(
                registry_store=InMemoryChannelRuntimeRegistryStore(),
            ),
        )

        self.assertEqual(
            runtime.profile_access_requirements(profile),
            (
                "access-binding:wecom-corp-id",
                "access-binding:wecom-agent-id",
                "access-binding:wecom-corp-secret",
            ),
        )


if __name__ == "__main__":
    unittest.main()
