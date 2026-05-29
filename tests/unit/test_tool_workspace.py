from __future__ import annotations

from tests.unit.tool_test_support import *  # noqa: F403


class ToolWorkspaceTestCase(ToolTestCaseBase):
    def test_executes_workspace_read_tool_with_bound_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir:
            Path(workspace_dir, "notes.txt").write_text(
                "alpha\nbeta\ngamma\n",
                encoding="utf-8",
            )

            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="read",
                        arguments={"path": "notes.txt", "offset": 2, "limit": 2},
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertIn("notes.txt", str(tool_run.output_payload))
        self.assertIn("beta", str(tool_run.output_payload))
        self.assertIn("gamma", str(tool_run.output_payload))
        self.assertEqual(tool_run.result.metadata["path"], "notes.txt")
        self.assertEqual(tool_run.result.metadata["start_line"], 2)
        self.assertEqual(tool_run.result.metadata["end_line"], 3)
        self.assertFalse(tool_run.result.metadata["truncated"])

    def test_workspace_read_tool_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir, tempfile.TemporaryDirectory() as outside_dir:
            Path(outside_dir, "escape.txt").write_text("outside\n", encoding="utf-8")

            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="read",
                        arguments={"path": "../escape.txt"},
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )

        self.assertEqual(tool_run.status, ToolRunStatus.FAILED)
        self.assertIsNotNone(tool_run.error)
        assert tool_run.error is not None
        self.assertIn("cannot traverse upward", tool_run.error.message)

    def test_workspace_read_tool_prefers_session_bound_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as bound_workspace, tempfile.TemporaryDirectory() as fake_workspace:
            Path(bound_workspace, "notes.txt").write_text(
                "from session binding\n",
                encoding="utf-8",
            )
            Path(fake_workspace, "notes.txt").write_text(
                "from forged context\n",
                encoding="utf-8",
            )
            self.session_service.ensure_session(
                EnsureSessionInput(
                    key="agent:assistant:main",
                    agent_id="assistant",
                    workspace=bound_workspace,
                ),
            )

            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="read",
                        arguments={"path": "notes.txt"},
                        execution_context=ToolExecutionContext(
                            attrs={
                                "session_key": "agent:assistant:main",
                                "workspace_dir": fake_workspace,
                            },
                        ),
                    ),
                ),
            )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertIn("from session binding", str(tool_run.output_payload))
        self.assertNotIn("from forged context", str(tool_run.output_payload))

    def test_executes_workspace_list_tool_with_bound_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir:
            Path(workspace_dir, "notes.txt").write_text("hello\n", encoding="utf-8")
            Path(workspace_dir, "docs").mkdir()
            Path(workspace_dir, "docs", "guide.md").write_text("guide\n", encoding="utf-8")

            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="workspace_list",
                        arguments={"path": ".", "limit": 10},
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertIn("Workspace Path Listing", str(tool_run.output_payload))
        self.assertEqual(tool_run.result.metadata["listed_type"], "directory")
        self.assertEqual(tool_run.result.metadata["entry_count"], 2)
        self.assertEqual(tool_run.result.metadata["entries"][0]["path"], "docs")
        self.assertEqual(tool_run.result.metadata["entries"][1]["path"], "notes.txt")

    def test_workspace_list_tool_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir:
            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="workspace_list",
                        arguments={"path": "../escape"},
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )

        self.assertEqual(tool_run.status, ToolRunStatus.FAILED)
        self.assertIsNotNone(tool_run.error)
        assert tool_run.error is not None
        self.assertIn("cannot traverse upward", tool_run.error.message)

    def test_workspace_list_tool_prefers_session_bound_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as bound_workspace, tempfile.TemporaryDirectory() as fake_workspace:
            Path(bound_workspace, "bound.txt").write_text("bound\n", encoding="utf-8")
            Path(fake_workspace, "fake.txt").write_text("fake\n", encoding="utf-8")
            self.session_service.ensure_session(
                EnsureSessionInput(
                    key="agent:assistant:main",
                    agent_id="assistant",
                    workspace=bound_workspace,
                ),
            )

            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="workspace_list",
                        arguments={},
                        execution_context=ToolExecutionContext(
                            attrs={
                                "session_key": "agent:assistant:main",
                                "workspace_dir": fake_workspace,
                            },
                        ),
                    ),
                ),
            )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(tool_run.result.metadata["entry_count"], 1)
        self.assertEqual(tool_run.result.metadata["entries"][0]["path"], "bound.txt")

    def test_executes_workspace_write_tool_with_bound_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir:
            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="write",
                        arguments={"path": "notes.txt", "content": "alpha\nbeta\n"},
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )
            written = Path(workspace_dir, "notes.txt").read_text(encoding="utf-8")

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(written, "alpha\nbeta\n")
        self.assertIn("notes.txt", str(tool_run.output_payload))
        self.assertEqual(tool_run.result.metadata["path"], "notes.txt")
        self.assertEqual(tool_run.result.metadata["bytes_written"], len("alpha\nbeta\n".encode("utf-8")))
        self.assertFalse(tool_run.result.metadata["existed_before"])

    def test_workspace_write_tool_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir:
            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="write",
                        arguments={"path": "../escape.txt", "content": "outside\n"},
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )

        self.assertEqual(tool_run.status, ToolRunStatus.FAILED)
        self.assertIsNotNone(tool_run.error)
        assert tool_run.error is not None
        self.assertIn("cannot traverse upward", tool_run.error.message)

    def test_workspace_write_tool_rejects_memory_managed_path(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir:
            memory_path = Path(workspace_dir, "MEMORY.md")
            memory_path.write_text("# Memory\n", encoding="utf-8")

            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="write",
                        arguments={
                            "path": "MEMORY.md",
                            "content": "bypassed memory service\n",
                        },
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )
            memory_text = memory_path.read_text(encoding="utf-8")

        self.assertEqual(tool_run.status, ToolRunStatus.FAILED)
        self.assertEqual(memory_text, "# Memory\n")
        self.assertIsNotNone(tool_run.error)
        assert tool_run.error is not None
        self.assertIn("memory-managed paths", tool_run.error.message)

    def test_workspace_write_tool_creates_missing_parent_directories(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir:
            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="write",
                        arguments={
                            "path": "nested/deeper/notes.txt",
                            "content": "created with parents\n",
                        },
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )
            written = Path(workspace_dir, "nested", "deeper", "notes.txt").read_text(
                encoding="utf-8",
            )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(written, "created with parents\n")
        self.assertEqual(tool_run.result.metadata["path"], "nested/deeper/notes.txt")

    def test_workspace_write_tool_prefers_session_bound_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as bound_workspace, tempfile.TemporaryDirectory() as fake_workspace:
            self.session_service.ensure_session(
                EnsureSessionInput(
                    key="agent:assistant:main",
                    agent_id="assistant",
                    workspace=bound_workspace,
                ),
            )

            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="write",
                        arguments={"path": "notes.txt", "content": "from session binding\n"},
                        execution_context=ToolExecutionContext(
                            attrs={
                                "session_key": "agent:assistant:main",
                                "workspace_dir": fake_workspace,
                            },
                        ),
                    ),
                ),
            )
            bound_text = Path(bound_workspace, "notes.txt").read_text(encoding="utf-8")
            fake_path = Path(fake_workspace, "notes.txt")

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(bound_text, "from session binding\n")
        self.assertFalse(fake_path.exists())

    def test_executes_workspace_search_tool_with_bound_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir:
            Path(workspace_dir, "notes.txt").write_text(
                "alpha\nsession_workspace_lookup\nomega\n",
                encoding="utf-8",
            )
            Path(workspace_dir, "docs.md").write_text(
                "session_workspace_lookup appears here too\n",
                encoding="utf-8",
            )
            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="workspace_search",
                        arguments={"query": "session_workspace_lookup", "limit": 2},
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertIn("Workspace Search Results", str(tool_run.output_payload))
        self.assertEqual(tool_run.result.metadata["query"], "session_workspace_lookup")
        self.assertEqual(tool_run.result.metadata["result_count"], 2)
        self.assertEqual(tool_run.result.metadata["results"][0]["path"], "docs.md")

    def test_workspace_search_tool_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir:
            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="workspace_search",
                        arguments={"query": "alpha", "path": "../escape"},
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )

        self.assertEqual(tool_run.status, ToolRunStatus.FAILED)
        self.assertIsNotNone(tool_run.error)
        assert tool_run.error is not None
        self.assertIn("cannot traverse upward", tool_run.error.message)

    def test_workspace_search_tool_prefers_session_bound_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as bound_workspace, tempfile.TemporaryDirectory() as fake_workspace:
            Path(bound_workspace, "notes.txt").write_text(
                "from session binding\n",
                encoding="utf-8",
            )
            Path(fake_workspace, "notes.txt").write_text(
                "from forged context\n",
                encoding="utf-8",
            )
            self.session_service.ensure_session(
                EnsureSessionInput(
                    key="agent:assistant:main",
                    agent_id="assistant",
                    workspace=bound_workspace,
                ),
            )

            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="workspace_search",
                        arguments={"query": "session binding"},
                        execution_context=ToolExecutionContext(
                            attrs={
                                "session_key": "agent:assistant:main",
                                "workspace_dir": fake_workspace,
                            },
                        ),
                    ),
                ),
            )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(tool_run.result.metadata["result_count"], 1)
        self.assertEqual(tool_run.result.metadata["results"][0]["path"], "notes.txt")
        self.assertIn("session binding", tool_run.result.metadata["results"][0]["line_text"])

    def test_executes_workspace_edit_tool_with_bound_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir:
            Path(workspace_dir, "notes.txt").write_text(
                "alpha\nbeta\ngamma\n",
                encoding="utf-8",
            )
            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="edit",
                        arguments={
                            "path": "notes.txt",
                            "oldText": "beta",
                            "newText": "delta",
                        },
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )
            edited = Path(workspace_dir, "notes.txt").read_text(encoding="utf-8")

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(edited, "alpha\ndelta\ngamma\n")
        self.assertIn("notes.txt", str(tool_run.output_payload))
        self.assertEqual(tool_run.result.metadata["path"], "notes.txt")
        self.assertEqual(tool_run.result.metadata["start_line"], 2)
        self.assertEqual(tool_run.result.metadata["end_line"], 2)
        self.assertEqual(tool_run.result.metadata["replacement_count"], 1)

    def test_workspace_edit_tool_rejects_multiple_matches(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir:
            Path(workspace_dir, "notes.txt").write_text(
                "repeat\nrepeat\n",
                encoding="utf-8",
            )
            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="edit",
                        arguments={
                            "path": "notes.txt",
                            "oldText": "repeat",
                            "newText": "done",
                        },
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )

        self.assertEqual(tool_run.status, ToolRunStatus.FAILED)
        self.assertIsNotNone(tool_run.error)
        assert tool_run.error is not None
        self.assertIn("exactly one match", tool_run.error.message)

    def test_workspace_edit_tool_rejects_memory_managed_path(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir:
            daily_path = Path(workspace_dir, "memory", "2026-05-22.md")
            daily_path.parent.mkdir()
            daily_path.write_text("alpha\n", encoding="utf-8")

            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="edit",
                        arguments={
                            "path": "memory/2026-05-22.md",
                            "oldText": "alpha",
                            "newText": "beta",
                        },
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )
            memory_text = daily_path.read_text(encoding="utf-8")

        self.assertEqual(tool_run.status, ToolRunStatus.FAILED)
        self.assertEqual(memory_text, "alpha\n")
        self.assertIsNotNone(tool_run.error)
        assert tool_run.error is not None
        self.assertIn("memory-managed paths", tool_run.error.message)

    def test_workspace_edit_tool_prefers_session_bound_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as bound_workspace, tempfile.TemporaryDirectory() as fake_workspace:
            Path(bound_workspace, "notes.txt").write_text(
                "from session binding\n",
                encoding="utf-8",
            )
            Path(fake_workspace, "notes.txt").write_text(
                "from forged context\n",
                encoding="utf-8",
            )
            self.session_service.ensure_session(
                EnsureSessionInput(
                    key="agent:assistant:main",
                    agent_id="assistant",
                    workspace=bound_workspace,
                ),
            )

            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="edit",
                        arguments={
                            "path": "notes.txt",
                            "oldText": "from session binding",
                            "newText": "edited from binding",
                        },
                        execution_context=ToolExecutionContext(
                            attrs={
                                "session_key": "agent:assistant:main",
                                "workspace_dir": fake_workspace,
                            },
                        ),
                    ),
                ),
            )
            bound_text = Path(bound_workspace, "notes.txt").read_text(encoding="utf-8")
            fake_text = Path(fake_workspace, "notes.txt").read_text(encoding="utf-8")

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertIn("edited from binding", bound_text)
        self.assertEqual(fake_text, "from forged context\n")
        self.assertEqual(
            Path(str(tool_run.result.metadata["workspace_dir"])).resolve(),
            Path(bound_workspace).resolve(),
        )

    def test_executes_workspace_exec_tool_with_bound_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir:
            Path(workspace_dir, "nested").mkdir()

            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="exec",
                        arguments={"command": "pwd", "cwd": "nested"},
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertIn("Workspace Command Execution", str(tool_run.output_payload))
        self.assertEqual(tool_run.result.metadata["cwd"], "nested")
        self.assertEqual(tool_run.result.metadata["exit_code"], 0)
        self.assertIn(
            str(Path(workspace_dir, "nested").resolve()),
            tool_run.result.metadata["stdout"],
        )

    def test_workspace_exec_tool_rejects_cwd_escape(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir:
            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="exec",
                        arguments={"command": "pwd", "cwd": "../escape"},
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )

        self.assertEqual(tool_run.status, ToolRunStatus.FAILED)
        self.assertIsNotNone(tool_run.error)
        assert tool_run.error is not None
        self.assertIn("cannot traverse upward", tool_run.error.message)

    def test_workspace_exec_tool_prefers_session_bound_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as bound_workspace, tempfile.TemporaryDirectory() as fake_workspace:
            Path(bound_workspace, "marker.txt").write_text(
                "from session binding\n",
                encoding="utf-8",
            )
            Path(fake_workspace, "marker.txt").write_text(
                "from forged context\n",
                encoding="utf-8",
            )
            self.session_service.ensure_session(
                EnsureSessionInput(
                    key="agent:assistant:main",
                    agent_id="assistant",
                    workspace=bound_workspace,
                ),
            )

            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="exec",
                        arguments={"command": "cat marker.txt"},
                        execution_context=ToolExecutionContext(
                            attrs={
                                "session_key": "agent:assistant:main",
                                "workspace_dir": fake_workspace,
                            },
                        ),
                    ),
                ),
            )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertIn("from session binding", tool_run.result.metadata["stdout"])
        self.assertNotIn("from forged context", tool_run.result.metadata["stdout"])

    def test_workspace_exec_tool_returns_nonzero_exit_without_failing(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir:
            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="exec",
                        arguments={"command": "printf 'problem\\n' >&2; exit 7"},
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(tool_run.result.metadata["exit_code"], 7)
        self.assertIn("problem", tool_run.result.metadata["stderr"])

    def test_workspace_exec_can_start_background_process_and_manage_it(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir:
            started = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="exec",
                        arguments={
                            "command": "printf 'start\\n'; sleep 0.05; printf 'done\\n'",
                            "background": True,
                        },
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )
            process_id = str(started.result.metadata["process_id"])

            listed = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="process",
                        arguments={"action": "list"},
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )
            deadline = time.monotonic() + 0.5
            while True:
                polled = asyncio.run(
                    self.tool_service.execute(
                        ExecuteToolInput(
                            tool_id="process",
                            arguments={"action": "poll", "process_id": process_id},
                            execution_context=ToolExecutionContext(
                                attrs={"workspace_dir": workspace_dir},
                            ),
                        ),
                    ),
                )
                if "done" in str(polled.result.metadata.get("stdout", "")):
                    break
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.02)
            removed = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="process",
                        arguments={"action": "remove", "process_id": process_id},
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )

        self.assertEqual(started.status, ToolRunStatus.SUCCEEDED)
        self.assertTrue(started.result.metadata["background"])
        self.assertIn("Background Process Started", str(started.output_payload))
        self.assertEqual(listed.status, ToolRunStatus.SUCCEEDED)
        self.assertIn(process_id, str(listed.output_payload))
        self.assertEqual(polled.status, ToolRunStatus.SUCCEEDED)
        self.assertIn(polled.result.metadata["status"], {"exited", "failed"})
        self.assertIn("start", polled.result.metadata["stdout"])
        self.assertIn("done", polled.result.metadata["stdout"])
        self.assertEqual(removed.status, ToolRunStatus.SUCCEEDED)
        self.assertTrue(removed.result.metadata["removed"])

    def test_workspace_process_tool_can_kill_background_process(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir:
            started = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="exec",
                        arguments={
                            "command": "sleep 5",
                            "background": True,
                        },
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )
            process_id = str(started.result.metadata["process_id"])
            killed = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="process",
                        arguments={"action": "kill", "process_id": process_id},
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )
            deadline = time.monotonic() + 0.5
            while True:
                polled = asyncio.run(
                    self.tool_service.execute(
                        ExecuteToolInput(
                            tool_id="process",
                            arguments={"action": "poll", "process_id": process_id},
                            execution_context=ToolExecutionContext(
                                attrs={"workspace_dir": workspace_dir},
                            ),
                        ),
                    ),
                )
                if polled.result.metadata.get("status") == "killed":
                    break
                if time.monotonic() >= deadline:
                    break
                time.sleep(0.02)

        self.assertEqual(killed.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(polled.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(polled.result.metadata["status"], "killed")

    def test_executes_workspace_apply_patch_tool_with_bound_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir:
            Path(workspace_dir, "notes.txt").write_text(
                "alpha\nbeta\ngamma\n",
                encoding="utf-8",
            )
            patch_input = "\n".join(
                [
                    "*** Begin Patch",
                    "*** Add File: added.txt",
                    "+new file",
                    "*** Update File: notes.txt",
                    "@@",
                    " alpha",
                    "-beta",
                    "+delta",
                    " gamma",
                    "*** Delete File: added.txt",
                    "*** End Patch",
                ],
            )
            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="apply_patch",
                        arguments={"input": patch_input},
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )
            edited = Path(workspace_dir, "notes.txt").read_text(encoding="utf-8")

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertEqual(edited, "alpha\ndelta\ngamma\n")
        self.assertFalse(Path(workspace_dir, "added.txt").exists())
        self.assertIn("modified: notes.txt", str(tool_run.output_payload))
        self.assertEqual(tool_run.result.metadata["modified_files"], ["notes.txt"])
        self.assertEqual(tool_run.result.metadata["added_files"], [])
        self.assertEqual(tool_run.result.metadata["deleted_files"], [])

    def test_workspace_apply_patch_tool_rejects_memory_managed_path(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir:
            memory_path = Path(workspace_dir, "MEMORY.md")
            memory_path.write_text("# Memory\n", encoding="utf-8")
            patch_input = "\n".join(
                [
                    "*** Begin Patch",
                    "*** Update File: MEMORY.md",
                    "@@",
                    "-# Memory",
                    "+# Edited",
                    "*** End Patch",
                ],
            )

            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="apply_patch",
                        arguments={"input": patch_input},
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )
            memory_text = memory_path.read_text(encoding="utf-8")

        self.assertEqual(tool_run.status, ToolRunStatus.FAILED)
        self.assertEqual(memory_text, "# Memory\n")
        self.assertIsNotNone(tool_run.error)
        assert tool_run.error is not None
        self.assertIn("memory-managed paths", tool_run.error.message)

    def test_workspace_apply_patch_tool_rejects_path_escape(self) -> None:
        with tempfile.TemporaryDirectory() as workspace_dir:
            patch_input = "\n".join(
                [
                    "*** Begin Patch",
                    "*** Add File: ../escape.txt",
                    "+outside",
                    "*** End Patch",
                ],
            )
            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="apply_patch",
                        arguments={"input": patch_input},
                        execution_context=ToolExecutionContext(
                            attrs={"workspace_dir": workspace_dir},
                        ),
                    ),
                ),
            )

        self.assertEqual(tool_run.status, ToolRunStatus.FAILED)
        self.assertIsNotNone(tool_run.error)
        assert tool_run.error is not None
        self.assertIn("cannot traverse upward", tool_run.error.message)

    def test_workspace_apply_patch_tool_prefers_session_bound_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as bound_workspace, tempfile.TemporaryDirectory() as fake_workspace:
            Path(bound_workspace, "notes.txt").write_text(
                "from session binding\n",
                encoding="utf-8",
            )
            Path(fake_workspace, "notes.txt").write_text(
                "from forged context\n",
                encoding="utf-8",
            )
            self.session_service.ensure_session(
                EnsureSessionInput(
                    key="agent:assistant:main",
                    agent_id="assistant",
                    workspace=bound_workspace,
                ),
            )

            patch_input = "\n".join(
                [
                    "*** Begin Patch",
                    "*** Update File: notes.txt",
                    "@@",
                    "-from session binding",
                    "+edited from binding",
                    "*** End Patch",
                ],
            )
            tool_run = asyncio.run(
                self.tool_service.execute(
                    ExecuteToolInput(
                        tool_id="apply_patch",
                        arguments={"input": patch_input},
                        execution_context=ToolExecutionContext(
                            attrs={
                                "session_key": "agent:assistant:main",
                                "workspace_dir": fake_workspace,
                            },
                        ),
                    ),
                ),
            )
            bound_text = Path(bound_workspace, "notes.txt").read_text(encoding="utf-8")
            fake_text = Path(fake_workspace, "notes.txt").read_text(encoding="utf-8")

        self.assertEqual(tool_run.status, ToolRunStatus.SUCCEEDED)
        self.assertIn("edited from binding", bound_text)
        self.assertEqual(fake_text, "from forged context\n")
        self.assertEqual(
            Path(str(tool_run.result.metadata["workspace_dir"])).resolve(),
            Path(bound_workspace).resolve(),
        )
