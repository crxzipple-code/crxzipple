# Unit Test Layout

`tests/unit` follows a module-first layout.

## Rules

- Keep different modules in different files.
- Keep transport-specific tests in transport-specific files:
  - `test_<module>_cli.py`
  - `test_<module>_http.py`
- Keep domain or service tests in `test_<module>.py` when they are not tied to one interface.
- Extract shared setup, fakes, and adapters into `<module>_test_support.py` once a test file starts carrying reusable scaffolding.
- Support files are helpers only. They must not define collected tests.

## Root Surface Files

`test_cli.py` and `test_http.py` are reserved for top-level entrypoint smoke coverage.

- Do not add module-specific CLI tests back into `test_cli.py`.
- Do not add module-specific HTTP tests back into `test_http.py`.

## Split Triggers

Split a file when one of these becomes true:

- The file mixes unrelated modules.
- The file contains multiple transport surfaces for the same module.
- The file grows enough that shared setup dominates the file.
- A reusable fake/adapter/helper appears that another test file would want.

## Current Pattern

- Shared transport scaffolding:
  - `cli_test_support.py`
  - `http_test_support.py`
- Module support files:
  - `orchestration_test_support.py`
  - `tool_test_support.py`
  - `skill_test_support.py`

## Runtime Markers

Markers are assigned centrally in `tests/conftest.py`.

- `fast`: module-local tests that avoid full HTTP/CLI/runtime assembly.
- `runtime`: tests that assemble the runtime container, HTTP app, CLI app, worker loop, or daemon surface.
- `benchmark`: CLI benchmark command coverage; these tests must not run real multi-worker SQLite benchmarks.
- `integration` / `live`: external browser/service smoke tests under `tests/integration`.

Useful commands:

```bash
make test-unit-fast
make test-unit-runtime
make test-unit

PYTHONPATH=src pytest -q tests/unit -m fast
PYTHONPATH=src pytest -q tests/unit -m runtime
PYTHONPATH=src pytest -q -o faulthandler_timeout=120 tests/unit --durations=120 --durations-min=0.2
PYTHONPATH=src pytest --collect-only -q tests -m live
```

Do not move slow live/browser/benchmark behavior into unmarked unit tests. If a test only verifies CLI or HTTP wiring, fake the module port instead of launching real worker loops.

`CliModuleTestCase` injects a shared runtime container for commands invoked with the test's default `self.env`. This keeps multi-command CLI scenarios from rebuilding the whole app for every subcommand while preserving Typer parsing and output coverage. Use a custom env or explicit `obj` when a test must verify fresh settings loading or a custom container.

`tests/conftest.py` deliberately forces unit tests onto the file events backend and clears Redis event env vars. Do not remove that isolation to make local dev-stack behavior convenient; cross-process Redis coverage belongs in integration/runtime tests.

## Anti-Patterns

- Reintroducing deleted aggregator files like `test_tool.py` or `test_orchestration.py`
- Mixing CLI and HTTP coverage for the same module into one file
- Hiding large shared fixtures inside the top of a test file instead of moving them into support
