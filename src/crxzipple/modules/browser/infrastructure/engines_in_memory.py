from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.browser.domain import (
    BrowserActionFamily,
    BrowserActionResult,
    BrowserExecutionPlan,
    BrowserPageActionCommand,
    BrowserProfileRuntimeState,
    BrowserTab,
    BrowserValidationError,
)

from ..application.ports import BrowserActionEngine, BrowserControlEngine
from .cdp_urls import json_tab_endpoints
from .engines_tab_state import (
    METADATA_ACTIVE_TARGET_KEY,
    METADATA_NEXT_TAB_ID_KEY,
    METADATA_TABS_KEY,
    find_tab,
    load_tabs,
    next_tab_id,
    set_active_target,
    store_tabs,
)


@dataclass(frozen=True, slots=True)
class InMemoryCdpControlEngine(BrowserControlEngine):
    family: str = "cdp-control"

    def ensure_attached(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> BrowserProfileRuntimeState:
        runtime_state.mark_attached(
            browser_ref=f"cdp:{plan.profile.name}",
            running_pid=runtime_state.running_pid or 1,
        )
        runtime_state.metadata.setdefault(METADATA_TABS_KEY, [])
        runtime_state.metadata.setdefault(METADATA_NEXT_TAB_ID_KEY, 1)
        runtime_state.metadata.setdefault(METADATA_ACTIVE_TARGET_KEY, None)
        return runtime_state

    def list_tabs(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> tuple[BrowserTab, ...]:
        del plan
        return load_tabs(runtime_state)

    def open_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        url: str,
    ) -> BrowserTab:
        target_id = next_tab_id(runtime_state, prefix=plan.profile.name)
        tab = BrowserTab(
            target_id=target_id,
            url=url,
            title=url,
            type="page",
            ws_url=(
                f"ws://127.0.0.1/devtools/page/{target_id}"
                if plan.capabilities.supports_per_tab_ws
                else None
            ),
            json_endpoints=(
                json_tab_endpoints(
                    plan.profile.cdp_url or "http://127.0.0.1",
                    target_id,
                )
                if plan.capabilities.supports_json_tab_endpoints
                else None
            ),
        )
        tabs = load_tabs(runtime_state) + (tab,)
        store_tabs(runtime_state, tabs)
        set_active_target(runtime_state, tab.target_id)
        return tab

    def navigate_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        target_id: str,
        url: str,
    ) -> BrowserTab:
        del plan
        tabs = []
        updated: BrowserTab | None = None
        for tab in load_tabs(runtime_state):
            if tab.target_id == target_id:
                updated = BrowserTab(
                    target_id=tab.target_id,
                    url=url,
                    title=url,
                    type=tab.type,
                    ws_url=tab.ws_url,
                    json_endpoints=tab.json_endpoints,
                )
                tabs.append(updated)
            else:
                tabs.append(tab)
        if updated is None:
            raise BrowserValidationError(f"Browser tab '{target_id}' was not found.")
        store_tabs(runtime_state, tuple(tabs))
        set_active_target(runtime_state, updated.target_id)
        return updated

    def focus_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        target_id: str,
    ) -> BrowserTab:
        del plan
        tab = find_tab(runtime_state, target_id=target_id)
        set_active_target(runtime_state, tab.target_id)
        return tab

    def close_tab(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        target_id: str,
    ) -> None:
        del plan
        current_tabs = load_tabs(runtime_state)
        tabs = tuple(tab for tab in current_tabs if tab.target_id != target_id)
        if len(tabs) == len(current_tabs):
            raise BrowserValidationError(f"Browser tab '{target_id}' was not found.")
        store_tabs(runtime_state, tabs)
        active_target = runtime_state.metadata.get(METADATA_ACTIVE_TARGET_KEY)
        if active_target == target_id:
            set_active_target(runtime_state, tabs[0].target_id if tabs else None)

    def reset_profile(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> None:
        del plan
        runtime_state.metadata.clear()
        runtime_state.remember_target(None)
        runtime_state.mark_closed()

    def stop_profile(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
    ) -> None:
        del plan
        runtime_state.metadata.clear()
        runtime_state.remember_target(None)
        runtime_state.mark_closed()


@dataclass(frozen=True, slots=True)
class InMemoryCdpBackedPlaywrightActionEngine(BrowserActionEngine):
    family: BrowserActionFamily = "cdp-backed-playwright"

    def supports(
        self,
        *,
        command: BrowserPageActionCommand,
    ) -> bool:
        del command
        return True

    def execute(
        self,
        *,
        plan: BrowserExecutionPlan,
        runtime_state: BrowserProfileRuntimeState,
        tab: BrowserTab | None,
        command: BrowserPageActionCommand,
    ) -> BrowserActionResult:
        del runtime_state
        if tab is None:
            raise BrowserValidationError("cdp-backed-playwright actions require a tab.")
        return BrowserActionResult(
            command=command,
            ok=True,
            target_id=tab.target_id,
            value={
                "engine": self.family,
                "control_family": plan.control_family,
                "profile": plan.profile.name,
                "tab": {
                    "target_id": tab.target_id,
                    "url": tab.url,
                    "title": tab.title,
                    "type": tab.type,
                },
                "ref": command.target.ref,
                "selector": command.target.selector,
                "payload": dict(command.payload),
            },
            message=f"Executed {command.kind} via cdp-backed-playwright.",
        )

    def clear_profile(
        self,
        *,
        profile_name: str,
    ) -> None:
        del profile_name


__all__ = [
    "InMemoryCdpBackedPlaywrightActionEngine",
    "InMemoryCdpControlEngine",
]
