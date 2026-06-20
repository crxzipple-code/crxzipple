# Command Tools

`tools/command` contains bundled command-execution tools.

## Availability

- `exec` and `process` are regular command tools.
- They still require a bound workspace at execution time.
- They use the session-bound workspace first.

## Effects

- `exec` requires `command_execution`.
- `process` requires `command_execution`.
- `exec` is treated as mutating because shell commands may change local state.
- `process` is treated as mutating because it can terminate or remove background processes.

## `exec`

Parameters:

- `command` required
- `cwd` optional relative directory inside the workspace
- `timeout_seconds` optional
- `background` optional boolean

Behavior:

- Runs the command through a local POSIX shell from the bound workspace.
- Keeps the current working directory inside the workspace.
- Can be used for environment probes, dependency checks, short Node/Python
  scripts, downloaded resource inspection, and HTTP/API request reproduction.
- Reports `stdout`, `stderr`, and `exit_code`.
- When `background=true`, starts the command and returns a `process_id` immediately.
- Non-zero exit codes are returned in the result instead of failing the tool call.
- Times out when the command runs too long.
- Treat command output as evidence for the next step; if a probe adds no new
  fact, change strategy instead of repeating it.

Example:

```text
Use exec to run `pwd && ls` from the workspace root.
```

Background example:

```text
Use exec with `background=true` to run `npm run dev` from the workspace root.
```

## `process`

Parameters:

- `action` required: `list`, `poll`, `log`, `kill`, or `remove`
- `process_id` required for `poll`, `log`, `kill`, and `remove`
- `stdout_offset` optional
- `stderr_offset` optional
- `limit` optional

Behavior:

- `list` returns visible background processes for the current session or workspace scope.
- `poll` returns current state plus incremental stdout and stderr slices.
- `log` returns stdout and stderr slices without changing process state.
- `kill` terminates a running background process.
- `remove` forgets a finished process session.

Example:

```text
Use process with action `list` to show background commands for the current workspace.
```

## Current Limits

- `exec` is currently inline-only.
- `exec` truncates long stdout and stderr to keep tool responses bounded.
- `process` only manages commands started by `exec` with `background=true`.
- `process` state and output are persisted in the filesystem-backed process store.
- Direct CLI and HTTP consumers can inspect the same process sessions when they
  share the same `APP_DATABASE_URL` namespace.
