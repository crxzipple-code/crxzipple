# crxzipple

CRXZipple is a local Agent Runtime and fullscreen operations console. It is a
DDD-oriented modular monolith that coordinates agent runs, LLM invocations,
tool execution, daemon-managed workers, channel runtimes, event-backed
observation, and Settings/Operations governance surfaces.

The current product UI lives in `frontend` and exposes four main work areas:

- Workbench: chat/session/run entrypoint.
- Operations: event-driven operations read models for runtime monitoring.
- Trace: run and event inspection.
- Settings: configuration governance and owner-module management surfaces.

## Current Direction

The project is being converged toward clear owner-module boundaries:

- business truth stays in the owner module;
- cross-process runtime facts flow through the events backend;
- Operations observes from the side and materializes read models;
- Settings governs configuration without stealing ownership of module entities;
- long-running runtime processes are owned by daemon;
- `frontend` is the only active frontend line.

If code and older docs disagree, start with `AGENTS.md`, `docs/README.md`, and
the active architecture docs. Files under `docs/archive/` are historical context
only.

## Quick Start

Prerequisites:

- Python 3.11+
- Node.js and npm
- Docker with Compose support
- `make`

Start the full local development stack:

```bash
make dev-up
```

This starts:

- Postgres on `127.0.0.1:5432`
- Redis on `127.0.0.1:6379`
- API on `http://127.0.0.1:8000`
- daemon supervisor for workers and channel runtimes
- frontend Vite server on `http://127.0.0.1:4173`

Useful companion commands:

```bash
make dev-status
make dev-down
```

Infra-only commands:

```bash
make dev-infra-up
make dev-infra-status
make dev-infra-down
```

The dev scripts read `.env` when present. Start from `.env.example` for local
overrides and never commit real credentials.

## Manual Runtime Flow

The default local runtime uses Postgres and Redis. SQLite is only an explicit
lightweight fallback or test backend.

```bash
source scripts/dev/infra-env.sh
python -m crxzipple.main db upgrade head
python -m crxzipple.main serve
```

In another terminal:

```bash
source scripts/dev/infra-env.sh
python -m crxzipple.main daemon run --service-set workers --service-set channels-stack
python -m crxzipple.main daemon status
```

In another terminal:

```bash
cd frontend
npm run dev
```

## Repository Layout

```text
src/crxzipple/
  bootstrap/        composition root and dependency wiring
  core/             settings, database, logging, process config
  interfaces/       HTTP and CLI entrypoints
  modules/          bounded contexts
  shared/           cross-module primitives and contracts

frontend/           Vue 3 runtime console
config/             local profile and policy config
tools/              bundled tool packages and provider manifests
docs/               active architecture and UI docs
tests/              unit and integration-oriented test suites
alembic/            database migrations
scripts/dev/        local stack scripts
```

Each bounded context follows the same internal layering:

- `domain`: entities, value objects, domain exceptions, repository protocols.
- `application`: use cases, services, ports, query services, runtime services.
- `infrastructure`: SQLAlchemy repositories, file/Redis stores, external
  adapters.
- `interfaces`: HTTP/CLI DTOs, routers, serializers. Keep this layer thin.

`src/crxzipple/bootstrap/container.py` is the composition root. Add wiring
there, not business behavior.

## Modules

Current bounded contexts under `src/crxzipple/modules` include:

- `access`: external provider/account/credential readiness and inventory.
- `agent`: agent profiles, home/workspace config, profile resolution.
- `artifacts`: artifact metadata, filesystem storage, preview/download.
- `authorization`: internal ABAC policy, decisions, approvals, grants, audit.
- `browser`, `mobile`, `ocr`: managed capability runtimes.
- `channels`: channel profiles, runtime bindings, delivery, dead letters.
- `daemon`: service specs, instances, leases, process supervision.
- `dispatch`: generic task dispatch lifecycle.
- `events`: topic/cursor/event backend and contract registry.
- `llm`: model/provider profiles, invocation records, adapters, token data.
- `memory`: memory files, store, indexing, retrieval, write facts.
- `operations`: observer runtime and operations read-model projections.
- `orchestration`: agent run intake, scheduler, executor, engine, waits.
- `session`: conversation/session/message persistence.
- `settings`: configuration governance, effective config, audit.
- `skills`: filesystem-backed skill catalog and validation.
- `tool`: tool catalog, tool runs, scheduler, worker, runtime adapters.

