from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from crxzipple.bootstrap import AppContainer
from crxzipple.interfaces.http.dependencies import get_container
from crxzipple.modules.skills.application.models import InstalledSkill, SkillPackage
from crxzipple.modules.skills.domain import (
    SkillError,
    SkillInstallScope,
    SkillNotFoundError,
    SkillValidationError,
)

router = APIRouter()


def _raise_skill_http_error(exc: SkillError) -> None:
    if isinstance(exc, SkillNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, SkillValidationError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    raise HTTPException(status_code=500, detail=str(exc)) from exc


class SkillManifestResponse(BaseModel):
    api_version: str
    kind: str
    name: str
    description: str
    version: str | None = None
    tags: list[str] = Field(default_factory=list)
    instructions_path: str
    required_tools: list[str] = Field(default_factory=list)
    optional_tools: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)


class SkillResponse(BaseModel):
    name: str
    description: str
    version: str | None = None
    tags: list[str] = Field(default_factory=list)
    source: str
    root_path: str
    manifest_path: str
    instructions_path: str
    manifest: SkillManifestResponse

    @classmethod
    def from_entity(cls, package: SkillPackage) -> "SkillResponse":
        return cls(
            name=package.name,
            description=package.description,
            version=package.version,
            tags=list(package.tags),
            source=package.source,
            root_path=package.root_path,
            manifest_path=package.manifest_path,
            instructions_path=package.instructions_path,
            manifest=SkillManifestResponse(
                api_version=package.manifest.api_version,
                kind=package.manifest.kind,
                name=package.manifest.name,
                description=package.manifest.description,
                version=package.manifest.version,
                tags=list(package.manifest.tags),
                instructions_path=package.manifest.instructions_path,
                required_tools=list(package.manifest.required_tools),
                optional_tools=list(package.manifest.optional_tools),
                allowed_tools=list(package.manifest.allowed_tools),
            ),
        )


class SkillDetailResponse(SkillResponse):
    instructions: str | None = None


class ValidateSkillRequest(BaseModel):
    path: str = Field(min_length=1)


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
    def from_entity(cls, result: InstalledSkill) -> "SkillInstallResponse":
        return cls(
            scope=result.scope.value,
            target_root=result.target_root,
            target_path=result.target_path,
            skill=SkillResponse.from_entity(result.package),
        )


@router.get("", response_model=list[SkillResponse])
def list_skills(
    container: Annotated[AppContainer, Depends(get_container)],
    workspace_dir: str | None = Query(default=None),
    surface: str = Query(default="interactive"),
) -> list[SkillResponse]:
    items = container.skill_manager.list_available(
        workspace_dir=workspace_dir,
        surface=surface,
    )
    return [SkillResponse.from_entity(item) for item in items]


@router.get("/{skill_name}", response_model=SkillDetailResponse)
def get_skill(
    skill_name: str,
    container: Annotated[AppContainer, Depends(get_container)],
    workspace_dir: str | None = Query(default=None),
    surface: str = Query(default="interactive"),
    include_instructions: bool = Query(default=False),
) -> SkillDetailResponse:
    try:
        package = container.skill_manager.get(
            workspace_dir=workspace_dir,
            skill_name=skill_name,
            surface=surface,
        )
        response = SkillDetailResponse(**SkillResponse.from_entity(package).model_dump())
        if include_instructions:
            response.instructions = container.skill_manager.read(
                workspace_dir=workspace_dir,
                skill_name=skill_name,
                path=None,
                surface=surface,
            ).content
        return response
    except SkillError as exc:
        _raise_skill_http_error(exc)


@router.post("/validate", response_model=SkillResponse)
def validate_skill(
    payload: ValidateSkillRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillResponse:
    try:
        package = container.skill_manager.validate(path=payload.path)
    except SkillError as exc:
        _raise_skill_http_error(exc)
    return SkillResponse.from_entity(package)


@router.post(
    "/install",
    response_model=SkillInstallResponse,
    status_code=status.HTTP_201_CREATED,
)
def install_skill(
    payload: InstallSkillRequest,
    container: Annotated[AppContainer, Depends(get_container)],
) -> SkillInstallResponse:
    try:
        result = container.skill_manager.install(
            source_dir=payload.source_dir,
            scope=payload.scope,
            workspace_dir=payload.workspace_dir,
        )
    except SkillError as exc:
        _raise_skill_http_error(exc)
    return SkillInstallResponse.from_entity(result)
