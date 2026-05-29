from __future__ import annotations

from dataclasses import fields
from pathlib import Path
import unittest

from crxzipple.modules.channels.domain import (
    ChannelAccountProfile,
    ChannelProfile,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


class ChannelAccessArchitectureTestCase(unittest.TestCase):
    def test_channel_account_profile_has_no_auth_ref_field(self) -> None:
        field_names = {field.name for field in fields(ChannelAccountProfile)}

        self.assertNotIn("auth_ref", field_names)

    def test_channel_profiles_reject_direct_credential_sources(self) -> None:
        for forbidden_binding_id in (
            "env:LARK_APP_SECRET",
            "file:/tmp/lark-secret",
            "codex_auth_json",
            "auth_ref",
        ):
            with self.subTest(forbidden_binding_id=forbidden_binding_id):
                with self.assertRaisesRegex(ValueError, "direct credential source"):
                    ChannelProfile(
                        channel_type="lark",
                        accounts=(
                            ChannelAccountProfile(
                                account_id="default",
                                credential_bindings={
                                    "lark_app_secret": forbidden_binding_id,
                                },
                            ),
                        ),
                    )

    def test_channel_profile_config_uses_access_binding_ids(self) -> None:
        config_root = PROJECT_ROOT / "config" / "channel_profiles"
        offenders: list[str] = []
        for path in sorted(config_root.rglob("*")):
            if path.suffix not in {".json", ".yaml", ".yml"}:
                continue
            text = path.read_text(encoding="utf-8")
            for forbidden in ("env:", "file:", "codex_auth_json", "auth_ref"):
                if forbidden in text:
                    offenders.append(f"{path.relative_to(PROJECT_ROOT)}:{forbidden}")

        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
