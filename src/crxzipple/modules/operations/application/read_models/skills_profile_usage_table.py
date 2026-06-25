from __future__ import annotations

from typing import Any

from crxzipple.modules.operations.application.read_models.models import (
    OperationsTableColumnModel,
    OperationsTableRowModel,
    OperationsTableSectionModel,
)
from crxzipple.modules.operations.application.read_models.skills_common import text


def profile_usage_table(
    agent_service: Any | None,
    *,
    surface: str,
    available: int,
    ready: int,
) -> OperationsTableSectionModel:
    list_profiles = getattr(agent_service, "list_profiles", None)
    profiles: tuple[Any, ...] = ()
    if callable(list_profiles):
        try:
            profiles = tuple(list_profiles() or ())
        except Exception:
            profiles = ()
    rows = [
        OperationsTableRowModel(
            id=f"profile:{text(getattr(profile, 'id', ''))}",
            cells={
                "profile": text(getattr(profile, "id", "")),
                "surface": surface,
                "available_skills": str(available),
                "ready_skills": str(ready),
                "status": "Enabled"
                if bool(getattr(profile, "enabled", True))
                else "Disabled",
            },
            status="Enabled" if bool(getattr(profile, "enabled", True)) else "Disabled",
            tone="success" if bool(getattr(profile, "enabled", True)) else "neutral",
        )
        for profile in profiles[:40]
    ]
    if not rows and available:
        rows = [
            OperationsTableRowModel(
                id=f"profile:surface:{surface}",
                cells={
                    "profile": "all",
                    "surface": surface,
                    "available_skills": str(available),
                    "ready_skills": str(ready),
                    "status": "Available",
                },
                status="Available",
                tone="success",
            ),
        ]
    return OperationsTableSectionModel(
        id="profile_usage",
        title="Profile Usage",
        columns=(
            OperationsTableColumnModel("profile", "Profile"),
            OperationsTableColumnModel("surface", "Surface"),
            OperationsTableColumnModel("available_skills", "Available Skills"),
            OperationsTableColumnModel("ready_skills", "Ready Skills"),
            OperationsTableColumnModel("status", "Status"),
        ),
        rows=tuple(rows),
        total=len(rows),
        empty_state="No profile usage is available.",
    )
