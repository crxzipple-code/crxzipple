from __future__ import annotations

from crxzipple.modules.settings.domain import SettingsNotFoundError
from tests.unit.http_test_support import *


class AgentHttpTestCase(HttpModuleTestCase):
    def test_agent_profile_endpoints_register_fetch_and_list(self) -> None:
            with tempfile.TemporaryDirectory() as tempdir:
                home_dir = Path(tempdir) / "agent-writer-home"
                workdir = Path(tempdir) / "agent-writer-work"
                create_response = self.client.post(
                    "/agents",
                    json={
                        "id": "writer",
                        "name": "Writer",
                        "identity": {"display_name": "Writer Agent", "emoji": ":memo:"},
                        "instruction_policy": {
                            "system_prompt": "Be concise.",
                            "stream_by_default": True,
                        },
                        "llm_routing_policy": {
                            "default_llm_id": "openai.gpt-5.4-mini",
                            "fallback_llm_ids": ["openai.gpt-5.4"],
                        },
                        "execution_policy": {"timeout_seconds": 90, "max_turns": 8},
                        "runtime_preferences": {
                            "home_dir": str(home_dir),
                            "workdir": str(workdir),
                            "sandbox_mode": "sandbox",
                        },
                    },
                )

                self.assertEqual(create_response.status_code, 201)
                created_payload = create_response.json()
                self.assertEqual(created_payload["id"], "writer")
                self.assertTrue(created_payload["created_at"].endswith("+00:00"))
                self.assertTrue(created_payload["updated_at"].endswith("+00:00"))
                self.assertLessEqual(
                    datetime.fromisoformat(created_payload["created_at"]),
                    datetime.fromisoformat(created_payload["updated_at"]),
                )
                self.assertEqual(
                    created_payload["llm_routing_policy"]["default_llm_id"],
                    "openai.gpt-5.4-mini",
                )

                self.assertTrue((home_dir / "agent.json").is_file())
                self.assertTrue((home_dir / "AGENT.md").is_file())
                self.assertTrue((home_dir / "SOUL.md").is_file())
                self.assertTrue((home_dir / "USER.md").is_file())
                self.assertTrue((home_dir / "IDENTITY.md").is_file())
                self.assertFalse((home_dir / "MEMORY.md").exists())
                self.assertFalse((home_dir / "memory").exists())
                self.assertTrue((home_dir / "skills").is_dir())
                self.assertTrue((home_dir / ".state").is_dir())
                with self.assertRaises(SettingsNotFoundError):
                    self.client.app.state.container.require(AppKey.SETTINGS_QUERY_SERVICE).get_resource(
                        "writer",
                    )

                get_response = self.client.get("/agents/writer")
                list_response = self.client.get("/agents")

                self.assertEqual(get_response.status_code, 200)
                fetched_payload = get_response.json()
                listed_payload = list_response.json()
                self.assertTrue(fetched_payload["created_at"].endswith("+00:00"))
                self.assertTrue(fetched_payload["updated_at"].endswith("+00:00"))
                self.assertEqual(fetched_payload["identity"]["display_name"], "Writer Agent")
                self.assertEqual(
                    fetched_payload["runtime_preferences"]["home_dir"],
                    str(home_dir),
                )
                self.assertEqual(
                    fetched_payload["runtime_preferences"]["workdir"],
                    str(workdir),
                )
                self.assertEqual(
                    fetched_payload["runtime_preferences"]["workspace"],
                    str(workdir),
                )
                self.assertEqual(list_response.status_code, 200)
                self.assertEqual(len(listed_payload), 1)
                self.assertTrue(listed_payload[0]["created_at"].endswith("+00:00"))
                self.assertTrue(listed_payload[0]["updated_at"].endswith("+00:00"))
                self.assertTrue(listed_payload[0]["instruction_policy"]["stream_by_default"])

    def test_agent_enable_disable_updates_agent_truth_without_settings_resource(self) -> None:
            with tempfile.TemporaryDirectory() as tempdir:
                home_dir = Path(tempdir) / "agent-writer-home"
                create_response = self.client.post(
                    "/agents",
                    json={
                        "id": "writer",
                        "name": "Writer",
                        "enabled": False,
                        "llm_routing_policy": {"default_llm_id": "openai.gpt-5.4-mini"},
                        "runtime_preferences": {"home_dir": str(home_dir)},
                    },
                )
                self.assertEqual(create_response.status_code, 201)
                self.assertFalse(create_response.json()["enabled"])

                enable_response = self.client.post("/agents/writer/enable")
                self.assertEqual(enable_response.status_code, 200)
                self.assertTrue(enable_response.json()["enabled"])
                self.assertTrue(self.client.get("/agents/writer").json()["enabled"])

                disable_response = self.client.post(
                    "/agents/writer/disable",
                    json={"reason": "pause profile", "actor": "unit-test"},
                )
                self.assertEqual(disable_response.status_code, 200)
                self.assertFalse(disable_response.json()["enabled"])
                self.assertFalse(self.client.get("/agents/writer").json()["enabled"])

                enable_with_reason_response = self.client.post(
                    "/agents/writer/enable",
                    json={"reason": "resume profile", "actor": "unit-test"},
                )
                self.assertEqual(enable_with_reason_response.status_code, 200)
                self.assertTrue(enable_with_reason_response.json()["enabled"])

                disable_without_body_response = self.client.post("/agents/writer/disable")
                self.assertEqual(disable_without_body_response.status_code, 200)
                self.assertFalse(disable_without_body_response.json()["enabled"])
                with self.assertRaises(SettingsNotFoundError):
                    self.client.app.state.container.require(AppKey.SETTINGS_QUERY_SERVICE).get_resource(
                        "writer",
                    )

    def test_agent_resolution_endpoint_reads_owner_modules_without_settings_truth(self) -> None:
            with tempfile.TemporaryDirectory() as tempdir:
                home_dir = Path(tempdir) / "agent-writer-home"
                llm_response = self.client.post(
                    "/llms",
                    json={
                        "id": "writer-llm",
                        "provider": "openai",
                        "api_family": "openai_responses",
                        "model_name": "gpt-5",
                        "capabilities": ["tool_calling"],
                        "credential_binding_id": "openai-api-key",
                    },
                )
                self.assertEqual(llm_response.status_code, 201)
                seed_catalog_tool(
                    self.client.app.state.container,
                    tool_id="agent-search",
                    name="Agent Search",
                    description="Search for agent test data.",
                    access_requirements=("env:AGENT_TEST_TOOL_TOKEN",),
                    required_effect_ids=("weather_data",),
                )
                create_response = self.client.post(
                    "/agents",
                    json={
                        "id": "writer",
                        "name": "Writer",
                        "llm_routing_policy": {"default_llm_id": "writer-llm"},
                        "runtime_preferences": {
                            "home_dir": str(home_dir),
                            "attrs": {
                                "tool_ids": ["agent-search"],
                                "skill_ids": ["memory-recall"],
                            },
                        },
                    },
                )
                self.assertEqual(create_response.status_code, 201)
                self.assertNotIn(
                    "skill_ids",
                    create_response.json()["runtime_preferences"]["attrs"],
                )
                self.assertNotIn(
                    "tool_ids",
                    create_response.json()["runtime_preferences"]["attrs"],
                )
                self.client.app.state.container.require(AppKey.AUTHORIZATION_SERVICE).grant_agent_effect_authorization(
                    agent_id="writer",
                    effect_id="weather_data",
                )

                response = self.client.get("/agents/writer/resolution")

                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertEqual(payload["profile_id"], "writer")
                self.assertEqual(payload["summary"]["llm_routes"], 1)
                self.assertEqual(payload["summary"]["tools"], 1)
                self.assertEqual(payload["summary"]["authorization_grants"], 1)
                self.assertNotIn("skills", payload["summary"])
                self.assertNotIn("skills", payload)
                self.assertEqual(payload["llm_routes"][0]["llm_id"], "writer-llm")
                self.assertTrue(payload["llm_routes"][0]["resolved"])
                self.assertEqual(payload["llm_routes"][0]["model_name"], "gpt-5")
                self.assertEqual(payload["tools"][0]["tool_id"], "agent-search")
                self.assertTrue(payload["tools"][0]["resolved"])
                self.assertIn(
                    "env:AGENT_TEST_TOOL_TOKEN",
                    [item["requirement"] for item in payload["access_grants"]],
                )
                self.assertIn(
                    "openai-api-key",
                    [item["requirement"] for item in payload["access_grants"]],
                )
                self.assertEqual(
                    payload["authorization_grants"][0]["effect_ids"],
                    ["weather_data"],
                )
                self.assertEqual(
                    payload["authorization_grants"][0]["action"],
                    "tool.effect.authorize",
                )
                self.assertTrue(
                    any(item["source"] == "agent" for item in payload["trace"]),
                )
                with self.assertRaises(SettingsNotFoundError):
                    self.client.app.state.container.require(AppKey.SETTINGS_QUERY_SERVICE).get_resource(
                        "writer",
                    )

    def test_agent_resolution_endpoint_returns_404_for_missing_profile(self) -> None:
            response = self.client.get("/agents/missing/resolution")

            self.assertEqual(response.status_code, 404)

    def test_agent_update_and_delete_are_owned_by_agent_module(self) -> None:
            with tempfile.TemporaryDirectory() as tempdir:
                home_dir = Path(tempdir) / "agent-writer-home"
                create_response = self.client.post(
                    "/agents",
                    json={
                        "id": "writer",
                        "name": "Writer",
                        "llm_routing_policy": {"default_llm_id": "openai.gpt-5.4-mini"},
                        "runtime_preferences": {"home_dir": str(home_dir)},
                    },
                )
                self.assertEqual(create_response.status_code, 201)

                update_response = self.client.put(
                    "/agents/writer",
                    json={
                        "name": "Writer Updated",
                        "llm_routing_policy": {"default_llm_id": "openai.gpt-5.4"},
                        "reason": "refresh profile",
                        "actor": "unit-test",
                    },
                )

                self.assertEqual(update_response.status_code, 200)
                self.assertEqual(update_response.json()["name"], "Writer Updated")
                self.assertEqual(
                    update_response.json()["llm_routing_policy"]["default_llm_id"],
                    "openai.gpt-5.4",
                )
                home_payload = json.loads((home_dir / "agent.json").read_text(encoding="utf-8"))
                self.assertEqual(home_payload["name"], "Writer Updated")
                self.assertEqual(
                    home_payload["llm_routing_policy"]["default_llm_id"],
                    "openai.gpt-5.4",
                )

                delete_response = self.client.delete(
                    "/agents/writer",
                    params={"reason": "remove profile", "actor": "unit-test"},
                )

                self.assertEqual(delete_response.status_code, 204)
                self.assertEqual(self.client.get("/agents/writer").status_code, 404)
                self.assertEqual(self.client.get("/agents").json(), [])
                self.assertFalse((home_dir / "agent.json").exists())
                self.assertTrue((home_dir / "AGENT.md").exists())
                with self.assertRaises(SettingsNotFoundError):
                    self.client.app.state.container.require(AppKey.SETTINGS_QUERY_SERVICE).get_resource(
                        "writer",
                    )

    def test_agent_sync_profiles_endpoint_uses_configured_profiles(self) -> None:
            home_root = Path(tempfile.mkdtemp())
            self.addCleanup(shutil.rmtree, home_root, True)
            home_dir = home_root / "writer-home"
            settings = replace(
                load_settings(),
                database_url=self.harness.database_url,
                agent_profiles=(
                    AgentProfileSettings(
                        id="writer",
                        name="Writer",
                        identity={"display_name": "Writer Agent"},
                        instruction_policy={
                            "system_prompt": "Be concise.",
                            "stream_by_default": True,
                        },
                        llm_routing_policy={"default_llm_id": "openai.gpt-5.4-mini"},
                        execution_policy={"timeout_seconds": 75, "max_turns": 7},
                        runtime_preferences={
                            "home_dir": str(home_dir),
                            "sandbox_mode": "sandbox",
                        },
                    ),
                ),
                tool_openapi_providers=(),
                tool_mcp_providers=(),
                llm_profiles=(),
            )
            client = TestClient(create_app(settings=settings))
            try:
                sync_response = client.post("/agents/sync-profiles")
                self.assertEqual(sync_response.status_code, 200)
                self.assertEqual([item["id"] for item in sync_response.json()], ["writer"])
                self.assertEqual(
                    sync_response.json()[0]["identity"]["display_name"],
                    "Writer Agent",
                )

                get_response = client.get("/agents/writer")
                self.assertEqual(get_response.status_code, 200)
                self.assertEqual(
                    get_response.json()["execution_policy"]["timeout_seconds"],
                    75,
                )
                self.assertTrue((home_dir / "agent.json").is_file())
                self.assertTrue((home_dir / "AGENT.md").is_file())
            finally:
                client.close()

    def test_agent_migrate_home_endpoint_copies_legacy_workspace_assets(self) -> None:
            with tempfile.TemporaryDirectory() as tempdir:
                root = Path(tempdir)
                workspace = root / "legacy-workspace"
                home_dir = root / "agent-home"
                (workspace / "memory").mkdir(parents=True)
                (workspace / "skills" / "weather").mkdir(parents=True)
                (workspace / "AGENTS.md").write_text("legacy agent rules", encoding="utf-8")
                (workspace / "SOUL.md").write_text("calm voice", encoding="utf-8")
                (workspace / "memory" / "preferences.md").write_text(
                    "prefers concise replies",
                    encoding="utf-8",
                )
                (workspace / "skills" / "weather" / "SKILL.md").write_text(
                    "# Weather\n",
                    encoding="utf-8",
                )

                create_response = self.client.post(
                    "/agents",
                    json={
                        "id": "writer",
                        "name": "Writer",
                        "llm_routing_policy": {"default_llm_id": "openai.gpt-5.4-mini"},
                        "runtime_preferences": {"workspace": str(workspace)},
                    },
                )
                self.assertEqual(create_response.status_code, 201)

                migrate_response = self.client.post(
                    "/agents/writer/migrate-home",
                    json={"home_dir": str(home_dir)},
                )

                self.assertEqual(migrate_response.status_code, 200)
                payload = migrate_response.json()
                self.assertEqual(payload["source_dir"], str(workspace))
                self.assertEqual(payload["home_dir"], str(home_dir))
                self.assertEqual(payload["workdir"], str(workspace))
                self.assertEqual(
                    payload["profile"]["runtime_preferences"]["home_dir"],
                    str(home_dir),
                )
                self.assertEqual(
                    payload["profile"]["runtime_preferences"]["workdir"],
                    str(workspace),
                )
                self.assertEqual(
                    payload["profile"]["runtime_preferences"]["workspace"],
                    str(workspace),
                )
                self.assertIn("AGENTS.md -> AGENT.md", payload["copied_paths"])
                self.assertNotIn("memory/preferences.md", payload["copied_paths"])
                self.assertIn("skills/weather/SKILL.md", payload["copied_paths"])
                self.assertTrue((home_dir / "agent.json").is_file())
                self.assertEqual(
                    (home_dir / "AGENT.md").read_text(encoding="utf-8"),
                    "legacy agent rules",
                )
                self.assertEqual(
                    (home_dir / "SOUL.md").read_text(encoding="utf-8"),
                    "calm voice",
                )
                self.assertFalse((home_dir / "memory" / "preferences.md").exists())
                self.assertTrue((home_dir / "skills" / "weather" / "SKILL.md").is_file())
                self.assertTrue((workspace / "AGENTS.md").is_file())

    def test_agent_export_and_sync_home_endpoint_round_trip_profile_config(self) -> None:
            with tempfile.TemporaryDirectory() as tempdir:
                root = Path(tempdir)
                home_dir = root / "agent-home"
                workdir = root / "workdir"
                create_response = self.client.post(
                    "/agents",
                    json={
                        "id": "writer",
                        "name": "Writer",
                        "llm_routing_policy": {"default_llm_id": "openai.gpt-5.4-mini"},
                        "runtime_preferences": {
                            "home_dir": str(home_dir),
                            "workdir": str(workdir),
                        },
                    },
                )
                self.assertEqual(create_response.status_code, 201)

                export_response = self.client.post("/agents/writer/export-home", json={})
                self.assertEqual(export_response.status_code, 200)
                self.assertEqual(export_response.json()["home_dir"], str(home_dir))

                agent_config_path = home_dir / "agent.json"
                payload = json.loads(agent_config_path.read_text(encoding="utf-8"))
                payload["name"] = "Writer Home"
                payload["instruction_policy"]["stream_by_default"] = True
                payload["llm_routing_policy"]["default_llm_id"] = "openai.gpt-5.4"
                payload["runtime_preferences"]["workdir"] = str(root / "project-b")
                agent_config_path.write_text(
                    json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )

                sync_response = self.client.post("/agents/writer/sync-home", json={})

                self.assertEqual(sync_response.status_code, 200)
                synced = sync_response.json()["profile"]
                self.assertEqual(synced["name"], "Writer Home")
                self.assertTrue(synced["instruction_policy"]["stream_by_default"])
                self.assertEqual(
                    synced["llm_routing_policy"]["default_llm_id"],
                    "openai.gpt-5.4",
                )
                self.assertEqual(
                    synced["runtime_preferences"]["workdir"],
                    str(root / "project-b"),
                )

    def test_agent_home_endpoint_reads_and_updates_files(self) -> None:
            with tempfile.TemporaryDirectory() as tempdir:
                root = Path(tempdir)
                home_dir = root / "agent-home"
                create_response = self.client.post(
                    "/agents",
                    json={
                        "id": "writer",
                        "name": "Writer",
                        "llm_routing_policy": {"default_llm_id": "openai.gpt-5.4-mini"},
                        "runtime_preferences": {"home_dir": str(home_dir)},
                    },
                )
                self.assertEqual(create_response.status_code, 201)

                get_response = self.client.get("/agents/writer/home")
                self.assertEqual(get_response.status_code, 200)
                files = {item["name"]: item for item in get_response.json()["files"]}
                self.assertIn("AGENT.md", files)
                self.assertIn("agent.json", files)

                update_response = self.client.put(
                    "/agents/writer/home",
                    json={
                        "files": [
                            {
                                "name": "AGENT.md",
                                "content": "# AGENT.md\n\nUpdated role instructions.\n",
                            },
                            {
                                "name": "SOUL.md",
                                "content": "# SOUL.md\n\n- Voice: measured\n",
                            },
                        ],
                    },
                )

                self.assertEqual(update_response.status_code, 200)
                updated_files = {
                    item["name"]: item
                    for item in update_response.json()["files"]
                }
                self.assertEqual(
                    updated_files["AGENT.md"]["content"],
                    "# AGENT.md\n\nUpdated role instructions.\n",
                )
                self.assertEqual(
                    updated_files["SOUL.md"]["content"],
                    "# SOUL.md\n\n- Voice: measured\n",
                )
                self.assertEqual(
                    (home_dir / "AGENT.md").read_text(encoding="utf-8"),
                    "# AGENT.md\n\nUpdated role instructions.\n",
                )
                self.assertEqual(
                    (home_dir / "SOUL.md").read_text(encoding="utf-8"),
                    "# SOUL.md\n\n- Voice: measured\n",
                )

    def test_agent_sync_home_endpoint_accepts_legacy_agent_json_shape(self) -> None:
            with tempfile.TemporaryDirectory() as tempdir:
                root = Path(tempdir)
                home_dir = root / "agent-home"
                create_response = self.client.post(
                    "/agents",
                    json={
                        "id": "writer",
                        "name": "Writer",
                        "llm_routing_policy": {"default_llm_id": "openai.gpt-5.4-mini"},
                        "runtime_preferences": {"home_dir": str(home_dir)},
                    },
                )
                self.assertEqual(create_response.status_code, 201)

                agent_config_path = home_dir / "agent.json"
                agent_config_path.write_text(
                    json.dumps(
                        {
                            "id": "writer",
                            "name": "Legacy Writer",
                            "default_llm_id": "openai.gpt-5.4",
                            "workdir": str(root / "legacy-workdir"),
                            "sandbox_mode": "sandbox",
                        },
                        ensure_ascii=True,
                        indent=2,
                        sort_keys=True,
                    )
                    + "\n",
                    encoding="utf-8",
                )

                sync_response = self.client.post("/agents/writer/sync-home", json={})

                self.assertEqual(sync_response.status_code, 200)
                synced = sync_response.json()["profile"]
                self.assertEqual(synced["name"], "Legacy Writer")
                self.assertNotIn("description", synced)
                self.assertEqual(
                    synced["llm_routing_policy"]["default_llm_id"],
                    "openai.gpt-5.4",
                )
                self.assertEqual(
                    synced["runtime_preferences"]["workdir"],
                    str(root / "legacy-workdir"),
                )
                self.assertEqual(
                    synced["runtime_preferences"]["sandbox_mode"],
                    "sandbox",
                )

    def test_agent_get_endpoint_reads_file_first_home_config_without_sync(self) -> None:
            with tempfile.TemporaryDirectory() as tempdir:
                root = Path(tempdir)
                home_dir = root / "agent-home"
                create_response = self.client.post(
                    "/agents",
                    json={
                        "id": "writer",
                        "name": "Writer",
                        "llm_routing_policy": {"default_llm_id": "openai.gpt-5.4-mini"},
                        "runtime_preferences": {
                            "home_dir": str(home_dir),
                            "workdir": str(root / "workdir-a"),
                        },
                    },
                )
                self.assertEqual(create_response.status_code, 201)

                agent_config_path = home_dir / "agent.json"
                payload = json.loads(agent_config_path.read_text(encoding="utf-8"))
                payload["name"] = "Writer From Home"
                payload["instruction_policy"]["system_prompt"] = "Use the home config."
                payload["llm_routing_policy"]["default_llm_id"] = "openai.gpt-5.4"
                payload["runtime_preferences"]["workdir"] = str(root / "workdir-b")
                agent_config_path.write_text(
                    json.dumps(payload, ensure_ascii=True, indent=2, sort_keys=True) + "\n",
                    encoding="utf-8",
                )

                get_response = self.client.get("/agents/writer")

                self.assertEqual(get_response.status_code, 200)
                profile = get_response.json()
                self.assertEqual(profile["name"], "Writer From Home")
                self.assertEqual(
                    profile["instruction_policy"]["system_prompt"],
                    "Use the home config.",
                )
                self.assertEqual(
                    profile["llm_routing_policy"]["default_llm_id"],
                    "openai.gpt-5.4",
                )
                self.assertEqual(
                    profile["runtime_preferences"]["workdir"],
                    str(root / "workdir-b"),
                )

    def test_agent_endpoints_discover_home_only_profiles_without_db_snapshot(self) -> None:
            agent_home_root = derive_agent_home_root(self.harness.database_url)
            home_dir = agent_home_root / "file-only-writer"
            home_dir.mkdir(parents=True, exist_ok=True)
            (home_dir / "agent.json").write_text(
                json.dumps(
                    {
                        "id": "file-only-writer",
                        "name": "File Only Writer",
                        "enabled": True,
                        "instruction_policy": {
                            "system_prompt": "You only exist in files.",
                            "stream_by_default": False,
                        },
                        "llm_routing_policy": {
                            "default_llm_id": "openai.gpt-5.4-mini",
                            "fallback_llm_ids": [],
                        },
                        "runtime_preferences": {
                            "home_dir": str(home_dir),
                            "workdir": str(home_dir / "workspace"),
                            "attrs": {},
                        },
                    },
                    ensure_ascii=True,
                    indent=2,
                    sort_keys=True,
                )
                + "\n",
                encoding="utf-8",
            )

            list_response = self.client.get("/agents")
            get_response = self.client.get("/agents/file-only-writer")

            self.assertEqual(list_response.status_code, 200)
            self.assertIn(
                "file-only-writer",
                [item["id"] for item in list_response.json()],
            )
            self.assertEqual(get_response.status_code, 200)
            get_payload = get_response.json()
            self.assertEqual(get_payload["name"], "File Only Writer")
            self.assertTrue(get_payload["created_at"].endswith("+00:00"))
            self.assertTrue(get_payload["updated_at"].endswith("+00:00"))
            self.assertEqual(
                get_payload["runtime_preferences"]["home_dir"],
                str(home_dir),
            )


if __name__ == "__main__":
    unittest.main()
