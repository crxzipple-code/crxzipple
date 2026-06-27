from __future__ import annotations

from pathlib import Path

from crxzipple.modules.skills.application.owner_package_index import (
    DEFAULT_SOURCE_IDS,
    domain_source_type,
)
from crxzipple.modules.skills.domain import (
    SkillSource as DomainSkillSource,
    SkillSourceType,
    SkillValidationError,
)

EDITABLE_SOURCE_TYPES = frozenset(
    {
        SkillSourceType.MANAGED,
        SkillSourceType.EXTERNAL,
    },
)


def normalize_source_id(source_id: str) -> str:
    normalized = source_id.strip()
    if not normalized:
        raise SkillValidationError("Skill source id is required.")
    if "/" in normalized or "\\" in normalized:
        raise SkillValidationError("Skill source id cannot contain path separators.")
    return normalized


def normalize_source_root(root_path: str) -> str:
    candidate = root_path.strip()
    if not candidate:
        raise SkillValidationError("Skill source root_path is required.")
    try:
        resolved = Path(candidate).expanduser().resolve(strict=True)
    except OSError as exc:
        raise SkillValidationError(
            f"Skill source root_path '{candidate}' could not be resolved.",
        ) from exc
    if not resolved.is_dir():
        raise SkillValidationError(
            f"Skill source root_path '{candidate}' is not a directory.",
        )
    return str(resolved)


def ensure_custom_source_id(source_id: str) -> None:
    if source_id in DEFAULT_SOURCE_IDS:
        raise SkillValidationError(
            f"Skill source '{source_id}' is managed by the runtime and cannot be edited.",
        )


def editable_source_type(source_kind: str) -> SkillSourceType:
    source_type = domain_source_type(source_kind)
    if source_type not in EDITABLE_SOURCE_TYPES:
        raise SkillValidationError(
            "Custom skill sources must use managed or external source_kind.",
        )
    return source_type


def ensure_custom_source(source: DomainSkillSource) -> None:
    ensure_custom_source_id(source.source_id)
    if source.source_type not in EDITABLE_SOURCE_TYPES:
        raise SkillValidationError(
            f"Skill source '{source.source_id}' is not a custom editable source.",
        )
