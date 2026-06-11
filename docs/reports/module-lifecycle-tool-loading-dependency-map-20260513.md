# Module Lifecycle Tool Loading Dependency Map 2026-05-13

This snapshot records the current Tool loading dependency graph for the P0/P7
architecture guards in
`docs/reports/module-lifecycle-tool-loading-checklist-20260513.md`.

It is a baseline, not a target design. Production code may still contain these
dependencies during migration; the target is to move them behind explicit
activation plans and typed handler dependencies.

## Acceptance Review Scope

P4 implementation has landed for the app assembly path:
`runtime_plan()` delegates scanned package activation to
`app/assembly/tool_packages.py::activate_tool_packages(...)`. The app assembly
package activation helper owns the direct `ToolPackageApplyContext`
construction, resolves
`ResolvedToolPackageActivation` entries, and calls `apply_tool_package_plans(...)`
once. P5 readiness has also landed for Tool execution: Access-backed
credential/access requirements, OAuth account bindings, and daemon runtime
requirements are checked before run creation. The internal dependency startup
gate has also landed for tool packages: missing required service dependencies
fail activation before runtime event services are constructed. Operations Tool
UI/read model classification also uses combined Tool readiness to distinguish
credential setup from runtime setup/degradation.

The completed P3 baseline is:

- Scanned tool packages are loaded through one apply hook.
- `_build_tool_infrastructure()` scans package metadata and builds Tool core
  registries/gateway only.
- `runtime_plan()` runs the `tool.activate_packages` activation task after owner
  module service references exist; app assembly applies
  local/OpenAPI/remote/sandbox handlers once.
- `app/container.py` does not contain the previous two-phase
  `include_local=False` / `include_runtimes=False` registration split.

## Current App Assembly Flow

```text
build_runtime_app_container(target)
  -> runtime_plan()
  -> tool_core_factories()
       -> discover_tool_namespaces()
       -> builds Tool core registries/gateway only
  -> tool_execution_factories()
       -> build Tool service graph and AppKey.TOOL_SERVICE
  -> orchestration_factories()
       -> builds orchestration graph with ToolServiceAdapter(AppKey.TOOL_SERVICE)
  -> tool.activate_packages
       -> activate_tool_packages_from_context(...)
       -> activate_tool_packages(...)
       -> ToolPackageApplyContext(explicit dependency bindings, registries, settings)
       -> apply_tool_package_plans(..., include_openapi=dynamic)
       -> resolves and registers scanned local/OpenAPI/remote/sandbox handlers once
```

`activate_tool_packages()` is now the app activation scanned package stage;
`app/assembly/tool.py` declares the activation task and delegates package apply
to `app/assembly/tool_packages.py`, which owns the direct
`apply_tool_package_plans()` call. The previous two-phase split has been removed
from the runtime container path: scan once, resolve dependencies once, apply
local/openapi/runtime handlers once.
The old `register_tool_namespaces(...)` compatibility entrypoint has been
removed.
The old `register_scanned_tool_packages(...)` wrapper has also been removed;
the sandbox worker follows the same explicit plan/apply path and disables
local/OpenAPI registration for its isolated runtime.

P6 container narrowing has landed: the app assembly tool core plan exposes
`tool_core_factories()`, its scanned package list is named
`tool_package_plans`, and `AppContainer` no longer exposes
`tool_discovery_registry`, `sandbox_tool_registry`, or a duplicate
`credential_provider` alias. It also no longer exposes app-assembly-only config
snapshots and runtime state handles such as `browser_system_config`,
`mobile_state_root`, or `daemon_state_root`. Operations source read models now
receive an explicit `OperationsSourceReadModelContext` instead of an anonymous
`SimpleNamespace`; the context lists only the owner application/query services
used for operations projections and exposes the observer runtime through a
named attachment method.
Architecture guards also pin the runtime startup boundary: Access/Daemon
readiness adapters and scanned package apply must be declared by app assembly;
event relay, operations observer, orchestration scheduler runtime, and tool
runtime event services are constructed by target-specific `runtime_plan()`
factories after their explicit requirements exist.
Tool apply now rejects duplicate namespaces, tool ids, and runtime keys before
registration; the runtime registry and discovery registry also fail fast on
duplicate direct registration instead of silently overwriting. `LocalToolRuntimeRegistry`
is now only the local runtime handler registry and continues to support explicit
test/development handler replacement; source/function catalog remains the tool
definition truth.
Architecture tests now scan handler/runtime implementation paths to prevent
`AppContainer`, `SimpleNamespace`, `PortResolver`, broad `container` objects, and
`orchestration_*_lookup` from returning to Tool handler execution.
The composition root now lives in app assembly: browser/mobile/daemon/ocr,
events, event runtime and core runtime service graph builders live under
`src/crxzipple/app/assembly/*`. `app/container.py` only wraps the assembled
registry and no longer owns detailed infrastructure recipes.

## Current Handler Dependency Surface

The current local handler constructor object is `ToolHandlerFactoryDeps`, created
from `ToolPackageApplyContext` and each tool manifest's dependency declarations.
Tool handlers must not receive a broad container or resolver object.

