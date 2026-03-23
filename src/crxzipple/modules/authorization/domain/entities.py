from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from crxzipple.modules.authorization.domain.value_objects import (
    AuthorizationEffect,
    AuthorizationObligation,
)


@dataclass(frozen=True, slots=True)
class AuthorizationPolicy:
    id: str
    effect: AuthorizationEffect
    actions: tuple[str, ...]
    description: str = ""
    subject_type: str | None = None
    subject_id: str | None = None
    subject_match: dict[str, Any] = field(default_factory=dict)
    resource_kind: str | None = None
    resource_id: str | None = None
    resource_match: dict[str, Any] = field(default_factory=dict)
    context_match: dict[str, Any] = field(default_factory=dict)
    condition: dict[str, Any] | None = None
    obligations: tuple[AuthorizationObligation, ...] = ()
    priority: int = 0
    enabled: bool = True
    source_kind: str = "imported"

