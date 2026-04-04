# Tools Root

`tools/` is the single governance root for bundled tool assets.

## Namespace Contract

- Each direct child under `tools/` is one tool namespace.
- Each namespace must include `tool.yaml`.
- The tool runtime scans `tools/*/tool.yaml` only.
- Python code, OpenAPI specs, and other tool assets live beside that manifest.

## Supported Namespace Kinds

### `kind: local_package`

Use for bundled Python-backed tools and runtime handlers.

Expected manifest sections:

- `namespace`
- `local_tools`
- `remote_runtimes`
- `sandbox_runtimes`

Local tool entries declare the full tool metadata plus an explicit Python
entrypoint such as `tools.workspace.local:read`.

### `kind: openapi`

Use for bundled OpenAPI-backed remote tools.

Expected manifest fields:

- `namespace`
- `spec`
- `description`
- `timeout_seconds`
- `default_effect_ids`
- `credentials`

The namespace name is used as the provider name.

## Runtime Notes

- Bundled OpenAPI namespaces are loaded by default.
- Setting `APP_TOOL_OPENAPI_PROVIDER_PATHS` switches provider loading to the
  explicit config/env path flow and disables bundled OpenAPI namespace loading.

## Bundled Namespace Notes

- `command`: local command-execution tools bound to the current session workspace.
  See [command/README.md](/Users/crxzy/Documents/crxzipple/tools/command/README.md).
- `workspace`: local filesystem tools bound to the current session workspace.
  See [workspace/README.md](/Users/crxzy/Documents/crxzipple/tools/workspace/README.md).
