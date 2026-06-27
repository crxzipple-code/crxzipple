from __future__ import annotations

from pydantic import BaseModel, Field

from crxzipple.modules.skills.application.models import (
    SkillCreateRequest,
    SkillMutationResult,
    SkillPackage,
    SkillReadiness,
    SkillUpdateRequest,
)
from crxzipple.modules.skills.domain import SkillInstallScope


class SkillManifestResponse(BaseModel):
    api_version: str
    kind: str
    name: str
    description: str
    version: str | None = None
    tags: list[str] = Field(default_factory=list)
    when_to_use: str | None = None
    anti_patterns: list[str] = Field(default_factory=list)
    instructions_path: str
    required_tools: list[str] = Field(default_factory=list)
    optional_tools: list[str] = Field(default_factory=list)
    suggested_tools: list[str] = Field(default_factory=list)
    required_effects: list[str] = Field(default_factory=list)
    required_access: list[str] = Field(default_factory=list)
    surfaces: list[str] = Field(default_factory=list)
    supported_platforms: list[str] = Field(default_factory=list)
    setup_hints: list[str] = Field(default_factory=list)


class SkillResourceResponse(BaseModel):
    path: str
    kind: str
    size_bytes: int


class SkillRequirementsResponse(BaseModel):
    required_tools: list[str] = Field(default_factory=list)
    optional_tools: list[str] = Field(default_factory=list)
    suggested_tools: list[str] = Field(default_factory=list)
    required_effects: list[str] = Field(default_factory=list)
    surfaces: list[str] = Field(default_factory=list)
    supported_platforms: list[str] = Field(default_factory=list)
    required_access: list[str] = Field(default_factory=list)
    setup_hints: list[str] = Field(default_factory=list)


class SkillReadinessResponse(BaseModel):
    status: str
    ready: bool
    missing_tools: list[str] = Field(default_factory=list)
    missing_access: list[str] = Field(default_factory=list)
    missing_effects: list[str] = Field(default_factory=list)
    unsupported_surfaces: list[str] = Field(default_factory=list)
    unsupported_platforms: list[str] = Field(default_factory=list)
    validation_errors: list[str] = Field(default_factory=list)
    setup_hints: list[str] = Field(default_factory=list)

    @classmethod
    def from_entity(cls, readiness: SkillReadiness) -> SkillReadinessResponse:
        return cls(
            status=readiness.status.value,
            ready=readiness.ready,
            missing_tools=list(readiness.missing_tools),
            missing_access=list(readiness.missing_access),
            missing_effects=list(readiness.missing_effects),
            unsupported_surfaces=list(readiness.unsupported_surfaces),
            unsupported_platforms=list(readiness.unsupported_platforms),
            validation_errors=list(readiness.validation_errors),
            setup_hints=list(readiness.setup_hints),
        )


class SkillResponse(BaseModel):
    name: str
    description: str
    version: str | None = None
    tags: list[str] = Field(default_factory=list)
    source: str
    root_path: str
    manifest_path: str
    instructions_path: str
    resources: list[SkillResourceResponse] = Field(default_factory=list)
    requirements: SkillRequirementsResponse
    manifest: SkillManifestResponse
    enabled: bool = True
    readiness: SkillReadinessResponse | None = None

    @classmethod
    def from_entity(
        cls,
        package: SkillPackage,
        *,
        enabled: bool = True,
        readiness: SkillReadiness | None = None,
    ) -> SkillResponse:
        requirements = package.requirements
        return cls(
            name=package.name,
            description=package.description,
            version=package.version,
            tags=list(package.tags),
            source=package.source,
            root_path=package.root_path,
            manifest_path=package.manifest_path,
            instructions_path=package.instructions_path,
            resources=[
                SkillResourceResponse(
                    path=resource.path,
                    kind=resource.kind,
                    size_bytes=resource.size_bytes,
                )
                for resource in package.resources
            ],
            requirements=SkillRequirementsResponse(
                required_tools=list(requirements.required_tools),
                optional_tools=list(requirements.optional_tools),
                suggested_tools=list(requirements.suggested_tools),
                required_effects=list(requirements.required_effects),
                surfaces=list(requirements.surfaces),
                supported_platforms=list(requirements.supported_platforms),
                required_access=list(requirements.required_access),
                setup_hints=list(requirements.setup_hints),
            ),
            manifest=SkillManifestResponse(
                api_version=package.manifest.api_version,
                kind=package.manifest.kind,
                name=package.manifest.name,
                description=package.manifest.description,
                version=package.manifest.version,
                tags=list(package.manifest.tags),
                when_to_use=package.manifest.when_to_use,
                anti_patterns=list(package.manifest.anti_patterns),
                instructions_path=package.manifest.instructions_path,
                required_tools=list(package.manifest.required_tools),
                optional_tools=list(package.manifest.optional_tools),
                suggested_tools=list(package.manifest.suggested_tools),
                required_effects=list(package.manifest.required_effects),
                required_access=list(package.manifest.required_access),
                surfaces=list(package.manifest.surfaces),
                supported_platforms=list(package.manifest.supported_platforms),
                setup_hints=list(package.manifest.setup_hints),
            ),
            enabled=enabled,
            readiness=(
                SkillReadinessResponse.from_entity(readiness)
                if readiness is not None
                else None
            ),
        )


