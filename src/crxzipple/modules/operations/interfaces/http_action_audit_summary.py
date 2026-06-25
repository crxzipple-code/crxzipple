from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel


def operations_action_result_summary(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, BaseModel):
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        return value.dict()
    if isinstance(value, dict):
        return _json_safe_summary(value)
    if isinstance(value, list):
        return {"items": _json_safe_summary(value), "count": len(value)}
    return {
        "type": type(value).__name__,
        "id": str(getattr(value, "id", "") or getattr(value, "run_id", "") or ""),
        "status": str(getattr(value, "status", "") or ""),
    }


def operations_action_error_summary(exc: BaseException) -> dict[str, Any]:
    if isinstance(exc, HTTPException):
        return {
            "type": type(exc).__name__,
            "status_code": exc.status_code,
            "detail": _json_safe_summary(exc.detail),
        }
    return {
        "type": type(exc).__name__,
        "message": str(exc),
    }


def _json_safe_summary(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _json_safe_summary(item) for key, item in list(value.items())[:50]
        }
    if isinstance(value, list):
        return [_json_safe_summary(item) for item in value[:50]]
    if isinstance(value, tuple):
        return [_json_safe_summary(item) for item in value[:50]]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    if hasattr(value, "value"):
        return str(value.value)
    return str(value)
