from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from crxzipple.modules.mobile.domain.entities import MobileDeviceRuntimeState
from crxzipple.modules.mobile.domain.value_objects import (
    MobileActionCommand,
    MobileActionResult,
    MobileCommand,
    MobileControlCommand,
    MobileDeviceCapabilities,
    MobileExecutionPlan,
    MobileStoredRef,
    MobileSystemConfig,
    ResolvedMobileDevice,
)


class MobileSystemConfigStore(Protocol):
    def load(self) -> MobileSystemConfig:
        ...

    def save(self, config: MobileSystemConfig) -> MobileSystemConfig:
        ...


class MobileDeviceResolver(Protocol):
    def resolve(
        self,
        *,
        system: MobileSystemConfig,
        device_name: str | None,
    ) -> ResolvedMobileDevice:
        ...


class MobileCapabilitiesResolver(Protocol):
    def resolve(self, *, device: ResolvedMobileDevice) -> MobileDeviceCapabilities:
        ...


class MobileRuntimeStateStore(Protocol):
    def get(self, *, device_name: str) -> MobileDeviceRuntimeState | None:
        ...

    def save(self, state: MobileDeviceRuntimeState) -> None:
        ...

    def delete(self, *, device_name: str) -> None:
        ...


class MobileRefStore(Protocol):
    def get_refs(
        self,
        *,
        device_name: str,
        generation: int,
    ) -> tuple[MobileStoredRef, ...]:
        ...

    def save_refs(
        self,
        *,
        device_name: str,
        generation: int,
        refs: tuple[MobileStoredRef, ...],
    ) -> None:
        ...

    def delete_refs(
        self,
        *,
        device_name: str,
        generation: int,
    ) -> None:
        ...


class MobileControlCommandAssembler(Protocol):
    def assemble(
        self,
        *,
        device_name: str | None,
        kind: str,
        payload: Mapping[str, Any] | None = None,
        timeout_ms: int | None = None,
    ) -> MobileControlCommand:
        ...


class MobileActionCommandAssembler(Protocol):
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
        ...


class MobileExecutionPlanner(Protocol):
    def plan(
        self,
        *,
        system: MobileSystemConfig,
        device: ResolvedMobileDevice | None,
        capabilities: MobileDeviceCapabilities | None,
        command: MobileCommand,
    ) -> MobileExecutionPlan:
        ...


class MobileControlEngine(Protocol):
    family: str

    def execute(
        self,
        *,
        plan: MobileExecutionPlan,
        runtime_state: MobileDeviceRuntimeState | None,
    ) -> tuple[MobileActionResult, MobileDeviceRuntimeState | None]:
        ...


class MobileActionEngine(Protocol):
    family: str

    def execute(
        self,
        *,
        plan: MobileExecutionPlan,
        runtime_state: MobileDeviceRuntimeState,
    ) -> tuple[MobileActionResult, MobileDeviceRuntimeState]:
        ...


@dataclass(frozen=True, slots=True)
class MobileEngineBinding:
    control_engine: MobileControlEngine
    action_engine: MobileActionEngine


class MobileEngineRegistry(Protocol):
    def resolve(
        self,
        *,
        control_family: str,
        action_family: str,
    ) -> MobileEngineBinding:
        ...


class MobileExecutionCoordinator(Protocol):
    def execute(self, command: MobileCommand) -> MobileActionResult:
        ...
