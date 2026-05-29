from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from tests.unit.http_test_support import HttpModuleTestCase


class MemoryHttpTestCase(HttpModuleTestCase):
    def test_memory_runtime_defaults_owner_endpoint(self) -> None:
        defaults_response = self.client.get("/memory/runtime-defaults")
        self.assertEqual(defaults_response.status_code, 200)
        defaults_payload = defaults_response.json()
        self.assertEqual(defaults_payload["id"], "default")
        self.assertIn(defaults_payload["retrieval_backend"], {"keyword", "hybrid", "vector"})
        self.assertIn(defaults_payload["vector_provider"], {"local", "openai_compatible"})
        self.assertIn("vector_credential_binding_id", defaults_payload)

        update_response = self.client.put(
            "/memory/runtime-defaults",
            json={
                "retrieval_backend": "hybrid",
                "vector_provider": "openai_compatible",
                "vector_model": "text-embedding-3-small",
                "vector_credential_binding_id": "memory-openai-api-key",
                "watch_interval_seconds": 12.5,
            },
        )
        self.assertEqual(update_response.status_code, 200)
        updated_payload = update_response.json()
        self.assertEqual(updated_payload["id"], "default")
        self.assertEqual(updated_payload["retrieval_backend"], "hybrid")
        self.assertEqual(updated_payload["vector_provider"], "openai_compatible")
        self.assertEqual(updated_payload["vector_model"], "text-embedding-3-small")
        self.assertEqual(
            updated_payload["vector_credential_binding_id"],
            "memory-openai-api-key",
        )
        self.assertEqual(updated_payload["watch_interval_seconds"], 12.5)

        refreshed_response = self.client.get("/memory/runtime-defaults")
        self.assertEqual(refreshed_response.status_code, 200)
        self.assertEqual(
            refreshed_response.json()["vector_credential_binding_id"],
            "memory-openai-api-key",
        )

    def test_memory_overview_search_excerpt_and_write_endpoints(self) -> None:
        llm_response = self.client.post(
            "/llms",
            json={
                "id": "local-chat",
                "provider": "openai",
                "api_family": "openai_responses",
                "model_name": "gpt-5.4-mini",
                "credential_binding_id": "openai-api-key",
            },
        )
        self.assertEqual(llm_response.status_code, 201)

        with tempfile.TemporaryDirectory() as tempdir:
            home_dir = Path(tempdir) / "writer-home"
            agent_response = self.client.post(
                "/agents",
                json={
                    "id": "writer",
                    "name": "Writer",
                    "llm_routing_policy": {"default_llm_id": "local-chat"},
                    "runtime_preferences": {"home_dir": str(home_dir)},
                },
            )
            self.assertEqual(agent_response.status_code, 201)

            daily_response = self.client.post(
                "/memory/daily",
                json={
                    "agent_id": "writer",
                    "content": "Remember the benchmark plan.",
                    "title": "Today",
                },
            )
            self.assertEqual(daily_response.status_code, 201)
            daily_payload = daily_response.json()
            self.assertTrue(daily_payload["path"].startswith("memory/"))

            long_term_response = self.client.post(
                "/memory/long-term",
                json={
                    "agent_id": "writer",
                    "content": "# Preferences\nUse concise file refs.\n",
                },
            )
            self.assertEqual(long_term_response.status_code, 201)
            self.assertEqual(long_term_response.json()["path"], "MEMORY.md")

            overview_response = self.client.get(
                "/memory/overview",
                params={"agent_id": "writer"},
            )
            self.assertEqual(overview_response.status_code, 200)
            overview_payload = overview_response.json()
            self.assertEqual(overview_payload["space_id"], "writer")
            self.assertEqual(overview_payload["long_term"]["path"], "MEMORY.md")
            self.assertTrue(any(item["path"] == daily_payload["path"] for item in overview_payload["recent_files"]))

            search_response = self.client.get(
                "/memory/search",
                params={"agent_id": "writer", "query": "benchmark plan"},
            )
            self.assertEqual(search_response.status_code, 200)
            search_payload = search_response.json()
            self.assertGreaterEqual(len(search_payload), 1)
            self.assertTrue(
                any(item["path"] == daily_payload["path"] for item in search_payload),
            )

            excerpt_response = self.client.get(
                "/memory/excerpt",
                params={
                    "agent_id": "writer",
                    "path": daily_payload["path"],
                    "start_line": 1,
                    "line_count": 4,
                },
            )
            self.assertEqual(excerpt_response.status_code, 200)
            excerpt_payload = excerpt_response.json()
            self.assertEqual(excerpt_payload["path"], daily_payload["path"])
            self.assertIn("benchmark plan", excerpt_payload["text"])

            rebuild_response = self.client.post(
                "/memory/spaces/writer/actions/rebuild-index",
            )
            self.assertEqual(rebuild_response.status_code, 200)
            rebuild_payload = rebuild_response.json()
            self.assertEqual(rebuild_payload["scope_ref"], "writer")
            self.assertEqual(rebuild_payload["action"], "rebuild-index")
            self.assertTrue(rebuild_payload["rebuilt"])
            self.assertGreaterEqual(rebuild_payload["file_count"], 2)

            export_response = self.client.post(
                "/memory/spaces/writer/actions/export",
            )
            self.assertEqual(export_response.status_code, 200)
            export_payload = export_response.json()
            self.assertEqual(export_payload["scope_ref"], "writer")
            self.assertEqual(export_payload["space"]["scope_ref"], "writer")
            self.assertTrue(
                any(item["path"] == daily_payload["path"] for item in export_payload["files"]),
            )

            migration_response = self.client.post(
                "/memory/actions/migrate-legacy-agent-homes",
                json={"agent_ids": ["writer"], "dry_run": True},
            )
            self.assertEqual(migration_response.status_code, 200)
            migration_payload = migration_response.json()
            self.assertTrue(migration_payload["dry_run"])
            self.assertEqual(migration_payload["scanned"], 1)
            self.assertEqual(migration_payload["agents"][0]["agent_id"], "writer")

    def test_memory_excerpt_endpoint_returns_404_for_missing_file(self) -> None:
        llm_response = self.client.post(
            "/llms",
            json={
                "id": "local-chat",
                "provider": "openai",
                "api_family": "openai_responses",
                "model_name": "gpt-5.4-mini",
                "credential_binding_id": "openai-api-key",
            },
        )
        self.assertEqual(llm_response.status_code, 201)

        with tempfile.TemporaryDirectory() as tempdir:
            home_dir = Path(tempdir) / "writer-home"
            agent_response = self.client.post(
                "/agents",
                json={
                    "id": "writer",
                    "name": "Writer",
                    "llm_routing_policy": {"default_llm_id": "local-chat"},
                    "runtime_preferences": {"home_dir": str(home_dir)},
                },
            )
            self.assertEqual(agent_response.status_code, 201)

            excerpt_response = self.client.get(
                "/memory/excerpt",
                params={"agent_id": "writer", "path": "memory/missing.md"},
            )
            self.assertEqual(excerpt_response.status_code, 404)
            self.assertEqual(
                excerpt_response.json()["detail"],
                "Memory excerpt was not found.",
            )

    def test_memory_space_and_policy_owner_endpoints(self) -> None:
        llm_response = self.client.post(
            "/llms",
            json={
                "id": "local-chat",
                "provider": "openai",
                "api_family": "openai_responses",
                "model_name": "gpt-5.4-mini",
                "credential_binding_id": "openai-api-key",
            },
        )
        self.assertEqual(llm_response.status_code, 201)

        with tempfile.TemporaryDirectory() as tempdir:
            home_dir = Path(tempdir) / "writer-home"
            agent_response = self.client.post(
                "/agents",
                json={
                    "id": "writer",
                    "name": "Writer",
                    "llm_routing_policy": {"default_llm_id": "local-chat"},
                    "runtime_preferences": {"home_dir": str(home_dir)},
                },
            )
            self.assertEqual(agent_response.status_code, 201)

            overview_response = self.client.get(
                "/memory/overview",
                params={"agent_id": "writer"},
            )
            self.assertEqual(overview_response.status_code, 200)

            spaces_response = self.client.get("/memory/spaces")
            self.assertEqual(spaces_response.status_code, 200)
            self.assertTrue(
                any(item["scope_ref"] == "writer" for item in spaces_response.json()),
            )

            upsert_space_response = self.client.put(
                "/memory/spaces/project-alpha",
                json={
                    "owner_kind": "project",
                    "owner_id": "alpha",
                    "retrieval_backend": "hybrid",
                    "engine_id": "file_markdown",
                    "metadata": {"purpose": "shared project memory"},
                },
            )
            self.assertEqual(upsert_space_response.status_code, 200)
            upserted_space = upsert_space_response.json()
            self.assertEqual(upserted_space["scope_ref"], "project-alpha")
            self.assertEqual(upserted_space["owner_kind"], "project")
            self.assertEqual(upserted_space["metadata"]["purpose"], "shared project memory")

            get_space_response = self.client.get("/memory/spaces/project-alpha")
            self.assertEqual(get_space_response.status_code, 200)
            self.assertEqual(get_space_response.json()["retrieval_backend"], "hybrid")

            disable_space_response = self.client.post(
                "/memory/spaces/project-alpha/disable",
            )
            self.assertEqual(disable_space_response.status_code, 200)
            self.assertEqual(disable_space_response.json()["status"], "disabled")

            disabled_spaces_response = self.client.get(
                "/memory/spaces",
                params={"include_disabled": True},
            )
            self.assertEqual(disabled_spaces_response.status_code, 200)
            self.assertTrue(
                any(
                    item["scope_ref"] == "project-alpha" and item["status"] == "disabled"
                    for item in disabled_spaces_response.json()
                ),
            )

            delete_space_response = self.client.delete("/memory/spaces/project-alpha")
            self.assertEqual(delete_space_response.status_code, 204)
            missing_space_response = self.client.get("/memory/spaces/project-alpha")
            self.assertEqual(missing_space_response.status_code, 404)

            policy_response = self.client.put(
                "/memory/policies/writer-memory",
                json={
                    "target_kind": "space",
                    "target_id": "writer",
                    "remember_enabled": False,
                    "max_recall_items": 2,
                },
            )
            self.assertEqual(policy_response.status_code, 200)
            self.assertFalse(policy_response.json()["remember_enabled"])

            policies_response = self.client.get("/memory/policies")
            self.assertEqual(policies_response.status_code, 200)
            self.assertEqual(policies_response.json()[0]["policy_id"], "writer-memory")

            disable_response = self.client.post(
                "/memory/policies/writer-memory/disable",
            )
            self.assertEqual(disable_response.status_code, 200)
            self.assertEqual(disable_response.json()["status"], "disabled")

            delete_response = self.client.delete("/memory/policies/writer-memory")
            self.assertEqual(delete_response.status_code, 204)

    def test_memory_runtime_test_endpoints_apply_policy(self) -> None:
        llm_response = self.client.post(
            "/llms",
            json={
                "id": "local-chat",
                "provider": "openai",
                "api_family": "openai_responses",
                "model_name": "gpt-5.4-mini",
                "credential_binding_id": "openai-api-key",
            },
        )
        self.assertEqual(llm_response.status_code, 201)

        with tempfile.TemporaryDirectory() as tempdir:
            home_dir = Path(tempdir) / "writer-home"
            agent_response = self.client.post(
                "/agents",
                json={
                    "id": "writer",
                    "name": "Writer",
                    "llm_routing_policy": {"default_llm_id": "local-chat"},
                    "runtime_preferences": {"home_dir": str(home_dir)},
                },
            )
            self.assertEqual(agent_response.status_code, 201)

            first_remember = self.client.post(
                "/memory/runtime/remember",
                json={
                    "agent_id": "writer",
                    "content": "Runtime policy recall sample one.",
                    "title": "Sample one",
                },
            )
            self.assertEqual(first_remember.status_code, 201)
            self.assertEqual(first_remember.json()["scope"]["scope_ref"], "writer")

            second_remember = self.client.post(
                "/memory/runtime/remember",
                json={
                    "agent_id": "writer",
                    "content": "Runtime policy recall sample two.",
                    "title": "Sample two",
                },
            )
            self.assertEqual(second_remember.status_code, 201)

            policy_response = self.client.put(
                "/memory/policies/writer-runtime-policy",
                json={
                    "target_kind": "agent",
                    "target_id": "writer",
                    "max_recall_items": 1,
                    "remember_enabled": False,
                },
            )
            self.assertEqual(policy_response.status_code, 200)

            recall_response = self.client.post(
                "/memory/runtime/recall",
                json={
                    "agent_id": "writer",
                    "query": "Runtime policy recall sample",
                    "max_items": 10,
                },
            )
            self.assertEqual(recall_response.status_code, 200)
            recall_payload = recall_response.json()
            self.assertEqual(recall_payload["scope"]["scope_ref"], "writer")
            self.assertEqual(len(recall_payload["items"]), 1)

            blocked_remember = self.client.post(
                "/memory/runtime/remember",
                json={
                    "agent_id": "writer",
                    "content": "This write should be blocked.",
                },
            )
            self.assertEqual(blocked_remember.status_code, 409)
            self.assertIn("remember is disabled", blocked_remember.json()["detail"])

    def test_memory_runtime_recall_searches_private_and_default_shared_layers(self) -> None:
        llm_response = self.client.post(
            "/llms",
            json={
                "id": "local-chat",
                "provider": "openai",
                "api_family": "openai_responses",
                "model_name": "gpt-5.4-mini",
                "credential_binding_id": "openai-api-key",
            },
        )
        self.assertEqual(llm_response.status_code, 201)

        with tempfile.TemporaryDirectory() as tempdir:
            home_dir = Path(tempdir) / "writer-home"
            agent_response = self.client.post(
                "/agents",
                json={
                    "id": "writer",
                    "name": "Writer",
                    "llm_routing_policy": {"default_llm_id": "local-chat"},
                    "runtime_preferences": {"home_dir": str(home_dir)},
                },
            )
            self.assertEqual(agent_response.status_code, 201)

            private_write = self.client.post(
                "/memory/runtime/remember",
                json={
                    "agent_id": "writer",
                    "content": "Layered recall sees writer birthday private memory.",
                    "title": "Private",
                },
            )
            self.assertEqual(private_write.status_code, 201)

            common_space = self.client.put(
                "/memory/spaces/common",
                json={
                    "owner_kind": "shared",
                    "owner_id": "common",
                    "retrieval_backend": "hybrid",
                    "engine_id": "file_markdown",
                    "metadata": {"default_recall_enabled": True},
                },
            )
            self.assertEqual(common_space.status_code, 200)

            common_seed = self.client.post(
                "/memory/runtime/remember",
                json={
                    "scope_ref": "common",
                    "content": "Layered recall sees common birthday policy memory.",
                    "title": "Common",
                },
            )
            self.assertEqual(common_seed.status_code, 201)

            common_policy = self.client.put(
                "/memory/policies/common-read-only",
                json={
                    "target_kind": "space",
                    "target_id": "common",
                    "recall_enabled": True,
                    "remember_enabled": False,
                    "max_recall_items": 10,
                },
            )
            self.assertEqual(common_policy.status_code, 200)

            recall_response = self.client.post(
                "/memory/runtime/recall",
                json={
                    "agent_id": "writer",
                    "query": "Layered recall birthday",
                    "max_items": 10,
                },
            )
            self.assertEqual(recall_response.status_code, 200)
            recall_payload = recall_response.json()
            self.assertEqual(recall_payload["scope"]["scope_ref"], "writer")
            searched_scopes = {
                layer["scope_ref"] for layer in recall_payload["searched_layers"]
            }
            item_scopes = {
                item["source_scope_ref"] for item in recall_payload["items"]
            }
            self.assertIn("writer", searched_scopes)
            self.assertIn("common", searched_scopes)
            self.assertIn("writer", item_scopes)
            self.assertIn("common", item_scopes)

            blocked_common_write = self.client.post(
                "/memory/runtime/remember",
                json={
                    "agent_id": "writer",
                    "target_scope_ref": "common",
                    "content": "This shared write should be blocked.",
                },
            )
            self.assertEqual(blocked_common_write.status_code, 409)
            self.assertIn("not writable", blocked_common_write.json()["detail"])


if __name__ == "__main__":
    unittest.main()
