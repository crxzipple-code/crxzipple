from __future__ import annotations

from fastapi import HTTPException

from crxzipple.modules.skills.application.exceptions import SkillCapabilityUnavailableError
from crxzipple.modules.skills.domain import (
    SkillError,
    SkillNotFoundError,
    SkillValidationError,
)


def raise_skill_http_error(exc: SkillError) -> None:
    if isinstance(exc, SkillNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, SkillValidationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if isinstance(exc, SkillCapabilityUnavailableError):
        raise HTTPException(status_code=501, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc
