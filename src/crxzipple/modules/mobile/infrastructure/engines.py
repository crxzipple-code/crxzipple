from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.artifacts.application.services import ArtifactApplicationService
from crxzipple.modules.mobile.application.ports import MobileActionEngine, MobileRefStore
from crxzipple.modules.mobile.domain import (
    MobileActionCommand,
    MobileActionResult,
    MobileDeviceRuntimeState,
    MobileExecutionError,
    MobileExecutionPlan,
    MobileValidationError,
)
from crxzipple.modules.ocr.application.services import OcrApplicationService

from .adb_engine_helpers import make_client as _make_client
from .mobile_snapshot_actions import (
    execute_screenshot as _execute_screenshot,
    execute_snapshot as _execute_snapshot,
)
from .mobile_control_engine import AdbControlEngine
from .mobile_interaction_actions import (
    execute_press as _execute_press,
    execute_swipe as _execute_swipe,
    execute_tap as _execute_tap,
    execute_type as _execute_type,
    execute_wait as _execute_wait,
)


@dataclass(frozen=True, slots=True)
class AdbBackedMobileActionEngine(MobileActionEngine):
    ref_store: MobileRefStore
    artifact_service: ArtifactApplicationService | None = None
    ocr_service: OcrApplicationService | None = None
    family: str = "adb-backed"

    def execute(
        self,
        *,
        plan: MobileExecutionPlan,
        runtime_state: MobileDeviceRuntimeState,
    ) -> tuple[MobileActionResult, MobileDeviceRuntimeState]:
        command = plan.command
        if not isinstance(command, MobileActionCommand):
            raise MobileExecutionError("Invalid mobile action command.")
        if plan.device is None:
            raise MobileExecutionError("Resolved mobile device is required for mobile actions.")
        client = _make_client(plan, timeout_ms=command.timeout_ms)
        try:
            if command.kind == "snapshot":
                return _execute_snapshot(
                    plan=plan,
                    command=command,
                    runtime_state=runtime_state,
                    client=client,
                    ref_store=self.ref_store,
                    artifact_service=self.artifact_service,
                    ocr_service=self.ocr_service,
                )
            if command.kind == "screenshot":
                return _execute_screenshot(
                    plan=plan,
                    command=command,
                    runtime_state=runtime_state,
                    client=client,
                    artifact_service=self.artifact_service,
                )
            if command.kind == "tap":
                return _execute_tap(
                    self.ref_store,
                    plan=plan,
                    command=command,
                    runtime_state=runtime_state,
                    client=client,
                )
            if command.kind == "swipe":
                return _execute_swipe(
                    self.ref_store,
                    plan=plan,
                    command=command,
                    runtime_state=runtime_state,
                    client=client,
                )
            if command.kind == "type":
                return _execute_type(
                    self.ref_store,
                    plan=plan,
                    command=command,
                    runtime_state=runtime_state,
                    client=client,
                )
            if command.kind == "press":
                return _execute_press(
                    plan=plan,
                    command=command,
                    runtime_state=runtime_state,
                    client=client,
                )
            if command.kind == "wait":
                return _execute_wait(
                    plan=plan,
                    command=command,
                    runtime_state=runtime_state,
                    client=client,
                )
        except MobileExecutionError as exc:
            runtime_state.mark_command_failed(str(exc))
            raise
        raise MobileValidationError(f"Unsupported mobile action kind '{command.kind}'.")


__all__ = ["AdbBackedMobileActionEngine", "AdbControlEngine"]
