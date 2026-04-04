from __future__ import annotations

from pathlib import Path
import re
import unittest


UNIT_DIR = Path(__file__).resolve().parent


class TestLayoutTestCase(unittest.TestCase):
    def test_legacy_aggregator_files_do_not_return(self) -> None:
        legacy_paths = (
            UNIT_DIR / "test_browser.py",
            UNIT_DIR / "test_tool.py",
            UNIT_DIR / "test_orchestration.py",
        )

        for path in legacy_paths:
            self.assertFalse(path.exists(), f"legacy aggregator file returned: {path.name}")

    def test_root_transport_files_remain_top_level_only(self) -> None:
        cli_tests = re.findall(
            r"^    def test_",
            (UNIT_DIR / "test_cli.py").read_text(),
            re.MULTILINE,
        )
        http_tests = re.findall(
            r"^    def test_",
            (UNIT_DIR / "test_http.py").read_text(),
            re.MULTILINE,
        )

        self.assertLessEqual(len(cli_tests), 10)
        self.assertLessEqual(len(http_tests), 5)

    def test_support_modules_do_not_define_collected_tests(self) -> None:
        support_paths = sorted(UNIT_DIR.glob("*_test_support.py"))

        for path in support_paths:
            text = path.read_text()
            self.assertNotRegex(path.name, r"^test_")
            self.assertNotRegex(text, r"^def test_", msg=f"support file contains test function: {path.name}")
            self.assertNotRegex(
                text,
                r"^class Test",
                msg=f"support file contains collected test class: {path.name}",
            )
