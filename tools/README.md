# Tool Source Authoring Contract

`tools/` contains bundled Tool sources. Each direct child directory is one
namespace and must include `tool.yaml`.

The runtime treats these manifests as source declarations:

```text
tools/<namespace>/tool.yaml
  -> bundled ToolSource
  -> discovery candidate
  -> ToolFunction catalog row
  -> runtime handler registration
```

`tool.yaml` is not a side-effect loader and it is not the whole catalog truth.
Tool source/function rows own effective enablement, policy overrides, credential
bindings, stale/deprecated state, and discovery history. Local runtime registries
only map active function `handler_ref` values to handlers.

## Namespace Rules

- Directory name and `namespace` must match.
- `kind` must be `local_package` or `openapi` for bundled sources.
- Tool ids and runtime keys must be unique across the bundled package set.
- Required dependencies must be declared in `dependencies` at package or tool
  level; missing required services fail app activation.
- Capabilities must be declared with `capabilities` and must exist in the Tool
  capability catalog.
- External credentials must be declared as Access credential requirements or
  OpenAPI credential bindings. Do not declare `env:`, `file:`, raw tokens, or
  inline secret source references in tool manifests.

## Local Package

Use `kind: local_package` for Python-backed tools.

Required top-level fields:

- `kind: local_package`
- `namespace`
- `local_tools`

Optional top-level fields:

- `capabilities`
- `dependencies`
- `prompt`
- `remote_runtimes`
- `sandbox_runtimes`

Each `local_tools` entry declares user-facing function metadata and the handler
entrypoint. Example:

```yaml
kind: local_package
namespace: example
capabilities:
  - workspace.read
dependencies:
  - id: session_workspace_lookup
    kind: service_dependency
local_tools:
  - id: example_read
    name: Example Read
    description: Read an example resource.
    provider_name: local_system
    entrypoint: tools.example.local:example_read
    tool_kind: function
    parameters:
      - name: path
        data_type: string
        description: Relative path.
        required: true
    supported_modes: [inline]
    supported_strategies: [async]
    supported_environments: [local]
    runtime_key: example_read
```

Handler factories receive typed dependency objects built from declared
dependencies. They must not look up a container, resolver, registry, or owner
module service at execution time.

## OpenAPI Source

Use `kind: openapi` for bundled remote HTTP tools. The namespace becomes the
source namespace; operations become ToolFunction candidates during source sync.

Expected fields:

- `kind: openapi`
- `namespace`
- `spec`
- `description`
- `timeout_seconds`
- `default_effect_ids`
- `credentials`

Credential bindings reference Access binding ids, not secret source locations.

## Prompt Bundle Metadata

Every bundled source may declare a prompt-facing ability bundle. The source is
the stable grouping boundary; `prompt` only controls how that bundle is
introduced to the agent. Do not use source-kind labels such as "OpenAPI",
"MCP", or "local package" as the bundle title.

```yaml
prompt:
  title: Workspace Files
  summary: Inspect, search, read, and edit files inside the session-bound workspace.
```

For very large sources, `prompt.groups` can divide functions inside that single
source. Groups must declare exact function ids; the system will not infer groups
from names, tags, source kind, or capability ids.
Use `order` when prompt display order matters; source config is otherwise
normalized for stable hashing.

```yaml
prompt:
  title: Browser Automation
  summary: Operate browser profiles, tabs, pages, DOM snapshots, network traces, and diagnostics.
  groups:
    navigation:
      order: 10
      title: Navigation
      summary: Open pages, switch tabs, and wait for page state.
      function_ids:
        - browser.navigate
        - browser.tabs.list
```

## Runtime Behavior

- App assembly first syncs bundled sources into the ToolSource repository.
- Discovery reconciles candidates into ToolFunction rows.
- Package activation registers only active local function `handler_ref` values.
- Disabled, stale, deprecated, deleted, or missing function/source rows do not
  become runtime handlers.
- Recursive filesystem `tool.json` discovery is retired. New local tools must
  enter as `local_package` sources with `tool.yaml`; source sync then materializes
  `ToolFunction` rows before any runtime handler can be used.

## Bundled Namespace Notes

- `browser`: local browser automation tools backed by Browser owner services and
  daemon-managed profile runtime. The stable source id is
  `bundled.local_package.browser`; browser profile is runtime context, not a
  separate Tool Source.
- `command`: local command-execution tools bound to the current session
  workspace.
- `openai_image`: OpenAI image generation and editing tools backed by the Images
  API. Requires the `openai-api-key` Access credential binding and runs through
  background tool execution.
- `workspace`: local filesystem tools bound to the current session workspace.
