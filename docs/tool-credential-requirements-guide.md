# Tool Credential Requirements Guide

Tool packages declare external credentials as Access-owned requirements. Tool
code and manifests must not point directly at `env:`, `file:`, raw tokens, or
local auth files. The only value a tool should carry is an Access credential
binding id.

## Contract

Every credential need is expressed as a requirement set:

```yaml
credential_requirements:
  - requirement_set_id: my_tool.credentials
    requirements:
      - requirement_id: my_tool.api_key
        slot: api_key
        display_name: API key
        expected_kind: api_key
        binding_id: provider-api-key
        provider: provider_name
        transport: runtime_context
        setup_flow_hint:
          flow_kind: manual
          provider: provider_name
```

Use stable `slot` names. UI and Access actions bind credentials by slot, so a
renamed slot is a breaking configuration change.

Persisted ToolFunction / ToolProviderBackend records normalize each requirement
into the shared Access structure. Runtime handlers should treat the manifest as
authoring input only; the execution path receives resolved binding ids through
the Tool catalog and provider backend context.

## OpenAPI Tools

OpenAPI providers use `securitySchemes` and operation/global `security` to
generate requirement declarations. The provider manifest maps scheme names to
Access binding ids:

```yaml
kind: openapi
namespace: brave_search
spec: openapi.json
credentials:
  SubscriptionToken: brave-search-api-key
```

For basic auth, use username/password binding ids:

```yaml
credentials:
  BasicAuth:
    username_binding_id: provider-basic-username
    password_binding_id: provider-basic-password
```

Do not use `source`, `username_source`, `password_source`, `env:`, `file:`, raw
tokens, or other direct credential sources in OpenAPI provider config.

## Native / Local Tools

Native tools declare the same `credential_requirements` field in `tool.yaml`.
At runtime, resolve the binding through the typed dependency object injected by
tool package activation. Tool handlers must not reach into the app container or
arbitrary registry values. Example:

```python
api_key = deps.credential_provider.resolve_credential(
    "provider-api-key",
    consumer=consumer_ref,
)
```

Runtime options such as base URL, model name, timeout, and retry count may still
come from regular configuration. Secrets do not.

## Provider Backends

Provider backends are Tool-owned runtime suppliers for stable function
capabilities such as `image_generation`, `web_search`, or provider-hosted
media APIs. A backend declares its own credential requirements and runtime
requirements:

```yaml
provider_backends:
  - backend_id: openai_image.default
    display_name: OpenAI Images
    capability: image_generation
    runtime_kind: local
    runtime_ref: openai_image_generate
    credential_requirements:
      - requirement_set_id: openai_image.backend.credentials
        requirements:
          - requirement_id: openai_image.backend.openai_api_key
            slot: openai_api_key
            expected_kind: api_key
            binding_id: openai-api-key
            provider: openai
            transport: runtime_context
```

Stable functions opt into backend resolution with `provider_backend_policy`
metadata generated from the backend's `stable_functions` list. Tool submission
selects an active backend, records the selected backend id in
`ToolRun.metadata.provider_backend`, and injects a `provider_backend` payload
into the execution context. Handlers read binding ids from that context and
resolve secret material through the injected credential provider.

Provider backend readiness is owned by the Tool application service. It
aggregates Access credential readiness and runtime requirement readiness, then
exposes the same payload to `/tools/provider-backends`, Settings Tool Catalog,
and Operations Tool Provider Backend Health.

## Expected Kinds

Use the narrowest matching kind:

- `api_key` for header/query API keys.
- `bearer_token` for token strings used in Authorization headers.
- `basic` for HTTP basic username/password slots.
- `app_secret` for provider app secrets such as Lark app secret.
- `webhook_secret` for inbound signature or verification secrets.
- `oauth2_account` / `openid_connect` for user/account OAuth grants.

The UI filters candidate bindings by `expected_kind`. If a binding kind does not
match, Access reports `kind_mismatch`.

## Redaction

Tool responses, run metadata, logs, and errors must not include credential
values. Show binding ids or masked previews only. URL sanitization must redact
query credentials before recording request metadata.
