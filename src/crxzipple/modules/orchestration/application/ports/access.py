from __future__ import annotations

from typing import Protocol

from crxzipple.modules.access import AccessRequirementReadiness


class AccessReadinessPort(Protocol):
    def check_credential_binding(
        self,
        binding: str,
        *,
        workspace_dir: str | None = None,
        allow_literal: bool = False,
    ) -> AccessRequirementReadiness:
        ...

    def check_requirements(
        self,
        requirements: tuple[str, ...],
        *,
        workspace_dir: str | None = None,
    ) -> tuple[AccessRequirementReadiness, ...]:
        ...
