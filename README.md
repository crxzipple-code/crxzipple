# crxzipple

CRXZipple is a DDD-oriented local Agent Runtime console and runtime. It
coordinates agent runs, tool and LLM execution, daemon-managed workers,
event-backed observation, Operations projections, and the fullscreen
`frontend` Workbench / Trace / Operations / Settings console.

## Layout

- `src/crxzipple/core`: process-level configuration and bootstrap helpers
- `src/crxzipple/shared`: shared building blocks used across bounded contexts
- `src/crxzipple/modules`: bounded contexts split by business capability
- `tests`: unit and integration test suites

## Current modules

- `access`
- `agent`
- `artifacts`
- `authorization`
- `browser`
- `channels`
- `daemon`
- `dispatch`
- `events`
- `llm`
- `memory`
- `mobile`
- `ocr`
- `operations`
- `orchestration`
- `process`
- `session`
- `skills`
- `tool`

## Agent Development Contract

Hosted coding agents should start from `AGENTS.md`. Larger follow-up work should
also read `docs/agents/hosted-agent-operating-contract.md` before changing code.
The active documentation index lives in `docs/README.md`; archived design notes
under `docs/archive/` are historical background only.

## CLI

The unified CLI entrypoint lives in `src/crxzipple/interfaces/cli/main.py`.

Example:

```bash
PYTHONPATH=src python3 -m crxzipple.main --help
PYTHONPATH=src python3 -m crxzipple.main db upgrade head
PYTHONPATH=src python3 -m crxzipple.main llm sync-profiles
PYTHONPATH=src python3 -m crxzipple.main tool providers
PYTHONPATH=src python3 -m crxzipple.main tool roots
PYTHONPATH=src python3 -m crxzipple.main auth policies
PYTHONPATH=src python3 -m crxzipple.main tool discover --provider local_builtin
APP_TOOL_OPENAPI_PROVIDER_PATHS=/tmp/openapi-providers PYTHONPATH=src python3 -m crxzipple.main tool discover --provider sample_api
APP_TOOL_MCP_PROVIDERS='[{"name":"sample_mcp","command":["python3","./mcp_server.py"]}]' PYTHONPATH=src python3 -m crxzipple.main tool discover --provider sample_mcp
PYTHONPATH=src python3 -m crxzipple.main tool run echo --strategy thread --input '{"message":"hello from thread"}'
PYTHONPATH=src python3 -m crxzipple.main tool run echo --strategy process --input '{"message":"hello from process"}'
PYTHONPATH=src python3 -m crxzipple.main tool run echo --mode background --strategy process --input '{"message":"hello from background process"}'
APP_TOOL_OPENAPI_PROVIDER_PATHS=/tmp/openapi-providers PYTHONPATH=src python3 -m crxzipple.main tool run sample_api.search_docs --environment remote --input '{"body":{"query":"ddd","limit":3}}'
APP_TOOL_MCP_PROVIDERS='[{"name":"sample_mcp","command":["python3","./mcp_server.py"]}]' PYTHONPATH=src python3 -m crxzipple.main tool run sample_mcp.echo --environment remote --input '{"message":"hello","uppercase":true}'
```

Background tool runs are processed by daemon-managed scheduler and worker
services. Start the local infra first, then start the worker stack through
daemon, not by launching an unmanaged long-running worker:

```bash
bash scripts/dev/up-infra.sh
source scripts/dev/infra-env.sh
python3 -m crxzipple.main daemon run --service-set workers
python3 -m crxzipple.main daemon status
python3 -m crxzipple.main daemon show worker:tool
python3 -m crxzipple.main tool cancel-run <run-id>
```

The `tool-worker` and `tool-scheduler` CLI entrypoints are hidden from root
help, but remain invokable for daemon service specs and short diagnostic `once`
commands.

The `process` CLI group is a local diagnostic primitive used underneath daemon.
Do not use it as the application runtime entrypoint for long-lived internal
services; start those through `daemon run` / `daemon ensure` so ownership,
health, and shutdown stay centralized.

## HTTP

The unified HTTP entrypoint lives in `src/crxzipple/interfaces/http/app.py`.

Examples:

```bash
PYTHONPATH=src python3 -c "from crxzipple.interfaces.http.app import app; print(app.title)"
PYTHONPATH=src python3 -m uvicorn crxzipple.interfaces.http.app:app --reload
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/daemon/status
```

## Database

The default local runtime path uses Postgres from `compose.yaml` together with
Redis for cross-process events:

