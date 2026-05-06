# Process Module

`modules/process` owns the low-level background process primitive.

It is infrastructure for application services that need to manage OS processes.
It is not an application runtime coordinator and should not become a side door
around daemon. Current consumers include:

- `daemon`, which owns long-lived internal service lifecycle
- local diagnostic CLI commands under `crxzipple.main process`

## Responsibilities

- start shell commands as background processes for trusted local callers
- persist process session state
- read stdout and stderr slices
- report status and exit codes
- terminate and remove finished sessions

## Boundaries

- The module does not resolve session workspaces.
- The module does not enforce tool visibility or authorization policies.
- The module does not decide which application services should be running.
- The module does not expose a public HTTP surface for arbitrary command start.
- Long-lived internal services must be started through `daemon`.
- Consumer-specific metadata such as `workspace_root` belongs in
  `ProcessSession.metadata`, not in the domain core.

## Storage Model

- Process sessions are stored in a filesystem-backed process store.
- The store root is derived from `APP_DATABASE_URL`, so separate app database
  namespaces do not share process sessions by default.
- Each process session keeps:
  - `session.json`
  - `stdout.log`
  - `stderr.log`
  - `exit_code`

## CLI

The direct CLI group is exposed only for trusted local diagnostics:

```bash
PYTHONPATH=src python3 -m crxzipple.main process --help
```

Useful commands:

```bash
APP_DATABASE_URL=sqlite:///./crxzipple.db PYTHONPATH=src python3 -m crxzipple.main process start "sleep 30" --working-directory /tmp
APP_DATABASE_URL=sqlite:///./crxzipple.db PYTHONPATH=src python3 -m crxzipple.main process list
APP_DATABASE_URL=sqlite:///./crxzipple.db PYTHONPATH=src python3 -m crxzipple.main process get <process-id>
APP_DATABASE_URL=sqlite:///./crxzipple.db PYTHONPATH=src python3 -m crxzipple.main process output <process-id>
APP_DATABASE_URL=sqlite:///./crxzipple.db PYTHONPATH=src python3 -m crxzipple.main process terminate <process-id>
APP_DATABASE_URL=sqlite:///./crxzipple.db PYTHONPATH=src python3 -m crxzipple.main process remove <process-id>
```

## HTTP

There is intentionally no public `/processes` HTTP API. API, channel, and CLI
runtime entrypoints should request daemon-managed services instead of starting
raw shell commands through HTTP.
