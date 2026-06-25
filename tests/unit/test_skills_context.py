from __future__ import annotations

from datetime import datetime, timedelta, timezone
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from crxzipple.app.integration.skill_runtime_request_resolution import (
    SkillAuthorizationServiceAdapter,
)
from crxzipple.modules.authorization.application import AuthorizationApplicationService
from crxzipple.modules.authorization.infrastructure import (
    AbacAuthorizationEvaluator,
    InMemoryAuthorizationPolicyRepository,
)
from crxzipple.modules.skills.application import (
    SkillAccessRequirementReadiness,
    SkillAuthorizationReadiness,
    SkillCreateRequest,
    SkillDraftCreateRequest,
    SkillDraftIntent,
    SkillManager,
    SkillRuntimeRequestResolutionContext,
    SkillRuntimeRequestResolver,
)
from crxzipple.modules.skills.application.events import (
    SKILL_DRAFT_APPLY_FAILED_EVENT,
    SKILL_DRAFT_CREATED_EVENT,
    SKILL_DRAFT_DELETED_EVENT,
    SKILL_DRAFT_DIFF_BUILT_EVENT,
    SKILL_DRAFT_REJECTED_EVENT,
    SKILL_DRAFT_VALIDATED_EVENT,
)
from crxzipple.modules.skills.domain import SkillReadinessSnapshot, SkillRequirements
from crxzipple.modules.skills.domain import (
    SkillEnablementPolicy,
    SkillEnablementTargetKind,
    SkillInstallScope,
    SkillRuntimeVisibility,
)
from crxzipple.modules.skills.infrastructure.filesystem import (
    FilesystemSkillRepository,
    FilesystemSkillSourceRoot,
)
from crxzipple.modules.skills.domain import SkillNotFoundError, SkillValidationError
from tests.unit.skill_test_support import write_skill_package as _write_skill_package


class _FakeSkillAccessPort:
    def __init__(self, ready_requirements: tuple[str, ...]) -> None:
        self.ready_requirements = set(ready_requirements)

    def check_requirements(
        self,
        requirements: tuple[str, ...],
        *,
        workspace_dir: str | None = None,
    ) -> tuple[SkillAccessRequirementReadiness, ...]:
        return tuple(
            SkillAccessRequirementReadiness(
                requirement=requirement,
                ready=requirement in self.ready_requirements,
                status="ready" if requirement in self.ready_requirements else "setup_needed",
                reason=None if requirement in self.ready_requirements else "missing",
            )
            for requirement in requirements
        )


class _FakeSkillToolReadinessPort:
    def __init__(self, available_tool_ids: tuple[str, ...]) -> None:
        self.available_tool_ids = available_tool_ids

    def list_available_tool_ids(self) -> tuple[str, ...]:
        return self.available_tool_ids


class _FakeSkillAuthorizationPort:
    def __init__(self, ready_effects: tuple[str, ...]) -> None:
        self.ready_effects = set(ready_effects)

    def check_required_effects(
        self,
        *,
        skill,
        effect_ids: tuple[str, ...],
        context,
    ) -> SkillAuthorizationReadiness:
        missing = tuple(effect for effect in effect_ids if effect not in self.ready_effects)
        return SkillAuthorizationReadiness(
            ready=not missing,
            status="ready" if not missing else "setup_needed",
            missing_effects=missing,
            reason=None if not missing else "missing effect grant",
        )


class _FakeOwnerCatalogRepository:
    def __init__(self) -> None:
        self.readiness: dict[str, SkillReadinessSnapshot] = {}
        self.drafts: dict[str, object] = {}
        self.draft_audits: dict[str, list[object]] = {}
        self.policies: dict[str, SkillEnablementPolicy] = {}

    def get_readiness(self, skill_id: str) -> SkillReadinessSnapshot | None:
        return self.readiness.get(skill_id)

    def get_enablement_policy(self, policy_id: str):
        return self.policies.get(policy_id)

    def upsert_enablement_policy(self, policy: SkillEnablementPolicy):
        self.policies[policy.policy_id] = policy
        return policy

    def upsert_readiness(
        self,
        snapshot: SkillReadinessSnapshot,
    ) -> SkillReadinessSnapshot:
        self.readiness[snapshot.skill_id] = snapshot
        return snapshot

    def save_draft(self, draft):
        self.drafts[draft.draft_id] = draft
        return draft

    def get_draft(self, draft_id: str):
        return self.drafts.get(draft_id)

    def list_drafts(
        self,
        *,
        status: str | None = None,
        skill_name: str | None = None,
        run_id: str | None = None,
        workspace_dir: str | None = None,
        limit: int = 100,
    ):
        now = datetime.now(timezone.utc)
        items = []
        for draft in self.drafts.values():
            if status is not None and draft.status.value != status:
                continue
            if status is None and draft.expires_at is not None and draft.expires_at <= now:
                continue
            if skill_name is not None and draft.skill_name != skill_name:
                continue
            if run_id is not None and draft.created_by_run_id != run_id:
                continue
            if workspace_dir is not None and draft.workspace_dir != workspace_dir:
                continue
            items.append(draft)
        return tuple(items)[:limit]

    def delete_draft(self, draft_id: str) -> bool:
        return self.drafts.pop(draft_id, None) is not None

    def append_draft_audit(self, record):
        self.draft_audits.setdefault(record.draft_id, []).append(record)
        return record

    def list_draft_audit(
        self,
        *,
        draft_id: str,
        limit: int = 100,
    ):
        return tuple(reversed(self.draft_audits.get(draft_id, ())))[:limit]


