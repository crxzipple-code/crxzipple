from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tests.unit.http_test_support import HttpModuleTestCase


class SkillsAuthoringHttpTestCase(HttpModuleTestCase):
    def test_draft_lifecycle_create_validate_diff_reject_delete_and_apply(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir) / "workspace"
            workspace.mkdir()

            draft_payload = {
                "intent": "create",
                "skill_name": "postmortem-writing",
                "workspace_dir": str(workspace),
                "manifest": {
                    "name": "postmortem-writing",
                    "description": "Write concise incident postmortems.",
                    "required_tools": ["workspace_read"],
                },
                "instructions_body": "# Postmortem Writing\n\nCapture impact, timeline, and follow-ups.",
                "support_files": [
                    {
                        "path": "references/template.md",
                        "content": "# Template\n\n- Impact\n- Timeline\n",
                    },
                ],
                "reason": "unit test",
            }

            create_response = self.client.post("/skills/drafts", json=draft_payload)
            self.assertEqual(create_response.status_code, 201)
            created = create_response.json()
            draft_id = created["draft_id"]
            self.assertEqual(created["status"], "draft")
            self.assertEqual(created["skill_name"], "postmortem-writing")

            list_response = self.client.get(
                "/skills/drafts",
                params={"workspace_dir": str(workspace)},
            )
            self.assertEqual(list_response.status_code, 200)
            self.assertEqual([item["draft_id"] for item in list_response.json()], [draft_id])

            get_response = self.client.get(f"/skills/drafts/{draft_id}")
            self.assertEqual(get_response.status_code, 200)
            self.assertEqual(get_response.json()["manifest"]["description"], "Write concise incident postmortems.")

            validate_response = self.client.post(f"/skills/drafts/{draft_id}/validate")
            self.assertEqual(validate_response.status_code, 200)
            validation = validate_response.json()["validation"]
            self.assertTrue(validation["valid"])
            self.assertEqual(validation["readiness_status"], "setup_needed")
            self.assertEqual(validation["missing_tools"], ["workspace_read"])

            diff_response = self.client.post(f"/skills/drafts/{draft_id}/diff")
            self.assertEqual(diff_response.status_code, 200)
            diff_payload = diff_response.json()["diff"]
            self.assertEqual(diff_payload["manifest_diff"]["status"], "added")
            self.assertIn("Instructions changes", diff_payload["summary"])

            reject_response = self.client.post(
                f"/skills/drafts/{draft_id}/reject",
                json={"reason": "not this one"},
            )
            self.assertEqual(reject_response.status_code, 200)
            self.assertEqual(reject_response.json()["status"], "rejected")

            delete_response = self.client.delete(f"/skills/drafts/{draft_id}")
            self.assertEqual(delete_response.status_code, 200)
            self.assertEqual(delete_response.json()["draft_id"], draft_id)
            audit_response = self.client.get(f"/skills/drafts/{draft_id}/audit")
            self.assertEqual(audit_response.status_code, 200)
            self.assertEqual(
                [item["action"] for item in reversed(audit_response.json())],
                ["create", "validate", "diff", "reject", "delete"],
            )
            missing_response = self.client.get(f"/skills/drafts/{draft_id}")
            self.assertEqual(missing_response.status_code, 404)

            apply_create = self.client.post("/skills/drafts", json=draft_payload)
            self.assertEqual(apply_create.status_code, 201)
            apply_id = apply_create.json()["draft_id"]
            apply_response = self.client.post(
                f"/skills/drafts/{apply_id}/apply",
                json={"reason": "approved"},
            )
            self.assertEqual(apply_response.status_code, 200)
            self.assertEqual(apply_response.json()["status"], "applied")
            apply_audit = self.client.get(f"/skills/drafts/{apply_id}/audit")
            self.assertEqual(apply_audit.status_code, 200)
            self.assertEqual(apply_audit.json()[0]["action"], "apply")
            self.assertEqual(apply_audit.json()[0]["status"], "succeeded")
            self.assertTrue(
                (
                    workspace
                    / ".crxzipple"
                    / "skills"
                    / "postmortem-writing"
                    / "SKILL.md"
                ).is_file(),
            )
            self.assertTrue(
                (
                    workspace
                    / ".crxzipple"
                    / "skills"
                    / "postmortem-writing"
                    / "references"
                    / "template.md"
                ).is_file(),
            )

    def test_update_draft_apply_rejects_stale_target_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            workspace = Path(tempdir) / "workspace"
            workspace.mkdir()

            create_response = self.client.post(
                "/skills",
                json={
                    "name": "daily-brief",
                    "description": "Prepare daily briefs.",
                    "instructions": "# Daily Brief\n\nSummarize yesterday.",
                    "workspace_dir": str(workspace),
                },
            )
            self.assertEqual(create_response.status_code, 201)

            draft_response = self.client.post(
                "/skills/drafts",
                json={
                    "intent": "update",
                    "skill_name": "daily-brief",
                    "workspace_dir": str(workspace),
                    "manifest": {
                        "name": "daily-brief",
                        "description": "Prepare daily operational briefs.",
                    },
                    "instructions_body": "# Daily Brief\n\nSummarize yesterday and risks.",
                },
            )
            self.assertEqual(draft_response.status_code, 201)
            draft_id = draft_response.json()["draft_id"]

            mutate_response = self.client.put(
                "/skills/daily-brief/instructions",
                json={
                    "workspace_dir": str(workspace),
                    "content": "# Daily Brief\n\nSomeone changed this first.",
                },
            )
            self.assertEqual(mutate_response.status_code, 200)

            apply_response = self.client.post(
                f"/skills/drafts/{draft_id}/apply",
                json={"reason": "approved"},
            )
            self.assertEqual(apply_response.status_code, 400)
            self.assertIn("target changed", apply_response.json()["detail"])


if __name__ == "__main__":
    unittest.main()