Some supporting modules, such as `delivery` and `event_relay`, provide narrower
runtime capabilities and should be treated with the same owner-boundary rules.

## Data Truth

Business facts belong to owner modules:

- orchestration owns run lifecycle and engine progress;
- tool owns tool catalog, tool runs, assignments, worker facts;
- llm owns profiles, invocations, streaming/token records;
- channels owns channel profiles, runtimes and delivery/dead-letter facts;
- session owns conversations and messages;
- access owns external credential/provider readiness;
- authorization owns internal policy and grants;
- settings owns settings resources, versions, overrides and audit;
- operations owns operations projections, not business truth.

Cross-process facts flow through the events backend. Shared local runtime should
use Redis-backed events. Do not treat an in-memory event bus as a cross-process
runtime backend.

Operations follows this path:

```text
owner module runtime fact
  -> events backend
  -> operations-observer daemon service
  -> operations projection materializer
  -> Postgres operations_projections
  -> /operations/{module}
  -> frontend Operations page
```

Frontend Operations pages should read `/operations/{module}` and
`/operations/stream`, not stitch together truth by directly calling owner
module APIs.

## Settings, Access and Authorization

These three surfaces are intentionally separate:

- Settings governs configuration resources, versions, overrides and effective
  config materialization.
- Access manages external providers, accounts, credentials, setup flows,
  readiness, inventory and external access audit.
- Authorization manages internal ABAC policy, subject/resource/context checks,
  approval-driven temporary grants, impact preview and authorization audit.

Module-owned entities remain owned by their module. For example, Agent Profile
create/update/enable/disable/delete operations go through the Agent application
service. Settings may provide a centralized governance view or orchestration of
owner-module actions, but it must not become a generic proxy that rewrites owner
truth behind the module.

## UI

The current UI source is `frontend/`.

Routes:

- `/workbench`
- `/workbench/threads/:sessionKey`
- `/workbench/runs/:runId`
- `/operations/:module?`
- `/trace/:traceId?`
- `/settings/:resource?`

Operations modules currently include orchestration, tool, llm, access,
channels, memory, skills, events and daemon. Settings resources include
overview, agent profiles, llm profiles, tool catalog, skill catalog, memory
config, access assets, authorization policies, channel profiles, runtime
defaults, environment, audit logs, event registry and backup restore.

Frontend API calls should go through `frontend/src/shared/api/client.ts`.
`VITE_API_BASE` defaults to `/api`; Vite proxying should return JSON API
responses, not HTML fallbacks.

## HTTP

The unified HTTP app is `src/crxzipple/interfaces/http/app.py`.

```bash
PYTHONPATH=src python -m crxzipple.main serve
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/about
curl http://127.0.0.1:8000/daemon/status
```

Major route groups:

- `/agents`
- `/llms`
- `/tools`
- `/orchestration`
- `/operations`
- `/settings` and `/ui/settings`
- `/access` and `/ui/access`
- `/authorization`
- `/events`
- `/channels`
- `/sessions`
- `/memory/*`
- `/artifacts`
- `/daemon`

## CLI

The unified CLI entrypoint is `src/crxzipple/interfaces/cli/main.py`.

```bash
PYTHONPATH=src python -m crxzipple.main --help
PYTHONPATH=src python -m crxzipple.main about
PYTHONPATH=src python -m crxzipple.main db upgrade head
PYTHONPATH=src python -m crxzipple.main daemon status
PYTHONPATH=src python -m crxzipple.main llm sync-profiles
PYTHONPATH=src python -m crxzipple.main agent sync-profiles
PYTHONPATH=src python -m crxzipple.main tool providers
PYTHONPATH=src python -m crxzipple.main auth policies
```

