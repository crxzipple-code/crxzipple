# Agent Workspace Bootstrap Design

## Goal

Make `agent.runtime_preferences.workspace` actually participate in prompt construction.

The mechanism should:

- resolve a workspace directory for the current run
- load a small set of trusted workspace bootstrap files
- inject their contents into system prompt space
- keep boundary validation and prompt-size limits outside `PromptAssembler`

This should follow the same broad shape as OpenClaw:

- workspace resolution
- bootstrap file loading
- context-file assembly
- prompt injection

## Current State

Today `crxzipple` has:

- `AgentRuntimePreferences.workspace`
- `PromptAssembler`
- `Session` transcript assembly

But it does **not** have:

- workspace resolution for runs
- bootstrap file loading
- AGENTS/TOOLS/IDENTITY style prompt injection

`PromptAssembler` currently only injects:

- `profile.instruction_policy.system_prompt`
- optional effect request instruction
- session messages

## Design Principles

1. `agent` stores preferred workspace path, but does not load files itself.
2. `orchestration` owns the run-time prompt-building flow.
3. workspace bootstrap files are treated as trusted system-context inputs.
4. file-system reading, boundary checks, and truncation live in a dedicated helper layer.
5. `PromptAssembler` stays thin and only consumes resolved context files.

## Bootstrap Files

First version should support a fixed allowlist:

- `AGENTS.md`
- `SOUL.md`
- `TOOLS.md`
- `IDENTITY.md`
- `USER.md`
- `BOOTSTRAP.md`
- `MEMORY.md`
- `memory.md`

Recommended first pass:

- required-ish primary file: `AGENTS.md`
- optional companions: the rest

## Target Flow

1. resolve workspace for the run
2. load bootstrap files from that workspace
3. convert loaded files into injected prompt context blocks
4. prepend those blocks into system prompt space
5. continue with existing session transcript assembly

Conceptually:

`AgentProfile.workspace -> WorkspaceResolver -> BootstrapLoader -> ContextFiles -> PromptAssembler`

## Proposed Components

### 1. Workspace Resolver

Add a small orchestration-side helper:

- `modules/orchestration/application/workspace_context.py`

Responsibilities:

- take `AgentProfile.runtime_preferences.workspace`
- normalize to an absolute path
- optionally fall back to a configured default later
- return `ResolvedWorkspaceContext`

Suggested object:

```python
@dataclass(frozen=True, slots=True)
class ResolvedWorkspaceContext:
    workspace_dir: str | None
    agent_id: str
```

For the first version:

- if agent has no workspace, inject nothing
- do not invent fallback directories yet

### 2. Bootstrap Loader

In the same file or a sibling helper:

- `load_workspace_bootstrap_files(workspace_dir: str) -> tuple[WorkspaceBootstrapFile, ...]`

Suggested object:

```python
@dataclass(frozen=True, slots=True)
class WorkspaceBootstrapFile:
    name: str
    path: str
    content: str
```

Responsibilities:

- only load recognized bootstrap basenames
- ignore missing files
- reject files outside workspace root
- reject oversized files
- trim per-file and total prompt budget

### 3. Prompt Context Files

Add a prompt-facing object:

```python
@dataclass(frozen=True, slots=True)
class PromptContextFile:
    path: str
    content: str
```

`PromptAssembler` should accept:

- `context_files: tuple[PromptContextFile, ...] = ()`

And inject them as system messages before transcript messages.

### 4. Prompt Injection Format

Keep it simple and explicit.

Append one extra system message after base system prompt:

```text
# Project Context

The following workspace files were loaded for this agent run.

## AGENTS.md
...

## TOOLS.md
...
```

This is enough for the first version.

No need yet for:

- multiple system fragments
- plugin hooks
- workspace notes
- bootstrap warning UI text

## Suggested File Changes

### Add

- `src/crxzipple/modules/orchestration/application/workspace_context.py`

### Update

- `src/crxzipple/modules/orchestration/application/prompt_assembler.py`
  - accept `context_files`
  - inject a project-context system message

- `src/crxzipple/modules/orchestration/application/engine.py`
  - resolve workspace context before prompt assembly
  - pass `context_files` into `PromptAssembler`

## Safety Rules

The loader should enforce:

- absolute-path normalization
- workspace-root containment
- no symlink/hardlink escape if feasible
- recognized bootstrap filename allowlist
- per-file max chars
- total max chars

Recommended starting limits:

- per file: `20_000` chars
- total: `80_000` chars

## Phase Plan

### Phase 1

Minimal working chain:

- support `AGENTS.md` only
- inject one project-context system message
- no caching
- no config knobs

### Phase 2

Expand to companion files:

- `SOUL.md`
- `TOOLS.md`
- `IDENTITY.md`
- `USER.md`
- `BOOTSTRAP.md`
- `MEMORY.md`

### Phase 3

Add hardening and ergonomics:

- caching
- truncation diagnostics
- optional extra bootstrap globs
- per-agent/default workspace fallback

## Why This Fits Crxzipple

This keeps current boundaries intact:

- `agent` still just stores workspace preference
- `orchestration` still owns prompt-building
- `session` still owns transcript
- no new domain is introduced

It also avoids the wrong design:

- no file reading inside `AgentProfile`
- no prompt-file logic inside `Session`
- no direct AGENTS loading inside random interface handlers

## Immediate Next Step

Implement Phase 1:

- load `AGENTS.md` from `agent.runtime_preferences.workspace`
- inject it into `PromptAssembler` as one project-context system message
- add unit tests for:
  - workspace missing
  - AGENTS.md present
  - file outside workspace rejected
  - prompt contains injected context
