from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from crxzipple.modules.mobile.domain import MobileActionResult, MobileActionCommand, MobileControlCommand, MobileStoredRef


@dataclass(frozen=True, slots=True)
class MobileResultSerializer:
    def serialize(self, result: MobileActionResult) -> dict[str, Any]:
        return {
            "ok": result.ok,
            "device_name": result.device_name,
            "message": result.message,
            "command": self._serialize_command(result.command),
            "value": self._serialize_value(result.value),
        }

    def _serialize_command(
        self,
        command: MobileControlCommand | MobileActionCommand,
    ) -> dict[str, Any]:
        if isinstance(command, MobileControlCommand):
            return {
                "family": "control",
                "device_name": command.device_name,
                "kind": command.kind,
                "payload": dict(command.payload),
                "timeout_ms": command.timeout_ms,
            }
        return {
            "family": "action",
            "device_name": command.device_name,
            "kind": command.kind,
            "target": {
                "ref": command.target.ref,
                "selector": command.target.selector,
            },
            "payload": dict(command.payload),
            "timeout_ms": command.timeout_ms,
        }

    def _serialize_value(self, value: Any) -> Any:
        if isinstance(value, MobileStoredRef):
            return {
                "ref": value.ref,
                "generation": value.generation,
                "source": value.source,
                "text": value.text,
                "content_desc": value.content_desc,
                "resource_id": value.resource_id,
                "class_name": value.class_name,
                "xpath": value.xpath,
                "bounds": list(value.bounds) if value.bounds is not None else None,
                "clickable": value.clickable,
                "focusable": value.focusable,
                "focused": value.focused,
                "enabled": value.enabled,
            }
        if isinstance(value, tuple | list):
            return [self._serialize_value(item) for item in value]
        if isinstance(value, Mapping):
            return {str(key): self._serialize_value(item) for key, item in value.items()}
        return value