class SkillDetailResponse(SkillResponse):
    instructions: str | None = None


class ValidateSkillRequest(BaseModel):
    path: str = Field(min_length=1)


class SkillWriteRequest(BaseModel):
    content: str = Field(default="")
    workspace_dir: str | None = None


class CreateSkillRequest(BaseModel):
    name: str = Field(min_length=1)
    description: str = Field(min_length=1)
    instructions: str = Field(min_length=1)
    scope: SkillInstallScope = SkillInstallScope.WORKSPACE
    workspace_dir: str | None = None
    version: str | None = None
    tags: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    optional_tools: list[str] = Field(default_factory=list)
    suggested_tools: list[str] = Field(default_factory=list)
    required_effects: list[str] = Field(default_factory=list)
    required_access: list[str] = Field(default_factory=list)
    surfaces: list[str] = Field(default_factory=list)
    supported_platforms: list[str] = Field(default_factory=list)
    setup_hints: list[str] = Field(default_factory=list)

    def to_application_request(self) -> SkillCreateRequest:
        return SkillCreateRequest(
            name=self.name,
            description=self.description,
            instructions=self.instructions,
            scope=self.scope,
            workspace_dir=self.workspace_dir,
            version=self.version,
            tags=tuple(self.tags),
            required_tools=tuple(self.required_tools),
            optional_tools=tuple(self.optional_tools),
            suggested_tools=tuple(self.suggested_tools),
            required_effects=tuple(self.required_effects),
            required_access=tuple(self.required_access),
            surfaces=tuple(self.surfaces),
            supported_platforms=tuple(self.supported_platforms),
            setup_hints=tuple(self.setup_hints),
        )


class UpdateSkillRequest(BaseModel):
    workspace_dir: str | None = None
    description: str | None = None
    version: str | None = None
    tags: list[str] | None = None
    required_tools: list[str] | None = None
    optional_tools: list[str] | None = None
    suggested_tools: list[str] | None = None
    required_effects: list[str] | None = None
    required_access: list[str] | None = None
    surfaces: list[str] | None = None
    supported_platforms: list[str] | None = None
    setup_hints: list[str] | None = None

    def to_application_request(self, skill_name: str) -> SkillUpdateRequest:
        return SkillUpdateRequest(
            skill_name=skill_name,
            workspace_dir=self.workspace_dir,
            description=self.description,
            version=self.version,
            tags=_optional_tuple(self.tags),
            required_tools=_optional_tuple(self.required_tools),
            optional_tools=_optional_tuple(self.optional_tools),
            suggested_tools=_optional_tuple(self.suggested_tools),
            required_effects=_optional_tuple(self.required_effects),
            required_access=_optional_tuple(self.required_access),
            surfaces=_optional_tuple(self.surfaces),
            supported_platforms=_optional_tuple(self.supported_platforms),
            setup_hints=_optional_tuple(self.setup_hints),
        )


class SkillEnablementRequest(BaseModel):
    workspace_dir: str | None = None
    surface: str = "interactive"
    reason: str | None = None


class SkillMutationResponse(BaseModel):
    action: str
    changed: bool
    message: str
    skill: SkillResponse

    @classmethod
    def from_entity(cls, result: SkillMutationResult) -> SkillMutationResponse:
        return cls(
            action=result.action,
            changed=result.changed,
            message=result.message,
            skill=SkillResponse.from_entity(
                result.skill,
                enabled=result.action != "disable",
            ),
        )


class SkillReadinessMapResponse(BaseModel):
    skills: dict[str, SkillReadinessResponse]

    @classmethod
    def from_entities(
        cls,
        readiness: dict[str, SkillReadiness],
    ) -> SkillReadinessMapResponse:
        return cls(
            skills={
                name: SkillReadinessResponse.from_entity(item)
                for name, item in readiness.items()
            },
        )


def _optional_tuple(value: list[str] | None) -> tuple[str, ...] | None:
    if value is None:
        return None
    return tuple(value)
