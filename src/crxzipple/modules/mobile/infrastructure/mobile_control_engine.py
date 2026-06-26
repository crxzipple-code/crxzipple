from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.mobile.application.ports import MobileControlEngine
from crxzipple.modules.mobile.domain import (
    MobileActionResult,
    MobileControlCommand,
    MobileDeviceRuntimeState,
    MobileExecutionError,
    MobileExecutionPlan,
    MobileValidationError,
)

from .adb_client import AndroidAdbClient
from .adb_engine_helpers import make_client as _make_client


@dataclass(frozen=True, slots=True)
class AdbControlEngine(MobileControlEngine):
    family: str = "adb-control"

    def execute(
        self,
        *,
        plan: MobileExecutionPlan,
        runtime_state: MobileDeviceRuntimeState | None,
    ) -> tuple[MobileActionResult, MobileDeviceRuntimeState | None]:
        command = plan.command
        if not isinstance(command, MobileControlCommand):
            raise MobileExecutionError("Invalid mobile control command.")
        if command.kind == "list-devices":
            probe = AndroidAdbClient.probe_adb_devices(adb_binary=plan.system.adb_binary)
            adb_available = bool(probe.get("adb_available"))
            probe_ok = bool(probe.get("probe_ok"))
            connected = bool(probe.get("connected"))
            connected_count = int(probe.get("connected_device_count") or 0)
            device_count = int(probe.get("device_count") or 0)
            adb_error = str(probe.get("adb_error") or "").strip() or None
            if not adb_available:
                message = "Unable to inspect Android devices because adb is not available."
            elif not probe_ok:
                message = "Unable to inspect Android devices because adb probing failed."
            elif connected:
                message = f"Detected {connected_count} connected Android device(s)."
            elif device_count > 0:
                message = "Android devices were detected, but none are currently online."
            else:
                message = "No Android devices are currently connected."
            return (
                MobileActionResult(
                    ok=True,
                    device_name=None,
                    message=message,
                    command=command,
                    value={
                        "adb_binary": plan.system.adb_binary,
                        "adb_available": adb_available,
                        "probe_ok": probe_ok,
                        "adb_error": adb_error,
                        "connected": connected,
                        "device_count": device_count,
                        "connected_device_count": connected_count,
                        "devices": probe.get("devices", []),
                    },
                ),
                None,
            )

        if plan.device is None:
            raise MobileValidationError(
                "Resolved mobile device is required for this control command.",
            )

        state = runtime_state or MobileDeviceRuntimeState(device_name=plan.device.name)
        client = _make_client(plan, timeout_ms=command.timeout_ms)
        try:
            if command.kind == "launch-app":
                app_package = str(
                    command.payload.get("app_package") or plan.device.app_package or "",
                ).strip()
                app_activity = str(
                    command.payload.get("app_activity")
                    or plan.device.app_activity
                    or "",
                ).strip()
                if not app_package or not app_activity:
                    raise MobileValidationError(
                        "launch-app requires app_package and app_activity.",
                    )
                client.start_activity(
                    app_package=app_package,
                    app_activity=app_activity,
                )
                state.clear_error()
                return (
                    MobileActionResult(
                        ok=True,
                        device_name=plan.device.name,
                        message="Launched Android app activity.",
                        command=command,
                        value={
                            "app_package": app_package,
                            "app_activity": app_activity,
                        },
                    ),
                    state,
                )
            if command.kind == "activate-app":
                app_id = str(
                    command.payload.get("app_id") or plan.device.app_package or "",
                ).strip()
                app_activity = (
                    str(
                        command.payload.get("app_activity")
                        or plan.device.app_activity
                        or "",
                    ).strip()
                    or None
                )
                if not app_id:
                    raise MobileValidationError(
                        "activate-app requires app_id or configured app_package.",
                    )
                client.activate_app(app_id=app_id, app_activity=app_activity)
                state.clear_error()
                return (
                    MobileActionResult(
                        ok=True,
                        device_name=plan.device.name,
                        message="Activated Android app.",
                        command=command,
                        value={"app_id": app_id, "app_activity": app_activity},
                    ),
                    state,
                )
            if command.kind == "terminate-app":
                app_id = str(
                    command.payload.get("app_id") or plan.device.app_package or "",
                ).strip()
                if not app_id:
                    raise MobileValidationError(
                        "terminate-app requires app_id or configured app_package.",
                    )
                client.terminate_app(app_id=app_id)
                state.clear_error()
                return (
                    MobileActionResult(
                        ok=True,
                        device_name=plan.device.name,
                        message="Terminated Android app.",
                        command=command,
                        value={"app_id": app_id},
                    ),
                    state,
                )
        except MobileExecutionError as exc:
            state.mark_command_failed(str(exc))
            raise

        raise MobileValidationError(f"Unsupported mobile control kind '{command.kind}'.")


__all__ = ["AdbControlEngine"]
