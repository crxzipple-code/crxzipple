from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Protocol

from crxzipple.modules.browser.domain.entities import BrowserProfileRuntimeState
from crxzipple.modules.browser.domain.value_objects import (
    BrowserActionFamily,
    BrowserActionResult,
    BrowserActionTarget,
    BrowserCommand,
    BrowserControlCommand,
    BrowserControlFamily,
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileCapabilities,
    BrowserStoredRef,
    BrowserSystemConfig,
    BrowserTab,
    ResolvedBrowserProfile,
)


class BrowserSystemConfigStore(Protocol):
    def load(self) -> BrowserSystemConfig:
        ...

    def save(self, config: BrowserSystemConfig) -> BrowserSystemConfig:
        ...


class BrowserProfileResolver(Protocol):
    def resolve(
        self,
        *,
        system: BrowserSystemConfig,
        profile_name: str,
    ) -> ResolvedBrowserProfile:
        ...


class BrowserCapabilitiesResolver(Protocol):
    def resolve(
        self,
        *,
        profile: ResolvedBrowserProfile,
    ) -> BrowserProfileCapabilities:
        ...


class BrowserRuntimeStateStore(Protocol):
    def get(
        self,
        *,
        profile_name: str,
    ) -> BrowserProfileRuntimeState | None:
        ...

    def save(self, state: BrowserProfileRuntimeState) -> None:
        ...

    def delete(
        self,
        *,
        profile_name: str,
    ) -> None:
        ...


class BrowserRefStore(Protocol):
    def get_tab_refs(
        self,
        *,
        profile_name: str,
        target_id: str,
    ) -> tuple[BrowserStoredRef, ...]:
        ...

    def save_tab_refs(
        self,
        *,
        profile_name: str,
        target_id: str,
        refs: tuple[BrowserStoredRef, ...],
    ) -> None:
        ...

    def delete_tab_refs(
        self,
        *,
        profile_name: str,
        target_id: str,
    ) -> None:
        ...

    def delete_profile_refs(
        self,
        *,
        profile_name: str,
    ) -> None:
        ...


class BrowserControlCommandAssembler(Protocol):
    def assemble(
        self,
        *,
        profile_name: str,
        kind: str,
        target_id: str | None = None,
        payload: Mapping[str, Any] | None = None,
        timeout_ms: int | None = None,
    ) -> BrowserControlCommand:
        ...


class BrowserPageActionAssembler(Protocol):
    def assemble(
        self,
        *,
        profile_name: str,
        kind: str,
        target_id: str | None = None,
        ref: str | None = None,
        selector: str | None = None,
        payload: Mapping[str, Any] | None = None,
        timeout_ms: int | None = None,
    ) -> BrowserPageActionCommand:
        ...


class BrowserExecutionPlanner(Protocol):
    def plan(
        self,
        *,
        system: BrowserSystemConfig,
        profile: ResolvedBrowserProfile,
        capabilities: BrowserProfileCapabilities,
        command: BrowserCommand,
    ) -> BrowserExecutionPlan:
        ...


class BrowserControlEngine(Protocol):
    family: BrowserControlFamily

    def ensure_attached(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> BrowserProfileRuntimeState:
        ...

    def list_tabs(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> tuple[BrowserTab, ...]:
        ...

    def open_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        url: str,
    ) -> BrowserTab:
        ...

    def navigate_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        target_id: str,
        url: str,
    ) -> BrowserTab:
        ...

    def focus_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        target_id: str,
    ) -> BrowserTab:
        ...

    def close_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        target_id: str,
    ) -> None:
        ...

    def stop_profile(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> None:
        ...

    def reset_profile(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> None:
        ...


class BrowserProfileTabOps(Protocol):
    def list_tabs(self) -> tuple[BrowserTab, ...]:
        ...

    def open_tab(self, url: str) -> BrowserTab:
        ...

    def navigate_tab(self, target_id: str, url: str) -> BrowserTab:
        ...

    def focus_tab(self, target_id: str) -> BrowserTab:
        ...

    def close_tab(self, target_id: str) -> None:
        ...


class BrowserProfileTabOpsFactory(Protocol):
    def create(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        control_engine: BrowserControlEngine,
    ) -> BrowserProfileTabOps:
        ...


class BrowserProfileSelectionOps(Protocol):
    def ensure_tab_available(
        self,
        *,
        requested_target: BrowserActionTarget,
    ) -> BrowserTab:
        ...


class BrowserProfileSelectionOpsFactory(Protocol):
    def create(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        tab_ops: BrowserProfileTabOps,
    ) -> BrowserProfileSelectionOps:
        ...


class BrowserActionEngine(Protocol):
    family: BrowserActionFamily

    def supports(
        self,
        *,
        command: BrowserPageActionCommand,
    ) -> bool:
        ...

    def execute(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab | None,
        command: BrowserPageActionCommand,
    ) -> BrowserActionResult:
        ...

    def clear_profile(
        self,
        *,
        profile_name: str,
    ) -> None:
        ...


@dataclass(frozen=True, slots=True)
class BrowserEngineBinding:
    control_engine: BrowserControlEngine
    action_engine: BrowserActionEngine


class BrowserEngineRegistry(Protocol):
    def control_engine(self, *, family: BrowserControlFamily) -> BrowserControlEngine:
        ...

    def action_engine(self, *, family: BrowserActionFamily) -> BrowserActionEngine:
        ...

    def resolve(
        self,
        *,
        plan: BrowserExecutionPlan,
        command: BrowserCommand,
    ) -> BrowserEngineBinding:
        ...


class BrowserExecutionCoordinator(Protocol):
    def execute(self, command: BrowserCommand) -> BrowserActionResult:
        ...
