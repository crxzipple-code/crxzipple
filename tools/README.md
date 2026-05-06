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
- `openai_image`: OpenAI image generation and editing tools backed by the Images API.
  These tools are background-only because image generation/editing can be slow;
  orchestration waits for tool completion and resumes the run instead of blocking
  the inline agent worker. Requires `OPENAI_API_KEY`. Defaults to `gpt-image-2`; set
  `OPENAI_IMAGE_MODEL` to override the default model for this namespace. If
  OpenAI returns an organization-verification 403 for a GPT Image model, verify
  the API organization in Platform settings or retry with a model the
  organization can access. Long image runs default to a 300 second timeout; set
  `OPENAI_IMAGE_TIMEOUT_SECONDS` to tune it.
- `workspace`: local filesystem tools bound to the current session workspace.
  See [workspace/README.md](/Users/crxzy/Documents/crxzipple/tools/workspace/README.md).
