# Tool Module

This bounded context models a tool platform that can be used directly by
interfaces and reused by other bounded contexts such as `agent`.

## Core concepts

- `Tool`: aggregate root for a tool definition and execution contract
- `ToolRun`: aggregate root for one execution attempt with runtime lifecycle
- `ToolSource`: Tool-owned source declaration such as bundled local package,
  OpenAPI, MCP, CLI, or provider backend source.
- `ToolFunction`: stable executable catalog row produced by source discovery.
- `ToolProviderBackend`: Tool-owned runtime supplier for provider capabilities
  such as image generation.
- `ToolSpec`: local package authoring manifest that gets translated into
  discovery candidates.
- `ToolExecutionSupport`: the supported `mode + strategy + environment` matrix
- `ToolExecutionTarget`: the concrete execution target chosen for a run
- `ToolCatalogSourceKind`: source declaration kind for catalog governance.
- `ToolFunctionRuntimeKind`: runtime surface used to execute a catalog function.

## What belongs here

- Tool source/function/backend metadata and discovery information
- Input contract and parameter definitions
- Execution guardrails such as timeout, confirmation, and state mutation
- Execution support across:
  - modes: `inline`, `background`
  - strategies: `async`, `thread`, `process`
  - environments: `local`, `sandbox`, `remote`
- Local package, OpenAPI, MCP, CLI, and provider backend source discovery
- Per-run lifecycle state such as `created`, `running`, `succeeded`, and `failed`
- Availability state (`active` / `disabled` / `stale` / `deprecated` /
  `deleted`)
- Background execution handoff for local async runs
- Runtime routing across `local`, `sandbox`, and `remote` adapters

## Runtime organization

The tool application is split into explicit runtime-facing services:

- `ToolCatalogService` owns process-local debug registrations and delegates
  production definitions to the Tool source/function catalog.
- `ToolSubmissionService` validates requested tool targets, creates tool runs,
  executes inline runs, and enqueues background runs.
- `ToolBackgroundSchedulerService` assigns queued background tool runs to
  available tool workers through the dispatch backend.
- `ToolWorkerService` owns tool worker registration, heartbeats, assigned-run
  execution, cancellation, recovery, and terminal lifecycle updates.
- `ToolApplicationService` is the public tool application surface used by
  interfaces and other modules. It does not own scheduler or worker runtime
  methods.
- `ToolProviderBackendReadinessEvaluator` aggregates Access credential readiness
  and runtime requirements for provider backends; Settings and Operations
  consume that query surface instead of interpreting backend credentials
  themselves.

The scheduler and worker are intentionally separate. The scheduler decides which
worker gets a queued background run. The worker executes assigned runs and may
process multiple in-flight assignments concurrently through its async runtime
loop when `max_in_flight > 1`.

Tool workers report tool lifecycle state only. They do not complete or mutate an
orchestration run. Orchestration observes terminal tool events and decides how to
resume an outer agent run.

## What does not belong here

- Conversation or session lifecycle
- Agent-specific orchestration rules
- Concrete tool business logic such as workspace/file tools or debug/demo tools
- External credential governance, setup, rotation, and audit. Tools declare
  credential requirements and resolve Access binding ids at runtime; they do
  not read secret sources directly.

Those concerns should stay in other bounded contexts and reference tools by id.

## Credential requirements

Tool packages declare external credential needs through structured credential
requirements. See
[`docs/tool-credential-requirements-guide.md`](../../../../docs/tool-credential-requirements-guide.md)
for the authoring contract.

- OpenAPI provider `credentials` map security scheme names to Access binding ids.
- Native/local packages use the `credential_requirements` manifest field.
- Runtime code resolves binding ids through typed dependencies and the injected
  Access credential provider.
- Provider backend handlers receive the selected backend context through
  `ToolExecutionContext.provider_backend`; they read binding ids from that
  context instead of hardcoding secret sources.
- `env:`, `file:`, raw tokens, and inline secret sources are
  not accepted in tool manifests or provider config.

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
- Runtime resolution never triggers provider discovery or runtime registry
  backfill. Source/function catalog rows are the definition truth; the local
  runtime registry only maps active catalog function `handler_ref` values to
  in-process handlers.
- Re-running discovery refreshes source/function/backend catalog rows when the
  source contract changes while preserving user-governed fields.
- Recursive filesystem `tool.json` discovery is retired. Executable local tools
  must enter the source/function catalog through `local_package` source manifests
  and package activation.
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
- A single tool worker process can execute multiple I/O-heavy background runs
  concurrently by running with `--max-in-flight > 1`; daemon-managed workers
  default to Settings `runtime-defaults/defaults` `tool_worker.max_in_flight`
