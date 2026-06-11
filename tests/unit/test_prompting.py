from __future__ import annotations

import unittest

from crxzipple.modules.orchestration.application.prompting import (
    PromptBlock,
    PromptBlockPolicy,
    PromptMode,
    apply_system_prompt_budget,
    build_agent_instruction_block,
    estimate_text_tokens,
)
from crxzipple.modules.context_workspace.application.runtime_contract import (
    load_runtime_contract,
)
from crxzipple.modules.orchestration.application.flow_context import (
    build_flow_context_payload,
)
from crxzipple.modules.orchestration.application.prompting.runtime_context import (
    build_runtime_context_message,
)


class PromptBudgetTestCase(unittest.TestCase):
    def test_budget_preserves_higher_priority_blocks_first(self) -> None:
        blocks = (
            PromptBlock(
                kind="low_priority_context",
                content="L" * 80,
                policy=PromptBlockPolicy(priority=100),
            ),
            PromptBlock(
                kind="high_priority_context",
                content="H" * 40,
                policy=PromptBlockPolicy(priority=900),
            ),
        )

        planned = apply_system_prompt_budget(
            blocks,
            total_max_chars=45,
            total_max_tokens=12,
        )

        self.assertEqual([block.kind for block in planned], ["high_priority_context"])

    def test_budget_honors_block_max_tokens(self) -> None:
        blocks = (
            PromptBlock(
                kind="project_context",
                content="project " * 20,
                policy=PromptBlockPolicy(max_tokens=4, truncate_strategy="tail"),
            ),
        )

        planned = apply_system_prompt_budget(blocks)

        self.assertEqual(len(planned), 1)
        self.assertTrue(planned[0].truncated)
        self.assertLessEqual(estimate_text_tokens(planned[0].content), 4)

    def test_budget_respects_mode_allowlist(self) -> None:
        blocks = (
            PromptBlock(
                kind="compaction_only",
                content="compaction-specific guidance",
                policy=PromptBlockPolicy(mode_allowlist=(PromptMode.COMPACTION,)),
            ),
            PromptBlock(
                kind="general",
                content="general guidance",
            ),
        )

        normal = apply_system_prompt_budget(blocks, mode=PromptMode.NORMAL_TURN)
        compaction = apply_system_prompt_budget(blocks, mode=PromptMode.COMPACTION)

        self.assertEqual([block.kind for block in normal], ["general"])
        self.assertEqual(
            [block.kind for block in compaction],
            ["compaction_only", "general"],
        )


class PromptInstructionTestCase(unittest.TestCase):
    def test_agent_instruction_preserves_profile_prompt_without_static_contract(self) -> None:
        block = build_agent_instruction_block("Be precise.")

        self.assertIsNotNone(block)
        assert block is not None
        self.assertEqual(block.kind, "agent_instruction")
        self.assertEqual(block.content, "Be precise.")

    def test_runtime_contract_asset_carries_engineering_runtime_contract(self) -> None:
        contract = load_runtime_contract()

        self.assertEqual(contract.version, "2026-06-10")
        self.assertIn("rg --files", contract.content)
        self.assertIn("exec", contract.content)
        self.assertIn("process", contract.content)
        self.assertIn("public search or remote fetch tools", contract.content)
        self.assertIn("browser/runtime observation", contract.content)
        self.assertIn("Do not substitute search snippets", contract.content)

    def test_runtime_context_includes_environment_and_command_tool_facts(self) -> None:
        message = build_runtime_context_message(
            agent_id="assistant",
            llm_id="llm.default",
            home_dir="/agents/assistant",
            workspace_dir="/workspace/project",
            available_tool_ids=("exec", "process", "brave_search.web_search"),
        )

        self.assertIn("# Runtime Context", message)
        self.assertIn("- Agent: assistant", message)
        self.assertIn("- Model: llm.default", message)
        self.assertIn("- Timezone:", message)
        self.assertIn("- Agent home: /agents/assistant", message)
        self.assertIn("- Workspace: /workspace/project", message)
        self.assertIn(
            "- Local command runtime: exec, process available via Context Tree schema enablement",
            message,
        )
        self.assertIn(
            "- Network access: unknown unless an enabled tool verifies it",
            message,
        )
        self.assertIn(
            "- Long-running local services: use daemon-managed services when available",
            message,
        )

    def test_approval_resume_flow_context_explains_once_scope_expiry(self) -> None:
        payload = build_flow_context_payload(
            mode=PromptMode.APPROVAL_RESUME,
            hint_payload={
                "decision": "allow_once",
                "effect_id": "weather_data",
                "label": "Weather data access",
            },
        )

        self.assertEqual(payload.mode, "approval_resume")
        self.assertIn("valid only for the current turn", payload.summary)
        self.assertIn("request it again", payload.summary)
        self.assertIn("applies only to the requested effect above", payload.summary)
        self.assertIn("request a different effect", payload.summary)


if __name__ == "__main__":
    unittest.main()