```bash
bash scripts/dev/up-infra.sh
source scripts/dev/infra-env.sh
python -m crxzipple.main db upgrade head
```

SQLite is only for explicit lightweight fallback or tests. Run migrations
against SQLite only when you intentionally want the single-file fallback:

```bash
APP_DATABASE_URL=sqlite:///./crxzipple.db alembic upgrade head
```

The unified CLI now exposes the same migration flow:

```bash
APP_DATABASE_URL=sqlite:///./crxzipple.db PYTHONPATH=src python3 -m crxzipple.main db upgrade head
APP_DATABASE_URL=sqlite:///./crxzipple.db PYTHONPATH=src python3 -m crxzipple.main db downgrade base
APP_DATABASE_URL=sqlite:///./crxzipple.db PYTHONPATH=src python3 -m crxzipple.main db stamp head
APP_DATABASE_URL=sqlite:///./crxzipple.db PYTHONPATH=src python3 -m crxzipple.main db current
APP_DATABASE_URL=sqlite:///./crxzipple.db PYTHONPATH=src python3 -m crxzipple.main db history
APP_DATABASE_URL=sqlite:///./crxzipple.db PYTHONPATH=src python3 -m crxzipple.main db revision "add session metadata" --autogenerate
APP_DATABASE_URL=sqlite:///./crxzipple.db PYTHONPATH=src python3 -m crxzipple.main db revision-empty "manual checkpoint"
```

Future revisions can be generated with:

```bash
APP_DATABASE_URL=sqlite:///./crxzipple.db alembic revision --autogenerate -m "describe change"
```

## Local Dev

The default local development path runs Postgres and Redis through Docker
Compose, then starts API, daemon, and frontend as local processes:

```bash
make dev-up
```

This starts:

- Postgres on `127.0.0.1:5432`
- Redis on `127.0.0.1:6379`
- API on `http://127.0.0.1:8000`
- daemon supervisor through `daemon run` for `workers` and `channels-stack`
- frontend Vite dev server on `http://127.0.0.1:4173`

Useful companion commands:

```bash
make dev-status
make dev-down
```

Infra-only commands are also available:

```bash
make dev-infra-up
make dev-infra-status
make dev-infra-down
```

If you prefer the explicit multi-terminal flow, keep using:

```bash
# terminal 1
cd /path/to/crxzipple
source scripts/dev/infra-env.sh
python -m crxzipple.main db upgrade head
python -m crxzipple.main serve
```

```bash
# terminal 2
cd /path/to/crxzipple
source scripts/dev/infra-env.sh
python -m crxzipple.main daemon run --service-set workers --service-set channels-stack
python -m crxzipple.main daemon status
```

```bash
# terminal 3
cd /path/to/crxzipple/frontend
npm run dev
```

To stop only Postgres and Redis:

```bash
bash scripts/dev/down-infra.sh
```

If you need the old file-backed fallback explicitly:

```bash
export APP_EVENTS_BACKEND=file
```

## Logging

The project uses Python's standard `logging` module with a shared config entrypoint in `src/crxzipple/core/logger.py`.

Useful environment variables:

```bash
APP_LOG_LEVEL=DEBUG
APP_LOG_JSON=true
APP_TOOL_RUN_MAX_ATTEMPTS=3
APP_TOOL_RUN_LEASE_SECONDS=30
APP_TOOL_RUN_HEARTBEAT_SECONDS=5
APP_TOOL_OPENAPI_PROVIDER_PATHS=/tmp/openapi-providers
APP_TOOL_MCP_PROVIDERS='[{"name":"sample_mcp","command":["python3","./mcp_server.py"],"timeout_seconds":10}]'
APP_LLM_PROFILE_PATHS=./config/llm_profiles
APP_AGENT_PROFILE_PATHS=./config/agent_profiles
APP_AUTHORIZATION_ENABLED=false
APP_AUTHORIZATION_POLICY_PATHS=./config/authorization_policies
```

Bundled tool assets are governed from the repository `tools/` root. Each direct
child is one namespace and must include `tool.yaml`.

Filesystem-discovered local tool extensions are still discovered from:

- `.crxzipple/tools/`
- `tools/`

Place each extension in its own subdirectory with a `tool.json` manifest and
entrypoint script.

Bundled OpenAPI providers now live under `tools/<namespace>/tool.yaml` with the
spec beside them. Set `APP_TOOL_OPENAPI_PROVIDER_PATHS` to switch to the
explicit config/env path flow for custom provider files; the variable accepts an
`os.pathsep`-separated list of files or directories.

