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

## Anti-Patterns

- Reintroducing deleted aggregator files like `test_tool.py` or `test_orchestration.py`
- Mixing CLI and HTTP coverage for the same module into one file
- Hiding large shared fixtures inside the top of a test file instead of moving them into support
