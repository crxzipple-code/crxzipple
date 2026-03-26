from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest

from crxzipple.modules.agent.application import RegisterAgentProfileInput
from crxzipple.modules.agent.domain.value_objects import (
    AgentLlmRoutingPolicy,
    AgentRuntimePreferences,
)
from crxzipple.modules.memory.application import (
    ApproveMemoryCandidateInput,
    CreateMemoryCandidateInput,
    ListMemoryCandidatesInput,
    ListMemoryEntriesInput,
    RecordMemoryFlushInput,
    RecallMemoryEntriesInput,
    RejectMemoryCandidateInput,
)
from crxzipple.modules.memory.domain.exceptions import (
    MemoryCandidateAlreadyReviewedError,
)
from crxzipple.modules.memory.domain.value_objects import MemoryCandidateStatus
from tests.unit.support import SqliteTestHarness


class MemoryTestCase(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = SqliteTestHarness()
        self.container = self.harness.build_container()
        self._workspaces: list[tempfile.TemporaryDirectory[str]] = []

    def tearDown(self) -> None:
        for workspace in self._workspaces:
            workspace.cleanup()
        self.harness.close()

    def _register_workspace_agent(self, agent_id: str = "writer") -> Path:
        workspace = tempfile.TemporaryDirectory()
        self._workspaces.append(workspace)
        workspace_path = Path(workspace.name)
        self.container.agent_service.register_profile(
            RegisterAgentProfileInput(
                id=agent_id,
                name=agent_id,
                llm_routing_policy=AgentLlmRoutingPolicy(default_llm_id="local-chat"),
                runtime_preferences=AgentRuntimePreferences(
                    workspace=str(workspace_path),
                ),
            ),
        )
        return workspace_path

    def test_create_candidate_persists_pending_memory(self) -> None:
        candidate = self.container.memory_service.create_candidate(
            CreateMemoryCandidateInput(
                agent_id="writer",
                title="Response preference",
                content="The user prefers concise bullet summaries.",
                summary="Prefer concise bullet summaries.",
                session_key="agent:writer:main",
                run_id="run-memory-1",
                tags=("preference", "style"),
                metadata={"source": "turn"},
            ),
        )

        fetched = self.container.memory_service.get_candidate(candidate.id)
        pending = self.container.memory_service.list_candidates(
            ListMemoryCandidatesInput(
                agent_id="writer",
                status=MemoryCandidateStatus.PENDING,
            ),
        )

        self.assertEqual(fetched.id, candidate.id)
        self.assertEqual(fetched.status, MemoryCandidateStatus.PENDING)
        self.assertEqual(fetched.tags, ("preference", "style"))
        self.assertEqual(fetched.metadata["source"], "turn")
        self.assertEqual([item.id for item in pending], [candidate.id])

    def test_approve_candidate_creates_searchable_entry(self) -> None:
        candidate = self.container.memory_service.create_candidate(
            CreateMemoryCandidateInput(
                agent_id="writer",
                title="Project decision",
                content="Use effect-based approvals as the primary prompt-time approval unit.",
                summary="Effect approvals are the main approval unit.",
                tags=("decision",),
            ),
        )

        entry = self.container.memory_service.approve_candidate(
            ApproveMemoryCandidateInput(candidate_id=candidate.id),
        )

        approved_candidate = self.container.memory_service.get_candidate(candidate.id)
        entries = self.container.memory_service.list_entries(
            ListMemoryEntriesInput(agent_id="writer", query="effect-based"),
        )

        self.assertEqual(approved_candidate.status, MemoryCandidateStatus.APPROVED)
        self.assertEqual(approved_candidate.approved_entry_id, entry.id)
        self.assertEqual(entry.source_candidate_id, candidate.id)
        self.assertEqual([item.id for item in entries], [entry.id])

    def test_rejected_candidate_cannot_be_reviewed_again(self) -> None:
        candidate = self.container.memory_service.create_candidate(
            CreateMemoryCandidateInput(
                agent_id="writer",
                title="Rejected memory",
                content="Do not store this memory.",
            ),
        )

        rejected = self.container.memory_service.reject_candidate(
            RejectMemoryCandidateInput(
                candidate_id=candidate.id,
                reason="not durable enough",
            ),
        )

        self.assertEqual(rejected.status, MemoryCandidateStatus.REJECTED)
        self.assertEqual(rejected.review_reason, "not durable enough")

        with self.assertRaises(MemoryCandidateAlreadyReviewedError):
            self.container.memory_service.approve_candidate(
                ApproveMemoryCandidateInput(candidate_id=candidate.id),
            )

    def test_recall_entries_prefers_matching_memories(self) -> None:
        first = self.container.memory_service.create_candidate(
            CreateMemoryCandidateInput(
                agent_id="writer",
                title="Approval model",
                content="Use effect-based approvals as the main approval unit.",
                summary="Effect-based approvals are primary.",
                tags=("approval", "design"),
            ),
        )
        second = self.container.memory_service.create_candidate(
            CreateMemoryCandidateInput(
                agent_id="writer",
                title="Frontend layout",
                content="Keep the composer fixed at the bottom.",
                summary="Bottom-fixed composer.",
                tags=("frontend",),
            ),
        )
        self.container.memory_service.approve_candidate(
            ApproveMemoryCandidateInput(candidate_id=first.id),
        )
        self.container.memory_service.approve_candidate(
            ApproveMemoryCandidateInput(candidate_id=second.id),
        )

        recalled = self.container.memory_service.recall_entries(
            RecallMemoryEntriesInput(
                agent_id="writer",
                query_text="How should approval work for effects?",
                limit=2,
            ),
        )

        self.assertEqual(len(recalled), 1)
        self.assertEqual(recalled[0].title, "Approval model")

    def test_create_candidate_auto_captures_workspace_memory_while_remaining_pending(
        self,
    ) -> None:
        workspace = self._register_workspace_agent()

        candidate = self.container.memory_service.create_candidate(
            CreateMemoryCandidateInput(
                agent_id="writer",
                title="Workspace memory",
                content="Persist this as durable memory right away.",
                summary="Auto-captured workspace memory.",
                session_key="agent:writer:main",
            ),
        )

        entries = self.container.memory_service.list_entries(
            ListMemoryEntriesInput(agent_id="writer"),
        )
        memory_files = sorted((workspace / "memory").glob("*.md"))

        self.assertEqual(candidate.status, MemoryCandidateStatus.PENDING)
        self.assertIsNotNone(candidate.approved_entry_id)
        self.assertEqual(candidate.metadata["capture_mode"], "auto")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].id, candidate.approved_entry_id)
        self.assertEqual(
            entries[0].metadata["storage_kind"],
            "workspace_file",
        )
        self.assertEqual(
            entries[0].metadata["memory_file_path"],
            memory_files[0].relative_to(workspace).as_posix(),
        )
        self.assertIsInstance(entries[0].metadata["memory_file_line_start"], int)
        self.assertIsInstance(entries[0].metadata["memory_file_line_end"], int)
        self.assertGreaterEqual(
            entries[0].metadata["memory_file_line_end"],
            entries[0].metadata["memory_file_line_start"],
        )
        self.assertEqual(len(memory_files), 1)
        self.assertIn(
            "Persist this as durable memory right away.",
            memory_files[0].read_text("utf-8"),
        )

    def test_approve_candidate_keeps_auto_captured_workspace_memory_without_duplication(
        self,
    ) -> None:
        self._register_workspace_agent()

        candidate = self.container.memory_service.create_candidate(
            CreateMemoryCandidateInput(
                agent_id="writer",
                title="Keep me",
                content="This memory should stay in the workspace file.",
                summary="Keep the recorded memory.",
            ),
        )

        before_entries = self.container.memory_service.list_entries(
            ListMemoryEntriesInput(agent_id="writer"),
        )
        approved_entry = self.container.memory_service.approve_candidate(
            ApproveMemoryCandidateInput(candidate_id=candidate.id),
        )
        after_entries = self.container.memory_service.list_entries(
            ListMemoryEntriesInput(agent_id="writer"),
        )
        approved_candidate = self.container.memory_service.get_candidate(candidate.id)

        self.assertEqual(len(before_entries), 1)
        self.assertEqual(len(after_entries), 1)
        self.assertEqual(approved_entry.id, candidate.approved_entry_id)
        self.assertEqual(after_entries[0].id, approved_entry.id)
        self.assertEqual(approved_candidate.status, MemoryCandidateStatus.APPROVED)

    def test_reject_candidate_removes_auto_captured_workspace_memory(self) -> None:
        workspace = self._register_workspace_agent()

        candidate = self.container.memory_service.create_candidate(
            CreateMemoryCandidateInput(
                agent_id="writer",
                title="Forget me",
                content="This memory should be removed during review.",
                summary="Reject the recorded memory.",
            ),
        )

        rejected = self.container.memory_service.reject_candidate(
            RejectMemoryCandidateInput(
                candidate_id=candidate.id,
                reason="not worth keeping",
            ),
        )
        entries = self.container.memory_service.list_entries(
            ListMemoryEntriesInput(agent_id="writer"),
        )
        memory_files = sorted((workspace / "memory").glob("*.md"))

        self.assertEqual(rejected.status, MemoryCandidateStatus.REJECTED)
        self.assertEqual(entries, [])
        self.assertEqual(len(memory_files), 1)
        self.assertNotIn(
            "This memory should be removed during review.",
            memory_files[0].read_text("utf-8"),
        )

    def test_workspace_memory_search_refreshes_after_file_changes(self) -> None:
        workspace = self._register_workspace_agent()

        candidate = self.container.memory_service.create_candidate(
            CreateMemoryCandidateInput(
                agent_id="writer",
                title="Search refresh",
                content="Original memory text for indexing.",
                summary="Original indexed summary.",
            ),
        )
        self.assertIsNotNone(candidate.approved_entry_id)
        memory_file_path = workspace / str(candidate.metadata["memory_file_path"])
        original_text = memory_file_path.read_text("utf-8")
        updated_text = original_text.replace(
            "Original memory text for indexing.",
            "Rewritten memory text with freshness token alpha-refresh.",
        )
        updated_text = updated_text.replace(
            "Original indexed summary.",
            "Updated indexed summary with freshness token alpha-refresh.",
        )
        memory_file_path.write_text(updated_text, encoding="utf-8")
        stat = memory_file_path.stat()
        os.utime(
            memory_file_path,
            ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000),
        )

        entries = self.container.memory_service.list_entries(
            ListMemoryEntriesInput(
                agent_id="writer",
                query="alpha-refresh",
            ),
        )

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].id, candidate.approved_entry_id)
        self.assertIn("alpha-refresh", entries[0].content)

    def test_record_flush_entry_writes_workspace_memory(self) -> None:
        workspace = self._register_workspace_agent()

        entry = self.container.memory_service.record_flush_entry(
            RecordMemoryFlushInput(
                agent_id="writer",
                session_key="agent:writer:main",
                run_id="run-memory-flush-1",
                content=(
                    "# Durable Memory\n\n"
                    "Keep effect approvals as the default way to grant risky access."
                ),
            ),
        )

        entries = self.container.memory_service.list_entries(
            ListMemoryEntriesInput(
                agent_id="writer",
                query="effect approvals",
            ),
        )
        memory_files = sorted((workspace / "memory").glob("*.md"))

        self.assertEqual(entry.metadata["kind"], "memory_flush")
        self.assertEqual(entry.title, "Durable Memory")
        self.assertEqual(entry.run_id, "run-memory-flush-1")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0].id, entry.id)
        self.assertEqual(len(memory_files), 1)
        self.assertIn(
            "Keep effect approvals as the default way to grant risky access.",
            memory_files[0].read_text("utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