LLM profile configs are loaded from `config/llm_profiles/*.yaml`, `*.yml`, or
`*.json` by default when that directory exists. Override the search path with
`APP_LLM_PROFILE_PATHS`, which also accepts an `os.pathsep`-separated list of
files or directories. Profiles can set `max_concurrency` and an optional shared
`concurrency_key` to protect slower model backends while the executor advances
other runs concurrently.

Agent profile configs are loaded from `config/agent_profiles/*.yaml`, `*.yml`,
or `*.json` by default when that directory exists. Override the search path
with `APP_AGENT_PROFILE_PATHS`.

Authorization policy configs are loaded from
`config/authorization_policies/*.yaml`, `*.yml`, or `*.json` by default when
that directory exists. Authorization enforcement is enabled by default; set
`APP_AUTHORIZATION_ENABLED=false` to disable it, and override the search path
with `APP_AUTHORIZATION_POLICY_PATHS`.

Authorization enforcement currently lives at the outer interface/orchestration
layer. The `tool` and `llm` subsystems remain authorization-agnostic and do not
depend on the authorization module directly.

The bundled default policy set currently:

- allows `llm.invoke` and `llm.stream`
- allows `tool.run` for non-mutating tools
- denies scope/surface-mismatched tools before they reach orchestration
- denies everything else by default unless a policy or approval grants access

Useful authorization commands:

```bash
APP_AUTHORIZATION_ENABLED=true PYTHONPATH=src python3 -m crxzipple.main auth policies
APP_AUTHORIZATION_ENABLED=true PYTHONPATH=src python3 -m crxzipple.main auth check llm.invoke llm_profile --resource-id openai.gpt-5.4-mini --context '{"interface":"cli"}'
```

Bundled LLM profile configs:

- `openai.gpt-5.4`
- `openai.gpt-5.4-mini`
- `openai.gpt-5-codex`
- `openai_codex.gpt-5-codex`

Sync the configured profiles into the database with:

```bash
PYTHONPATH=src python3 -m crxzipple.main llm sync-profiles
PYTHONPATH=src python3 -m crxzipple.main llm sync-profiles --profile openai.gpt-5.4
```

Agent profiles can also be synced from config files. The loader supports an
optional `defaults` block plus a `profiles` list:

```yaml
defaults:
  instruction_policy:
    stream_by_default: true
  llm_routing_policy:
    default_llm_id: openai.gpt-5.4-mini
  execution_policy:
    timeout_seconds: 120
    max_turns: 12

profiles:
  - id: writer
    name: Writer
    identity:
      display_name: Writer Agent
    instruction_policy:
      system_prompt: You write concise, structured answers.
```

Sync the configured agent profiles with:

```bash
PYTHONPATH=src python3 -m crxzipple.main agent sync-profiles
PYTHONPATH=src python3 -m crxzipple.main agent sync-profiles --profile writer
```

`openai_codex.gpt-5-codex` is an experimental profile that uses the local
Codex login stored in `~/.codex/auth.json` and the ChatGPT Codex backend rather
than the public OpenAI API key flow.

The LLM HTTP interface also exposes a streaming SSE endpoint:

```bash
curl -N \
  -X POST http://127.0.0.1:8000/llms/openai_codex.gpt-5-codex/stream \
  -H 'Content-Type: application/json' \
  -d '{"messages":[{"role":"system","content":"You are a concise coding assistant."},{"role":"user","content":"Reply with exactly the single word codex-stream-ok."}]}'
```

Bundled streaming-capable profiles currently include:

- `openai.gpt-5.4`
- `openai.gpt-5.4-mini`
- `openai.gpt-5-codex`
- `openai_codex.gpt-5-codex`

The existing CLI `llm invoke` command remains non-streaming and returns the
final invocation record after completion.

Bundled OpenAPI provider configs:

- `brave_search`: Brave web search, news search, and autosuggest.
- `open_meteo_geocoding`: Open-Meteo place search and ID lookup.
- `open_meteo_weather`: Open-Meteo forecast weather endpoint.
- `itick_market`: iTick stock metadata, stock quotes, and crypto quotes.

Credential requirements:

- `BRAVE_SEARCH_API_KEY` for `brave_search`
- `ITICK_API_TOKEN` for `itick_market`
- `open_meteo_geocoding` and `open_meteo_weather` work without credentials on the public endpoints

