from __future__ import annotations

from crxzipple.app.integration.context_workspace_skills import SkillContextNodeProvider
from crxzipple.modules.context_workspace.application import (
    ContextActionInput,
    ContextOwnerRegistry,
    ContextSliceBuilderService,
    ContextTreeService,
    ContextWorkspaceService,
    EnsureContextWorkspaceInput,
)
from crxzipple.modules.context_workspace.domain import ContextAction
from crxzipple.modules.context_workspace.infrastructure import (
    InMemoryContextNodeRepository,
    InMemoryContextOperationRepository,
    InMemoryContextWorkspaceRepository,
)
from crxzipple.modules.skills.application import (
    SkillPackage,
    SkillReadResult,
    SkillRuntimeRequestResolutionContext,
    SkillRuntimeRequestResolver,
)
from crxzipple.modules.skills.domain import SkillManifest, SkillNotFoundError


def test_skill_adapter_expands_available_ready_skill_nodes() -> None:
    skill_service = _FakeSkillService(
        _package("skill-a", description="Useful for focused work."),
        _package("skill-b", description="Filtered out by prompt resolution."),
    )
    services = _context_services(skill_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:skills",
            agent_id="assistant",
            metadata={
                "workspace_dir": "/workspace",
                "runtime_request_surface": "interactive",
                "available_skill_names": ["skill-a"],
            },
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:skills",
            node_id="skills.available",
            action=ContextAction.EXPAND,
        ),
    )
    tree = services["tree"].list_tree("session:skills")
    skill_nodes = [node for node in tree.nodes if node.parent_id == "skills.available"]

    assert [node.title for node in skill_nodes] == ["skill-a"]
    assert skill_nodes[0].owner_ref["workspace_dir"] == "/workspace"
    assert "Useful for focused work." in skill_nodes[0].summary


def test_runtime_resolution_ready_names_drive_context_tree_llm_slice() -> None:
    skill_service = _FakeSkillService(
        _package("skill-a", description="Ready workflow."),
        _package("skill-b", description="Requires missing tool."),
    )
    packages = skill_service.list_available(
        workspace_dir="/workspace",
        surface="interactive",
    )
    resolution = SkillRuntimeRequestResolver().resolve(
        packages,
        available_tool_ids=(),
        context=SkillRuntimeRequestResolutionContext(
            workspace_dir="/workspace",
            surface="interactive",
        ),
    )
    catalog = resolution.runtime_request_catalog

    assert catalog is not None
    assert catalog.metadata["available_skill_names"] == ["skill-a"]
    assert "skill-a" in catalog.content
    assert "skill-b" not in catalog.content

    services = _context_services(skill_service)
    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:skills-runtime",
            agent_id="assistant",
            metadata={
                "workspace_dir": "/workspace",
                "runtime_request_surface": "interactive",
                "available_skill_names": catalog.metadata["available_skill_names"],
            },
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:skills-runtime",
            node_id="skills.available",
            action=ContextAction.EXPAND,
        ),
    )
    tree = services["tree"].list_tree("session:skills-runtime")
    skill_nodes = [node for node in tree.nodes if node.parent_id == "skills.available"]

    assert [node.title for node in skill_nodes] == ["skill-a"]
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:skills-runtime",
            node_id="skills.skill.skill-a",
            action=ContextAction.PIN,
        ),
    )

    context_slice = services["slice"].build_slice(
        session_key="session:skills-runtime",
        run_id="run-skills-runtime",
        provider_profile="codex",
    )
    slice_items = {item.item_id: item for item in context_slice.items}

    assert "skills.skill.skill-a" in slice_items
    assert "skills.skill.skill-b" not in slice_items
    ready_item = slice_items["skills.skill.skill-a"]
    assert ready_item.metadata["owner_resolution"] == "handle_only"
    assert ready_item.text == ""
    assert ready_item.owner_ref["skill_name"] == "skill-a"
    assert skill_service.read_calls == []


