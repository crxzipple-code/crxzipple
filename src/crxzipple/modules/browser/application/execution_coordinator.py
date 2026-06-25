from __future__ import annotations

from dataclasses import dataclass
from typing import get_args

from crxzipple.modules.browser.domain import (
    BrowserActionResult,
    BrowserActionTarget,
    BrowserCommand,
    BrowserControlCommand,
    BrowserPageActionCommand,
    BrowserPageActionKind,
    BrowserProfileRuntimeState,
    BrowserTab,
    BrowserValidationError,
)

from .ports import (
    BrowserCapabilitiesResolver,
    BrowserEngineRegistry,
    BrowserExecutionCoordinator,
    BrowserExecutionPlanner,
    BrowserProfileResolver,
    BrowserProfileSelectionOpsFactory,
    BrowserProfileTabOpsFactory,
    BrowserRefStore,
    BrowserRuntimeStateStore,
    BrowserSystemConfigStore,
)
from .runtime_payloads import browser_runtime_status_payload as _runtime_status_payload

_TAB_SCOPED_ACTIONS = frozenset(get_args(BrowserPageActionKind))


def _disabled_profile_command_allowed(command: BrowserCommand) -> bool:
    return isinstance(command, BrowserControlCommand) and command.kind in {"status", "stop"}


