from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping
from uuid import uuid4

from crxzipple.modules.mobile.domain import (
    MobileActionCommand,
    MobileActionResult,
    MobileActionTarget,
    MobileControlCommand,
    MobileDeviceCapabilities,
    MobileDeviceConfig,
    MobileDeviceRuntimeState,
    MobileExecutionPlan,
    MobileExecutionError,
    MobileSystemConfig,
    MobileValidationError,
    ResolvedMobileDevice,
)
from .ports import (
    MobileCapabilitiesResolver,
    MobileControlCommandAssembler,
    MobileActionCommandAssembler,
    MobileDeviceLeaseStore,
    MobileEngineRegistry,
    MobileExecutionCoordinator,
    MobileExecutionPlanner,
    MobileRuntimeStateStore,
    MobileSystemConfigStore,
    MobileDeviceResolver,
)

_ALLOWED_CONTROL_KINDS = frozenset(
    {
        "list-devices",
        "launch-app",
        "activate-app",
        "terminate-app",
    }
)
_ALLOWED_ACTION_KINDS = frozenset(
    {
        "snapshot",
        "screenshot",
        "tap",
        "swipe",
        "type",
        "press",
        "wait",
    }
)


def _normalize_control_kind(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in _ALLOWED_CONTROL_KINDS:
        raise MobileValidationError(f"Unsupported mobile control kind '{value}'.")
    return normalized


def _normalize_action_kind(value: str) -> str:
    normalized = value.strip().lower()
    if normalized not in _ALLOWED_ACTION_KINDS:
        raise MobileValidationError(f"Unsupported mobile action kind '{value}'.")
    return normalized


@dataclass(frozen=True, slots=True)
class DefaultMobileDeviceResolver(MobileDeviceResolver):
    system_config_store: MobileSystemConfigStore
    device_probe: Callable[..., Mapping[str, Any]] | None = None

    def _probe_connected_devices(
        self,
        *,
        system: MobileSystemConfig,
    ) -> tuple[dict[str, Any], ...]:
        if self.device_probe is None:
            return ()
        payload = self.device_probe(adb_binary=system.adb_binary)
        if not isinstance(payload, Mapping):
            return ()
        if not bool(payload.get("adb_available")) or not bool(payload.get("probe_ok")):
            return ()
        devices = payload.get("devices")
        if not isinstance(devices, list):
            return ()
        connected: list[dict[str, Any]] = []
        for item in devices:
            if not isinstance(item, dict):
                continue
            serial = str(item.get("serial") or "").strip()
            state = str(item.get("state") or "").strip().lower()
            if not serial or state != "device":
                continue
            connected.append(dict(item))
        return tuple(connected)

    def _persist_discovered_devices(
        self,
        *,
        system: MobileSystemConfig,
        connected_devices: tuple[dict[str, Any], ...],
    ) -> MobileSystemConfig:
        if not connected_devices:
            return system
        existing_devices = list(system.devices)
        existing_names = {device.name for device in existing_devices}
        existing_udids = {device.udid for device in existing_devices if device.udid}
        changed = False
        for item in connected_devices:
            serial = str(item.get("serial") or "").strip()
            if not serial or serial in existing_names or serial in existing_udids:
                continue
            existing_devices.append(
                MobileDeviceConfig(
                    name=serial,
                    udid=serial,
                    app_package=None,
                    app_activity=None,
                )
            )
            changed = True
        if not changed:
            return system
        updated = MobileSystemConfig(
            default_device=system.default_device,
            devices=tuple(existing_devices),
            adb_binary=system.adb_binary,
        )
        return self.system_config_store.save(updated)

    def resolve(
        self,
        *,
        system: MobileSystemConfig,
        device_name: str | None,
    ) -> ResolvedMobileDevice:
        connected_devices = self._probe_connected_devices(system=system)
        system = self._persist_discovered_devices(
            system=system,
            connected_devices=connected_devices,
        )
        connected_by_serial = {
            str(item.get("serial") or "").strip(): item
            for item in connected_devices
            if str(item.get("serial") or "").strip()
        }
        normalized_name = (device_name or system.default_device or "").strip()
        if not normalized_name:
            if len(connected_by_serial) == 1:
                normalized_name = next(iter(connected_by_serial))
            else:
                raise MobileValidationError(
                    "Device name is required when no default mobile device is configured.",
                )
        devices = {device.name: device for device in system.devices}
        device = devices.get(normalized_name)
        if device is None and normalized_name in connected_by_serial:
            device = MobileDeviceConfig(
                name=normalized_name,
                udid=normalized_name,
                app_package=None,
                app_activity=None,
            )
        if device is None:
            raise MobileValidationError(
                f"Mobile device '{normalized_name}' is neither configured nor currently connected.",
            )
        if device.udid and connected_by_serial and device.udid not in connected_by_serial:
            raise MobileValidationError(
                f"Mobile device '{normalized_name}' is not currently connected.",
            )
        return ResolvedMobileDevice(
            name=device.name,
            platform=device.platform,
            udid=device.udid,
            app_package=device.app_package,
            app_activity=device.app_activity,
        )


@dataclass(frozen=True, slots=True)
class DefaultMobileCapabilitiesResolver(MobileCapabilitiesResolver):
    def resolve(self, *, device: ResolvedMobileDevice) -> MobileDeviceCapabilities:
        return MobileDeviceCapabilities(
            mode="adb-android",
            control_family="adb-control",
            action_family="adb-backed",
            supports_screenshot=True,
            supports_app_management=True,
        )


@dataclass(frozen=True, slots=True)
class DefaultMobileControlCommandAssembler(MobileControlCommandAssembler):
    def assemble(
        self,
        *,
        device_name: str | None,
        kind: str,
        payload: Mapping[str, Any] | None = None,
        timeout_ms: int | None = None,
    ) -> MobileControlCommand:
        return MobileControlCommand(
            device_name=device_name,
            kind=_normalize_control_kind(kind),  # type: ignore[arg-type]
            payload=dict(payload or {}),
            timeout_ms=timeout_ms,
        )


@dataclass(frozen=True, slots=True)
class DefaultMobileActionCommandAssembler(MobileActionCommandAssembler):
    def assemble(
        self,
        *,
        device_name: str | None,
        kind: str,
        ref: str | None = None,
        selector: str | None = None,
        payload: Mapping[str, Any] | None = None,
        timeout_ms: int | None = None,
    ) -> MobileActionCommand:
        return MobileActionCommand(
            device_name=device_name,
            kind=_normalize_action_kind(kind),  # type: ignore[arg-type]
            target=MobileActionTarget(
                ref=ref,
                selector=selector,
            ),
            payload=dict(payload or {}),
            timeout_ms=timeout_ms,
        )


@dataclass(frozen=True, slots=True)
class DefaultMobileExecutionPlanner(MobileExecutionPlanner):
    def plan(
        self,
        *,
        system: MobileSystemConfig,
        device: ResolvedMobileDevice | None,
        capabilities: MobileDeviceCapabilities | None,
        command: MobileControlCommand | MobileActionCommand,
    ) -> MobileExecutionPlan:
        return MobileExecutionPlan(
            system=system,
            device=device,
            capabilities=capabilities,
            command=command,
        )


@dataclass(slots=True)
class MobileExecutionCoordinatorService(MobileExecutionCoordinator):
    system_config_store: MobileSystemConfigStore
    device_resolver: MobileDeviceResolver
    capabilities_resolver: MobileCapabilitiesResolver
    runtime_state_store: MobileRuntimeStateStore
    execution_planner: MobileExecutionPlanner
    engine_registry: MobileEngineRegistry
    device_lease_store: MobileDeviceLeaseStore | None = None
    lease_ttl_seconds: int = 300

    def execute(
        self,
        command: MobileControlCommand | MobileActionCommand,
    ) -> MobileActionResult:
        system = self.system_config_store.load()
        if isinstance(command, MobileControlCommand) and command.kind == "list-devices":
            plan = self.execution_planner.plan(
                system=system,
                device=None,
                capabilities=None,
                command=command,
            )
            binding = self.engine_registry.resolve(
                control_family="adb-control",
                action_family="adb-backed",
            )
            result, _ = binding.control_engine.execute(plan=plan, runtime_state=None)
            return result

        device = self.device_resolver.resolve(
            system=system,
            device_name=command.device_name,
        )
        lease_id: str | None = None
        try:
            if self.device_lease_store is not None:
                lease = self.device_lease_store.acquire(
                    device_name=device.name,
                    owner_kind="mobile-execution",
                    owner_id=uuid4().hex,
                    ttl_seconds=max(int(self.lease_ttl_seconds), 1),
                )
                lease_id = lease.id
            capabilities = self.capabilities_resolver.resolve(device=device)
            runtime_state = self.runtime_state_store.get(device_name=device.name)
            plan = self.execution_planner.plan(
                system=system,
                device=device,
                capabilities=capabilities,
                command=command,
            )
            binding = self.engine_registry.resolve(
                control_family=capabilities.control_family,
                action_family=capabilities.action_family,
            )
            active_runtime_state = runtime_state
            try:
                if isinstance(command, MobileControlCommand):
                    result, updated_state = binding.control_engine.execute(
                        plan=plan,
                        runtime_state=runtime_state,
                    )
                else:
                    active_runtime_state = runtime_state or MobileDeviceRuntimeState(
                        device_name=device.name,
                    )
                    result, updated_state = binding.action_engine.execute(
                        plan=plan,
                        runtime_state=active_runtime_state,
                    )
            except MobileExecutionError:
                if active_runtime_state is not None:
                    self.runtime_state_store.save(active_runtime_state)
                raise
            if updated_state is None:
                self.runtime_state_store.delete(device_name=device.name)
            else:
                self.runtime_state_store.save(updated_state)
            return result
        finally:
            if lease_id is not None and self.device_lease_store is not None:
                self.device_lease_store.release(lease_id=lease_id, reason="execution-finished")
