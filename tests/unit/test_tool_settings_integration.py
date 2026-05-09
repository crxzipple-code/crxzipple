from __future__ import annotations

import unittest

from crxzipple.modules.tool.application.discovery import ToolDiscoveryProviderDescriptor
from crxzipple.modules.tool.application.settings_integration import (
    ToolEnablementDiscoveryGateway,
    ToolEnablementRuntimeGateway,
    ToolEnablementService,
)
from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.modules.tool.application.settings_integration import (
    tool_settings_bootstrap_config_from_settings,
)
from crxzipple.modules.tool.domain import Tool, ToolSourceKind
from crxzipple.modules.tool.domain.value_objects import ToolKind
from crxzipple.shared.settings import (
    ToolEnablementConfig,
    ToolProviderConfig,
    ToolRootConfig,
)


class _StaticDiscoveryGateway:
    def __init__(self, specs: tuple[ToolSpec, ...]) -> None:
        self.specs = specs

    def list_providers(self) -> list[ToolDiscoveryProviderDescriptor]:
        return [
            ToolDiscoveryProviderDescriptor(
                name="weather",
                description="Weather provider",
                source_kind=ToolSourceKind.REMOTE_REGISTRY,
            ),
        ]

    def discover(self, *, provider_name: str | None = None) -> list[ToolSpec]:
        return list(self.specs)


class _StaticRuntimeGateway:
    def __init__(self, tools: tuple[Tool, ...]) -> None:
        self.tools = tools

    def list_local_tools(self) -> list[Tool]:
        return list(self.tools)

    async def execute(self, tool, target, arguments, execution_context=None):
        return None


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
                        "ApiKeyAuth": "env:PETSTORE_TOKEN",
                        "BasicAuth": {
                            "username_source": "env:PETSTORE_USER",
                            "password_source": "env:PETSTORE_PASSWORD",
                        },
                    },
                },
            ),
        )
        bindings = bootstrap.openapi_providers[0].credential_bindings

        self.assertEqual(bindings[0].scheme_name, "ApiKeyAuth")
        self.assertEqual(bindings[0].source, "env:PETSTORE_TOKEN")
        self.assertEqual(bindings[1].scheme_name, "BasicAuth")
        self.assertEqual(bindings[1].username_source, "env:PETSTORE_USER")
        self.assertEqual(bindings[1].password_source, "env:PETSTORE_PASSWORD")

    def test_enablement_discovery_adapter_applies_pattern_and_explicit_override(self) -> None:
        gateway = ToolEnablementDiscoveryGateway(
            _StaticDiscoveryGateway(
                (
                    _tool_spec("weather.forecast", provider_name="weather"),
                    _tool_spec("weather.current", provider_name="weather"),
                ),
            ),
            ToolEnablementService(
                (
                    ToolEnablementConfig(pattern="weather.*", enabled=False),
                    ToolEnablementConfig(tool_id="weather.current", enabled=True),
                ),
            ),
        )

        discovered = {spec.id: spec for spec in gateway.discover(provider_name="weather")}

        self.assertFalse(discovered["weather.forecast"].enabled)
        self.assertTrue(discovered["weather.current"].enabled)

    def test_enablement_runtime_adapter_applies_local_scope(self) -> None:
        gateway = ToolEnablementRuntimeGateway(
            _StaticRuntimeGateway((_tool("workspace.read"), _tool("shell.exec"),)),
            ToolEnablementService(
                (
                    ToolEnablementConfig(scope="local", enabled=False),
                    ToolEnablementConfig(tool_id="workspace.read", enabled=True),
                ),
            ),
        )

        tools = {tool.id: tool for tool in gateway.list_local_tools()}

        self.assertTrue(tools["workspace.read"].enabled)
        self.assertFalse(tools["shell.exec"].enabled)


def _tool_spec(tool_id: str, *, provider_name: str) -> ToolSpec:
    return ToolSpec(
        id=tool_id,
        name=tool_id,
        description=f"{tool_id} tool",
        provider_name=provider_name,
        kind=ToolKind.HTTP,
        source_kind=ToolSourceKind.REMOTE_REGISTRY,
    )


def _tool(tool_id: str) -> Tool:
    return Tool(
        id=tool_id,
        name=tool_id,
        description=f"{tool_id} tool",
        kind=ToolKind.FUNCTION,
        source_kind=ToolSourceKind.LOCAL_DISCOVERY,
    )


if __name__ == "__main__":
    unittest.main()
