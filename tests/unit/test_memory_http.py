from __future__ import annotations

from tests.unit.http_test_support import *


class MemoryHttpTestCase(HttpModuleTestCase):
    def test_memory_overview_search_excerpt_and_write_endpoints(self) -> None:
        llm_response = self.client.post(
            "/llms",
            json={
                "id": "local-chat",
                "provider": "openai",
                "api_family": "openai_responses",
                "model_name": "gpt-5.4-mini",
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
            self.assertEqual(len(search_payload), 1)
            self.assertEqual(search_payload[0]["path"], daily_payload["path"])

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

    def test_memory_excerpt_endpoint_returns_404_for_missing_file(self) -> None:
        llm_response = self.client.post(
            "/llms",
            json={
                "id": "local-chat",
                "provider": "openai",
                "api_family": "openai_responses",
                "model_name": "gpt-5.4-mini",
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


if __name__ == "__main__":
    unittest.main()
