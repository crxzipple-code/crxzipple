from __future__ import annotations

from tests.unit.http_test_support import *


class SkillsHttpTestCase(HttpModuleTestCase):
    def test_skills_endpoints_list_show_validate_and_install_packages(self) -> None:
        with tempfile.TemporaryDirectory() as tempdir:
            root = Path(tempdir)
            workspace = root / "workspace"
            workspace.mkdir()
            source_skill = root / "release-ops-src"
            _write_skill_package(
                source_skill,
                name="release-ops",
                description="Prepare and validate releases.",
                instructions="# Release Ops\n\nFollow the release checklist.\n",
                version="1.2.0",
                tags=("release", "ops"),
                required_tools=("memory_search",),
                allowed_tools=("memory_search", "memory_read"),
            )

            list_response = self.client.get("/skills")
            self.assertEqual(list_response.status_code, 200)
            list_payload = list_response.json()
            self.assertEqual(len(list_payload), 1)
            self.assertEqual(list_payload[0]["name"], "memory-recall")

            show_response = self.client.get(
                "/skills/memory-recall",
                params={"include_instructions": True},
            )
            self.assertEqual(show_response.status_code, 200)
            show_payload = show_response.json()
            self.assertEqual(show_payload["name"], "memory-recall")
            self.assertIn("Memory Recall", show_payload["instructions"])

            validate_response = self.client.post(
                "/skills/validate",
                json={"path": str(source_skill)},
            )
            self.assertEqual(validate_response.status_code, 200)
            validate_payload = validate_response.json()
            self.assertEqual(validate_payload["name"], "release-ops")
            self.assertEqual(validate_payload["version"], "1.2.0")
            self.assertNotIn("allowed_tools", validate_payload["manifest"])
            self.assertEqual(
                validate_payload["requirements"]["suggested_tools"],
                ["memory_search", "memory_read"],
            )
            self.assertEqual(
                validate_payload["requirements"]["required_tools"],
                ["memory_search"],
            )

            install_response = self.client.post(
                "/skills/install",
                json={
                    "source_dir": str(source_skill),
                    "scope": "workspace",
                    "workspace_dir": str(workspace),
                },
            )
            self.assertEqual(install_response.status_code, 201)
            install_payload = install_response.json()
            self.assertEqual(install_payload["scope"], "workspace")
            self.assertEqual(install_payload["skill"]["name"], "release-ops")
            self.assertTrue(
                (workspace / ".crxzipple" / "skills" / "release-ops" / "skill.yaml").is_file(),
            )
            self.assertTrue(
                (workspace / ".crxzipple" / "skills" / "release-ops" / "SKILL.md").is_file(),
            )

            workspace_list_response = self.client.get(
                "/skills",
                params={"workspace_dir": str(workspace)},
            )
            self.assertEqual(workspace_list_response.status_code, 200)
            workspace_names = [item["name"] for item in workspace_list_response.json()]
            self.assertEqual(workspace_names, ["memory-recall", "release-ops"])
            container = self.client.app.state.container
            validate_records = container.events_service.read_recent_event_topic(
                "events.named.skills.package.validate_succeeded",
                limit=10,
            )
            install_records = container.events_service.read_recent_event_topic(
                "events.named.skills.package.install_succeeded",
                limit=10,
            )
            self.assertTrue(
                any(record.envelope.payload.get("skill") == "release-ops" for record in validate_records)
            )
            self.assertTrue(
                any(record.envelope.payload.get("skill") == "release-ops" for record in install_records)
            )


if __name__ == "__main__":
    unittest.main()
