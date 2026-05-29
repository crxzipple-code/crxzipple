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
            external_root = root / "external-skills"
            _write_skill_package(
                external_root / "incident-response",
                name="incident-response",
                description="Coordinate incident response.",
                instructions="# Incident Response\n\nTriage production incidents.",
                tags=("incident",),
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

            create_response = self.client.post(
                "/skills",
                json={
                    "name": "analysis-skill",
                    "description": "Analyze local project context.",
                    "instructions": "# Analysis Skill\n\nRead the repository carefully.",
                    "workspace_dir": str(workspace),
                    "tags": ["analysis"],
                    "required_tools": ["workspace_read"],
                },
            )
            self.assertEqual(create_response.status_code, 201)
            create_payload = create_response.json()
            self.assertEqual(create_payload["action"], "create")
            self.assertTrue(
                (workspace / ".crxzipple" / "skills" / "analysis-skill" / "SKILL.md").is_file(),
            )

            update_response = self.client.patch(
                "/skills/analysis-skill",
                json={
                    "workspace_dir": str(workspace),
                    "description": "Analyze workspace context.",
                    "suggested_tools": ["workspace_read", "workspace_search"],
                },
            )
            self.assertEqual(update_response.status_code, 200)
            self.assertEqual(update_response.json()["skill"]["description"], "Analyze workspace context.")

            instructions_response = self.client.put(
                "/skills/analysis-skill/instructions",
                json={
                    "workspace_dir": str(workspace),
                    "content": "# Analysis Skill\n\nPrefer evidence over guesses.",
                },
            )
            self.assertEqual(instructions_response.status_code, 200)
            refreshed_response = self.client.get(
                "/skills/analysis-skill",
                params={
                    "workspace_dir": str(workspace),
                    "include_instructions": True,
                },
            )
            self.assertIn("Prefer evidence", refreshed_response.json()["instructions"])

            write_file_response = self.client.put(
                "/skills/analysis-skill/files/references/guide.md",
                json={"workspace_dir": str(workspace), "content": "# Guide\n"},
            )
            self.assertEqual(write_file_response.status_code, 200)
            self.assertTrue(
                (
                    workspace
                    / ".crxzipple"
                    / "skills"
                    / "analysis-skill"
                    / "references"
                    / "guide.md"
                ).is_file(),
            )
            delete_file_response = self.client.delete(
                "/skills/analysis-skill/files/references/guide.md",
                params={"workspace_dir": str(workspace)},
            )
            self.assertEqual(delete_file_response.status_code, 200)

            delete_created_response = self.client.delete(
                "/skills/analysis-skill",
                params={"workspace_dir": str(workspace)},
            )
            self.assertEqual(delete_created_response.status_code, 200)

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
            self.assertFalse(
                (workspace / ".crxzipple" / "skills" / "release-ops" / "skill.yaml").is_file(),
            )
            self.assertTrue(
                (workspace / ".crxzipple" / "skills" / "release-ops" / "SKILL.md").is_file(),
            )

            workspace_list_response = self.client.get(
                "/skills",
                params={"workspace_dir": str(workspace), "include_readiness": True},
            )
            self.assertEqual(workspace_list_response.status_code, 200)
            workspace_payload = workspace_list_response.json()
            workspace_names = [item["name"] for item in workspace_payload]
            self.assertEqual(workspace_names, ["memory-recall", "release-ops"])
            release_item = next(
                item for item in workspace_payload if item["name"] == "release-ops"
            )
            self.assertEqual(release_item["readiness"]["status"], "ready")
            self.assertEqual(release_item["readiness"]["missing_tools"], [])

            sources_response = self.client.get(
                "/skills/sources",
                params={"workspace_dir": str(workspace)},
            )
            self.assertEqual(sources_response.status_code, 200)
            source_ids = {item["source_id"] for item in sources_response.json()}
            self.assertEqual(source_ids, {"system", "workspace"})

            create_source_response = self.client.post(
                "/skills/sources",
                json={
                    "source_id": "external-local",
                    "root_path": str(external_root),
                    "source_kind": "external",
                },
            )
            self.assertEqual(create_source_response.status_code, 201)
            create_source_payload = create_source_response.json()
            self.assertEqual(create_source_payload["action"], "create")
            self.assertEqual(create_source_payload["source"]["package_count"], 1)

            external_list_response = self.client.get(
                "/skills",
                params={"source": "external-local"},
            )
            self.assertEqual(external_list_response.status_code, 200)
            self.assertEqual(
                [item["name"] for item in external_list_response.json()],
                ["incident-response"],
            )

            disable_source_response = self.client.patch(
                "/skills/sources/external-local",
                json={"enabled": False},
            )
            self.assertEqual(disable_source_response.status_code, 200)
            self.assertFalse(disable_source_response.json()["source"]["enabled"])
            external_disabled_response = self.client.get(
                "/skills",
                params={"source": "external-local"},
            )
            self.assertEqual(external_disabled_response.status_code, 200)
            self.assertEqual(external_disabled_response.json(), [])

            delete_source_response = self.client.delete(
                "/skills/sources/external-local",
            )
            self.assertEqual(delete_source_response.status_code, 200)
            post_delete_sources_response = self.client.get(
                "/skills/sources",
                params={"workspace_dir": str(workspace)},
            )
            self.assertNotIn(
                "external-local",
                {item["source_id"] for item in post_delete_sources_response.json()},
            )

            sync_response = self.client.post(
                "/skills/sync",
                json={"workspace_dir": str(workspace), "source_id": "workspace"},
            )
            self.assertEqual(sync_response.status_code, 200)
            sync_payload = sync_response.json()
            self.assertEqual(sync_payload["source_id"], "workspace")
            self.assertEqual(sync_payload["synced_count"], 1)
            self.assertEqual(sync_payload["skills"][0]["name"], "release-ops")
            installations_response = self.client.get(
                "/skills/installations",
                params={"limit": 40},
            )
            self.assertEqual(installations_response.status_code, 200)
            installation_actions = {
                item["action"] for item in installations_response.json()
            }
            self.assertIn("package_install", installation_actions)
            self.assertIn("source_sync", installation_actions)

            readiness_response = self.client.get(
                "/skills/release-ops/readiness",
                params={"workspace_dir": str(workspace)},
            )
            self.assertEqual(readiness_response.status_code, 200)
            self.assertEqual(readiness_response.json()["status"], "ready")

            disable_response = self.client.post(
                "/skills/release-ops/disable",
                json={"workspace_dir": str(workspace), "reason": "test"},
            )
            self.assertEqual(disable_response.status_code, 200)
            self.assertEqual(disable_response.json()["action"], "disable")
            self.assertFalse(disable_response.json()["skill"]["enabled"])

            disabled_list_response = self.client.get(
                "/skills",
                params={"workspace_dir": str(workspace)},
            )
            self.assertEqual(disabled_list_response.status_code, 200)
            self.assertNotIn(
                "release-ops",
                {item["name"] for item in disabled_list_response.json()},
            )

            disabled_visible_response = self.client.get(
                "/skills",
                params={
                    "workspace_dir": str(workspace),
                    "include_disabled": True,
                },
            )
            self.assertEqual(disabled_visible_response.status_code, 200)
            release_disabled = next(
                item
                for item in disabled_visible_response.json()
                if item["name"] == "release-ops"
            )
            self.assertFalse(release_disabled["enabled"])

            enable_response = self.client.post(
                "/skills/release-ops/enable",
                json={"workspace_dir": str(workspace), "reason": "test"},
            )
            self.assertEqual(enable_response.status_code, 200)
            self.assertTrue(enable_response.json()["skill"]["enabled"])

            delete_response = self.client.delete(
                "/skills/release-ops",
                params={"workspace_dir": str(workspace)},
            )
            self.assertEqual(delete_response.status_code, 200)
            self.assertEqual(delete_response.json()["action"], "delete")
            self.assertFalse(
                (workspace / ".crxzipple" / "skills" / "release-ops").exists(),
            )

            system_delete_response = self.client.delete("/skills/memory-recall")
            self.assertEqual(system_delete_response.status_code, 501)
            self.assertIn("readonly system source", system_delete_response.json()["detail"])
            container = self.client.app.state.container
            validate_records = container.require(AppKey.EVENTS_SERVICE).read_recent_event_topic(
                "events.named.skills.package.validate_succeeded",
                limit=10,
            )
            install_records = container.require(AppKey.EVENTS_SERVICE).read_recent_event_topic(
                "events.named.skills.package.install_succeeded",
                limit=10,
            )
            create_records = container.require(AppKey.EVENTS_SERVICE).read_recent_event_topic(
                "events.named.skills.package.created",
                limit=10,
            )
            update_records = container.require(AppKey.EVENTS_SERVICE).read_recent_event_topic(
                "events.named.skills.package.updated",
                limit=10,
            )
            delete_records = container.require(AppKey.EVENTS_SERVICE).read_recent_event_topic(
                "events.named.skills.package.deleted",
                limit=10,
            )
            enable_records = container.require(AppKey.EVENTS_SERVICE).read_recent_event_topic(
                "events.named.skills.package.enabled",
                limit=10,
            )
            disable_records = container.require(AppKey.EVENTS_SERVICE).read_recent_event_topic(
                "events.named.skills.package.disabled",
                limit=10,
            )
            source_create_records = container.require(
                AppKey.EVENTS_SERVICE,
            ).read_recent_event_topic(
                "events.named.skills.source.created",
                limit=10,
            )
            source_sync_records = container.require(
                AppKey.EVENTS_SERVICE,
            ).read_recent_event_topic(
                "events.named.skills.source.synced",
                limit=20,
            )
            source_delete_records = container.require(
                AppKey.EVENTS_SERVICE,
            ).read_recent_event_topic(
                "events.named.skills.source.deleted",
                limit=10,
            )
            self.assertTrue(
                any(record.envelope.payload.get("skill") == "release-ops" for record in validate_records)
            )
            self.assertTrue(
                any(record.envelope.payload.get("skill") == "release-ops" for record in install_records)
            )
            self.assertTrue(
                any(
                    record.envelope.payload.get("skill") == "analysis-skill"
                    for record in create_records
                ),
            )
            self.assertTrue(
                any(
                    record.envelope.payload.get("update_kind") == "instructions"
                    for record in update_records
                ),
            )
            self.assertTrue(
                any(
                    record.envelope.payload.get("skill") == "release-ops"
                    for record in delete_records
                ),
            )
            self.assertTrue(
                any(
                    record.envelope.payload.get("skill") == "release-ops"
                    for record in enable_records
                ),
            )
            self.assertTrue(
                any(
                    record.envelope.payload.get("skill") == "release-ops"
                    for record in disable_records
                ),
            )
            self.assertTrue(
                any(
                    record.envelope.payload.get("source_id") == "external-local"
                    for record in source_create_records
                ),
            )
            self.assertTrue(
                any(
                    record.envelope.payload.get("source_id") == "external-local"
                    for record in source_sync_records
                ),
            )
            self.assertTrue(
                any(
                    record.envelope.payload.get("source_id") == "external-local"
                    for record in source_delete_records
                ),
            )


if __name__ == "__main__":
    unittest.main()