- Background scheduling also applies per-capability run limits before claiming
  work: image tools default to the worker capacity, while shared-state local
  tools such as browser, command, workspace, mobile, and session tools default to
  one in-flight run per capability group. Tune with Settings Runtime Defaults
  `tool_worker.default_run_concurrency`, `tool_worker.image_run_concurrency`,
  and `tool_worker.shared_state_run_concurrency`.
- The sandbox runner isolates execution in a temporary working directory under
  `APP_SANDBOX_BASE_DIR`
- `APP_SANDBOX_BACKEND` now selects `subprocess` or `docker`
- Docker sandbox execution uses `APP_SANDBOX_DOCKER_BINARY` and
  `APP_SANDBOX_DOCKER_IMAGE`
- Cross-process worker wake-up and lifecycle observation require a shared events
  backend. The in-memory backend is process-local and should be treated as a
  test/local-single-process backend only.

## Current source path

- bundled tool namespaces are governed from repository `tools/*/tool.yaml`
- local packages, OpenAPI specs, MCP sources, CLI sources, and provider
  backends all materialize into Tool-owned source/function/backend catalog rows
- process-local registrations remain a debug/test overlay and are not the
  production catalog truth
- bundled OpenAPI namespaces: discover remote HTTP tools from
  `tools/<namespace>/tool.yaml` + colocated spec files and register matching
  remote runtime handlers
- configured OpenAPI providers: explicit override path for remote HTTP tools
- configured MCP providers: discover tools over a lightweight stdio `tools/list`
  call and invoke them through `tools/call`
- configured CLI sources: execute governed argv sessions through
  `cli_help`, `cli_execute`, `cli_read_output`, and `cli_cancel`; help output is
  not parsed into trusted tool functions

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

The current CLI source path supports:

- governed executable/argv execution with allowed subcommands, denied flags,
  cwd/root policy, timeout, output limits, and Access credential injection
- guided process sessions for help, execute, output polling, and cancellation
- explicit promoted functions declared in source config for stable high-frequency
  workflows

It intentionally does not auto-generate `ToolFunction` records from arbitrary CLI
help text. A help probe can inform a user or agent, but publishing a stable CLI
function requires an explicit promoted function contract.

## Bundled command source contract

The bundled `command` local package is the default engineering runtime source
for workspace-bound command execution.

- `exec` runs a shell command in the bound workspace.
- `process` manages background command sessions created by `exec`.
- Source-local prompt guidance lives in `tools/command/tool.yaml`; global
  runtime prompts must not duplicate command-specific strategy.
- The command source default prompt groups expose `exec` and `process` through
  Context Workspace provider mirror when the source is visible and policy allows
  the default group refs.

`exec` supports these model-facing control parameters:

- `timeout_seconds`: hard execution timeout for synchronous command execution.
- `max_output_tokens`: approximate combined stdout/stderr budget returned to the
  model. Full truncated raw output is preserved through Tool result artifacts
  and read handles when truncation occurs.
- `yield_time_ms`: optional wait budget for synchronous commands. If the command
  is still running after this many milliseconds, `exec` returns a background
  process handle instead of waiting for completion. The model should continue
  with `process poll` or `process log`. This parameter is ignored when
  `background=true`.
- `background`: start the command directly as a background process.

`exec` result metadata includes structured execution facts such as `exit_code`,
`timed_out`, `wall_time_seconds`, output budget fields, estimated output tokens,
and truncation flags. Provider-facing content remains bounded; owner facts and
artifacts keep the traceable full result path.

## Tool result envelope contract

Tool runtimes can attach `metadata["tool_result_envelope"]` to make result
replay explicit. The current envelope schema is
`2026-06-14.tool_result_envelope.v1`. `ToolRun.succeed()` normalizes the
envelope with `schema_version`, `tool_run_id`, `call_id`, and `tool_name`.

Use the envelope fields as follows:

- `provider_replay_payload`: compact content and facts that should be used by provider replay renderers.
- `user_summary_payload`: short user summary fields for Workbench.
- `trace_payload`: diagnostic details for Trace/Operations.
- `read_handles`: follow-up handles for omitted raw output, process logs, or
  artifacts.
- `artifact_refs`: durable artifact references for large text, raw output, image,
  or file material.
- `truncated`, `omitted_count`, and `omitted_chars`: explicit budget facts.

Large text blocks and raw output blocks are externalized by the Tool worker when
an artifact service is available, then merged back into the envelope as artifact
refs and read handles.

Removed legacy paths:

- `/tools/providers`, `/tools/discover`, `tool providers`, and `tool discover`
  have been removed. Use `tool sources`, `tool functions`, and explicit
  source sync commands.
- Process-local runtime registration is not a production API. Tests and
  benchmarks that need temporary tools must materialize a catalog source/function
  first, then register only the matching local runtime handler.

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
