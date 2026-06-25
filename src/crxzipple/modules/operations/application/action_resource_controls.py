from __future__ import annotations

from typing import Any

from crxzipple.modules.memory.application import (
    MemoryActorContext,
    MemoryRememberRequest,
)
from crxzipple.modules.operations.application.action_dependencies import (
    required_dependency,
)
from crxzipple.modules.skills.domain import SkillInstallScope


def validate_skill_package(skill_manager: Any, *, path: str) -> Any:
    return required_dependency(skill_manager, "skill manager").validate(path=path)


def install_global_skill(skill_manager: Any, *, source_dir: str) -> Any:
    return required_dependency(skill_manager, "skill manager").install(
        source_dir=source_dir,
        scope=SkillInstallScope.GLOBAL,
        workspace_dir=None,
    )


def sync_skills(
    skill_manager: Any,
    *,
    workspace_dir: str | None = None,
    source_id: str | None = None,
    surface: str = "interactive",
) -> Any:
    return required_dependency(skill_manager, "skill manager").sync(
        workspace_dir=workspace_dir,
        source_id=source_id,
        surface=surface,
    )


def collect_access_inventory(
    access_inventory_collector: Any,
    *,
    workspace_dir: str | None = None,
    include_ready: bool = True,
    include_disabled: bool = False,
) -> dict[str, Any]:
    collector = required_dependency(
        access_inventory_collector,
        "access inventory collector",
    )
    return dict(
        collector(
            workspace_dir=workspace_dir,
            include_ready=include_ready,
            include_disabled=include_disabled,
        ),
    )


def check_access_readiness(
    access_service: Any,
    *,
    requirements: list[str],
    credential_bindings: list[str],
    workspace_dir: str | None = None,
    allow_literal_credentials: bool = False,
) -> list[tuple[str, Any]]:
    service = required_dependency(access_service, "access service")
    checks: list[tuple[str, Any]] = []
    for requirement in requirements:
        readiness = service.check_requirement(requirement, workspace_dir=workspace_dir)
        checks.append(("requirement", readiness))
    for binding in credential_bindings:
        readiness = service.check_credential_binding(
            binding,
            workspace_dir=workspace_dir,
            allow_literal=allow_literal_credentials,
        )
        checks.append(("credential_binding", readiness))
    return checks


def begin_access_setup(
    access_service: Any,
    *,
    target: str,
    workspace_dir: str | None = None,
) -> Any:
    return required_dependency(access_service, "access service").begin_setup(
        target,
        workspace_dir=workspace_dir,
    )


def write_long_term_memory(
    memory_runtime_service: Any,
    *,
    agent_id: str,
    content: str,
    reason: str | None = None,
) -> Any:
    return required_dependency(
        memory_runtime_service,
        "memory runtime service",
    ).remember(
        MemoryRememberRequest(
            actor=MemoryActorContext(agent_id=agent_id),
            content=content,
            intent="freeform",
            retention="durable",
            metadata={"source": "operations", "reason": reason},
        ),
    )