def test_skill_adapter_expands_skill_instructions_node() -> None:
    skill_service = _FakeSkillService(
        _package("skill-a", description="Useful for focused work."),
    )
    services = _context_services(skill_service)

    services["workspace"].ensure_workspace(
        EnsureContextWorkspaceInput(
            session_key="session:skills",
            agent_id="assistant",
            metadata={"available_skill_names": ["skill-a"]},
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:skills",
            node_id="skills.available",
            action=ContextAction.EXPAND,
        ),
    )
    services["tree"].apply_action(
        ContextActionInput(
            session_key="session:skills",
            node_id="skills.skill.skill-a",
            action=ContextAction.EXPAND,
        ),
    )
    tree = services["tree"].list_tree("session:skills")
    children = [
        node
        for node in tree.nodes
        if node.parent_id == "skills.skill.skill-a"
    ]

    assert [node.kind for node in children] == ["skill_instructions"]
    assert "available through the skill_read tool" in children[0].summary
    assert "skill='skill-a'" in children[0].summary
    assert children[0].metadata["content_available_via"] == "skill_read"
    assert children[0].owner_ref["requested_path"].endswith("/SKILL.md")
    assert skill_service.read_calls == []


def _context_services(skill_service: "_FakeSkillService"):
    registry = ContextOwnerRegistry()
    registry.register(SkillContextNodeProvider(skill_service))
    workspaces = InMemoryContextWorkspaceRepository()
    nodes = InMemoryContextNodeRepository()
    operations = InMemoryContextOperationRepository()
    return {
        "workspace": ContextWorkspaceService(
            workspace_repository=workspaces,
            node_repository=nodes,
            owner_registry=registry,
        ),
        "tree": ContextTreeService(
            workspace_repository=workspaces,
            node_repository=nodes,
            operation_repository=operations,
            owner_registry=registry,
        ),
        "slice": ContextSliceBuilderService(
            workspace_repository=workspaces,
            node_repository=nodes,
        ),
    }


def _package(name: str, *, description: str) -> SkillPackage:
    return SkillPackage(
        manifest=SkillManifest(
            api_version="skills.crxzipple.dev/v1",
            kind="Skill",
            name=name,
            description=description,
            tags=("test",),
            when_to_use="when the task matches",
            required_tools=("tool-a",) if name == "skill-b" else (),
        ),
        root_path=f"/skills/{name}",
        manifest_path=f"/skills/{name}/skill.yaml",
        instructions_path=f"/skills/{name}/SKILL.md",
        source="unit-test",
    )


class _FakeSkillService:
    def __init__(self, *packages: SkillPackage) -> None:
        self._packages = {package.name: package for package in packages}
        self.read_calls: list[tuple[str, str | None, str]] = []

    def list_available(
        self,
        *,
        workspace_dir: str | None,
        surface: str,
        include_disabled: bool = False,
    ) -> tuple[SkillPackage, ...]:
        del workspace_dir, surface, include_disabled
        return tuple(self._packages.values())

    def get(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        surface: str,
        include_disabled: bool = False,
    ) -> SkillPackage:
        del workspace_dir, surface, include_disabled
        package = self._packages.get(skill_name)
        if package is None:
            raise SkillNotFoundError(f"Skill '{skill_name}' is not available.")
        return package

    def read(
        self,
        *,
        workspace_dir: str | None,
        skill_name: str,
        path: str | None,
        surface: str,
    ) -> SkillReadResult:
        del workspace_dir
        package = self.get(
            workspace_dir=None,
            skill_name=skill_name,
            surface=surface,
        )
        self.read_calls.append((skill_name, path, surface))
        return SkillReadResult(
            package=package,
            requested_path=path or "SKILL.md",
            resolved_path=package.instructions_path,
            content=f"# {skill_name}\n\nUse this skill only when relevant.",
        )
