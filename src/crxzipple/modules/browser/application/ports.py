from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, Protocol

from crxzipple.modules.browser.domain.entities import (
    BrowserProfileAllocation,
    BrowserProfileRuntimeState,
)
from crxzipple.modules.browser.domain.value_objects import (
    BrowserActionFamily,
    BrowserActionResult,
    BrowserActionTarget,
    BrowserCommand,
    BrowserControlCommand,
    BrowserControlFamily,
    BrowserExecutionPlan,
    BrowserNetworkBody,
    BrowserNetworkBodyKind,
    BrowserNetworkCapture,
    BrowserNetworkRequest,
    BrowserNetworkRequestFilter,
    BrowserProfileConfig,
    BrowserPageActionCommand,
    BrowserProfileCapabilities,
    BrowserProfilePool,
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


class BrowserProfilePoolStore(Protocol):
    def list_pools(self) -> tuple[BrowserProfilePool, ...]:
        ...

    def get_pool(self, *, pool_id: str) -> BrowserProfilePool | None:
        ...

    def save_pool(self, pool: BrowserProfilePool) -> BrowserProfilePool:
        ...

    def delete_pool(self, *, pool_id: str) -> None:
        ...


class BrowserProfileAllocationStore(Protocol):
    def list_allocations(self) -> tuple[BrowserProfileAllocation, ...]:
        ...

    def get_allocation(
        self,
        *,
        allocation_id: str,
    ) -> BrowserProfileAllocation | None:
        ...

    def save_allocation(
        self,
        allocation: BrowserProfileAllocation,
    ) -> BrowserProfileAllocation:
        ...

    def delete_allocation(self, *, allocation_id: str) -> None:
        ...


class BrowserAllocationTargetRecycler(Protocol):
    def close_owned_target(
        self,
        *,
        profile_name: str,
        target_id: str,
    ) -> None:
        ...


class BrowserAllocationTargetInspector(Protocol):
    def list_target_ids(
        self,
        *,
        profile_name: str,
    ) -> tuple[str, ...]:
        ...


class BrowserProfileHostServiceSync(Protocol):
    def sync_profile(
        self,
        *,
        system: BrowserSystemConfig,
        profile: BrowserProfileConfig,
    ) -> None:
        ...

    def remove_profile(self, *, profile_name: str) -> None:
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


class BrowserNetworkRedactor(Protocol):
    def redact_url(self, url: str) -> str:
        ...

    def redact_headers(self, headers: Mapping[str, str]) -> dict[str, str]:
        ...

    def redact_body(
        self,
        *,
        body: str,
        kind: BrowserNetworkBodyKind,
        mime_type: str | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> str:
        ...


class BrowserNetworkCaptureStore(Protocol):
    def start_capture(self, capture: BrowserNetworkCapture) -> BrowserNetworkCapture:
        ...

    def stop_capture(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        stopped_at: datetime,
    ) -> BrowserNetworkCapture | None:
        ...

    def get_capture(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
    ) -> BrowserNetworkCapture | None:
        ...

    def list_captures(
        self,
        *,
        profile_name: str | None = None,
        target_id: str | None = None,
    ) -> tuple[BrowserNetworkCapture, ...]:
        ...

    def save_request(self, request: BrowserNetworkRequest) -> BrowserNetworkRequest:
        ...

    def list_requests(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        filters: BrowserNetworkRequestFilter | None = None,
    ) -> tuple[BrowserNetworkRequest, ...]:
        ...

    def get_request(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        request_id: str,
    ) -> BrowserNetworkRequest | None:
        ...

    def store_body(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        request_id: str,
        kind: BrowserNetworkBodyKind,
        body: str | bytes,
        mime_type: str | None = None,
        headers: Mapping[str, str] | None = None,
        created_at: datetime | None = None,
    ) -> BrowserNetworkBody:
        ...

    def get_body(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
        body_ref: str,
    ) -> BrowserNetworkBody | None:
        ...

    def clear_capture(
        self,
        *,
        profile_name: str,
        target_id: str,
        capture_id: str,
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
