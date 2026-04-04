# Tool Module

This bounded context models a tool platform that can be used directly by
interfaces and reused by other bounded contexts such as `agent`.

## Core concepts

- `Tool`: aggregate root for a tool definition and execution contract
- `ToolRun`: aggregate root for one execution attempt with runtime lifecycle
- `ToolSpec`: application-layer discovery/provider manifest that gets translated
  into `Tool`
- `ToolExecutionSupport`: the supported `mode + strategy + environment` matrix
- `ToolExecutionTarget`: the concrete execution target chosen for a run
- `ToolSourceKind`: where the tool definition came from, such as manual registration
  or local discovery

## What belongs here

- Tool metadata and discovery information
- Input contract and parameter definitions
- Execution guardrails such as timeout, confirmation, and state mutation
- Execution support across:
  - modes: `inline`, `background`
  - strategies: `async`, `thread`, `process`
  - environments: `local`, `sandbox`, `remote`
- Local tool discovery and runtime binding
- Discovery providers and provider-specific manifests
- Per-run lifecycle state such as `created`, `running`, `succeeded`, and `failed`
- Availability state (`enabled` / `disabled`)
- Background execution handoff for local async runs
- Runtime routing across `local`, `sandbox`, and `remote` adapters

## What does not belong here

- Conversation or session lifecycle
- Agent-specific orchestration rules
- Concrete tool business logic such as workspace/file tools or debug/demo tools

Those concerns should stay in other bounded contexts and reference tools by id.

## Current implementation note

- `inline + async + local` executes in-process
- `inline + thread + local` executes through a real worker thread
- `inline + process + local` executes through a real child process
- `inline + async + sandbox` now executes through an isolated subprocess sandbox
- `inline + async + remote` routes through a dedicated remote runtime adapter
- `background + async + local` now persists a queued run in the database for a
  dedicated `tool-worker`
- `background + async + sandbox/remote` follows the same queued worker flow and
  resolves through the runtime router
- Tool discovery now goes through a provider registry; `discover-local` is a
  compatibility alias for provider `local_builtin`
- Re-running discovery now refreshes previously discovered non-manual tool
  definitions when the provider contract changes
- Filesystem-backed local tools can now be discovered from `tool.json`
  manifests under fixed repository paths and executed through the existing
  local runtime
- OpenAPI-backed remote tools can now be discovered through configured
  providers and executed through the `remote` runtime
- MCP-backed tools can now be discovered through configured stdio providers and
  executed through the same `remote` runtime surface
- Background runs now track `attempt_count`, `max_attempts`, `worker_id`,
  `heartbeat_at`, `lease_expires_at`, and `cancel_requested_at`
- Expired worker leases are recovered back into the queue until retry budget is
  exhausted
- Queued runs can be cancelled immediately, while running runs transition through
  `cancel_requested` before the worker closes them as `cancelled`
- The sandbox runner isolates execution in a temporary working directory under
  `APP_SANDBOX_BASE_DIR`
- `APP_SANDBOX_BACKEND` now selects `subprocess` or `docker`
- Docker sandbox execution uses `APP_SANDBOX_DOCKER_BINARY` and
  `APP_SANDBOX_DOCKER_IMAGE`
- The in-memory event bus is process-local, so background worker events are not
  visible to the caller process yet

## Current provider path

- bundled tool namespaces: governed from repository `tools/*/tool.yaml`
- `local_builtin`: discovers in-process local tools from the local catalog
- `local_filesystem`: discovers local tools from `tool.json` manifests under:
  - `.crxzipple/tools/`
  - `tools/`
- bundled OpenAPI namespaces: discover remote HTTP tools from
  `tools/<namespace>/tool.yaml` + colocated spec files and register matching
  remote runtime handlers
- configured OpenAPI providers: explicit override path for remote HTTP tools
- configured MCP providers: discover tools over a lightweight stdio `tools/list`
  call and invoke them through `tools/call`

OpenAPI discovery currently supports:

- path parameters
- query parameters
- JSON request bodies as a single `body` argument
- standard OpenAPI `securitySchemes` and operation/global `security`
  requirements
- `inline/background + async + remote`

The current MCP provider path supports:

- `tools/list` discovery from a configured stdio command
- parameter extraction from `inputSchema.properties` and `required`
- `tools/call` execution through the `remote` runtime
- a reusable local stdio MCP session with `initialize` and
  `notifications/initialized`
- `inline/background + async + remote`

It does not yet implement a full remote-capable MCP session manager or richer
transport negotiation.

The current filesystem local provider path supports:

- recursive `tool.json` discovery under the fixed repository-local tool roots
- `entrypoint` resolution using `<relative_file.py>:<callable>`
- top-level callables that work with `async`, `thread`, and `process`
- registration into the shared local runtime catalog so later CLI/HTTP/worker
  processes can execute the same discovered tools
- returning `ToolRunResult` as the recommended handler contract for keeping
  business content separate from execution metadata

Plain dict return values are no longer accepted. Tool runtimes must return
`ToolRunResult`.

Recommended local tool authoring conventions:

- export a top-level callable such as `run(arguments: dict[str, Any])`
- prefer `async def` unless the work is naturally blocking
- prefer `ToolRunResult.structured(content=..., details=..., metadata=...)` for
  structured results that should still expose explicit model-facing content
- prefer `ToolRunResult.text("...", details=..., metadata=...)` when the model
  should see a curated textual rendering
- keep model-facing multimodal content in `ToolRunResult.content`
- keep business output in `ToolRunResult.details`
- keep execution diagnostics in `ToolRunResult.metadata`
- `ToolRunResult.content` is required and must be a non-empty sequence of
  standardized content blocks
- do not use `details` as the primary transport for images, files, or model-facing
  textual output
- inline `image` / `file` blocks are automatically externalized into artifact
  refs during tool execution when the artifact service is available
- prefer lightweight attachment refs in persisted history; inline bytes should be
  treated as transient input to the LLM adapter, not long-term storage
- raise regular exceptions with clear messages and let the runtime map them into
  `ToolRunError`
- avoid mixing metadata like `process_id` or `working_directory` into
  `content`
