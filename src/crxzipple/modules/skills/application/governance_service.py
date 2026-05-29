from __future__ import annotations

from dataclasses import dataclass

from crxzipple.modules.skills.application.catalog_service import SkillCatalogService
from crxzipple.modules.skills.application.events import (
    SKILL_DISABLE_SUCCEEDED_EVENT,
    SKILL_ENABLE_SUCCEEDED_EVENT,
    SkillEventEmitter,
    emit_skill_event,
)
from crxzipple.modules.skills.application.exceptions import (
    SkillCapabilityUnavailableError,
)
from crxzipple.modules.skills.application.models import SkillMutationResult
from crxzipple.modules.skills.application.owner_state import (
    SkillOwnerStateService,
    skill_policy_id,
    utc_now,
)
from crxzipple.modules.skills.application.ports import (
    SkillOwnerCatalogRepositoryPort,
)
from crxzipple.modules.skills.domain import (
    SkillEnablementPolicy,
    SkillEnablementTargetKind,
    SkillInstallationStatus,
    SkillRuntimeVisibility,
)


@dataclass(slots=True)
class SkillGovernanceService:
    catalog_service: SkillCatalogService
    owner_state: SkillOwnerStateService
    owner_catalog_repository: SkillOwnerCatalogRepositoryPort | None = None
    event_emitter: SkillEventEmitter | None = None

    def enable(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        reason: str | None,
        surface: str,
    ) -> SkillMutationResult:
        return self._set_enabled(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            enabled=True,
            reason=reason,
            surface=surface,
        )

    def disable(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        reason: str | None,
        surface: str,
    ) -> SkillMutationResult:
        return self._set_enabled(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            enabled=False,
            reason=reason,
            surface=surface,
        )

    def _set_enabled(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        enabled: bool,
        reason: str | None,
        surface: str,
    ) -> SkillMutationResult:
        package = self.catalog_service.get(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            surface=surface,
            include_disabled=True,
        )
        if self.owner_catalog_repository is None:
            action = "enable" if enabled else "disable"
            raise SkillCapabilityUnavailableError(
                f"Skill {action} requires a governance repository; filesystem discovery has no enablement store.",
            )
        now = utc_now()
        policy = self.owner_catalog_repository.upsert_enablement_policy(
            SkillEnablementPolicy(
                policy_id=skill_policy_id(package.name),
                target_kind=SkillEnablementTargetKind.SKILL,
                target_id=package.name,
                enabled=enabled,
                trusted=False,
                runtime_visibility=(
                    SkillRuntimeVisibility.VISIBLE
                    if enabled
                    else SkillRuntimeVisibility.HIDDEN
                ),
                reason=reason,
                created_at=now,
                updated_at=now,
            ),
        )
        action = "enable" if policy.enabled else "disable"
        emit_skill_event(
            self.event_emitter,
            SKILL_ENABLE_SUCCEEDED_EVENT
            if policy.enabled
            else SKILL_DISABLE_SUCCEEDED_EVENT,
            status="succeeded",
            payload={
                "skill": package.name,
                "skill_name": package.name,
                "source": package.source,
                "workspace_dir": workspace_dir or "",
                "enabled": policy.enabled,
                "reason": reason or "",
            },
        )
        self.owner_state.record_installation(
            action=f"package_{action}",
            status=SkillInstallationStatus.SUCCEEDED,
            package=package,
            workspace_dir=workspace_dir,
            reason=reason,
            message=f"Skill '{package.name}' {action}d.",
            metadata={"enabled": policy.enabled},
        )
        return SkillMutationResult(
            skill=package,
            action=action,
            changed=True,
            message=f"Skill '{package.name}' {action}d.",
        )
