from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from crxzipple.modules.browser.domain import (
    BrowserActionResult,
    BrowserControlCommand,
    BrowserPageActionCommand,
    BrowserTab,
)


@dataclass(frozen=True, slots=True)
class BrowserResultSerializer:
    def serialize(self, result: BrowserActionResult) -> dict[str, Any]:
        return {
            "ok": result.ok,
            "target_id": result.target_id,
            "message": result.message,
            "command": self._serialize_command(result.command),
            "value": self._serialize_value(result.value),
        }

    def _serialize_command(
        self,
        command: BrowserControlCommand | BrowserPageActionCommand,
    ) -> dict[str, Any]:
        if isinstance(command, BrowserControlCommand):
            return {
                "family": "control",
                "profile_name": command.profile_name,
                "kind": command.kind,
                "target_id": command.target_id,
                "payload": dict(command.payload),
                "timeout_ms": command.timeout_ms,
            }

        return {
            "family": "page-action",
            "profile_name": command.profile_name,
            "kind": command.kind,
            "target": {
                "target_id": command.target.target_id,
                "ref": command.target.ref,
                "selector": command.target.selector,
            },
            "payload": dict(command.payload),
            "timeout_ms": command.timeout_ms,
        }

    def _serialize_value(self, value: Any) -> Any:
        if isinstance(value, BrowserTab):
            return {
                "target_id": value.target_id,
                "url": value.url,
                "title": value.title,
                "type": value.type,
                "ws_url": value.ws_url,
                "json_endpoints": dict(value.json_endpoints) if value.json_endpoints else None,
            }
        if isinstance(value, tuple | list):
            return [self._serialize_value(item) for item in value]
        if isinstance(value, Mapping):
            return {str(key): self._serialize_value(item) for key, item in value.items()}
        return value
