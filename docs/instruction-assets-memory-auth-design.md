# Instruction Assets, Memory, And Access Design

## Goal

Capture the design direction for three related areas:

- `skill` as task-scoped instruction assets
- `memory` as durable knowledge and recall
- `access` as third-party connection, credential, login, and readiness control
  plane

This document also records the comparison with OpenClaw, Hermes, and Claude Code
Rev, because those systems show useful patterns and important boundary risks.

The target is not to copy one external runtime. The target is to keep
`crxzipple` modular while becoming good at consuming a richer skill and memory
ecosystem.

## Core Position

`profile`, `skill`, `memory`, `authorization`, and `access` are separate
concepts.

- `profile` is the persistent agent identity and base contract.
- `skill` is a task-scoped method and instruction package.
- `memory` is durable knowledge plus recall.
- `authorization` is the final tool/effect decision system.
- `access` prepares external connections, credentials, login state, and
  readiness.
- `orchestration` resolves and assembles these inputs into a run.

The short rule is:

```text
modules declare access requirements in their own assets
access prepares connections, credentials, login state, and setup flows
ABAC decides whether the current execution context may perform an effect
orchestration decides what is applicable and visible for this run
```

## External Systems

### OpenClaw

OpenClaw is closest to a guidance-package model with stronger metadata.

Useful patterns:

- `SKILL.md` remains the core asset.
- Skills are loaded from multiple roots with precedence.
- Skill metadata can declare runtime requirements such as binaries, env vars,
  config paths, OS, and install hints.
- Runtime eligibility can filter unavailable skills before prompt rendering.
- Skill-specific env values can be injected from user config with sanitization.

Risks to avoid:

- skill command dispatch can make skills feel like a runtime surface.
- env injection must stay tightly scoped and must not become credential leakage.

### Hermes

Hermes is the strongest example of productized skill management.

Useful patterns:

- one user-level skill repository, `~/.hermes/skills`
- bundled skill sync with a manifest that preserves user edits
- hub and optional skill installation
- readiness states such as `available`, `setup_needed`, and `unsupported`
- explicit setup metadata for env vars, credential files, and secret capture
- session-scoped env passthrough for declared skill variables

Risks to avoid:

- setup flow should not turn skills into permission owners.
- secret passthrough must exclude provider credentials that belong to the host
  runtime.

### Claude Code Rev

Claude Code Rev treats skills as executable prompt commands.

Useful patterns:

- skills can be represented as command assets.
- forked skills can select a subagent and optionally override model selection.
- system-level login and connector setup provide a good user experience.
- long-term memory and session memory are separated clearly.

Risks to avoid:

- skill becomes deeply coupled to agent runtime, hooks, compaction, tool
  permission, subagents, and session state.
- skill starts acting like a small orchestration system.

For `crxzipple`, this is useful as a comparison point, not as the model to copy.

## Skill Design

### Definition

`skill` is a task-scoped instruction asset.

It can describe:

- when it applies
- what method to follow
- which tools or capabilities the method expects
- which references, templates, assets, or scripts support the method

It must not own:

- tool authorization
- run lifecycle
- worker scheduling
- session lifecycle hooks
- subagent runtime
- compaction lifecycle

### Canonical Source

`SKILL.md` should become the canonical skill source.

The portable package shape should be:

```text
my-skill/
  SKILL.md
  references/
  templates/
  assets/
  scripts/
```

Other files are adapters or generated views:

- external ecosystem metadata
- local `crxzipple` sidecar metadata
- cached normalized manifests
- install or marketplace metadata

### Normalized Manifest

At runtime, `crxzipple` should consume a normalized manifest derived from
`SKILL.md` and optional sidecars.

Suggested fields:

- `name`
- `description`
- `version`
- `tags`
- `when_to_use`
- `anti_patterns`
- `required_tools`
- `optional_tools`
- `suggested_tools`
- `required_effects`
- `surfaces`
- `resources`
- `origin`
- `extensions`

`allowed_tools` should be avoided as a core skill term because it sounds like an
authorization decision. In this system, authorization belongs to ABAC.

Legacy or imported skill packages may contain auth-like fields such as
`required_auth`, `required_secrets`, or `required_credential_files`. Treat them
as compatibility hints only. They must not become the runtime source of truth for
credentials or login.

Current runtime callers should read the normalized `requirements` view instead
of interpreting legacy manifest fields directly. The compatibility fields remain
visible for import/reporting, but their meaning is "this external skill expects
such a credential shape", not "grant this skill credential authority".

Prompt catalog metadata should not duplicate auth-like compatibility fields as
top-level runtime fields. Runtime code that needs them should read
`requirements.compatibility_*` explicitly.

