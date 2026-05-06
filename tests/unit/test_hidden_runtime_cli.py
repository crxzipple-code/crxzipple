from __future__ import annotations

from tests.unit.cli_test_support import *


class HiddenRuntimeCliTestCase(CliModuleTestCase):
    def test_internal_runtime_entrypoints_remain_invokable(self) -> None:
        for command in (
            "tool-worker",
            "tool-scheduler",
            "channel-runtime",
            "orchestration-scheduler",
            "orchestration-executor",
            "operations-observer",
        ):
            result = self.runner.invoke(app, [command, "--help"], env=self.env)

            self.assertEqual(result.exit_code, 0, msg=f"{command}: {result.stdout}")


if __name__ == "__main__":
    unittest.main()
