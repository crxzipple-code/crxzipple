from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from crxzipple.modules.mobile.application import MobileExecutionCoordinatorService
from crxzipple.modules.mobile.application.ports import MobileEngineBinding
from crxzipple.modules.mobile.domain import (
    MobileActionCommand,
    MobileActionResult,
    MobileDeviceCapabilities,
    MobileDeviceRuntimeState,
    MobileExecutionError,
    MobileExecutionPlan,
    MobileSystemConfig,
    ResolvedMobileDevice,
)
from crxzipple.modules.mobile.infrastructure import FileBackedMobileDeviceLeaseStore


class _SystemConfigStore:
    def load(self) -> MobileSystemConfig:
        return MobileSystemConfig(default_device="pixel")


class _DeviceResolver:
    def resolve(
        self,
        *,
        system: MobileSystemConfig,
        device_name: str | None,
    ) -> ResolvedMobileDevice:
        return ResolvedMobileDevice(
            name=device_name or system.default_device or "pixel",
            platform="android",
            udid="serial-1",
        )


class _CapabilitiesResolver:
    def resolve(self, *, device: ResolvedMobileDevice) -> MobileDeviceCapabilities:
        return MobileDeviceCapabilities(
            mode="adb-android",
            control_family="adb-control",
            action_family="adb-backed",
        )


class _RuntimeStateStore:
    def __init__(self) -> None:
        self.saved: dict[str, MobileDeviceRuntimeState] = {}

    def get(self, *, device_name: str) -> MobileDeviceRuntimeState | None:
        return self.saved.get(device_name)

    def save(self, state: MobileDeviceRuntimeState) -> None:
        self.saved[state.device_name] = state

    def delete(self, *, device_name: str) -> None:
        self.saved.pop(device_name, None)


class _Planner:
    def plan(
        self,
        *,
        system: MobileSystemConfig,
        device: ResolvedMobileDevice | None,
        capabilities: MobileDeviceCapabilities | None,
        command: MobileActionCommand,
    ) -> MobileExecutionPlan:
        return MobileExecutionPlan(
            system=system,
            device=device,
            capabilities=capabilities,
            command=command,
        )


@dataclass(slots=True)
class _ActionEngine:
    lease_store: FileBackedMobileDeviceLeaseStore
    saw_active_lease: bool = False

    family = "adb-backed"

    def execute(
        self,
        *,
        plan: MobileExecutionPlan,
        runtime_state: MobileDeviceRuntimeState,
    ) -> tuple[MobileActionResult, MobileDeviceRuntimeState]:
        self.saw_active_lease = bool(
            self.lease_store.list_active(device_name=runtime_state.device_name),
        )
        return (
            MobileActionResult(
                ok=True,
                device_name=runtime_state.device_name,
                message="ok",
                command=plan.command,
            ),
            runtime_state,
        )


class _ControlEngine:
    family = "adb-control"

    def execute(
        self,
        *,
        plan: MobileExecutionPlan,
        runtime_state: MobileDeviceRuntimeState | None,
    ) -> tuple[MobileActionResult, MobileDeviceRuntimeState | None]:
        return (
            MobileActionResult(
                ok=True,
                device_name=plan.device.name if plan.device else None,
                message="ok",
                command=plan.command,
            ),
            runtime_state,
        )


@dataclass(slots=True)
class _Registry:
    action_engine: _ActionEngine

    def resolve(
        self,
        *,
        control_family: str,
        action_family: str,
    ) -> MobileEngineBinding:
        return MobileEngineBinding(
            control_engine=_ControlEngine(),
            action_engine=self.action_engine,
        )


class MobileDeviceLeaseTestCase(unittest.TestCase):
    def test_file_backed_device_lease_store_blocks_different_owner_until_release(self) -> None:
        with TemporaryDirectory() as tmpdir:
            store = FileBackedMobileDeviceLeaseStore(Path(tmpdir))

            lease = store.acquire(
                device_name="pixel",
                owner_kind="test",
                owner_id="owner-a",
                ttl_seconds=30,
            )
            same_owner = store.acquire(
                device_name="pixel",
                owner_kind="test",
                owner_id="owner-a",
                ttl_seconds=30,
            )

            self.assertEqual(same_owner.id, lease.id)
            with self.assertRaises(MobileExecutionError):
                store.acquire(
                    device_name="pixel",
                    owner_kind="test",
                    owner_id="owner-b",
                    ttl_seconds=30,
                )

            store.release(lease_id=lease.id)
            next_owner = store.acquire(
                device_name="pixel",
                owner_kind="test",
                owner_id="owner-b",
                ttl_seconds=30,
            )
            self.assertNotEqual(next_owner.id, lease.id)

    def test_execution_coordinator_holds_and_releases_device_lease(self) -> None:
        with TemporaryDirectory() as tmpdir:
            lease_store = FileBackedMobileDeviceLeaseStore(Path(tmpdir))
            action_engine = _ActionEngine(lease_store=lease_store)
            coordinator = MobileExecutionCoordinatorService(
                system_config_store=_SystemConfigStore(),
                device_resolver=_DeviceResolver(),
                capabilities_resolver=_CapabilitiesResolver(),
                runtime_state_store=_RuntimeStateStore(),
                execution_planner=_Planner(),
                engine_registry=_Registry(action_engine=action_engine),
                device_lease_store=lease_store,
            )

            result = coordinator.execute(MobileActionCommand(device_name="pixel", kind="snapshot"))

            self.assertTrue(result.ok)
            self.assertTrue(action_engine.saw_active_lease)
            self.assertEqual(lease_store.list_active(device_name="pixel"), ())

    def test_execution_coordinator_rejects_busy_device_before_engine_execution(self) -> None:
        with TemporaryDirectory() as tmpdir:
            lease_store = FileBackedMobileDeviceLeaseStore(Path(tmpdir))
            lease_store.acquire(
                device_name="pixel",
                owner_kind="other",
                owner_id="worker",
                ttl_seconds=30,
            )
            action_engine = _ActionEngine(lease_store=lease_store)
            coordinator = MobileExecutionCoordinatorService(
                system_config_store=_SystemConfigStore(),
                device_resolver=_DeviceResolver(),
                capabilities_resolver=_CapabilitiesResolver(),
                runtime_state_store=_RuntimeStateStore(),
                execution_planner=_Planner(),
                engine_registry=_Registry(action_engine=action_engine),
                device_lease_store=lease_store,
            )

            with self.assertRaises(MobileExecutionError):
                coordinator.execute(MobileActionCommand(device_name="pixel", kind="snapshot"))

            self.assertFalse(action_engine.saw_active_lease)


if __name__ == "__main__":
    unittest.main()
