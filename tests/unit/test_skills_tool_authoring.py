from __future__ import annotations

import asyncio
import unittest
from typing import Any

from crxzipple.modules.tool.domain import ToolExecutionContext
from tools.skills.local import (
    SkillsToolDeps,
    skill_draft_apply,
    skill_draft_create,
    skill_draft_diff,
    skill_draft_reject,
    skill_draft_update,
    skill_draft_validate,
)


class _FakeSkillManager:
    pass


class _FakeSkillAuthoringService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def create_draft(self, request: Any) -> dict[str, Any]:
        self.calls.append(("create_draft", {"request": request}))
        return {
            "draft_id": "draft-1",
            "status": "draft",
            "summary": "created",
            "next_step": "validate",
        }

    async def update_draft(self, *, draft_id: str, request: Any) -> dict[str, Any]:
        self.calls.append(
            ("update_draft", {"draft_id": draft_id, "request": request}),
        )
        return {"draft_id": draft_id, "status": "draft"}

    def validate_draft(self, draft_id: str) -> dict[str, Any]:
        self.calls.append(("validate_draft", {"draft_id": draft_id}))
        return {
            "draft_id": draft_id,
            "status": "validated",
            "readiness_status": "ready",
        }

    def build_draft_diff(self, draft_id: str) -> dict[str, Any]:
        self.calls.append(("build_draft_diff", {"draft_id": draft_id}))
        return {"draft_id": draft_id, "summary": "1 file changed"}

    def apply_draft(self, *, draft_id: str, reason: str | None = None) -> dict[str, Any]:
        self.calls.append(
            ("apply_draft", {"draft_id": draft_id, "reason": reason}),
        )
        return {
            "draft_id": draft_id,
            "status": "applied",
            "summary": "applied skill",
        }

    def reject_draft(
        self,
        *,
        draft_id: str,
        reason: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(
            ("reject_draft", {"draft_id": draft_id, "reason": reason}),
        )
        return {"draft_id": draft_id, "status": "rejected"}


class SkillsToolAuthoringTestCase(unittest.TestCase):
    def test_skill_draft_create_delegates_to_authoring_service(self) -> None:
        authoring = _FakeSkillAuthoringService()
        handler = skill_draft_create(
            SkillsToolDeps(
                skill_manager=_FakeSkillManager(),
                skill_authoring_service=authoring,
            ),
        )
        context = ToolExecutionContext(
            attrs={
                "workspace_dir": "/workspace",
                "surface": "interactive",
                "run_id": "run-1",
            },
        )

        result = asyncio.run(
            handler(
                {
                    "skill_name": "repo-review",
                    "summary": "Review repos carefully.",
                    "manifest": {
                        "name": "repo-review",
                        "description": "Review repositories.",
                    },
                    "instructions_body": "# Repo Review\n",
                    "support_files": [
                        {
                            "path": "references/examples.md",
                            "content": "# Examples\n",
                        },
                    ],
                },
                context,
            ),
        )

        self.assertEqual(authoring.calls[0][0], "create_draft")
        request = authoring.calls[0][1]["request"]
        self.assertEqual(request.workspace_dir, "/workspace")
        self.assertEqual(request.created_by_run_id, "run-1")
        self.assertEqual(result.metadata["tool"], "skill_draft_create")
        self.assertEqual(result.metadata["draft_id"], "draft-1")

    def test_authoring_lifecycle_handlers_delegate(self) -> None:
        authoring = _FakeSkillAuthoringService()
        deps = SkillsToolDeps(
            skill_manager=_FakeSkillManager(),
            skill_authoring_service=authoring,
        )

        asyncio.run(skill_draft_update(deps)({"draft_id": "draft-1", "patch": {}}))
        asyncio.run(skill_draft_validate(deps)({"draft_id": "draft-1"}))
        asyncio.run(skill_draft_diff(deps)({"draft_id": "draft-1"}))
        asyncio.run(skill_draft_reject(deps)({"draft_id": "draft-1"}))

        self.assertEqual(
            [name for name, _payload in authoring.calls],
            ["update_draft", "validate_draft", "build_draft_diff", "reject_draft"],
        )

    def test_skill_draft_apply_marks_approval_requirement(self) -> None:
        authoring = _FakeSkillAuthoringService()
        handler = skill_draft_apply(
            SkillsToolDeps(
                skill_manager=_FakeSkillManager(),
                skill_authoring_service=authoring,
            ),
        )

        result = asyncio.run(
            handler({"draft_id": "draft-1", "reason": "User approved."}),
        )

        self.assertEqual(authoring.calls[0][0], "apply_draft")
        self.assertEqual(authoring.calls[0][1]["reason"], "User approved.")
        self.assertTrue(result.metadata["approval_required"])
        self.assertEqual(result.metadata["required_effect_id"], "skill_authoring.apply")

    def test_authoring_tools_fail_without_authoring_service(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "skill_authoring_service"):
            skill_draft_create(SkillsToolDeps(skill_manager=_FakeSkillManager()))


if __name__ == "__main__":
    unittest.main()
