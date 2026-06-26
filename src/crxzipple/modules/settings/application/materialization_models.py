from __future__ import annotations

from dataclasses import dataclass
from typing import Any


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class SettingsMaterializationWarning:
    resource_kind: str
    resource_id: str
    code: str
    message: str

    def to_payload(self) -> JsonObject:
        return {
            "resource_kind": self.resource_kind,
            "resource_id": self.resource_id,
            "code": self.code,
            "message": self.message,
        }
