from __future__ import annotations

import unittest

from crxzipple.modules.orchestration.application.prompting import (
    PromptBlock,
    PromptBlockPolicy,
    PromptMode,
    apply_system_prompt_budget,
    build_flow_prompt_block,
    estimate_text_tokens,
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
    def test_approval_resume_flow_prompt_explains_once_scope_expiry(self) -> None:
        block = build_flow_prompt_block(
            mode=PromptMode.APPROVAL_RESUME,
            hint_payload={
                "decision": "allow_once",
                "effect_id": "weather_data",
                "label": "Weather data access",
            },
        )

        self.assertIsNotNone(block)
        assert block is not None
        self.assertIn("valid only for the current turn", block.content)
        self.assertIn("request it again", block.content)
        self.assertIn("applies only to the requested effect above", block.content)
        self.assertIn("request a different effect", block.content)


if __name__ == "__main__":
    unittest.main()