Visible command groups include `agent`, `auth`, `access`, `browser`, `daemon`,
`dispatch`, `llm`, `memory`, `mobile`, `ocr`, `orchestration`, `session`,
`skills`, `tool` and `db`. Runtime/worker command groups such as
`channel-runtime`, `operations-observer`, `tool-worker`, `tool-scheduler`,
`orchestration-scheduler` and `orchestration-executor` are hidden from root
help and are normally launched by daemon service specs.

## Configuration

Important local config paths:

- `.env.example`: local environment template.
- `config/llm_profiles/`: LLM profile files.
- `config/agent_profiles/`: agent profile files.
- `config/channel_profiles/`: channel profile files.
- `config/authorization_policies/`: authorization policy files.
- `tools/*/tool.yaml`: bundled tool/provider manifests.

Useful environment variables:

```bash
APP_DATABASE_URL=postgresql+psycopg://crxzipple:crxzipple@127.0.0.1:5432/crxzipple
APP_EVENTS_BACKEND=redis
APP_EVENTS_REDIS_URL=redis://127.0.0.1:6379/0
APP_LLM_PROFILE_PATHS=./config/llm_profiles
APP_AGENT_PROFILE_PATHS=./config/agent_profiles
APP_AUTHORIZATION_ENABLED=true
APP_AUTHORIZATION_POLICY_PATHS=./config/authorization_policies
APP_LOG_LEVEL=INFO
```

Provider credentials are optional until the matching provider/tool is used.
Common examples are `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `GEMINI_API_KEY`,
`BRAVE_SEARCH_API_KEY` and `ITICK_API_TOKEN`.

## Tools

Bundled tool namespaces are stored under `tools/`; each direct child should
include `tool.yaml`.

Current bundled namespaces include:

- `brave_search`
- `browser`
- `command`
- `debug`
- `itick_market`
- `memory`
- `mobile`
- `open_meteo_geocoding`
- `open_meteo_weather`
- `openai_image`
- `sessions`
- `skills`
- `workspace`

See `tools/README.md` and `src/crxzipple/modules/tool/README.md` for tool
manifest and runtime details.

## Development Checks

Run targeted checks for the area you changed. Common commands:

```bash
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py
PYTHONPATH=src pytest -q tests/unit/test_tool_background.py
PYTHONPATH=src pytest -q tests/unit/test_agent_http.py
PYTHONPATH=src pytest -q tests/unit/test_authorization.py
```

Frontend:

```bash
cd frontend
npm run typecheck
npm run build
npm run audit:operations-layout
```

Use `APP_DATABASE_URL` with the same database you are developing against when
running schema-dependent tests or CLI commands.

## Agent Development Contract

Hosted coding agents should start from:

- `AGENTS.md`
- `docs/README.md`
- `docs/agents/hosted-agent-operating-contract.md`

The most important rules:

- inspect the dirty worktree before editing;
- do not revert user changes;
- do not add compatibility layers for retired structures;
- identify the owner module and data truth before changing behavior;
- keep long-running services under daemon;
- keep Operations event/projection-driven;
- keep Settings as governance, not owner-module replacement.

## More Documentation

- `docs/README.md`: active documentation index.
- `docs/orchestration-design.md`: orchestration architecture.
- `docs/operations-data-truth-audit.md`: operations data truth and projection
  model.
- `docs/ui/current-ui-design-functional-spec.md`: current UI design/function
  spec.
- `docs/ui/runtime-ui-read-model-contracts.md`: UI read-model contracts.
- `src/crxzipple/modules/daemon/README.md`: daemon/runtime notes.
- `src/crxzipple/modules/tool/README.md`: tool runtime notes.
- `tests/unit/README.md`: test-suite notes.
