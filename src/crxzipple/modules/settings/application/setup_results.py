from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class SettingsBootstrapImportResult:
    imported_counts: Mapping[str, int]
    created: int = 0
    updated: int = 0
    skipped: int = 0
    audit_refs: tuple[str, ...] = field(default_factory=tuple)

    def to_payload(self) -> dict[str, Any]:
        return {
            "imported_counts": dict(self.imported_counts),
            "created": self.created,
            "updated": self.updated,
            "skipped": self.skipped,
            "audit_refs": list(self.audit_refs),
        }