class SkillsContextTestCase(unittest.TestCase):
    def test_manager_builds_runtime_request_catalog_from_available_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            workspace.mkdir()
            _write_skill_package(
                workspace / ".crxzipple" / "skills" / "repo-review",
                name="repo-review",
                description="Review repository changes carefully.",
                instructions="# Repo Review\n\nReview repository changes carefully.\n",
                version="1.2.3",
                tags=("review",),
                allowed_tools=("git_status", "git_diff"),
            )
            manager = SkillManager(
                repository=FilesystemSkillRepository(
                    global_root=root / "global",
                    system_root=root / "system",
                ),
            )

            catalog = manager.build_runtime_request_catalog(
                workspace_dir=str(workspace),
                surface="interactive",
            )

            self.assertIsNotNone(catalog)
            assert catalog is not None
            self.assertIn("# Available Skills", catalog.content)
            self.assertIn("repo-review", catalog.content)
            self.assertEqual(catalog.metadata["count"], 1)
            self.assertEqual(catalog.metadata["available_skill_names"], ["repo-review"])
            self.assertEqual(catalog.metadata["skills"][0]["name"], "repo-review")
            self.assertNotIn("allowed_tools", catalog.metadata["skills"][0])
            self.assertNotIn("suggested_tools", catalog.metadata["skills"][0])
            self.assertNotIn("required_tools", catalog.metadata["skills"][0])
            self.assertEqual(
                catalog.metadata["skills"][0]["requirements"]["suggested_tools"],
                ["git_status", "git_diff"],
            )

    def test_runtime_request_catalog_projects_normalized_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            skill_root = system_root / "repo-review"
            skill_root.mkdir(parents=True)
            (skill_root / "SKILL.md").write_text(
                "---\n"
                "name: repo-review\n"
                "description: Review repository changes carefully.\n"
                "required_tools: [git_diff]\n"
                "suggested_tools: [git_diff, github_pr_read]\n"
                "required_effects: [network]\n"
                "required_access:\n"
                "  - provider: github\n"
                "    kind: oauth_connector\n"
                "    scopes: [repo_read]\n"
                "  - github-review-binding\n"
                "---\n"
                "# Repo Review\n",
                encoding="utf-8",
            )
            manager = SkillManager(
                repository=FilesystemSkillRepository(
                    global_root=root / "global",
                    system_root=system_root,
                ),
            )

            catalog = manager.build_runtime_request_catalog(workspace_dir=None, surface=None)

            self.assertIsNotNone(catalog)
            assert catalog is not None
            self.assertIn("requires effects: network", catalog.content)
            skill_metadata = catalog.metadata["skills"][0]
            self.assertNotIn("required_effects", skill_metadata)
            self.assertNotIn("required_auth", skill_metadata)
            self.assertNotIn("required_secrets", skill_metadata)
            self.assertNotIn("required_credential_files", skill_metadata)
            self.assertEqual(
                skill_metadata["requirements"]["required_effects"],
                ["network"],
            )
            self.assertEqual(
                skill_metadata["requirements"]["required_access"],
                ["github:oauth_connector(repo_read)", "github-review-binding"],
            )

    def test_repository_rejects_direct_secret_and_file_skill_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            skill_root = system_root / "repo-review"
            skill_root.mkdir(parents=True)
            (skill_root / "SKILL.md").write_text(
                "---\n"
                "name: repo-review\n"
                "description: Review repository changes carefully.\n"
                "required_tools: [git_diff]\n"
                "required_access: [env:GITHUB_TOKEN]\n"
                "---\n"
                "# Repo Review\n",
                encoding="utf-8",
            )
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=system_root,
            )

            with self.assertRaisesRegex(
                SkillValidationError,
                "required_access must reference Access bindings",
            ):
                repository.validate(path=str(skill_root))

            (skill_root / "SKILL.md").write_text(
                "---\n"
                "name: repo-review\n"
                "description: Review repository changes carefully.\n"
                "required_tools: [file:/tmp/token]\n"
                "---\n"
                "# Repo Review\n",
                encoding="utf-8",
            )
            with self.assertRaisesRegex(
                SkillValidationError,
                "required_tools must reference ToolFunction ids",
            ):
                repository.validate(path=str(skill_root))

    def test_repository_rejects_retired_skill_access_frontmatter_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            skill_root = system_root / "repo-review"
            skill_root.mkdir(parents=True)
            (skill_root / "SKILL.md").write_text(
                "---\n"
                "name: repo-review\n"
                "description: Review repository changes carefully.\n"
                "required_secrets: [GITHUB_TOKEN]\n"
                "---\n"
                "# Repo Review\n",
                encoding="utf-8",
            )
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=system_root,
            )

            with self.assertRaisesRegex(
                SkillValidationError,
                "retired access fields",
            ):
                repository.validate(path=str(skill_root))

    def test_runtime_request_catalog_stays_summary_only_until_skill_read(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            skill_root = system_root / "release-ops"
            references = skill_root / "references"
            references.mkdir(parents=True)
            (skill_root / "SKILL.md").write_text(
                "---\n"
                "name: release-ops\n"
                "description: Coordinate release verification.\n"
                "when_to_use: Release planning and verification work.\n"
                "---\n"
                "# Release Ops\n\n"
                "FULL_INSTRUCTION_SENTINEL: read the release checklist carefully.\n",
                encoding="utf-8",
            )
            (references / "checklist.md").write_text(
                "RESOURCE_BODY_SENTINEL: private checklist details.\n",
                encoding="utf-8",
            )
            manager = SkillManager(
                repository=FilesystemSkillRepository(
                    global_root=root / "global",
                    system_root=system_root,
                ),
            )

            catalog = manager.build_runtime_request_catalog(workspace_dir=None, surface="")
            read_result = manager.read(
                workspace_dir=None,
                skill_name="release-ops",
                path=None,
                surface="",
            )

            self.assertIsNotNone(catalog)
            assert catalog is not None
            self.assertIn("release-ops", catalog.content)
            self.assertIn("references/checklist.md", catalog.content)
            self.assertNotIn("FULL_INSTRUCTION_SENTINEL", catalog.content)
            self.assertNotIn("RESOURCE_BODY_SENTINEL", catalog.content)
            self.assertIn("FULL_INSTRUCTION_SENTINEL", read_result.content)

    def test_manager_filters_skills_by_declared_surface(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            skill_root = system_root / "web-only"
            skill_root.mkdir(parents=True)
            (skill_root / "SKILL.md").write_text(
                "---\n"
                "name: web-only\n"
                "description: Only available on the web surface.\n"
                "surfaces: [web]\n"
                "---\n"
                "# Web Only\n",
                encoding="utf-8",
            )
            chat_skill_root = system_root / "chat-skill"
            chat_skill_root.mkdir(parents=True)
            (chat_skill_root / "SKILL.md").write_text(
                "---\n"
                "name: chat-skill\n"
                "description: Available on the interactive chat surface.\n"
                "surfaces: [chat]\n"
                "---\n"
                "# Chat Skill\n",
                encoding="utf-8",
            )
            manager = SkillManager(
                repository=FilesystemSkillRepository(
                    global_root=root / "global",
                    system_root=system_root,
                ),
            )

            self.assertEqual(
                [skill.name for skill in manager.list_available(workspace_dir=None, surface="web")],
                ["web-only"],
            )
            self.assertEqual(
                [skill.name for skill in manager.list_available(workspace_dir=None, surface="interactive")],
                ["chat-skill"],
            )
            with self.assertRaises(SkillNotFoundError):
                manager.read(
                    workspace_dir=None,
                    skill_name="web-only",
                    path=None,
                    surface="interactive",
                )
            self.assertEqual(
                manager.read(
                    workspace_dir=None,
                    skill_name="chat-skill",
                    path=None,
                    surface="interactive",
                ).package.name,
                "chat-skill",
            )

    def test_runtime_request_resolver_blocks_unsupported_platform(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            _write_skill_package(
                system_root / "mac-only",
                name="mac-only",
                description="Only available on macOS.",
                instructions="# Mac Only\n",
                supported_platforms=("macos",),
            )
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=system_root,
            )
            package = repository.get(workspace_dir=None, skill_name="mac-only")

            resolution = SkillRuntimeRequestResolver().resolve(
                (package,),
                available_tool_ids=(),
                context=SkillRuntimeRequestResolutionContext(
                    surface="interactive",
                    platform="linux",
                ),
            )

            self.assertFalse(resolution.skills[0].ready)
            self.assertEqual(resolution.skills[0].readiness.status, "unsupported")
            self.assertEqual(
                resolution.skills[0].readiness.unsupported_platforms,
                ("linux",),
            )
            self.assertEqual(resolution.ready_skills, ())

    def test_resolved_runtime_request_catalog_blocks_missing_access_and_effects(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            skill_root = system_root / "repo-review"
            skill_root.mkdir(parents=True)
            (skill_root / "SKILL.md").write_text(
                "---\n"
                "name: repo-review\n"
                "description: Review repository changes carefully.\n"
                "required_tools: [git_diff]\n"
                "required_effects: [network]\n"
                "required_access:\n"
                "  - provider: github\n"
                "    kind: oauth_connector\n"
                "    scopes: [repo_read]\n"
                "  - github-review-binding\n"
                "---\n"
                "# Repo Review\n",
                encoding="utf-8",
            )
            manager = SkillManager(
                repository=FilesystemSkillRepository(
                    global_root=root / "global",
                    system_root=system_root,
                ),
                runtime_request_resolver=SkillRuntimeRequestResolver(
                    access_port=_FakeSkillAccessPort(
                        (
                            "github:oauth_connector(repo_read)",
                        ),
                    ),
                    authorization_port=_FakeSkillAuthorizationPort(()),
                ),
            )

            resolution = manager.resolve_runtime_request_catalog(
                workspace_dir=None,
                surface="interactive",
                available_tool_ids=("git_diff",),
                agent_id="assistant",
                run_id="run-1",
            )

            readiness = resolution.skills[0].readiness
            self.assertFalse(readiness.ready)
            self.assertEqual(
                readiness.missing_access,
                ("github-review-binding",),
            )
            self.assertEqual(readiness.missing_effects, ("network",))
            self.assertIsNotNone(resolution.runtime_request_catalog)
            assert resolution.runtime_request_catalog is not None
            self.assertEqual(
                resolution.runtime_request_catalog.metadata["available_skill_names"],
                [],
            )

    def test_resolved_runtime_request_catalog_allows_ready_runtime_requirements(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            skill_root = system_root / "repo-review"
            skill_root.mkdir(parents=True)
            (skill_root / "SKILL.md").write_text(
                "---\n"
                "name: repo-review\n"
                "description: Review repository changes carefully.\n"
                "required_tools: [git_diff]\n"
                "required_effects: [network]\n"
                "required_access:\n"
                "  - provider: github\n"
                "    kind: oauth_connector\n"
                "    scopes: [repo_read]\n"
                "  - github-review-binding\n"
                "---\n"
                "# Repo Review\n",
                encoding="utf-8",
            )
            manager = SkillManager(
                repository=FilesystemSkillRepository(
                    global_root=root / "global",
                    system_root=system_root,
                ),
                runtime_request_resolver=SkillRuntimeRequestResolver(
                    access_port=_FakeSkillAccessPort(
                        (
                            "github:oauth_connector(repo_read)",
                            "github-review-binding",
                        ),
                    ),
                    authorization_port=_FakeSkillAuthorizationPort(("network",)),
                ),
            )

            resolution = manager.resolve_runtime_request_catalog(
                workspace_dir=None,
                surface="interactive",
                available_tool_ids=("git_diff",),
                interface="cli",
                agent_id="assistant",
                run_id="run-1",
            )

            self.assertTrue(resolution.skills[0].ready)
            self.assertEqual(resolution.ready_skills[0].name, "repo-review")

    def test_runtime_request_catalog_honors_source_runtime_visibility_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            _write_skill_package(
                system_root / "repo-review",
                name="repo-review",
                description="Review repository changes carefully.",
                instructions="# Repo Review\n",
            )
            owner_repository = _FakeOwnerCatalogRepository()
            owner_repository.upsert_enablement_policy(
                SkillEnablementPolicy(
                    policy_id="source:system:enablement",
                    target_kind=SkillEnablementTargetKind.SOURCE,
                    target_id="system",
                    enabled=True,
                    trusted=False,
                    runtime_visibility=SkillRuntimeVisibility.HIDDEN,
                ),
            )
            manager = SkillManager(
                repository=FilesystemSkillRepository(
                    global_root=root / "global",
                    system_root=system_root,
                ),
                owner_catalog_repository=owner_repository,
            )

            visible_catalog = manager.build_runtime_request_catalog(
                workspace_dir=None,
                surface="interactive",
            )
            resolution = manager.resolve_runtime_request_catalog(
                workspace_dir=None,
                surface="interactive",
                available_tool_ids=(),
            )

            self.assertIsNone(visible_catalog)
            self.assertEqual(resolution.skills, ())
            self.assertEqual(
                [package.name for package in manager.list_available(
                    workspace_dir=None,
                    surface="interactive",
                    include_disabled=True,
                )],
                ["repo-review"],
            )

    def test_runtime_request_catalog_honors_skill_runtime_visibility_policy(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            _write_skill_package(
                system_root / "repo-review",
                name="repo-review",
                description="Review repository changes carefully.",
                instructions="# Repo Review\n",
            )
            owner_repository = _FakeOwnerCatalogRepository()
            owner_repository.upsert_enablement_policy(
                SkillEnablementPolicy(
                    policy_id="skill:repo-review:enablement",
                    target_kind=SkillEnablementTargetKind.SKILL,
                    target_id="repo-review",
                    enabled=True,
                    trusted=False,
                    runtime_visibility=SkillRuntimeVisibility.HIDDEN,
                ),
            )
            manager = SkillManager(
                repository=FilesystemSkillRepository(
                    global_root=root / "global",
                    system_root=system_root,
                ),
                owner_catalog_repository=owner_repository,
            )

            visible_catalog = manager.build_runtime_request_catalog(
                workspace_dir=None,
                surface="interactive",
            )
            resolution = manager.resolve_runtime_request_catalog(
                workspace_dir=None,
                surface="interactive",
                available_tool_ids=(),
            )

            self.assertIsNone(visible_catalog)
            self.assertEqual(resolution.skills, ())

    def test_owner_readiness_uses_runtime_tool_catalog(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            _write_skill_package(
                system_root / "skill-authoring",
                name="skill-authoring",
                description="Author skills through governed drafts.",
                instructions="# Skill Authoring\n",
                required_tools=("skill_draft_create", "skill_draft_validate"),
            )
            manager = SkillManager(
                repository=FilesystemSkillRepository(
                    global_root=root / "global",
                    system_root=system_root,
                ),
                owner_catalog_repository=_FakeOwnerCatalogRepository(),
            )
            manager.configure_runtime_readiness(
                tool_readiness_port=_FakeSkillToolReadinessPort(
                    ("skill_draft_create", "skill_draft_validate"),
                ),
            )

            readiness = manager.readiness(
                workspace_dir=None,
                skill_name="skill-authoring",
                surface="interactive",
            )["skill-authoring"]

            self.assertTrue(readiness.ready)
            self.assertEqual(readiness.missing_tools, ())
            snapshot = manager.owner_catalog_repository.readiness["skill-authoring"]
            self.assertEqual(snapshot.status.value, "ready")
            self.assertEqual(
                [check["ok"] for check in snapshot.checks if check["kind"] == "tool"],
                [True, True],
            )

    def test_draft_validation_uses_runtime_requirement_ports(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            manager = SkillManager(
                repository=FilesystemSkillRepository(
                    global_root=root / "global",
                    system_root=root / "system",
                ),
                owner_catalog_repository=_FakeOwnerCatalogRepository(),
                runtime_request_resolver=SkillRuntimeRequestResolver(
                    access_port=_FakeSkillAccessPort(("github-ready",)),
                    authorization_port=_FakeSkillAuthorizationPort(()),
                ),
            )
            manager.configure_runtime_readiness(
                tool_readiness_port=_FakeSkillToolReadinessPort(("git_diff",)),
            )
            draft = manager.create_draft(
                SkillDraftCreateRequest(
                    intent=SkillDraftIntent.CREATE,
                    skill_name="repo-review",
                    manifest={
                        "name": "repo-review",
                        "description": "Review repository changes.",
                    },
                    instructions_body="# Repo Review\n\nReview the diff.",
                    requirements=SkillRequirements(
                        required_tools=("git_diff",),
                        required_access=("github-ready", "github-missing"),
                        required_effects=("network",),
                    ),
                ),
            )

            validated = manager.validate_draft(draft.draft_id)

            assert validated.validation is not None
            self.assertEqual(validated.validation.missing_tools, ())
            self.assertEqual(
                validated.validation.missing_access,
                ("github-missing",),
            )
            self.assertEqual(validated.validation.missing_effects, ("network",))
            self.assertEqual(validated.validation.readiness_status, "setup_needed")

    def test_authoring_draft_lifecycle_emits_operation_events(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            events: list[tuple[str, dict[str, object]]] = []
            manager = SkillManager(
                repository=FilesystemSkillRepository(
                    global_root=root / "global",
                    system_root=root / "system",
                ),
                owner_catalog_repository=_FakeOwnerCatalogRepository(),
                event_emitter=lambda name, payload: events.append((name, payload)),
            )
            manager.configure_runtime_readiness(
                tool_readiness_port=_FakeSkillToolReadinessPort(("git_diff",)),
            )

            draft = manager.create_draft(
                SkillDraftCreateRequest(
                    intent=SkillDraftIntent.CREATE,
                    skill_name="repo-review",
                    manifest={
                        "name": "repo-review",
                        "description": "Review repository changes.",
                    },
                    instructions_body="# Repo Review\n\nReview the diff.",
                    requirements=SkillRequirements(required_tools=("git_diff",)),
                    created_by_run_id="run-1",
                    created_by_turn_id="turn-1",
                    actor="assistant",
                    reason="capture workflow",
                ),
            )
            manager.validate_draft(draft.draft_id)
            manager.build_draft_diff(draft.draft_id)
            manager.reject_draft(draft_id=draft.draft_id, reason="not yet")
            manager.delete_draft(draft.draft_id)

            audit_actions = [
                record.action
                for record in reversed(manager.list_draft_audit(draft_id=draft.draft_id))
            ]
            self.assertEqual(
                audit_actions,
                ["create", "validate", "diff", "reject", "delete"],
            )

            event_names = [name for name, _payload in events]
            self.assertEqual(
                event_names,
                [
                    SKILL_DRAFT_CREATED_EVENT,
                    SKILL_DRAFT_VALIDATED_EVENT,
                    SKILL_DRAFT_DIFF_BUILT_EVENT,
                    SKILL_DRAFT_REJECTED_EVENT,
                    SKILL_DRAFT_DELETED_EVENT,
                ],
            )
            validated_event = events[1][1]
            self.assertEqual(validated_event["draft_id"], draft.draft_id)
            self.assertEqual(validated_event["skill"], "repo-review")
            self.assertEqual(validated_event["run_id"], "run-1")
            self.assertEqual(validated_event["missing_tools"], [])
            self.assertEqual(validated_event["readiness_status"], "ready")
            diff_event = events[2][1]
            self.assertIn("Create skill 'repo-review'", diff_event["diff_summary"])

    def test_authoring_draft_list_excludes_expired_active_drafts_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            manager = SkillManager(
                repository=FilesystemSkillRepository(
                    global_root=root / "global",
                    system_root=root / "system",
                ),
                owner_catalog_repository=_FakeOwnerCatalogRepository(),
            )

            expired = manager.create_draft(
                SkillDraftCreateRequest(
                    intent=SkillDraftIntent.CREATE,
                    skill_name="expired-skill",
                    manifest={
                        "name": "expired-skill",
                        "description": "Expired draft.",
                    },
                    instructions_body="# Expired\n",
                    expires_at=datetime.now(timezone.utc) - timedelta(days=1),
                ),
            )
            active = manager.create_draft(
                SkillDraftCreateRequest(
                    intent=SkillDraftIntent.CREATE,
                    skill_name="active-skill",
                    manifest={
                        "name": "active-skill",
                        "description": "Active draft.",
                    },
                    instructions_body="# Active\n",
                ),
            )

            self.assertEqual(
                [draft.draft_id for draft in manager.list_drafts()],
                [active.draft_id],
            )
            self.assertEqual(
                [draft.draft_id for draft in manager.list_drafts(status="draft")],
                [expired.draft_id, active.draft_id],
            )

    def test_apply_draft_rejects_readonly_system_source(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            events: list[tuple[str, dict[str, object]]] = []
            manager = SkillManager(
                repository=FilesystemSkillRepository(
                    global_root=root / "global",
                    system_root=root / "system",
                ),
                owner_catalog_repository=_FakeOwnerCatalogRepository(),
                event_emitter=lambda name, payload: events.append((name, payload)),
            )
            manager.configure_runtime_readiness(
                tool_readiness_port=_FakeSkillToolReadinessPort(()),
            )
            draft = manager.create_draft(
                SkillDraftCreateRequest(
                    intent=SkillDraftIntent.CREATE,
                    skill_name="system-write",
                    target_source_id="system",
                    manifest={
                        "name": "system-write",
                        "description": "Attempt to write a system skill.",
                    },
                    instructions_body="# System Write\n\nShould not apply.",
                ),
            )

            with self.assertRaisesRegex(
                SkillValidationError,
                "System skill source is readonly",
            ):
                manager.apply_draft(draft_id=draft.draft_id)
            self.assertEqual(events[-1][0], SKILL_DRAFT_APPLY_FAILED_EVENT)
            self.assertEqual(events[-1][1]["draft_id"], draft.draft_id)
            self.assertEqual(events[-1][1]["status"], "failed")

    def test_resolved_runtime_request_catalog_uses_authorization_effect_grants(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            skill_root = system_root / "repo-review"
            skill_root.mkdir(parents=True)
            (skill_root / "SKILL.md").write_text(
                "---\n"
                "name: repo-review\n"
                "description: Review repository changes carefully.\n"
                "required_effects: [network]\n"
                "---\n"
                "# Repo Review\n",
                encoding="utf-8",
            )
            auth_service = AuthorizationApplicationService(
                policy_repository=InMemoryAuthorizationPolicyRepository(),
                evaluator=AbacAuthorizationEvaluator(),
                enabled=True,
            )
            manager = SkillManager(
                repository=FilesystemSkillRepository(
                    global_root=root / "global",
                    system_root=system_root,
                ),
                runtime_request_resolver=SkillRuntimeRequestResolver(
                    authorization_port=SkillAuthorizationServiceAdapter(
                        auth_service,
                    ),
                ),
            )

            blocked = manager.resolve_runtime_request_catalog(
                workspace_dir=None,
                surface="interactive",
                available_tool_ids=(),
                interface="cli",
                agent_id="assistant",
                run_id="run-1",
            )
            self.assertEqual(blocked.skills[0].readiness.missing_effects, ("network",))

            auth_service.grant_agent_effect_authorization(
                agent_id="assistant",
                effect_id="network",
            )
            allowed = manager.resolve_runtime_request_catalog(
                workspace_dir=None,
                surface="interactive",
                available_tool_ids=(),
                interface="cli",
                agent_id="assistant",
                run_id="run-2",
            )

            self.assertTrue(allowed.skills[0].ready)
            self.assertEqual(allowed.ready_skills[0].name, "repo-review")

    def test_resolved_runtime_request_catalog_persists_readiness_changed_events(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            _write_skill_package(
                system_root / "repo-review",
                name="repo-review",
                description="Review repository changes carefully.",
                instructions="# Repo Review\n",
                required_tools=("git_diff",),
            )
            owner_repository = _FakeOwnerCatalogRepository()
            events: list[tuple[str, dict[str, object]]] = []
            manager = SkillManager(
                repository=FilesystemSkillRepository(
                    global_root=root / "global",
                    system_root=system_root,
                ),
                owner_catalog_repository=owner_repository,
                event_emitter=lambda name, payload: events.append((name, payload)),
            )

            blocked = manager.resolve_runtime_request_catalog(
                workspace_dir=None,
                surface="interactive",
                available_tool_ids=(),
                interface="cli",
                agent_id="assistant",
                run_id="run-blocked",
            )
            repeated = manager.resolve_runtime_request_catalog(
                workspace_dir=None,
                surface="interactive",
                available_tool_ids=(),
                interface="cli",
                agent_id="assistant",
                run_id="run-repeated",
            )
            ready = manager.resolve_runtime_request_catalog(
                workspace_dir=None,
                surface="interactive",
                available_tool_ids=("git_diff",),
                interface="cli",
                agent_id="assistant",
                run_id="run-ready",
            )

            self.assertFalse(blocked.skills[0].ready)
            self.assertFalse(repeated.skills[0].ready)
            self.assertTrue(ready.skills[0].ready)
            readiness_events = [
                payload
                for name, payload in events
                if name == "skills.readiness.changed"
            ]
            self.assertEqual(len(readiness_events), 2)
            self.assertEqual(readiness_events[0]["status"], "setup_needed")
            self.assertEqual(readiness_events[0]["missing_tools"], ["git_diff"])
            self.assertEqual(readiness_events[1]["status"], "ready")
            self.assertEqual(
                owner_repository.readiness["repo-review"].status.value,
                "ready",
            )

    def test_catalog_readiness_publishes_changed_event_once(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            _write_skill_package(
                system_root / "repo-review",
                name="repo-review",
                description="Review repository changes carefully.",
                instructions="# Repo Review\n\nReview repository changes carefully.\n",
                required_tools=("git_diff",),
            )
            owner_repository = _FakeOwnerCatalogRepository()
            events: list[tuple[str, dict[str, object]]] = []
            manager = SkillManager(
                repository=FilesystemSkillRepository(
                    global_root=root / "global",
                    system_root=system_root,
                ),
                owner_catalog_repository=owner_repository,
                event_emitter=lambda name, payload: events.append((name, payload)),
            )

            first = manager.readiness(
                workspace_dir=None,
                skill_name="repo-review",
                surface="interactive",
            )
            repeated = manager.readiness(
                workspace_dir=None,
                skill_name="repo-review",
                surface="interactive",
            )

            readiness_events = [
                payload
                for name, payload in events
                if name == "skills.readiness.changed"
            ]
            self.assertFalse(first["repo-review"].ready)
            self.assertFalse(repeated["repo-review"].ready)
            self.assertEqual(len(readiness_events), 1)
            self.assertEqual(readiness_events[0]["status"], "setup_needed")
            self.assertEqual(readiness_events[0]["missing_tools"], ["git_diff"])
            self.assertEqual(readiness_events[0]["readiness_scope"], "catalog")

    def test_repository_returns_empty_when_no_roots_exist(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            missing = Path(tempdir) / "missing"
            repository = FilesystemSkillRepository(
                global_root=missing,
                system_root=missing,
            )

            self.assertEqual(
                repository.list_available(workspace_dir=None),
                (),
            )

    def test_repository_discovers_workspace_global_and_system_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            global_root = root / "global"
            system_root = root / "system"
            _write_skill_package(
                workspace / ".crxzipple" / "skills" / "repo-review",
                name="repo-review",
                description="Review repository changes carefully.",
                instructions="# Repo Review\n\nReview repository changes carefully.\n",
            )
            _write_skill_package(
                global_root / "daily-brief",
                name="daily-brief",
                description="Summarize the day in one concise brief.",
                instructions="# Daily Brief\n\nSummarize the day.\n",
            )
            _write_skill_package(
                system_root / "openai-docs",
                name="openai-docs",
                description="Use official OpenAI documentation for current answers.",
                instructions="# OpenAI Docs\n\nUse official docs.\n",
            )
            repository = FilesystemSkillRepository(
                global_root=global_root,
                system_root=system_root,
            )

            skills = repository.list_available(workspace_dir=str(workspace))

            self.assertEqual(
                [skill.name for skill in skills],
                ["daily-brief", "openai-docs", "repo-review"],
            )
            self.assertEqual(
                [skill.source for skill in skills],
                ["global", "system", "workspace"],
            )
            self.assertEqual(
                skills[2].instructions_path,
                str(
                    (workspace / ".crxzipple" / "skills" / "repo-review" / "SKILL.md").resolve(),
                ),
            )

    def test_repository_source_precedence_prefers_workspace_global_custom_system(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            global_root = root / "global"
            custom_root = root / "custom"
            system_root = root / "system"
            for source_root, marker in (
                (workspace / ".crxzipple" / "skills", "workspace"),
                (global_root, "global"),
                (custom_root, "custom"),
                (system_root, "system"),
            ):
                _write_skill_package(
                    source_root / "shared-skill",
                    name="shared-skill",
                    description=f"{marker} copy.",
                    instructions=f"# Shared\n\n{marker}\n",
                )
            repository = FilesystemSkillRepository(
                global_root=global_root,
                system_root=system_root,
                source_provider=lambda: (
                    FilesystemSkillSourceRoot(
                        source_id="custom",
                        root_path=str(custom_root),
                    ),
                ),
            )

            workspace_skill = repository.get(
                workspace_dir=str(workspace),
                skill_name="shared-skill",
            )
            global_skill = repository.get(
                workspace_dir=None,
                skill_name="shared-skill",
            )
            fallback_repository = FilesystemSkillRepository(
                global_root=root / "missing-global",
                system_root=system_root,
                source_provider=lambda: (
                    FilesystemSkillSourceRoot(
                        source_id="custom",
                        root_path=str(custom_root),
                    ),
                ),
            )
            custom_skill = fallback_repository.get(
                workspace_dir=None,
                skill_name="shared-skill",
            )

            self.assertEqual(workspace_skill.source, "workspace")
            self.assertEqual(global_skill.source, "global")
            self.assertEqual(custom_skill.source, "custom")

    def test_repository_parses_manifest_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            _write_skill_package(
                system_root / "memory-recall",
                name="memory-recall",
                description="Recall durable memory before answering.",
                version="1",
                tags=("memory", "recall"),
                required_tools=("memory_search",),
                allowed_tools=("memory_search", "memory_read", "memory_write_daily"),
                instructions="# Memory Recall\n\nUse durable memory.\n",
            )
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=system_root,
            )

            skills = repository.list_available(workspace_dir=None)

            self.assertEqual(len(skills), 1)
            self.assertEqual(skills[0].name, "memory-recall")
            self.assertEqual(
                skills[0].description,
                "Recall durable memory before answering.",
            )
            self.assertEqual(skills[0].version, "1")
            self.assertEqual(skills[0].tags, ("memory", "recall"))
            self.assertEqual(skills[0].required_tools, ("memory_search",))
            self.assertEqual(
                skills[0].allowed_tools,
                ("memory_search", "memory_read", "memory_write_daily"),
            )
            self.assertEqual(
                skills[0].requirements.suggested_tools,
                ("memory_search", "memory_read", "memory_write_daily"),
            )

    def test_repository_fingerprint_changes_when_skill_content_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            skill_root = system_root / "release-ops"
            _write_skill_package(
                skill_root,
                name="release-ops",
                description="Prepare and validate releases.",
                instructions="# Release Ops\n\nFollow the release checklist.\n",
            )
            references = skill_root / "references"
            references.mkdir()
            checklist = references / "checklist.md"
            checklist.write_text("- cut branch\n", encoding="utf-8")
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=system_root,
            )

            first = repository.get(workspace_dir=None, skill_name="release-ops")
            checklist.write_text("- cut branch\n- run smoke tests\n", encoding="utf-8")
            second = repository.get(workspace_dir=None, skill_name="release-ops")
            (skill_root / "SKILL.md").write_text(
                (skill_root / "SKILL.md").read_text(encoding="utf-8")
                + "\nExtra instruction.\n",
                encoding="utf-8",
            )
            third = repository.get(workspace_dir=None, skill_name="release-ops")

            self.assertTrue(first.fingerprint.startswith("sha256:"))
            self.assertNotEqual(first.fingerprint, second.fingerprint)
            self.assertNotEqual(second.fingerprint, third.fingerprint)

    def test_repository_ignores_resource_symlinks_that_escape_package_root(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            skill_root = system_root / "release-ops"
            _write_skill_package(
                skill_root,
                name="release-ops",
                description="Prepare and validate releases.",
                instructions="# Release Ops\n\nFollow the release checklist.\n",
            )
            outside = system_root / "outside.md"
            outside.write_text("outside package\n", encoding="utf-8")
            references = skill_root / "references"
            references.mkdir()
            (references / "outside.md").symlink_to(outside)
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=system_root,
            )

            skill = repository.get(workspace_dir=None, skill_name="release-ops")

            self.assertEqual(skill.resources, ())

    def test_repository_discovers_skill_md_frontmatter_without_sidecar(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            skill_root = system_root / "github-review"
            skill_root.mkdir(parents=True)
            (skill_root / "SKILL.md").write_text(
                "---\n"
                "name: github-review\n"
                "description: Review GitHub pull requests with repository context.\n"
                "version: 2\n"
                "tags: [github, review]\n"
                "when_to_use: When a pull request needs code-review feedback.\n"
                "required_tools: [github_pr_read]\n"
                "suggested_tools: [github_pr_read, git_diff]\n"
                "required_access:\n"
                "  - provider: github\n"
                "    kind: oauth_connector\n"
                "    scopes: [repo_read]\n"
                "surfaces: [interactive]\n"
                "---\n"
                "# GitHub Review\n\n"
                "Review pull requests carefully.\n",
                encoding="utf-8",
            )
            references_root = skill_root / "references"
            references_root.mkdir()
            (references_root / "rubric.md").write_text(
                "# Rubric\n\nCheck correctness first.\n",
                encoding="utf-8",
            )
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=system_root,
            )

            skills = repository.list_available(workspace_dir=None)
            loaded = repository.read(
                workspace_dir=None,
                skill_name="github-review",
                path=None,
            )

            self.assertEqual(len(skills), 1)
            self.assertEqual(skills[0].manifest_path, str((skill_root / "SKILL.md").resolve()))
            self.assertEqual(skills[0].name, "github-review")
            self.assertEqual(skills[0].version, "2")
            self.assertEqual(skills[0].tags, ("github", "review"))
            self.assertEqual(skills[0].manifest.when_to_use, "When a pull request needs code-review feedback.")
            self.assertEqual(skills[0].required_tools, ("github_pr_read",))
            self.assertEqual(skills[0].suggested_tools, ("github_pr_read", "git_diff"))
            self.assertEqual(
                skills[0].requirements.required_tools,
                ("github_pr_read",),
            )
            self.assertEqual(
                skills[0].requirements.required_access,
                ("github:oauth_connector(repo_read)",),
            )
            self.assertEqual(skills[0].manifest.required_access, ("github:oauth_connector(repo_read)",))
            self.assertEqual(skills[0].manifest.surfaces, ("interactive",))
            self.assertEqual(skills[0].resources[0].path, "references/rubric.md")
            self.assertNotIn("name: github-review", loaded.content)
            self.assertIn("Review pull requests carefully", loaded.content)

    def test_skill_md_frontmatter_is_self_contained_and_ignores_legacy_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            skill_root = system_root / "review"
            _write_skill_package(
                skill_root,
                name="legacy-review",
                description="Legacy description.",
                instructions=(
                    "---\n"
                    "name: portable-review\n"
                    "description: Portable description.\n"
                    "suggested_tools: [git_diff]\n"
                    "---\n"
                    "# Portable Review\n\nUse portable metadata.\n"
                ),
                allowed_tools=("legacy_tool",),
                frontmatter=False,
            )
            (skill_root / "SKILL.md").write_text(
                "---\n"
                "name: portable-review\n"
                "description: Portable description.\n"
                "suggested_tools: [git_diff]\n"
                "---\n"
                "# Portable Review\n\nUse portable metadata.\n",
                encoding="utf-8",
            )
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=system_root,
            )

            skills = repository.list_available(workspace_dir=None)

            self.assertEqual(skills[0].name, "portable-review")
            self.assertEqual(skills[0].description, "Portable description.")
            self.assertEqual(skills[0].suggested_tools, ("git_diff",))
            self.assertEqual(skills[0].manifest_path, str((skill_root / "SKILL.md").resolve()))

    def test_repository_ignores_legacy_manifest_during_active_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            skill_root = system_root / "legacy-review"
            _write_skill_package(
                skill_root,
                name="legacy-review",
                description="Legacy description.",
                instructions="# Legacy Review\n\nUse old metadata.\n",
                allowed_tools=("legacy_tool",),
                frontmatter=False,
            )
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=system_root,
            )

            self.assertEqual(repository.list_available(workspace_dir=None), ())
            validated = repository.validate(path=str(skill_root))

            self.assertEqual(validated.name, "legacy-review")
            self.assertEqual(validated.manifest_path, str((skill_root / "skill.yaml").resolve()))

    def test_repository_prefers_workspace_over_global_and_system(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            global_root = root / "global"
            system_root = root / "system"
            _write_skill_package(
                workspace / ".crxzipple" / "skills" / "repo-review",
                name="repo-review",
                description="Workspace-local review instructions.",
                instructions="# Repo Review\n\nWorkspace-local review instructions.\n",
            )
            _write_skill_package(
                global_root / "repo-review",
                name="repo-review",
                description="Global review instructions.",
                instructions="# Repo Review\n\nGlobal review instructions.\n",
            )
            _write_skill_package(
                system_root / "repo-review",
                name="repo-review",
                description="System review instructions.",
                instructions="# Repo Review\n\nSystem review instructions.\n",
            )
            repository = FilesystemSkillRepository(
                global_root=global_root,
                system_root=system_root,
            )

            skills = repository.list_available(workspace_dir=str(workspace))

            self.assertEqual(len(skills), 1)
            self.assertEqual(skills[0].name, "repo-review")
            self.assertEqual(skills[0].source, "workspace")
            self.assertIn("workspace", skills[0].description.lower())

    def test_repository_ignores_directories_without_valid_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            invalid = system_root / "broken-skill"
            invalid.mkdir(parents=True)
            (invalid / "SKILL.md").write_text("# Broken\n", encoding="utf-8")
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=system_root,
            )

            self.assertEqual(repository.list_available(workspace_dir=None), ())

    def test_read_loads_skill_instructions_by_default(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            _write_skill_package(
                system_root / "release-ops",
                name="release-ops",
                description="Prepare and validate releases.",
                instructions="# Release Ops\n\nFollow the release checklist.\n",
            )
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=system_root,
            )

            loaded = repository.read(
                workspace_dir=None,
                skill_name="release-ops",
                path=None,
            )

            self.assertEqual(loaded.package.name, "release-ops")
            self.assertEqual(loaded.requested_path, "SKILL.md")
            self.assertIn("release checklist", loaded.content)

    def test_read_can_load_nested_skill_resource_within_package_scope(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            skill_root = system_root / "release-ops"
            _write_skill_package(
                skill_root,
                name="release-ops",
                description="Prepare and validate releases.",
                instructions=(
                    "# Release Ops\n\n"
                    "If you need the detailed checklist, read references/checklist.md.\n"
                ),
            )
            references_root = skill_root / "references"
            references_root.mkdir()
            (references_root / "checklist.md").write_text(
                "# Checklist\n\n- Cut branch\n- Run smoke tests\n",
                encoding="utf-8",
            )
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=system_root,
            )

            loaded = repository.read(
                workspace_dir=None,
                skill_name="release-ops",
                path="references/checklist.md",
            )

            self.assertEqual(loaded.requested_path, "references/checklist.md")
            self.assertTrue(loaded.resolved_path.endswith("references/checklist.md"))
            self.assertIn("Cut branch", loaded.content)

            package = repository.get(workspace_dir=None, skill_name="release-ops")
            self.assertEqual(package.resources[0].path, "references/checklist.md")
            self.assertEqual(package.resources[0].kind, "references")

    def test_read_rejects_paths_that_escape_the_skill_package(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            system_root = root / "system"
            skill_root = system_root / "release-ops"
            _write_skill_package(
                skill_root,
                name="release-ops",
                description="Prepare and validate releases.",
                instructions="# Release Ops\n\nFollow the release checklist.\n",
            )
            outside_file = system_root / "outside.md"
            outside_file.write_text("should stay unreadable\n", encoding="utf-8")
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=system_root,
            )

            with self.assertRaises(SkillValidationError):
                repository.read(
                    workspace_dir=None,
                    skill_name="release-ops",
                    path="../outside.md",
                )

    def test_install_normalizes_existing_target_race(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            source_root = root / "source" / "release-ops"
            _write_skill_package(
                source_root,
                name="release-ops",
                description="Prepare and validate releases.",
                instructions="# Release Ops\n\nFollow the release checklist.\n",
            )
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=root / "system",
            )

            with patch(
                "crxzipple.modules.skills.infrastructure.filesystem.repository.shutil.copytree",
                side_effect=FileExistsError("created by another writer"),
            ):
                with self.assertRaisesRegex(SkillValidationError, "already exists"):
                    repository.install(
                        source_dir=str(source_root),
                        scope=SkillInstallScope.GLOBAL,
                        workspace_dir=None,
                    )

    def test_create_normalizes_existing_target_race(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            workspace.mkdir()
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=root / "system",
            )
            target_path = workspace.resolve() / ".crxzipple" / "skills" / "release-ops"
            target_path_class = type(target_path)
            original_mkdir = target_path_class.mkdir

            def mkdir_with_race(path: Path, *args: object, **kwargs: object) -> None:
                if path == target_path:
                    raise FileExistsError("created by another writer")
                original_mkdir(path, *args, **kwargs)

            with patch.object(target_path_class, "mkdir", new=mkdir_with_race):
                with self.assertRaisesRegex(SkillValidationError, "already exists"):
                    repository.create(
                        SkillCreateRequest(
                            name="release-ops",
                            description="Prepare and validate releases.",
                            instructions="# Release Ops\n\nFollow the release checklist.\n",
                            workspace_dir=str(workspace),
                        ),
                    )

    def test_write_file_rejects_traversal_to_instruction_file(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            workspace.mkdir()
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=root / "system",
            )
            repository.create(
                SkillCreateRequest(
                    name="release-ops",
                    description="Prepare and validate releases.",
                    instructions="# Release Ops\n\nFollow the release checklist.\n",
                    workspace_dir=str(workspace),
                ),
            )
            instructions_path = workspace / ".crxzipple" / "skills" / "release-ops" / "SKILL.md"
            original_instructions = instructions_path.read_text(encoding="utf-8")

            with self.assertRaisesRegex(
                SkillValidationError,
                "must not contain traversal segments",
            ):
                repository.write_file(
                    workspace_dir=str(workspace),
                    skill_name="release-ops",
                    path="references/../SKILL.md",
                    content="# Hijacked",
                )

            self.assertEqual(instructions_path.read_text(encoding="utf-8"), original_instructions)

    def test_delete_file_rejects_traversal_inside_package(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            workspace.mkdir()
            repository = FilesystemSkillRepository(
                global_root=root / "global",
                system_root=root / "system",
            )
            repository.create(
                SkillCreateRequest(
                    name="release-ops",
                    description="Prepare and validate releases.",
                    instructions="# Release Ops\n\nFollow the release checklist.\n",
                    workspace_dir=str(workspace),
                ),
            )
            instructions_path = workspace / ".crxzipple" / "skills" / "release-ops" / "SKILL.md"

            with self.assertRaisesRegex(
                SkillValidationError,
                "must not contain traversal segments",
            ):
                repository.delete_file(
                    workspace_dir=str(workspace),
                    skill_name="release-ops",
                    path="references/../SKILL.md",
                )

            self.assertTrue(instructions_path.is_file())
