from __future__ import annotations

import threading

from crxzipple.modules.tool.application.discovery import ToolDiscoveryProviderDescriptor
from crxzipple.modules.tool.application.service_support import (
    RegisterToolInput,
    SetToolAvailabilityInput,
    SYSTEM_MANAGED_TOOL_TAG,
    ToolServiceBase,
    ToolServiceDependencies,
    build_tool_from_registration,
    build_tool_from_spec,
)
from crxzipple.modules.tool.application.specifications import ToolSpec
from crxzipple.modules.tool.domain.entities import Tool
from crxzipple.modules.tool.domain.exceptions import (
    ToolAlreadyExistsError,
    ToolDiscoveryProviderNotFoundError,
    ToolNotFoundError,
    ToolValidationError,
)
from crxzipple.modules.tool.domain.value_objects import ToolSourceKind
from crxzipple.shared.domain.events import Event


class ToolCatalogService(ToolServiceBase):
    def __init__(self, deps: ToolServiceDependencies) -> None:
        super().__init__(deps)
        self._manual_tools: dict[str, Tool] = {}
        self._catalog_lock = threading.RLock()
        self._local_extension_discovery_refreshed = False

    def register(self, data: RegisterToolInput) -> Tool:
        tool = build_tool_from_registration(data)
        tool.record_event(
            Event(
                name="tool.registered",
                payload={
                    "tool_id": tool.id,
                    "tool_name": tool.name,
                    "tool_kind": tool.kind.value,
                },
            ),
        )
        with self._catalog_lock:
            if data.id in self._manual_tools:
                raise ToolAlreadyExistsError(f"Tool '{data.id}' already exists.")
            self._manual_tools[tool.id] = tool
        with self.uow_factory() as uow:
            uow.collect(tool)
            uow.commit()
        return tool

    def list_discovery_providers(self) -> list[ToolDiscoveryProviderDescriptor]:
        if self.discovery_gateway is None:
            return []
        return self.discovery_gateway.list_providers()

    def discover_tools(self, *, provider_name: str | None = None) -> list[Tool]:
        specs = self._discover_specs(provider_name=provider_name)
        runtime_tools = self.runtime_local_tool_map(
            ensure_local_extension_discovery=False,
        )
        discovered: dict[str, Tool] = {}
        for spec in specs:
            discovered.setdefault(
                spec.id,
                runtime_tools.get(spec.id) or build_tool_from_spec(spec),
            )
        return [discovered[tool_id] for tool_id in sorted(discovered)]

    def discover_local_tools(self) -> list[Tool]:
        if self.discovery_gateway is None:
            return []
        discovered: dict[str, Tool] = {}
        for provider in self.discovery_gateway.list_providers():
            if provider.source_kind is not ToolSourceKind.LOCAL_DISCOVERY:
                continue
            for tool in self.discover_tools(provider_name=provider.name):
                discovered.setdefault(tool.id, tool)
        return [discovered[tool_id] for tool_id in sorted(discovered)]

    def set_availability(self, data: SetToolAvailabilityInput) -> Tool:
        if self.runtime_system_tool(data.id) is not None:
            raise ToolValidationError(
                f"Tool '{data.id}' is file-backed and cannot be enabled or disabled through the service.",
            )
        with self._catalog_lock:
            tool = self._manual_tools.get(data.id)
        if tool is None:
            raise ToolValidationError(
                f"Tool '{data.id}' is not a process-local manual tool. File-backed tools should be changed at the source manifest/provider.",
            )
        with self.uow_factory() as uow:
            changed = tool.enable() if data.enabled else tool.disable()
            if changed:
                uow.collect(tool)
                uow.commit()
            return tool

    def list_tools(self) -> list[Tool]:
        self.refresh_local_extension_discovery(force=True)
        resolved = self.resolved_tool_map(ensure_local_extension_discovery=False)
        return [resolved[tool_id] for tool_id in sorted(resolved)]

    def list_enabled_tools(self) -> list[Tool]:
        resolved = self.resolved_tool_map()
        return [
            resolved[tool_id]
            for tool_id in sorted(resolved)
            if resolved[tool_id].enabled
        ]

    def ensure_local_system_tools_registered(self) -> tuple[Tool, ...]:
        return tuple(self.runtime_system_tool_map().values())

    def get_tool(self, tool_id: str) -> Tool:
        tool = self.resolve_tool(tool_id)
        if tool is None:
            raise ToolNotFoundError(f"Tool '{tool_id}' was not found.")
        return tool

    def runtime_system_tool_map(self) -> dict[str, Tool]:
        return {
            tool.id: tool
            for tool in self.runtime_gateway.list_local_tools()
            if SYSTEM_MANAGED_TOOL_TAG in tool.tags
        }

    def runtime_local_tool_map(
        self,
        *,
        ensure_local_extension_discovery: bool = True,
    ) -> dict[str, Tool]:
        if ensure_local_extension_discovery:
            self.refresh_local_extension_discovery()
        return {tool.id: tool for tool in self.runtime_gateway.list_local_tools()}

    def runtime_system_tool(self, tool_id: str) -> Tool | None:
        return self.runtime_system_tool_map().get(tool_id)

    def resolved_tool_map(
        self,
        *,
        ensure_local_extension_discovery: bool = True,
    ) -> dict[str, Tool]:
        runtime_tools = self.runtime_local_tool_map(
            ensure_local_extension_discovery=ensure_local_extension_discovery,
        )
        resolved: dict[str, Tool] = dict(runtime_tools)
        for spec in self.discover_resolution_specs():
            resolved.setdefault(
                spec.id,
                runtime_tools.get(spec.id) or build_tool_from_spec(spec),
            )
        with self._catalog_lock:
            manual_tools = dict(self._manual_tools)
        for tool_id, tool in manual_tools.items():
            resolved[tool_id] = tool
        return resolved

    def resolve_tool(self, tool_id: str) -> Tool | None:
        with self._catalog_lock:
            manual_tool = self._manual_tools.get(tool_id)
        if manual_tool is not None:
            return manual_tool
        runtime_tool = self.runtime_local_tool_map().get(tool_id)
        if runtime_tool is not None:
            return runtime_tool
        for spec in self.discover_resolution_specs():
            if spec.id == tool_id:
                return build_tool_from_spec(spec)
        return None

    def discover_resolution_specs(self) -> list[ToolSpec]:
        if self.discovery_gateway is None:
            return []
        specs: list[ToolSpec] = []
        for provider in self.discovery_gateway.list_providers():
            if provider.source_kind is ToolSourceKind.LOCAL_DISCOVERY:
                continue
            specs.extend(self.discovery_gateway.discover(provider_name=provider.name))
        return specs

    def refresh_local_extension_discovery(self, *, force: bool = False) -> None:
        if self.discovery_gateway is None:
            return
        with self._catalog_lock:
            if self._local_extension_discovery_refreshed and not force:
                return
            provider_names = {
                provider.name for provider in self.discovery_gateway.list_providers()
            }
            if "local_filesystem" in provider_names:
                self.discovery_gateway.discover(provider_name="local_filesystem")
            self._local_extension_discovery_refreshed = True

    def _discover_specs(
        self,
        *,
        provider_name: str | None,
    ) -> list[ToolSpec]:
        if self.discovery_gateway is None:
            if provider_name is not None:
                raise ToolDiscoveryProviderNotFoundError(
                    f"Tool discovery provider '{provider_name}' is not configured.",
                )
            return []
        provider_names = {
            provider.name for provider in self.discovery_gateway.list_providers()
        }
        if provider_name is not None and provider_name not in provider_names:
            raise ToolDiscoveryProviderNotFoundError(
                f"Tool discovery provider '{provider_name}' was not found.",
            )
        specs = self.discovery_gateway.discover(provider_name=provider_name)
        if provider_name is None or provider_name == "local_filesystem":
            with self._catalog_lock:
                self._local_extension_discovery_refreshed = True
        return specs
