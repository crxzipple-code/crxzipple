from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path

from crxzipple.modules.access.domain import CredentialResolutionError


@dataclass(slots=True)
class CredentialResolver:
    def resolve(
        self,
        binding: str,
        *,
        workspace_dir: str | None = None,
        allow_literal: bool = False,
    ) -> str:
        normalized = binding.strip()
        if not normalized:
            raise CredentialResolutionError("credential binding cannot be empty.")
        if normalized.startswith("env:"):
            return self._resolve_env(normalized.removeprefix("env:"))
        if normalized.startswith("file:"):
            return self._resolve_file(
                normalized.removeprefix("file:"),
                workspace_dir=workspace_dir,
            )
        if allow_literal:
            return normalized
        raise CredentialResolutionError(
            f"unsupported credential binding source '{normalized}'.",
        )

    def is_ready(
        self,
        binding: str,
        *,
        workspace_dir: str | None = None,
        allow_literal: bool = False,
    ) -> bool:
        try:
            self.resolve(
                binding,
                workspace_dir=workspace_dir,
                allow_literal=allow_literal,
            )
        except CredentialResolutionError:
            return False
        return True

    def _resolve_env(self, env_name: str) -> str:
        normalized = env_name.strip()
        if not normalized:
            raise CredentialResolutionError("env credential binding has no variable name.")
        value = os.environ.get(normalized)
        if value is None or not value.strip():
            raise CredentialResolutionError(
                f"environment variable '{normalized}' is not configured.",
            )
        return value

    def _resolve_file(
        self,
        path_value: str,
        *,
        workspace_dir: str | None,
    ) -> str:
        normalized = path_value.strip()
        if not normalized:
            raise CredentialResolutionError("file credential binding has no path.")
        expanded = os.path.expandvars(os.path.expanduser(normalized))
        path = Path(expanded)
        if not path.is_absolute():
            if not workspace_dir:
                raise CredentialResolutionError(
                    f"relative credential file '{normalized}' requires a workspace.",
                )
            path = Path(workspace_dir) / path
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise CredentialResolutionError(
                f"credential file '{path}' could not be read.",
            ) from exc
        if not value:
            raise CredentialResolutionError(f"credential file '{path}' is empty.")
        return value