Example discovery flow for the bundled providers:

```bash
PYTHONPATH=src python3 -m crxzipple.main tool providers
PYTHONPATH=src python3 -m crxzipple.main tool discover --provider brave_search
PYTHONPATH=src python3 -m crxzipple.main tool discover --provider open_meteo_geocoding
PYTHONPATH=src python3 -m crxzipple.main tool discover --provider open_meteo_weather
PYTHONPATH=src python3 -m crxzipple.main tool discover --provider itick_market
```

Recommended layout:

```text
config/
└─ tool_providers/
   └─ sample_api.yaml

specs/
└─ sample_api.openapi.json
```

Example OpenAPI provider config:

```yaml
name: sample_api
spec_location: ../../specs/sample_api.openapi.json
base_url: https://api.example.com
timeout_seconds: 10
credentials:
  ApiKeyQuery: env:SAMPLE_API_KEY
  BearerAuth: env:SAMPLE_BEARER_TOKEN
```

Example filesystem tool layout:

```text
tools/
└─ greeter/
   ├─ tool.json
   └─ handler.py
```

Example manifest:

```json
{
  "id": "greeter",
  "name": "Greeter",
  "description": "Greet a person locally",
  "entrypoint": "handler.py:run",
  "supported_modes": ["inline", "background"],
  "supported_strategies": ["async", "thread", "process"],
  "supported_environments": ["local"]
}
```

Recommended handler contract:

```python
from typing import Any

from crxzipple.modules.tool import ToolRunResult


async def run(arguments: dict[str, Any]) -> ToolRunResult:
    return ToolRunResult(
        content={"message": f"hello {arguments['name']}"},
        metadata={"environment": "local"},
    )
```

Plain dict returns are still supported for backward compatibility, but new local
tools should prefer `ToolRunResult` so business content and runtime metadata stay
separate.

Recommended local tool conventions:

- Handler signature: use a top-level callable like `run(arguments: dict[str, Any])`
  so `thread` and `process` strategies can import and serialize it reliably.
- Async first: prefer `async def` handlers unless the tool is naturally blocking.
- Result shape: put user-facing business output in `ToolRunResult.content`.
- Metadata shape: keep runtime diagnostics such as `environment`, `process_id`,
  `thread_ident`, `working_directory`, or transport details in
  `ToolRunResult.metadata`.
- Exceptions: raise normal Python exceptions with a clear message; the tool
  runtime will convert them into `ToolRunError`.
- Compatibility: plain dict return values still work, but they make it easier to
  mix business data with runtime metadata.

OpenAPI provider config files support:

- `name`: provider identifier used by `tool discover --provider ...`
- `spec_location`: local path, `file://` URL, or `http(s)://` OpenAPI JSON document
- `base_url`: optional execution base URL override
- `description`: optional provider description
- `timeout_seconds`: optional per-provider HTTP timeout
- `credentials`: optional mapping from OpenAPI `securitySchemes` name to
  credential source, for example `"ApiKeyQuery": "env:SAMPLE_API_KEY"` or
  `{ "BasicAuth": { "username_source": "env:API_USER", "password_source": "env:API_PASSWORD" } }`

`APP_TOOL_OPENAPI_PROVIDERS` remains available as a compatibility fallback when
you want to inject the same provider config as an env JSON list instead of file-
based config.

The current `http_openapi` path supports discovery and execution for OpenAPI JSON
operations using path parameters, query parameters, JSON request bodies, and
standard OpenAPI `securitySchemes` / `security` requirements. Credential values
still come from external config or env vars; the spec tells the runtime where to
inject them. The discovered tools run through the existing `remote` runtime.

`APP_TOOL_MCP_PROVIDERS` currently accepts a JSON list of MCP stdio provider
configs. Each item supports:

- `name`: provider identifier used by `tool discover --provider ...`
- `command`: string or string list used to launch the MCP stdio process
- `args`: optional extra args when `command` is a string
- `description`: optional provider description
- `timeout_seconds`: optional per-request timeout

The current MCP path is a lightweight stdio adapter that uses `tools/list` for
discovery and `tools/call` for execution. It now keeps a local stdio MCP
process alive as a reusable session, performs `initialize`, sends
`notifications/initialized`, and reuses that session across multiple tool
calls within the same container. It is still intentionally narrower than a full
remote-capable MCP session client, but it fits the current provider/runtime
extension model cleanly.
