from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any, Protocol

from crxzipple.shared.settings import SettingsResourceRef


JsonObject = dict[str, Any]


@dataclass(frozen=True, slots=True)
class BootstrapSettingsResource:
    ref: SettingsResourceRef
    payload: Mapping[str, Any]
    source: str = "core.config.Settings"
    metadata: Mapping[str, Any] = field(default_factory=dict)


class CoreSettingsBootstrapImporter(Protocol):
    def collect_resources(
        self,
        settings: object,
    ) -> tuple[BootstrapSettingsResource, ...]:
        ...
