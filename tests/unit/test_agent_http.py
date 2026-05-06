from __future__ import annotations

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
                        "description": "Writes concise summaries.",
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
                self.assertEqual(create_response.json()["id"], "writer")
                self.assertEqual(
                    create_response.json()["llm_routing_policy"]["default_llm_id"],
                    "openai.gpt-5.4-mini",
                )

                self.assertTrue((home_dir / "agent.json").is_file())
                self.assertTrue((home_dir / "AGENT.md").is_file())
                self.assertTrue((home_dir / "SOUL.md").is_file())
                self.assertTrue((home_dir / "USER.md").is_file())
                self.assertTrue((home_dir / "IDENTITY.md").is_file())
                self.assertTrue((home_dir / "MEMORY.md").is_file())
                self.assertTrue((home_dir / "memory").is_dir())
                self.assertTrue((home_dir / "skills").is_dir())
                self.assertTrue((home_dir / ".state").is_dir())

                get_response = self.client.get("/agents/writer")
                list_response = self.client.get("/agents")

                self.assertEqual(get_response.status_code, 200)
                self.assertEqual(get_response.json()["identity"]["display_name"], "Writer Agent")
                self.assertEqual(
                    get_response.json()["runtime_preferences"]["home_dir"],
                    str(home_dir),
                )
                self.assertEqual(
                    get_response.json()["runtime_preferences"]["workdir"],
                    str(workdir),
                )
                self.assertEqual(
                    get_response.json()["runtime_preferences"]["workspace"],
                    str(workdir),
                )
                self.assertEqual(list_response.status_code, 200)
                self.assertEqual(len(list_response.json()), 1)
                self.assertTrue(
                    list_response.json()[0]["instruction_policy"]["stream_by_default"]
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
                        description="Default writer profile.",
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
                self.assertIn("memory/preferences.md", payload["copied_paths"])
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
                self.assertEqual(
                    (home_dir / "memory" / "preferences.md").read_text(encoding="utf-8"),
                    "prefers concise replies",
                )
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
                            "description": "Legacy home config.",
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
                self.assertEqual(synced["description"], "Legacy home config.")
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
                        "description": "Loaded directly from agent_home.",
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
            self.assertEqual(get_response.json()["name"], "File Only Writer")
            self.assertEqual(
                get_response.json()["runtime_preferences"]["home_dir"],
                str(home_dir),
            )


if __name__ == "__main__":
    unittest.main()
