from __future__ import annotations

from crxzipple.modules.orchestration.domain import OrchestrationRun


def optional_text(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def optional_int(value: object) -> int | None:
    return value if isinstance(value, int) and value >= 0 else None


def optional_positive_int(value: object) -> int | None:
    return value if isinstance(value, int) and value > 0 else None


def optional_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized or None


def truncate(value: str, *, limit: int) -> str:
    normalized = " ".join(value.split())
    if len(normalized) <= limit:
        return normalized
    return f"{normalized[: limit - 3].rstrip()}..."


def metadata_str(run: OrchestrationRun, key: str) -> str | None:
    value = run.metadata.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def metadata_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    metadata: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            continue
        if item is None or isinstance(item, str | int | float | bool):
            metadata[key] = item
    return metadata
