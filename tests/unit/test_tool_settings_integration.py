from __future__ import annotations

import unittest

from crxzipple.modules.tool.application.settings_integration import (
    tool_settings_bootstrap_config_from_settings,
)
from crxzipple.shared.settings import (
    ToolProviderConfig,
    ToolRootConfig,
)


class ToolSettingsIntegrationTestCase(unittest.TestCase):
    def test_openapi_provider_config_converts_to_bootstrap_settings(self) -> None:
        config = ToolProviderConfig(
            provider_id="weather",
            provider_kind="openapi",
            display_name="Weather API",
            base_url="https://weather.example.test",
            spec_path="config/openapi/weather.yaml",
            discovery={
                "timeout_seconds": 45,
                "max_concurrency": 3,
                "default_effect_ids": ("network_access",),
            },
        )

        bootstrap = tool_settings_bootstrap_config_from_settings((config,))
        provider = bootstrap.openapi_providers[0]

        self.assertEqual(provider.name, "weather")
        self.assertEqual(provider.spec_location, "config/openapi/weather.yaml")
        self.assertEqual(provider.base_url, "https://weather.example.test")
        self.assertEqual(provider.description, "Weather API")
        self.assertEqual(provider.timeout_seconds, 45)
        self.assertEqual(provider.max_concurrency, 3)
        self.assertEqual(provider.default_effect_ids, ("network_access",))
        self.assertEqual(bootstrap.mcp_providers, ())
        self.assertEqual(bootstrap.local_paths, ())

    def test_mcp_provider_mapping_converts_to_bootstrap_settings(self) -> None:
        bootstrap = tool_settings_bootstrap_config_from_settings(
            (
                {
                    "id": "filesystem",
                    "kind": "mcp",
                    "description": "Filesystem MCP",
                    "command": "uvx",
                    "args": ("mcp-server-filesystem", "/tmp/workspace"),
                    "timeout_seconds": "12",
                    "max_concurrency": "2",
                    "default_effect_ids": ("local_tool_access",),
                },
            ),
        )
        provider = bootstrap.mcp_providers[0]

        self.assertEqual(provider.name, "filesystem")
        self.assertEqual(
            provider.command,
            ("uvx", "mcp-server-filesystem", "/tmp/workspace"),
        )
        self.assertEqual(provider.description, "Filesystem MCP")
        self.assertEqual(provider.timeout_seconds, 12)
        self.assertEqual(provider.max_concurrency, 2)
        self.assertEqual(provider.default_effect_ids, ("local_tool_access",))

    def test_http_mcp_provider_mapping_converts_to_bootstrap_settings(self) -> None:
        bootstrap = tool_settings_bootstrap_config_from_settings(
            (
                {
                    "id": "sample",
                    "kind": "mcp",
                    "description": "Sample MCP",
                    "transport": "http",
                    "endpoint_url": "http://127.0.0.1:19800/mcp",
                    "timeout_seconds": "12",
                },
            ),
        )
        provider = bootstrap.mcp_providers[0]

        self.assertEqual(provider.name, "sample")
        self.assertEqual(provider.transport, "http")
        self.assertEqual(provider.endpoint_url, "http://127.0.0.1:19800/mcp")
        self.assertEqual(provider.command, ())

    def test_local_roots_convert_to_local_path_tuple(self) -> None:
        bootstrap = tool_settings_bootstrap_config_from_settings(
            providers=(
                {
                    "provider_id": "workspace-tools",
                    "provider_kind": "local_root",
                    "path": ".crxzipple/tools",
                },
            ),
            roots=(
                ToolRootConfig(root_id="bundled", path="tools"),
                {"id": "duplicate", "path": "tools"},
            ),
        )

        self.assertEqual(bootstrap.local_paths, (".crxzipple/tools", "tools"))

    def test_disabled_configs_are_filtered_by_default(self) -> None:
        bootstrap = tool_settings_bootstrap_config_from_settings(
            providers=(
                {
                    "provider_id": "disabled-openapi",
                    "provider_kind": "openapi",
                    "enabled": False,
                    "spec_location": "disabled.yaml",
                },
            ),
            roots=(ToolRootConfig(root_id="disabled-root", path="disabled", enabled=False),),
        )

        self.assertEqual(bootstrap.openapi_providers, ())
        self.assertEqual(bootstrap.local_paths, ())

        included = tool_settings_bootstrap_config_from_settings(
            providers=(
                {
                    "provider_id": "disabled-openapi",
                    "provider_kind": "openapi",
                    "enabled": False,
                    "spec_location": "disabled.yaml",
                },
            ),
            roots=(ToolRootConfig(root_id="disabled-root", path="disabled", enabled=False),),
            include_disabled=True,
        )

        self.assertEqual([item.name for item in included.openapi_providers], ["disabled-openapi"])
        self.assertEqual(included.local_paths, ("disabled",))

    def test_openapi_credential_bindings_mapping_is_preserved(self) -> None:
        bootstrap = tool_settings_bootstrap_config_from_settings(
            (
                {
                    "provider_id": "petstore",
                    "provider_kind": "openapi",
                    "spec_path": "petstore.yaml",
                    "credential_bindings": {
                        "ApiKeyAuth": "petstore-api-key",
                        "BasicAuth": {
                            "username_binding_id": "petstore-basic-username",
                            "password_binding_id": "petstore-basic-password",
                        },
                    },
                },
            ),
        )
        bindings = bootstrap.openapi_providers[0].credential_bindings

        self.assertEqual(bindings[0].scheme_name, "ApiKeyAuth")
        self.assertEqual(bindings[0].credential_binding_id, "petstore-api-key")
        self.assertEqual(bindings[1].scheme_name, "BasicAuth")
        self.assertEqual(bindings[1].username_binding_id, "petstore-basic-username")
        self.assertEqual(bindings[1].password_binding_id, "petstore-basic-password")

    def test_openapi_settings_reject_direct_credential_sources(self) -> None:
        for forbidden_binding_id in (
            "env:PETSTORE_TOKEN",
            "file:/tmp/petstore-token",
            "codex_auth_json",
            "auth_ref",
        ):
            with self.subTest(forbidden_binding_id=forbidden_binding_id):
                with self.assertRaisesRegex(ValueError, "direct credential source"):
                    tool_settings_bootstrap_config_from_settings(
                        (
                            {
                                "provider_id": "petstore",
                                "provider_kind": "openapi",
                                "spec_path": "petstore.yaml",
                                "credential_bindings": {
                                    "ApiKeyAuth": forbidden_binding_id,
                                },
                            },
                        ),
                    )

    def test_openapi_settings_reject_legacy_auth_ref_field(self) -> None:
        with self.assertRaisesRegex(ValueError, "no longer accepted"):
            tool_settings_bootstrap_config_from_settings(
                (
                    {
                        "provider_id": "petstore",
                        "provider_kind": "openapi",
                        "spec_path": "petstore.yaml",
                        "credential_bindings": {
                            "ApiKeyAuth": {"auth_ref": "petstore-token"},
                        },
                    },
                ),
            )

    def test_openapi_settings_reject_legacy_binding_alias_fields(self) -> None:
        for field_name in (
            "credential_binding",
            "credential_binding_ref",
            "binding_id",
            "username_binding",
            "password_binding",
        ):
            with self.subTest(field_name=field_name):
                with self.assertRaisesRegex(ValueError, "no longer accepted"):
                    tool_settings_bootstrap_config_from_settings(
                        (
                            {
                                "provider_id": "petstore",
                                "provider_kind": "openapi",
                                "spec_path": "petstore.yaml",
                                "credential_bindings": {
                                    "ApiKeyAuth": {
                                        "credential_binding_id": "petstore-api-key",
                                        field_name: "legacy-binding",
                                    },
                                },
                            },
                        ),
                    )

if __name__ == "__main__":
    unittest.main()
