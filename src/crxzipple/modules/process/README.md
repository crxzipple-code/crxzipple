# Process Module

`modules/process` owns background process lifecycle management.

It is a domain-level capability, not a `tool` implementation detail. Current
consumers include:

- `tools/command`, via the `exec` and `process` tools
- the direct CLI group at `crxzipple.main process`
- the direct HTTP endpoints under `/processes`

## Responsibilities

- start shell commands as background processes
- persist process session state
- read stdout and stderr slices
- report status and exit codes
- terminate and remove finished sessions

## Boundaries

- The module does not resolve session workspaces.
- The module does not enforce tool visibility or authorization policies.
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

The direct CLI group is exposed as:

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

The direct HTTP endpoints are:

- `POST /processes`
- `GET /processes`
- `GET /processes/{process_id}`
- `GET /processes/{process_id}/output`
- `POST /processes/{process_id}/terminate`
- `DELETE /processes/{process_id}`

Example:

```bash
curl -X POST http://127.0.0.1:8000/processes \
  -H 'Content-Type: application/json' \
  -d '{"command":"sleep 30","working_directory":"/tmp"}'
```
