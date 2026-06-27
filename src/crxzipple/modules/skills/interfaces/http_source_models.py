from __future__ import annotations

from pydantic import BaseModel, Field

from crxzipple.modules.skills.application.models import (
    InstalledSkill,
    SkillSource,
    SkillSourceCreateRequest,
    SkillSourceKind,
    SkillSourceMutationResult,
    SkillSourceUpdateRequest,
    SkillSyncResult,
)
from crxzipple.modules.skills.domain import SkillInstallation, SkillInstallScope
from crxzipple.modules.skills.interfaces.http_skill_models import SkillResponse


class InstallSkillRequest(BaseModel):
    source_dir: str = Field(min_length=1)
    scope: SkillInstallScope = SkillInstallScope.WORKSPACE
    workspace_dir: str | None = None


class SkillInstallResponse(BaseModel):
    scope: str
    target_root: str
    target_path: str
    skill: SkillResponse

    @classmethod
    def from_entity(cls, result: InstalledSkill) -> SkillInstallResponse:
        return cls(
            scope=result.scope.value,
            target_root=result.target_root,
            target_path=result.target_path,
            skill=SkillResponse.from_entity(result.package),
        )


class SkillSourceResponse(BaseModel):
    source_id: str
    source_kind: str
    root_path: str
    enabled: bool
    readonly: bool
    package_count: int
    metadata: dict[str, object] = Field(default_factory=dict)
    status: str = "active"
    sync_status: str = "never_synced"
    priority: int = 100

    @classmethod
    def from_entity(cls, source: SkillSource) -> SkillSourceResponse:
        return cls(
            source_id=source.source_id,
            source_kind=source.source_kind.value,
            root_path=source.root_path,
            enabled=source.enabled,
            readonly=source.readonly,
            package_count=source.package_count,
            metadata=source.metadata,
            status=source.status,
            sync_status=source.sync_status,
            priority=source.priority,
        )


class CreateSkillSourceRequest(BaseModel):
    source_id: str = Field(min_length=1)
    root_path: str = Field(min_length=1)
    source_kind: SkillSourceKind = SkillSourceKind.EXTERNAL
    enabled: bool = True
    readonly: bool = False
    priority: int = 100
    metadata: dict[str, object] = Field(default_factory=dict)

    def to_application_request(self) -> SkillSourceCreateRequest:
        return SkillSourceCreateRequest(
            source_id=self.source_id,
            root_path=self.root_path,
            source_kind=self.source_kind,
            enabled=self.enabled,
            readonly=self.readonly,
            priority=self.priority,
            metadata=dict(self.metadata),
        )


class UpdateSkillSourceRequest(BaseModel):
    root_path: str | None = None
    enabled: bool | None = None
    readonly: bool | None = None
    priority: int | None = None
    metadata: dict[str, object] | None = None

    def to_application_request(self, source_id: str) -> SkillSourceUpdateRequest:
        return SkillSourceUpdateRequest(
            source_id=source_id,
            root_path=self.root_path,
            enabled=self.enabled,
            readonly=self.readonly,
            priority=self.priority,
            metadata=dict(self.metadata) if self.metadata is not None else None,
        )


class SkillSourceMutationResponse(BaseModel):
    action: str
    changed: bool
    message: str
    source: SkillSourceResponse

    @classmethod
    def from_entity(
        cls,
        result: SkillSourceMutationResult,
    ) -> SkillSourceMutationResponse:
        return cls(
            action=result.action,
            changed=result.changed,
            message=result.message,
            source=SkillSourceResponse.from_entity(result.source),
        )


class SkillInstallationResponse(BaseModel):
    installation_id: str
    action: str
    status: str
    source_id: str | None = None
    skill_id: str | None = None
    skill_name: str | None = None
    source_uri: str | None = None
    target_uri: str | None = None
    actor_id: str | None = None
    reason: str | None = None
    message: str | None = None
    metadata: dict[str, object] = Field(default_factory=dict)
    created_at: str | None = None

    @classmethod
    def from_entity(
        cls,
        installation: SkillInstallation,
    ) -> SkillInstallationResponse:
        status_value = getattr(installation.status, "value", installation.status)
        return cls(
            installation_id=installation.installation_id,
            action=installation.action,
            status=str(status_value),
            source_id=installation.source_id,
            skill_id=installation.skill_id,
            skill_name=installation.skill_name,
            source_uri=installation.source_uri,
            target_uri=installation.target_uri,
            actor_id=installation.actor_id,
            reason=installation.reason,
            message=installation.message,
            metadata=dict(installation.metadata),
            created_at=installation.created_at.isoformat()
            if installation.created_at is not None
            else None,
        )


class SkillSyncRequest(BaseModel):
    workspace_dir: str | None = None
    source_id: str | None = None
    surface: str = "interactive"


class SkillSyncResponse(BaseModel):
    source_id: str | None = None
    synced_count: int
    skills: list[SkillResponse] = Field(default_factory=list)

    @classmethod
    def from_entity(cls, result: SkillSyncResult) -> SkillSyncResponse:
        return cls(
            source_id=result.source_id,
            synced_count=result.synced_count,
            skills=[SkillResponse.from_entity(package) for package in result.packages],
        )
