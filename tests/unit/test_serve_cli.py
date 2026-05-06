from __future__ import annotations

from types import SimpleNamespace

from tests.unit.cli_test_support import *


class ServeCliTestCase(CliModuleTestCase):
    def test_serve_runs_http_server_without_starting_worker_loops(self) -> None:
        fake_container = SimpleNamespace(
            settings=SimpleNamespace(),
        )
        fake_http_app = object()
        server_instances: list[object] = []

        class _FakeServer:
            def __init__(self, config):  # noqa: ANN001
                self.config = config
                self.run_called = False
                server_instances.append(self)

            def run(self) -> None:
                self.run_called = True

        with patch(
            "crxzipple.interfaces.cli.crxzipple.ensure_container",
            return_value=fake_container,
        ), patch(
            "crxzipple.interfaces.http.app.create_app",
            return_value=fake_http_app,
        ) as create_app_mock, patch(
            "crxzipple.interfaces.cli.crxzipple.uvicorn.Server",
            _FakeServer,
        ):
            result = self.runner.invoke(
                app,
                ["serve", "--host", "127.0.0.1", "--port", "8010"],
                env=self.env,
            )

        self.assertEqual(result.exit_code, 0)
        create_app_mock.assert_called_once()
        self.assertEqual(len(server_instances), 1)
        self.assertTrue(server_instances[0].run_called)

    def test_serve_rejects_sqlite_without_explicit_runtime_fallback(self) -> None:
        result = self.runner.invoke(
            app,
            ["serve", "--host", "127.0.0.1", "--port", "8010"],
            env=self.env_without_sqlite_runtime_fallback(),
        )

        self.assertEqual(result.exit_code, 1)
        self.assertIn("Refusing to start HTTP API with SQLite", result.stderr)
        self.assertIn("APP_ALLOW_SQLITE_RUNTIME_FALLBACK=1", result.stderr)


if __name__ == "__main__":
    unittest.main()
