from __future__ import annotations

import unittest

from crxzipple.modules.skills.application.models import SkillPackage
from crxzipple.modules.skills.application.settings_integration import (
    SkillEnablementManagerAdapter,
    SkillEnablementService,
)
from crxzipple.modules.skills.domain import SkillInstallScope, SkillManifest, SkillNotFoundError
from crxzipple.shared.settings import SkillEnablementConfig


class _StaticSkillManager:
    def __init__(self, packages: tuple[SkillPackage, ...]) -> None:
        self.packages = packages

    def list_available(self, *, workspace_dir: str | None, surface: str):
        return self.packages

    def read(self, *, workspace_dir: str | None, skill_name: str, path: str | None, surface: str):
        raise AssertionError("read should not be reached for disabled skills")

    def validate(self, *, path: str):
        return self.packages[0]

    def install(
        self,
        *,
        source_dir: str,
        scope: SkillInstallScope,
        workspace_dir: str | None,
    ):
        raise NotImplementedError


class SkillSettingsIntegrationTestCase(unittest.TestCase):
    def test_enablement_filters_disabled_skill_by_explicit_id(self) -> None:
        adapter = SkillEnablementManagerAdapter(
            manager=_StaticSkillManager(
                (
                    _skill("repo-review", source="workspace"),
                    _skill("memory-recall", source="system"),
                ),
            ),
            enablement=SkillEnablementService(
                (SkillEnablementConfig(skill_id="repo-review", enabled=False),),
            ),
        )

        self.assertEqual(
            [skill.name for skill in adapter.list_available(workspace_dir=None, surface="")],
            ["memory-recall"],
        )
        with self.assertRaises(SkillNotFoundError):
            adapter.get(workspace_dir=None, skill_name="repo-review", surface="")

    def test_enablement_applies_source_scope_and_pattern_override(self) -> None:
        adapter = SkillEnablementManagerAdapter(
            manager=_StaticSkillManager(
                (
                    _skill("repo-review", source="workspace"),
                    _skill("repo-merge", source="workspace"),
                    _skill("system-memory", source="system"),
                ),
            ),
            enablement=SkillEnablementService(
                (
                    SkillEnablementConfig(scope="workspace", pattern="repo-*", enabled=False),
                    SkillEnablementConfig(skill_id="repo-merge", enabled=True),
                ),
            ),
        )

        self.assertEqual(
            [skill.name for skill in adapter.list_available(workspace_dir=None, surface="")],
            ["repo-merge", "system-memory"],
        )


def _skill(name: str, *, source: str) -> SkillPackage:
    return SkillPackage(
        manifest=SkillManifest(
            api_version="skills.crxzipple/v1alpha1",
            kind="Skill",
            name=name,
            description=f"{name} skill",
        ),
        root_path=f"/tmp/{name}",
        manifest_path=f"/tmp/{name}/skill.yaml",
        instructions_path=f"/tmp/{name}/SKILL.md",
        source=source,
    )


if __name__ == "__main__":
    unittest.main()
