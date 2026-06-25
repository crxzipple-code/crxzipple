from __future__ import annotations

from datetime import datetime
import hashlib

from crxzipple.modules.skills.application.models import SkillPackage
from crxzipple.modules.skills.domain import (
    SkillPackageIndex,
    SkillPackageStatus,
    SkillSourceType,
)


DEFAULT_SOURCE_IDS = frozenset({"workspace", "global", "system"})


def skill_policy_id(skill_name: str) -> str:
    return f"skill:{skill_name}:enablement"


def source_policy_id(source_id: str) -> str:
    return f"source:{source_id}:enablement"


def domain_source_type(source_id: str) -> SkillSourceType:
    try:
        return SkillSourceType(source_id)
    except ValueError:
        return SkillSourceType.EXTERNAL


def package_id(package: SkillPackage) -> str:
    return f"{package.source}:{package.name}"


def package_index(package: SkillPackage, *, updated_at: datetime) -> SkillPackageIndex:
    return SkillPackageIndex(
        package_id=package_id(package),
        skill_id=package.name,
        name=package.name,
        source_id=package.source,
        root_uri=package.root_path,
        manifest_uri=package.manifest_path,
        instructions_uri=package.instructions_path,
        version=package.version,
        fingerprint=package.fingerprint or package_fingerprint(package),
        status=SkillPackageStatus.ACTIVE,
        requirements=package.requirements,
        capability_requirements={
            "required_tools": list(package.requirements.required_tools),
            "required_effects": list(package.requirements.required_effects),
            "required_access": list(package.requirements.required_access),
            "supported_platforms": list(package.requirements.supported_platforms),
        },
        metadata={
            "tags": list(package.tags),
            "description": package.description,
            "source": package.source,
        },
        indexed_at=updated_at,
        updated_at=updated_at,
    )


def package_fingerprint(package: SkillPackage) -> str:
    fingerprint_input = "|".join(
        (
            package.name,
            package.version or "",
            package.source,
            package.root_path,
            package.manifest_path,
            package.instructions_path,
        ),
    )
    return f"sha256:{hashlib.sha256(fingerprint_input.encode('utf-8')).hexdigest()}"


def package_root(package: SkillPackage) -> str:
    root_path = package.root_path.rstrip("/")
    if "/" not in root_path:
        return package.root_path
    return root_path.rsplit("/", 1)[0]
