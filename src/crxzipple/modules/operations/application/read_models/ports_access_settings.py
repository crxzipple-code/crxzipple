from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol


class OperationsAccessReadinessPort(Protocol):
    def check_requirement(self, requirement: str) -> Any: ...

    def check_requirements(self, requirements: tuple[str, ...]) -> tuple[Any, ...]: ...

    def check_credential_binding(
        self,
        binding_id: str,
        *,
        allow_literal: bool = False,
    ) -> Any: ...


class OperationsSettingsQueryPort(Protocol):
    def get_resource(self, resource_id: str) -> Any: ...

    def list_resources(
        self,
        *,
        resource_kind: str | None = None,
        owner_module: str | None = None,
    ) -> tuple[Any, ...]: ...

    def list_versions(self, resource_id: str) -> tuple[Any, ...]: ...

    def get_effective(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
        trace_context: Mapping[str, Any] | None = None,
    ) -> Any: ...

    def latest_snapshot(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
    ) -> Any | None: ...

    def list_overrides(
        self,
        resource_id: str,
        *,
        environment: str | None = None,
    ) -> tuple[Any, ...]: ...

    def list_audits(self) -> tuple[Any, ...]: ...
