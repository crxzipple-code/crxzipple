# Module Audit: process

## Verdict

Low risk after the output-window and stale-session hardening. Process remains a
small support capability scoped to local process sessions/supervision.

## Evidence

- 13 Python files.
- Largest files: `infrastructure/repository.py` (309), `interfaces/cli.py` (235), `infrastructure/supervisor.py` (143), `application/services.py` (107).

## Findings

- The module is small and easy to reason about.
- It should remain a support capability and not absorb daemon responsibilities.
- `read_output` now reads bounded stdout/stderr windows from filesystem logs
  instead of loading whole stream files before slicing.
- Repository process ids reject path traversal before resolving session files.
- Stale running sessions with dead PIDs are refreshed into terminal failed state.

## Launch Risks

- Subprocess output is bounded on read, but retention/quota policy for old
  process logs is still a cleanup follow-up.
- Leaked processes can still affect local runtime stability if callers never
  terminate/remove abandoned sessions.

## Recommendations

- Keep bounded output-window tests and stale-process refresh tests in place.
- Add retention cleanup policy for old process logs/sessions in a later support
  module hardening pass.
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

`infrastructure/repository.py` is 309 lines and uses filesystem process state,
bounded output-window reads, path-contained process-id resolution, and subprocess
inspection. `infrastructure/supervisor.py` is 143 lines and owns process launch.
These are correctly in infrastructure.

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
are capped by repository windows; process log retention/quota remains a follow-up.

### Concurrency And Multi-User Readiness

Concurrent process starts have working-directory validation and output read caps.
Old process/session retention cleanup still needs a policy decision.

### Remediation Checklist

- [x] Add process output size cap tests.
- [x] Add timeout and termination cleanup tests.
- [x] Add stale process/session cleanup tests.
- [x] Keep daemon long-running service ownership separate.

### Verification

- `PYTHONPATH=src pytest -q tests/unit/test_process_repository.py tests/unit/test_process_cli.py tests/unit/test_process_http.py --tb=short` -> 7 passed.
- `python -m ruff check src/crxzipple/modules/process/application/ports.py src/crxzipple/modules/process/application/services.py src/crxzipple/modules/process/infrastructure/repository.py src/crxzipple/modules/process/interfaces/cli.py tests/unit/test_process_repository.py tests/unit/test_process_cli.py` -> passed.
