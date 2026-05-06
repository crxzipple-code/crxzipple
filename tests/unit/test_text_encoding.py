from __future__ import annotations

import unittest

from crxzipple.modules.orchestration.interfaces.shared import build_inbound_instruction
from crxzipple.shared.text_encoding import (
    repair_possible_utf8_latin1_mojibake_content,
    repair_possible_utf8_latin1_mojibake_text,
)


class TextEncodingTestCase(unittest.TestCase):
    def test_repairs_utf8_latin1_mojibake_for_east_asian_text(self) -> None:
        expected = "你现在可以使用 mobile 工具控制这台已连接的 Android 手机。"
        garbled = expected.encode("utf-8").decode("latin1")

        self.assertEqual(
            repair_possible_utf8_latin1_mojibake_text(garbled),
            expected,
        )

    def test_leaves_normal_east_asian_text_unchanged(self) -> None:
        original = "先创建会话并抓取当前屏幕 snapshot。"

        self.assertEqual(
            repair_possible_utf8_latin1_mojibake_text(original),
            original,
        )

    def test_repairs_only_web_inbound_instruction_content(self) -> None:
        expected = "先创建会话并抓取当前屏幕 snapshot。"
        garbled = expected.encode("utf-8").decode("latin1")
        content = {"blocks": [{"type": "text", "text": garbled}]}

        web_instruction = build_inbound_instruction(source="web", content=content)
        cli_instruction = build_inbound_instruction(source="cli", content=content)

        self.assertEqual(
            web_instruction.content["blocks"][0]["text"],
            expected,
        )
        self.assertEqual(
            cli_instruction.content["blocks"][0]["text"],
            garbled,
        )

    def test_repairs_nested_text_blocks_without_touching_non_text_fields(self) -> None:
        expected = "观察当前屏幕并继续操作"
        garbled = expected.encode("utf-8").decode("latin1")
        content = {
            "blocks": [
                {"type": "text", "text": garbled},
                {"type": "image_ref", "artifact_id": "img_123", "mime_type": "image/png"},
            ],
        }

        repaired = repair_possible_utf8_latin1_mojibake_content(content)

        self.assertEqual(repaired["blocks"][0]["text"], expected)
        self.assertEqual(repaired["blocks"][1]["artifact_id"], "img_123")

