from __future__ import annotations

from typing import Protocol

from crxzipple.modules.authorization.domain.entities import AuthorizationPolicy


class AuthorizationPolicyRepository(Protocol):
    def list(self) -> list[AuthorizationPolicy]:
        ...