### Applicability

Skill constraints are applicability constraints, not permissions.

Examples:

- a GitHub PR review skill may require a GitHub tool capability
- a Gmail triage skill may require a Gmail tool capability
- a browser workflow skill may require browser control capability
- a memory workflow skill may require `memory_search` and `memory_read`

If those capability requirements are not satisfied, the skill is not applicable
or is shown as blocked.

This does not mean the skill is allowed to use a tool. It only means the method
needs that capability.

The credentials for those capabilities belong to the consuming module assets:
LLM profiles, channel profiles, tool packages, OpenAPI providers, CLI connector
profiles, or provider assets owned by `access`.

## Agent Profile Boundary

Agent profile should own:

- identity
- base instructions
- default model routing
- durable behavior preferences
- workspace or sandbox defaults

Agent profile should not own task-level tool preference.

The previous `tool_preferences` profile field has been removed from the runtime
profile model. Task-specific tool preference belongs in skills as
`required_tools`, `suggested_tools`, and `required_effects`.

Profile can still be an ABAC subject dimension. For example, a policy may allow
one profile to use a capability while another profile cannot. But profile is
not the place to express a workflow's preferred tool set.

## Authorization Boundary

Authorization is evaluated against the current execution context.

That context can include:

- profile baseline
- session-level grants
- run-level approvals
- surface
- tool facts
- resource attributes
- requested effects

`skill` is not an authorization subject.

`skill` can declare:

- this method needs `github.pr_write`
- this method needs `browser_control`
- this method needs `memory_search`

Authorization decides:

- whether this execution context may use the matching tool/effect now
- whether approval is needed
- whether the request must be denied

## Access Manager

### Definition

`access` is the system-level service for connection, credential, login, and
readiness state.

It is not ABAC.

It should own:

- access requirement and credential binding models
- OAuth connection flows
- connector setup status
- API key and secret capture
- credential file registration
- setup links
- readiness checks
- surface-specific setup instructions

It should not own:

- final tool allow/deny decisions
- skill selection policy
- protocol-specific request shaping
- tool execution
- run scheduling

Protocol-specific modules keep their protocol logic. For example, `access`
can resolve a bearer token, while an OpenAPI runtime still decides whether that
token becomes an `Authorization` header, query parameter, cookie, or basic-auth
header.

### Readiness States

Suggested states:

- `ready`
- `setup_needed`
- `waiting_user`
- `expired`
- `unsupported`

These states are inputs to resolver decisions and UI display. They are not
authorization outcomes by themselves.

### Surface Behavior

Setup action should adapt to surface:

- `web`: open OAuth or connector setup page
- `cli`: open browser or print an authorization URL and callback instructions
- `channel`: send setup link, QR code, or route the user to web setup

The module resolving a channel, model, tool, or connector should pass
its declared access requirement to `access`. `access` decides how to start the
setup flow for the current surface.

Current control surface:

- HTTP `POST /access/check` checks declared requirements or credential bindings
  and returns readiness plus optional `setup_flow`.
- HTTP `POST /access/setup` and `GET /access/setup` return a displayable setup
  action for one requirement or binding.
- HTTP `GET /access/inventory` discovers authorization targets used by model,
  tool, and channel assets, returning only blocked targets by default.
- CLI `crxzipple access check` and `crxzipple access setup` expose the same
  readiness and setup payloads.
- CLI `crxzipple access inventory` exposes the same aggregate readiness view for
  daemon and terminal workflows.

These surfaces must not return credential values. They only expose readiness,
missing setup reason, and safe setup instructions such as environment variable
names, file paths, login commands, or future OAuth/device-code actions.

Inventory granularity should follow access ownership, not catalog item count.
Targets should be authorization assets, credentials, or login states such as
`env:OPENAI_API_KEY`, `codex_auth_json`, `env:BRAVE_SEARCH_API_KEY`, or a
multi-field channel credential set. LLM profiles, tools, and channels should be
listed as usage metadata under the authorization target. The inventory should
not emit one target per model profile or one target per tool when those
usages share the same authorization asset.

Inventory metadata should use usage language:

- `asset_kind` describes the authorization asset, for example `env`, `file`,
  `codex_auth_json`, or `credential_set`.
- `usage_count`, `usage_types`, and `usages` describe which model, tool, or
  channel declarations depend on the asset.
- `declared_requirements` preserves the original declarations for diagnostics,
  while readiness checks use the canonical authorization target.

`setup_flow.actions` is the stable UI action protocol. Consumers should prefer
it over inferring behavior from `setup_flow.kind`. Current action kinds include
`configure_env`, `create_file`, and `run_command`; future OAuth and device-code
flows should add actions without changing existing readiness fields.

