# Local Assistant Permissions Design

## Goal

Design permissions for `crxzipple` as a local, private AI assistant.

This is not a multi-user enterprise authorization system.

The goal is:

- safe default behavior on a personal machine
- clear agent capability boundaries
- per-session user consent
- hard runtime limits for risky tools
- simple mental model for CLI and local web usage

## Product Positioning

`crxzipple` runs locally for a trusted primary user.

This means the permission model should optimize for:

- minimizing accidental damage
- keeping prompts and tools ergonomic
- making dangerous actions explicit
- avoiding heavyweight RBAC or tenant-oriented designs

It should not optimize first for:

- organization roles
- team-level delegation
- external identity providers
- policy authoring complexity

## Current State

Today, effective tool visibility is resolved at runtime by `ToolResolver`.

Current behavior:

- all `enabled` tools are considered
- tools with `requires_confirmation=True` are hidden from LLM exposure
- authorization is checked
- when authorization is disabled, all checks allow

That means the current default is effectively:

`all enabled, non-confirmation tools are visible`

Relevant implementation:

- `ToolResolver`: `src/crxzipple/modules/orchestration/application/tool_resolver.py`
- authorization service default: `src/crxzipple/modules/authorization/application/services.py`
- tool execution policy: `src/crxzipple/modules/tool/domain/value_objects.py`

## Design Principles

### 1. Agent capabilities come first

Every agent should have a default capability boundary.

The model should only see tools that are inside that boundary.

### 2. Session grants are explicit

Some permissions should be granted only after explicit user approval.

Those approvals should be scoped.

### 3. Runtime limits are hard, not advisory

Filesystem, shell, network, and background execution limits must be enforced outside the model.

### 4. Authorization remains useful

Authorization should become the dynamic decision layer.

Agent policy should define the static boundary.

### 5. Local-first ergonomics

The user should understand permissions as:

- what this agent is allowed to do by default
- what this conversation is temporarily allowed to do
- what always requires confirmation

## Three-Layer Model

Use three permission layers.

### Layer 1: Agent Tool Policy

Static defaults attached to the agent profile.

This defines what the agent may generally see and attempt.

### Layer 2: Session Grants

Temporary approvals attached to the current conversation/session.

This defines what the user has explicitly approved for the current thread.

### Layer 3: Hard Tool Guards

Runtime-enforced limits inside tool execution and dispatch paths.

This defines what is technically possible even if the model tries.

## Agent Tool Policy

Add a new value object under the agent domain.

Suggested name:

- `AgentToolPolicy`

Suggested location:

- `src/crxzipple/modules/agent/domain/value_objects.py`

### Suggested Fields

- `default_mode: "allow" | "ask" | "deny"`
- `allowed_tool_ids: tuple[str, ...]`
- `denied_tool_ids: tuple[str, ...]`
- `allowed_tags: tuple[str, ...]`
- `denied_tags: tuple[str, ...]`
- `allow_background_tools: bool`
- `allow_mutating_tools: bool`
- `allow_network: bool`
- `allowed_domains: tuple[str, ...]`
- `allowed_paths: tuple[str, ...]`
- `allow_shell: bool`
- `allow_workspace_write: bool`

### Semantics

- `default_mode=deny`
  Only explicitly allowed tools are visible.
- `default_mode=ask`
  Tools can be proposed, but not exposed to the LLM unless a session grant exists.
- `default_mode=allow`
  Tools inside policy boundaries are exposed directly.

### Recommended Defaults

#### Read-only assistant

- `default_mode=deny`
- allow only search, weather, read-file, summarize-style tools
- `allow_mutating_tools=false`
- `allow_background_tools=false`
- `allow_network=true` only for allowed domains if needed

#### Coding assistant

- `default_mode=deny`
- allow workspace file tools
- allow shell only inside workspace
- `allow_workspace_write=true`
- `allow_background_tools=true` only if needed
- network off by default

#### Trusted local agent

- `default_mode=ask`
- broader local tool access
- mutating tools allowed only after confirmation

## Session Grants

Session grants represent approvals made by the user during an active conversation.

These are not permanent agent defaults.

Suggested new session-side model:

- `SessionGrant`

Suggested storage options:

1. store inside session metadata for a minimal first version
2. later extract into a dedicated table if querying becomes important

### Suggested Fields

- `scope: "once" | "session" | "agent_default"`
- `grant_kind: "tool" | "path" | "domain" | "capability"`
- `value`
- `created_at`
- `expires_at`
- `source_run_id`

### Example Grants

- allow tool `shell.exec` once
- allow domain `api.github.com` for this session
- allow path `/Users/crxzy/Documents/crxzipple` for this session
- allow background tool execution once

## Hard Tool Guards

Agent policy and session grants are not enough by themselves.

The runtime must still enforce hard boundaries.

### Required Guard Categories

- filesystem path guard
- workspace write guard
- shell command guard
- network domain guard
- background execution guard
- credential exposure guard

### Example Rules