| Dependency | Current source | Current consumers | Target shape |
| --- | --- | --- | --- |
| `credential_provider` / Access service | `ToolDependencyBinding` | OpenAI image, OpenAPI runtime handlers, credential-aware tools | Explicit credential/readiness port in handler deps |
| `artifact_service` | `ToolDependencyBinding` | OpenAI image, browser tools | Explicit artifact application port |
| `memory_runtime_service` | `ToolDependencyBinding` | memory-local tools | Explicit scoped memory recall/remember runtime port |
| `process_service` | `ToolDependencyBinding` | process/session tools | Explicit process application port |
| `session_service` | `ToolDependencyBinding` | sessions tools | Explicit session application/query port |
| `session_runtime_control` | `ToolDependencyBinding` backed by app assembly | sessions tools | Session runtime port; orchestration-specific implementation stays outside Tool |
| `session_workspace_lookup` | `ToolDependencyBinding` closure | workspace/command tools | Explicit session workspace query port |
| `skill_manager` | `ToolDependencyBinding` | skill tools | Explicit skill catalog/readiness port |
| `browser_*` services and serializers | `ToolDependencyBinding` | browser local tools | Explicit browser runtime deps object |
| `mobile_*` services and serializers | `ToolDependencyBinding` | mobile local tools | Explicit mobile runtime deps object |

## Handler Lookup Migration Surface

The P5 surface is closed for this scope. Sessions tools use the
`session_runtime_control` port; orchestration-backed behavior is assembled
outside Tool. The old `orchestration_*_service_lookup` deferred
lambdas have been removed from the Tool apply adapter.

Typed dependency migration must preserve these boundaries:

- Handler factories declare required internal service dependencies before apply.
- Handler factories receive typed dependency objects or explicit fields, not
  `SimpleNamespace`, `PortResolver`, `container`, or `resolver`.
- OpenAI image uses an `OpenAIImageDeps`-style object with
  `credential_provider`; its dependencies are declared in
  `tools/openai_image/tool.yaml` and resolved through the generic
  `ToolHandlerFactoryDeps` path, not through an `openai_image` namespace
  special case. Its old `_legacy_deps` fallback has been removed, so tests or
  runtime code must pass typed deps rather than a container-shaped object.
- Memory local tools use `MemoryToolDeps` with `memory_runtime_service`; the
  runtime service owns scoped recall/remember and fails during apply when
  absent.
- Workspace and command tools use typed dependency objects with
  `session_workspace_lookup` and `process_service` instead of reading those
  dependencies from a runtime container.
- Browser/mobile/session/skill handlers use their own typed deps
  objects instead of sharing a broad service locator.
- No local tool handler receives Orchestration services directly. Sessions tools
  use the Session-owned `session_runtime_control` port; the Orchestration-backed
  implementation is assembled outside Tool.
- Missing required internal dependencies fail during resolve/apply, not through
  `getattr(container, "...", None)` checks inside handlers.

The P5 readiness surface must then classify dependency problems before runtime:

- Missing internal service dependencies fail activation and prevent worker or
  orchestration executor startup.
- Missing Access credential/access requirements produce Tool readiness states
  before execution is queued. `POST /tools/{tool_id}/runs` rejects them before
  creating a run.
- Missing OAuth account/token readiness is covered through Access credential
  binding checks.
- Missing daemon readiness now produces catalog/readiness states such as
  `setup_needed` or `degraded`; run submission rejects before creating a run.
- Missing `openai-api-key` binding for OpenAI image appears before execution is
  queued; handler execution is no longer the first readiness check.

## P0 Guard Contract

These rules are current architecture constraints even while the production code
is still migrating:

- Tool handler runtime paths must not hold `AppContainer`.
- Tool handler constructors/factories must not accept `SimpleNamespace`,
  `PortResolver`, `container`, or `resolver` as stable dependency objects.
- Tool handler execution paths must not perform delayed
  `orchestration_*_lookup` service discovery.
- `tools/*/tool.yaml` remains a Tool module resource protocol; module lifecycle
  or kernel code must not parse tool package manifests directly.
- `app/assembly/tool.py` declares the clearly named `tool.activate_packages`
  phase, while `app/assembly/tool_packages.py` owns package activation details;
  `app/container.py` must not call `register_tool_namespaces(...)` or construct
  a package apply context.

## P7 Regression Plan

Architecture tests now guard both governance text and the production app
assembly shape for the landed P4 apply context.

P5 implementation tests now cover Access credential, OAuth account, daemon
runtime readiness, required internal dependency fail-fast, and Operations Tool
readiness classification:

- Tool namespaces are scanned once.
- Local, OpenAPI, remote runtime, and sandbox runtime handlers are applied once.
- Duplicate tool id or namespace registration fails fast or is explicitly
  idempotent; it must not silently overwrite handlers.
- OpenAI image handlers receive a typed dependency object with
  `credential_provider`; they do not inspect container/resolver objects at
  execution time.
- Missing required internal service dependencies fail activation before worker
  or orchestration executor startup.
- Missing external credentials such as `openai-api-key` appear as setup
  readiness state before execution is queued.
- HTTP readiness and run submission agree for tools with missing Access
  requirements, and run records are not created.
- Missing OAuth account/token readiness is reported before execution is queued.
- Missing daemon runtime readiness is reported before execution is queued; run
  records are not created until the daemon requirement becomes ready.
- Operations Tool risk rows classify Access and Runtime readiness separately.
- Orchestration construction depends on `ToolExecutionPort`, not on scanned
  handler installation state.
- Tool background worker and orchestration executor startup happen after
  readiness checks.