Consumer paths should preserve the same payload shape when readiness blocks
work. For example, orchestration LLM resolution and channel runtime bootstrap
use `access_not_ready` with structured details containing the relevant
`setup_flow`, so UI and daemon surfaces do not need to parse free-form error
strings.

### Suggested Requirement Shape

```yaml
credential_binding: env:OPENAI_API_KEY

credentials:
  bearerAuth:
    source: env:GITHUB_TOKEN

access:
  requirements:
    - github:oauth_connector(repo_read,pr_write)
```

The first two examples are module-owned declarations. The last example is a generic
access requirement shape that can be used by future connector/provider assets.

## Memory Design

### Definition

`memory` is a durable knowledge service.

It should own:

- memory files
- durable memory entries
- indexing
- retrieval
- citations
- flush and write-back

It should not own:

- agent runtime
- run scheduling
- session transcript truth
- prompt assembly policy

### Boundary

Use three separate truths:

- `session` owns exact transcript history
- `memory` owns durable knowledge
- `orchestration` owns compaction and maintenance timing

These should not be collapsed into one memory concept.

The orchestration-facing memory port is intentionally read-oriented:
context resolution, index warmup, search, and file excerpts. Durable writes are
not direct orchestration service calls; they happen through memory tools or a
standardized maintenance run that invokes those tools.

### Recall Model

Recall should stay explicit and controlled:

- `memory_search` finds relevant durable knowledge
- `memory_read` retrieves cited content
- prompt bootstrap may include a small stable memory block
- heavy automatic recall should be avoided by default

This keeps memory from becoming a hidden second runtime.

### Capture Model

Durable writes should happen through explicit tools or standardized maintenance.

Recommended capture paths:

- user or model explicitly writes memory through memory tools
- orchestration triggers a memory flush maintenance run at a boundary

Normal run execution should not silently mutate durable memory.

## Skill, Memory, And Auth Interaction

Typical flow:

1. `orchestration` resolves the active profile and execution context.
2. `skill` catalog is normalized from available skill packages.
3. Skill applicability checks requirements against tool availability, surface,
   and capability facts.
4. Applicable skills are injected into prompt as task guidance.
5. The model may use `skill_read` to load instructions or supporting files.
6. Model, channel, tool, or connector resolvers ask `access` about their own
   credentials before exposing or executing unavailable capabilities.
7. If a tool call is attempted, ABAC still makes the final decision.
8. Memory recall remains explicit through memory tools unless a run policy adds
   bounded bootstrap context.

## Compatibility Direction

The future compatibility layer should treat external skill packages as source
formats and compile them into a local normalized manifest.

Recommended import layers:

- source bundle: original external skill package
- normalized manifest: `crxzipple` internal view
- compatibility report: ignored, degraded, and mapped fields
- runtime prompt rendering: prompt catalog and `skill_read` resources

External ecosystems should not define internal runtime ownership.

## Migration Notes

Suggested order:

1. Make `SKILL.md` frontmatter readable as the primary manifest source.
2. Add resource inventory for `references`, `templates`, `assets`, and
   `scripts`.
3. Add normalized skill requirements for tools, surfaces, resources, and
   compatibility metadata.
4. Make orchestration skill resolution aware of surface, tool availability, and
   applicability.
5. Upgrade `skill_read` to return package metadata and resource hints.
6. Move task-level tool preferences out of agent profile and into skill
   requirements or suggestions.
7. Add `access` as the system service for credential readiness and setup flows.
8. Keep ABAC as the only final permission decision point.

Current implementation status:

- `SKILL.md` frontmatter is the primary manifest source, with legacy
  `skill.yaml` treated as a fallback or compatibility sidecar.
- Skill HTTP/CLI responses and prompt catalog metadata expose normalized
  `requirements`; public `manifest` payloads do not expose legacy
  `allowed_tools` as a core field.
- Legacy tool preferences are normalized into `requirements.suggested_tools`.
  Auth-like skill hints are exposed through `requirements.compatibility_*`
  instead of runtime-facing manifest fields.
- Orchestration skill visibility currently checks required tool applicability;
  auth-like skill fields stay compatibility metadata and do not hide skills by
  themselves.

## Non-Goals

Do not add these to skill:

- `inline` or `fork` execution semantics
- direct tool authorization
- session lifecycle hooks
- compaction hooks
- worker scheduling
- standalone skill runs

Those belong to orchestration, tool, session, memory, or authorization.

## Final Rule

Keep instruction assets, knowledge assets, connection readiness, and permission
decisions separate.

This gives `crxzipple` room to ingest external ecosystems without turning
skills into a second orchestration runtime.
