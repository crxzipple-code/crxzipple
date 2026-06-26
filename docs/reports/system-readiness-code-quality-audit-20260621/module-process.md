# Module Audit: process

## Verdict

Low risk after the output-window, stale-session, and terminal-session retention
hardening. Process remains a small support capability scoped to local process
sessions/supervision.

## Evidence

- 15 Python files.
- Largest files: `infrastructure/repository.py` (327), `interfaces/cli.py`
  (233), `infrastructure/supervisor.py` (143), `application/services.py`
  (131), `infrastructure/repository_retention.py` (115).

## Findings

- The module is small and easy to reason about.
- It should remain a support capability and not absorb daemon responsibilities.
- `read_output` now reads bounded stdout/stderr windows from filesystem logs
  instead of loading whole stream files before slicing.
- Repository process ids reject path traversal before resolving session files.
- Stale running sessions with dead PIDs are refreshed into terminal failed state.
- Terminal session cleanup now enforces retention age, retained terminal-session
  count, and terminal-session byte budget without deleting running sessions.

## Launch Risks

- Leaked running processes can still affect local runtime stability if callers
  never terminate abandoned sessions; cleanup intentionally does not delete
  running sessions.

## Recommendations

- Keep bounded output-window tests and stale-process refresh tests in place.
- Keep terminal-session retention cleanup available as an explicit support
  operation; do not run hidden destructive cleanup from read paths.
- Keep daemon as owner of long-running services; Process should handle bounded sessions.

## Detailed Pass 1

### Files Reviewed

- `application/services.py`
- `application/ports.py`
- `domain/entities.py`
- `domain/value_objects.py`
- `infrastructure/repository.py`
- `infrastructure/supervisor.py`
- `interfaces/cli.py`

### File-Level Assessment

`application/services.py` is 107 lines and appropriately thin. It delegates process
start/read/terminate behavior to repository/supervisor ports and uses repository
window reads for output.

`infrastructure/repository.py` is 327 lines and uses filesystem process state,
bounded output-window reads, path-contained process-id resolution, and subprocess
inspection. Terminal cleanup policy lives in
`infrastructure/repository_retention.py`; `infrastructure/supervisor.py` is 143
lines and owns process launch. These are correctly in infrastructure.

`interfaces/cli.py` is 234 lines and stays within operational command scope.

### Boundary Cleanliness

Process owns bounded local process sessions and supervision primitives. Daemon owns
long-running service lifecycle. Process should not absorb daemon responsibilities or
business module state.

### Lifecycle Clarity

Process lifecycle should be:

1. start bounded process
2. store process session metadata
3. read status/output
4. terminate/cleanup
5. report errors without unbounded output

### Persistence And Efficiency

Filesystem state is acceptable for local bounded process sessions. Output reads
are capped by repository windows. Terminal-session cleanup is explicit and bounded
by age, retained terminal-session count, or terminal byte budget.

### Concurrency And Multi-User Readiness

Concurrent process starts have working-directory validation and output read caps.
Old terminal process/session cleanup now has a policy entrypoint. Running process
cleanup remains explicit terminate/remove behavior.

### Remediation Checklist

- [x] Add process output size cap tests.
- [x] Add timeout and termination cleanup tests.
- [x] Add stale process/session cleanup tests.
- [x] Add terminal-session retention/quota cleanup tests.
- [x] Keep daemon long-running service ownership separate.

### Verification

- `PYTHONPATH=src pytest -q tests/unit/test_process_repository.py tests/unit/test_process_cli.py tests/unit/test_process_http.py --tb=short --maxfail=1` -> 11 passed.
- `python -m ruff check src/crxzipple/modules/process/application/ports.py src/crxzipple/modules/process/application/services.py src/crxzipple/modules/process/domain/__init__.py src/crxzipple/modules/process/domain/value_objects.py src/crxzipple/modules/process/infrastructure/repository.py src/crxzipple/modules/process/infrastructure/repository_retention.py src/crxzipple/modules/process/interfaces/cli.py src/crxzipple/modules/process/interfaces/cli_payloads.py src/crxzipple/modules/process/__init__.py tests/unit/test_process_repository.py tests/unit/test_process_cli.py` -> passed.
- `python -m compileall -q src/crxzipple/modules/process tests/unit/test_process_repository.py tests/unit/test_process_cli.py` -> passed.