@dataclass(slots=True)
class BrowserExecutionCoordinatorService(BrowserExecutionCoordinator):
    system_config_store: BrowserSystemConfigStore
    profile_resolver: BrowserProfileResolver
    capabilities_resolver: BrowserCapabilitiesResolver
    runtime_state_store: BrowserRuntimeStateStore
    ref_store: BrowserRefStore
    execution_planner: BrowserExecutionPlanner
    engine_registry: BrowserEngineRegistry
    tab_ops_factory: BrowserProfileTabOpsFactory
    selection_ops_factory: BrowserProfileSelectionOpsFactory

    def execute(self, command: BrowserCommand) -> BrowserActionResult:
        system = self.system_config_store.load()
        profile = self.profile_resolver.resolve(
            system=system,
            profile_name=command.profile_name,
        )
        capabilities = self.capabilities_resolver.resolve(profile=profile)
        plan = self.execution_planner.plan(
            system=system,
            profile=profile,
            capabilities=capabilities,
            command=command,
        )
        if not profile.enabled and not _disabled_profile_command_allowed(command):
            raise BrowserValidationError(f"Browser profile '{profile.name}' is disabled.")

        runtime_state = self.runtime_state_store.get(profile_name=profile.name)
        if runtime_state is None:
            runtime_state = BrowserProfileRuntimeState(profile_name=profile.name)

        engine_binding = self.engine_registry.resolve(
            plan=plan,
            command=command,
        )
        control_engine = engine_binding.control_engine
        action_engine = engine_binding.action_engine
        if isinstance(command, BrowserControlCommand) and command.kind == "reset":
            if not capabilities.supports_reset:
                raise BrowserValidationError(
                    f"Browser profile '{profile.name}' does not support reset.",
                )
            control_engine.reset_profile(
                plan=plan,
                runtime_state=runtime_state,
            )
            action_engine.clear_profile(profile_name=profile.name)
            self.ref_store.delete_profile_refs(profile_name=profile.name)
            self.runtime_state_store.delete(profile_name=profile.name)
            return BrowserActionResult(
                command=command,
                ok=True,
                value={"profile_name": profile.name},
                message="Reset browser profile.",
            )

        if isinstance(command, BrowserControlCommand) and command.kind == "stop":
            control_engine.stop_profile(
                plan=plan,
                runtime_state=runtime_state,
            )
            action_engine.clear_profile(profile_name=profile.name)
            self.ref_store.delete_profile_refs(profile_name=profile.name)
            self.runtime_state_store.save(runtime_state)
            return BrowserActionResult(
                command=command,
                ok=True,
                value={
                    "profile_name": profile.name,
                    "runtime": _runtime_status_payload(runtime_state),
                },
                message="Stopped browser profile.",
            )

        if isinstance(command, BrowserControlCommand) and command.kind == "status":
            tabs: tuple[BrowserTab, ...] = ()
            tabs_error: str | None = None
            if runtime_state.attachment_status == "attached":
                try:
                    tabs = control_engine.list_tabs(
                        plan=plan,
                        runtime_state=runtime_state,
                    )
                except BrowserValidationError as exc:
                    tabs_error = str(exc)
            return BrowserActionResult(
                command=command,
                ok=True,
                target_id=runtime_state.last_target_id,
                value={
                    "profile_name": profile.name,
                    "driver": profile.driver,
                    "mode": capabilities.mode,
                    "enabled": profile.enabled,
                    "control_family": capabilities.control_family,
                    "action_family": capabilities.action_family,
                    "can_launch": capabilities.can_launch,
                    "supports_reset": capabilities.supports_reset,
                    "supports_per_tab_ws": capabilities.supports_per_tab_ws,
                    "supports_json_tab_endpoints": capabilities.supports_json_tab_endpoints,
                    "runtime": _runtime_status_payload(runtime_state),
                    "tabs": tabs,
                    "tab_count": len(tabs),
                    "tabs_error": tabs_error,
                },
                message="Loaded browser profile status.",
            )

        previous_host_generation = runtime_state.host_generation()
        runtime_state.mark_attaching()
        self.runtime_state_store.save(runtime_state)
        try:
            runtime_state = control_engine.ensure_attached(
                plan=plan,
                runtime_state=runtime_state,
            )
        except BrowserValidationError as exc:
            runtime_state.mark_failed(str(exc))
            self.runtime_state_store.save(runtime_state)
            raise
        current_host_generation = runtime_state.host_generation()
        if (
            previous_host_generation is not None
            and current_host_generation is not None
            and previous_host_generation != current_host_generation
        ):
            self.ref_store.delete_profile_refs(profile_name=profile.name)
            runtime_state.forget_all_pages()
            runtime_state.metadata["host_generation_changed"] = True
        self.runtime_state_store.save(runtime_state)

        tab_ops = self.tab_ops_factory.create(
            plan=plan,
            runtime_state=runtime_state,
            control_engine=control_engine,
        )

        if isinstance(command, BrowserControlCommand) and command.kind == "start":
            tabs = tab_ops.list_tabs()
            return BrowserActionResult(
                command=command,
                ok=True,
                target_id=runtime_state.last_target_id,
                value={
                    "profile_name": profile.name,
                    "runtime": _runtime_status_payload(runtime_state),
                    "tabs": tabs,
                    "tab_count": len(tabs),
                },
                message="Started browser profile.",
            )

        if isinstance(command, BrowserControlCommand) and command.kind == "list-tabs":
            tabs = tab_ops.list_tabs()
            return BrowserActionResult(
                command=command,
                ok=True,
                value=tabs,
                message=f"Listed {len(tabs)} tabs.",
            )

        if isinstance(command, BrowserControlCommand) and command.kind == "open-tab":
            if (
                capabilities.supports_managed_tab_limit
                and system.managed_tab_limit is not None
            ):
                current_tabs = tab_ops.list_tabs()
                if len(current_tabs) >= system.managed_tab_limit:
                    raise BrowserValidationError(
                        "Browser managed tab limit was reached.",
                    )
            url = self._require_payload_text(command, key="url")
            tab = tab_ops.open_tab(url)
            runtime_state.remember_target(tab.target_id)
            runtime_state.remember_page_opened(target_id=tab.target_id)
            self.runtime_state_store.save(runtime_state)
            return BrowserActionResult(
                command=command,
                ok=True,
                target_id=tab.target_id,
                value=tab,
                message="Opened browser tab.",
            )

        selection_ops = self.selection_ops_factory.create(
            plan=plan,
            runtime_state=runtime_state,
            tab_ops=tab_ops,
        )
        requested_target = (
            BrowserActionTarget(target_id=command.target_id)
            if isinstance(command, BrowserControlCommand)
            else command.target
        )
        resolved_tab = selection_ops.ensure_tab_available(
            requested_target=requested_target,
        )

        if isinstance(command, BrowserControlCommand) and command.kind == "navigate":
            url = self._require_payload_text(command, key="url")
            tab = tab_ops.navigate_tab(resolved_tab.target_id, url)
            self.ref_store.delete_tab_refs(
                profile_name=profile.name,
                target_id=resolved_tab.target_id,
            )
            runtime_state.reset_page_state(
                target_id=resolved_tab.target_id,
                reason="navigate",
            )
            runtime_state.remember_target(tab.target_id)
            self.runtime_state_store.save(runtime_state)
            return BrowserActionResult(
                command=command,
                ok=True,
                target_id=tab.target_id,
                value=tab,
                message="Navigated browser tab.",
            )

        if isinstance(command, BrowserControlCommand) and command.kind == "focus-tab":
            tab = tab_ops.focus_tab(resolved_tab.target_id)
            runtime_state.remember_target(tab.target_id)
            self.runtime_state_store.save(runtime_state)
            return BrowserActionResult(
                command=command,
                ok=True,
                target_id=tab.target_id,
                message="Focused browser tab.",
            )

        if isinstance(command, BrowserControlCommand) and command.kind == "close-tab":
            tab_ops.close_tab(resolved_tab.target_id)
            self.ref_store.delete_tab_refs(
                profile_name=profile.name,
                target_id=resolved_tab.target_id,
            )
            runtime_state.forget_page(target_id=resolved_tab.target_id)
            if runtime_state.last_target_id == resolved_tab.target_id:
                runtime_state.remember_target(None)
            self.runtime_state_store.save(runtime_state)
            return BrowserActionResult(
                command=command,
                ok=True,
                target_id=resolved_tab.target_id,
                message="Closed browser tab.",
            )

        if not isinstance(command, BrowserPageActionCommand):
            raise BrowserValidationError(
                f"Unsupported browser control kind '{command.kind}'.",
            )

        if command.kind not in _TAB_SCOPED_ACTIONS:
            raise BrowserValidationError(
                f"Unsupported browser execution kind '{command.kind}'.",
            )

        if command.target.ref is not None:
            stored_refs = self.ref_store.get_tab_refs(
                profile_name=profile.name,
                target_id=resolved_tab.target_id,
            )
            if runtime_state.restore_page_ref_session(
                target_id=resolved_tab.target_id,
                refs=stored_refs,
            ):
                self.runtime_state_store.save(runtime_state)

        result = action_engine.execute(
            plan=plan,
            runtime_state=runtime_state,
            tab=resolved_tab,
            command=command,
        )
        runtime_state.remember_target(result.target_id or resolved_tab.target_id)
        self.runtime_state_store.save(runtime_state)
        return result

    @staticmethod
    def _require_payload_text(command: BrowserCommand, *, key: str) -> str:
        value = command.payload.get(key)
        if not isinstance(value, str) or not value.strip():
            raise BrowserValidationError(f"payload.{key} is required.")
        return value.strip()
