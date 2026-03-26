Frontend tests are organized by scope so production code under `src/` stays free of test files.

- `unit/composables/`
  Composable-focused unit tests with mocked API boundaries.
- `unit/lib/`
  Unit tests for pure utilities and API helpers.
- `unit/support/`
  Shared factories and light test-only helpers.
- `integration/`
  Cross-composable or UI flow tests that exercise multiple layers together.
