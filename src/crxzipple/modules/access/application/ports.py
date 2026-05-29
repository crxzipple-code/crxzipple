from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol

from crxzipple.modules.settings.application.models import (
    CreateSettingsResourceInput,
    UpdateSettingsResourceInput,
)


class AccessSettingsQueryPort(Protocol):
    def get_resource(self, resource_id: str) -> Any:
        ...

    def get_effective(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
        trace_context: Mapping[str, Any] | None = None,
    ) -> Any:
        ...


class AccessSettingsActionPort(Protocol):
    def create_resource(self, request: CreateSettingsResourceInput) -> Any:
        ...

    def update_resource(self, request: UpdateSettingsResourceInput) -> Any:
        ...

    def enable_resource(
        self,
        resource_id: str,
        *,
        actor: str | None = None,
        reason: str = "",
    ) -> Any:
        ...

    def disable_resource(
        self,
        resource_id: str,
        *,
        actor: str | None = None,
        reason: str = "",
    ) -> Any:
        ...
