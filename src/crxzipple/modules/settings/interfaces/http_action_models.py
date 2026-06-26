from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SettingsActionRequest(BaseModel):
    resource_id: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    actor: str | None = None
    risk: str | None = None
    dry_run: bool = False
    expected_active_version_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