- a shell tool cannot write outside `allowed_paths`
- a network tool cannot call domains outside `allowed_domains`
- background tools require both policy permission and a session grant
- state-mutating tools can require confirmation even if visible

These checks should live in the tool execution path, not only in prompt/tool exposure.

## Decision Pipeline

The effective tool set for one run step should be computed in this order:

1. start from `list_enabled_tools()`
2. remove tools blocked by hard execution support incompatibility
3. apply `AgentToolPolicy` static filtering
4. apply session grants
5. apply authorization policy evaluation
6. remove tools that still require explicit confirmation
7. expose the remaining schemas to the model

This means:

- agent policy narrows the universe
- session grants open temporary doors
- authorization makes final dynamic decisions

## ToolResolver Changes

`ToolResolver` should become the single place where these layers are composed.

Suggested responsibilities:

- load agent tool policy
- load current session grants
- apply static tool filtering
- build authorization requests with richer context
- return:
  - visible tools
  - hidden-but-requestable tools
  - confirmation-required tools

### Suggested `ResolvedToolSet` additions

- `visible_tools`
- `hidden_tools`
- `requestable_tools`
- `confirmation_required_tools`
- `blocked_reasons_by_tool`

This will make UI and debugging much easier.

## Authorization Role

Authorization should remain the dynamic policy layer.

It should answer questions like:

- is this interface allowed to use this tool now
- is this agent allowed to use a mutating tool in this environment
- does this action require obligations such as confirmation

### Recommended Direction

Use authorization obligations instead of only allow/deny.

Important obligations:

- `require_confirmation`
- `require_session_grant`
- `limit_to_workspace`
- `limit_to_domains`
- `deny_background`

This fits the current authorization model well because `AuthorizationDecision` already supports obligations.

## UX Model

For a local assistant, permissions should feel like capability prompts, not admin consoles.

### Confirmation Scopes

When a dangerous action is requested, prompt with:

- allow once
- allow for this session
- always allow for this agent
- deny

### Suggested UI Language

- `Allow this tool once`
- `Allow for this thread`
- `Always allow for this agent`
- `Not now`

### Important UX Rule

Do not show all denied tools in the main composer.

The model should only see tools that are actually usable now.

## Data Model Proposal

### Agent

Add to `AgentProfile`:

- `tool_policy: AgentToolPolicy`

### Session

Add to session metadata or a new table:

- `session_grants`

### Orchestration

Run metadata may capture:

- effective tool ids for this turn
- grant ids used
- confirmation decisions used

This is useful for auditability and debugging.

## Example Config Shape

Example agent policy payload:

```json
{
  "tool_policy": {
    "default_mode": "deny",
    "allowed_tool_ids": [
      "filesystem.read_text",
      "brave_search.news_search",
      "open_meteo_weather.forecast_weather"
    ],
    "denied_tool_ids": [
      "shell.exec",
      "filesystem.write_text"
    ],
    "allow_background_tools": false,
    "allow_mutating_tools": false,
    "allow_network": true,
    "allowed_domains": [
      "search.brave.com",
      "api.open-meteo.com"
    ],
    "allowed_paths": [],
    "allow_shell": false,
    "allow_workspace_write": false
  }
}
```

Example coding agent policy:

```json
{
  "tool_policy": {
    "default_mode": "deny",
    "allowed_tags": ["workspace", "source-control", "shell"],
    "allow_background_tools": true,
    "allow_mutating_tools": true,
    "allow_network": false,
    "allowed_paths": ["/Users/crxzy/Documents/crxzipple"],
    "allow_shell": true,
    "allow_workspace_write": true
  }
}
```

## Implementation Plan

### Phase 1

Add static agent policy.

- add `AgentToolPolicy`
- persist it in agent profiles
- update CLI/HTTP DTOs
- update frontend selectors later if needed

### Phase 2

Teach `ToolResolver` to apply agent policy before authorization.

- filter by tool id and tags
- filter background and mutating tools
- pass richer context into authorization

### Phase 3

Add session grants.

- minimal metadata-backed storage first
- allow `once` and `session` grants

### Phase 4

Add confirmation obligations.

- authorization may return `require_confirmation`
- frontend/CLI can surface explicit prompts

### Phase 5

Add hard runtime guards for filesystem, shell, and network.

These should be enforced inside tool execution, not just during visibility resolution.

## Recommended First Cut

For the first product-quality version, do not try to implement the whole model at once.

The best first cut is:

1. `AgentToolPolicy`
2. `ToolResolver` static filtering
3. hard deny of dangerous tools by default
4. session-scoped confirmation for a small set of risky capabilities

That is enough to move the product from:

`all enabled tools are effectively visible`

to:

`each agent only sees the tools it is meant to use`

## Summary

For a local private assistant, permissions should not be modeled as enterprise user roles.

They should be modeled as:

- agent default capability boundaries
- session-scoped user grants
- hard runtime guards

This fits the current `crxzipple` architecture because:

- `AgentProfile` already owns strategy
- `ToolResolver` already owns effective tool exposure
- `AuthorizationDecision` already supports dynamic checks and obligations
- `session` already exists as the natural place for temporary grants
