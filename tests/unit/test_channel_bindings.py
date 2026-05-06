from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from crxzipple.modules.access import AccessApplicationService
from crxzipple.modules.channels.application.runtime import ChannelRuntimeBootstrapService
from crxzipple.modules.channels.application.services import (
    ChannelProfileApplicationService,
    ChannelRuntimeManager,
)
from crxzipple.modules.channels.application.bindings import (
    collect_channel_access_requirements,
    collect_channel_binding_env_vars,
    resolve_channel_metadata_binding,
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


class ChannelBindingsTestCase(unittest.TestCase):
    def test_resolves_env_binding_through_access_resolver(self) -> None:
        with patch.dict("os.environ", {"LARK_APP_SECRET": "secret-value"}):
            resolved = resolve_channel_metadata_binding(
                {"app_secret_binding": "env:LARK_APP_SECRET"},
                key="app_secret",
                description="Lark app secret",
                required=True,
            )

        self.assertEqual(resolved, "secret-value")

    def test_resolves_file_binding_value_through_access_resolver(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            credential_path = Path(tempdir) / "lark-secret.txt"
            credential_path.write_text("file-secret\n", encoding="utf-8")

            resolved = resolve_channel_metadata_binding(
                {"app_secret": f"file:{credential_path}"},
                key="app_secret",
                description="Lark app secret",
                required=True,
            )

        self.assertEqual(resolved, "file-secret")

    def test_preserves_literal_channel_metadata_values(self) -> None:
        resolved = resolve_channel_metadata_binding(
            {"verification_token": "literal-token"},
            key="verification_token",
            description="verification token",
            required=True,
        )

        self.assertEqual(resolved, "literal-token")

    def test_collects_env_vars_without_resolving_them(self) -> None:
        env_vars = collect_channel_binding_env_vars(
            {
                "app_id_binding": "env:LARK_APP_ID",
                "app_secret": "env:LARK_APP_SECRET",
                "literal": "value",
            },
        )

        self.assertEqual(env_vars, ("LARK_APP_ID", "LARK_APP_SECRET"))

    def test_collects_explicit_channel_access_requirements(self) -> None:
        requirements = collect_channel_access_requirements(
            {
                "access_requirements": ["github:oauth_connector(repo_read)"],
                "lark_app_id_binding": "env:LARK_APP_ID",
                "lark_bot_open_id_binding": "env:LARK_BOT_OPEN_ID",
            },
            binding_keys=("lark_app_id",),
        )

        self.assertEqual(
            requirements,
            ("github:oauth_connector(repo_read)", "env:LARK_APP_ID"),
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
                        metadata={"access_requirements": ["env:WEBHOOK_TOKEN"]},
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
        self.assertEqual(access[0]["requirement"], "env:WEBHOOK_TOKEN")
        self.assertEqual(access[0]["setup_flow"]["kind"], "env")

        with patch.dict("os.environ", {"WEBHOOK_TOKEN": "token"}):
            registration = runtime.ensure_registered("webhook")

        self.assertEqual(registration.channel_type, "webhook")


if __name__ == "__main__":
    unittest.main()
