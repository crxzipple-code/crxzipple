# Local Assistant Permissions Design

## Goal

Design permissions for `crxzipple` as a local, private AI assistant.

This is not a multi-user enterprise authorization system.

The goal is:

- safe default behavior on a personal machine
- clear human-owned permission boundaries
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

- `tool` declares facts, especially `required_effect_ids`
- `ToolResolver` computes visibility from:
  - tool facts
  - run/session temporary grants
  - long-term authorization rules
- if an effect is missing, the model gets `request_effect_access`
- user approval can grant:
  - once
  - for session
  - always for this agent
- long-term `always` grants are written into `auth`, not into the agent profile

Relevant implementation:

- `ToolResolver`: `src/crxzipple/modules/orchestration/application/tool_resolver.py`
- authorization service default: `src/crxzipple/modules/authorization/application/services.py`
- tool execution policy: `src/crxzipple/modules/tool/domain/value_objects.py`
- shared effects vocabulary: `src/crxzipple/shared/domain/effects.py`

## Design Principles

### 1. Tool facts come first

Every tool should declare its effects and runtime characteristics.

The system should reason from tool facts, not orchestration guesses.

### 2. Human authorization owns the truth

Agent profiles are not authorization truth.

Long-term rules belong to authorization.

Temporary approvals belong to run/session state.

### 3. Session grants are explicit

Some permissions should be granted only after explicit user approval.

Those approvals should be scoped.

### 4. Runtime limits are hard, not advisory

Filesystem, shell, network, and background execution limits must be enforced outside the model.

### 5. Local-first ergonomics

The user should understand permissions as:

- what this assistant is asking to do
- what this conversation is temporarily allowed to do
- what has been allowed long-term

## Permission Model

Use four layers.

### Layer 1: Tool Facts

Declared by the tool itself.

This defines what the tool requires and what side effects it can cause.

### Layer 2: Temporary Grants

Approvals attached to the current run or session.

This defines what the user has explicitly approved in the current interaction context.

### Layer 3: Long-Term Human Rules

Rules stored and evaluated by authorization.

These may include `agent_id`, `tool_id`, `effect_id`, and other context dimensions.

### Layer 4: Hard Tool Guards

Runtime-enforced limits inside tool execution and dispatch paths.

This defines what is technically possible even if the model tries.

## Agent Tool Preferences

Agent profiles may carry tool preferences, but not authorization truth.

Current name:

- `AgentToolPreferences`

Suggested location:

- `src/crxzipple/modules/agent/domain/value_objects.py`

### Current Fields

- `requested_effect_ids`
- `requested_tool_ids`
- `preferred_tags`
- `prefers_background_tools`
- `prefers_mutating_tools`

### Semantics

- these fields express intent and preference
- they do not mean `allow`
- they do not mean `deny`
- they should not be treated as authorization truth

## Session Grants

Temporary grants represent approvals made by the user during an active conversation.

These are not permanent agent defaults.

Suggested new session-side model:

- `SessionGrant`

Suggested storage options:

1. store inside session metadata for a minimal first version
2. later extract into a dedicated table if querying becomes important

### Suggested Fields

- `scope: "once" | "session"`
- `grant_kind: "tool" | "path" | "domain" | "effect"`
- `value`
- `created_at`
- `expires_at`
- `source_run_id`

### Example Grants

- allow tool `shell.exec` once
- allow domain `api.github.com` for this session
- allow path `/Users/crxzy/Documents/crxzipple` for this session
- allow background execution once

## Long-Term Authorization Rules

Long-term rules belong to authorization, not to agents.

Examples:

- allow `agent_id=writer` to access `effect_id=workspace_write`
- deny `tool_id=shell.exec` for every agent
- allow `agent_id=researcher` to access `tool_id=brave_search.news_search`

Important:

- `agent_id` is a rule condition
- `agent profile` is not the source of authority

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
3. apply explicit `tool.access_tool` deny from auth
4. apply explicit `tool.access_tool` allow from auth
5. apply run/session temporary grants
6. apply explicit `tool.access_effect` deny from auth
7. check whether `required_effect_ids` are satisfied by grants or auth rules
8. if not satisfied, expose `request_effect_access`
9. expose the remaining tool schemas to the model

This means:

- tool facts define requirements
- temporary grants open short-lived doors
- authorization owns long-term rules and fine-grained overrides

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

### Current `ResolvedToolSet` shape

- visible tools
- optional `effect_request` surface
- askable effects derived from missing required effects

## Authorization Role

Authorization should remain the long-term dynamic policy layer.

It should answer questions like:

- is this agent allowed long-term to access this effect
- is this specific tool denied even if its effects are generally safe
- is this specific tool explicitly allowed as an override
- is this tool allowed to run in this environment

## UX Model

For a local assistant, permissions should feel like capability prompts, not admin consoles.

### Confirmation Scopes

When a dangerous action is requested, prompt with:

- allow once
- allow for this session
- always allow for this agent
- deny

### Suggested UI Language

- `Allow this effect once`
- `Allow for this thread`
- `Always allow for this agent`
- `Not now`

### Important UX Rule

Do not show all denied tools in the main composer.

The model should only see tools that are actually usable now.

## Data Model Proposal

### Agent

Keep in `AgentProfile`:

- `tool_preferences: AgentToolPreferences`

### Session

Add to session metadata or a new table:

- `tool_grants.effect_ids`
- `tool_grants.tool_ids`

### Orchestration

Run metadata may capture:

- `granted_effect_ids_once`
- `granted_tool_ids_once`
- pending approval request state

This is useful for auditability and debugging.

## Example Config Shape

Example agent preferences payload:

```json
{
  "tool_preferences": {
    "requested_effect_ids": [
      "network_search",
      "weather_data"
    ],
    "requested_tool_ids": [
      "brave_search.news_search"
    ],
    "preferred_tags": [
      "search"
    ],
    "prefers_background_tools": false,
    "prefers_mutating_tools": false
  }
}
```

Example coding agent preferences:

```json
{
  "tool_preferences": {
    "requested_effect_ids": [
      "workspace_write",
      "command_execution"
    ],
    "preferred_tags": ["workspace", "shell"],
    "prefers_background_tools": true,
    "prefers_mutating_tools": true
  }
}
```

## Implementation Plan

Most of this is now implemented.

The main remaining step is:

- make runtime hard guards fully effect-aware so filesystem, shell, and network enforcement use the same shared effect vocabulary as visibility and approval

## Summary

For a local private assistant, permissions should not be modeled as enterprise user roles.

They should be modeled as:

- tool-declared effects and runtime facts
- session/run-scoped user grants
- human-owned long-term authorization rules
- hard runtime guards

This fits the current `crxzipple` architecture because:

- `tool` now declares `required_effect_ids`
- `ToolResolver` already owns effective tool exposure
- `auth` already owns long-term dynamic policy decisions
- `session` and `run` already exist as natural places for temporary grants
