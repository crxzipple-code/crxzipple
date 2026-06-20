# Claude Code Prompt Engineering Reference

> External reference captured on 2026-06-06 from
> `/Users/crxzy/Documents/claude-code-rev`. This is not a CRXZipple
> implementation contract. Use it to compare final LLM request shape, system
> prompt layering, context management, tool exposure, and investigation bias.

## Why This Reference Exists

Claude Code shows a mature prompt/runtime split for an agent that must solve
ambiguous engineering tasks. The important observation is not that it has a long
system prompt. The important part is that the prompt, tools, memory, context
budgeting, subagents, and compaction loop all push the model toward:

- understanding the task in the current workspace;
- inspecting before proposing;
- using dedicated tools;
- diagnosing failures;
- keeping long tasks alive through compaction;
- offloading broad exploration to subagents or deferred tools.

CRXZipple can use these ideas without copying Claude Code's programming-only
positioning.

## Final LLM Request Shape

Claude Code's Anthropic request is layered:

```text
BetaMessageStreamParams {
  model,
  messages: normalized API messages with prepended user context,
  system: cached system prompt blocks,
  tools: filtered tool schemas,
  tool_choice,
  betas,
  metadata,
  max_tokens,
  thinking,
  context_management?,
  output_config?,
  speed?
}
```

Source map:

- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:449` appends system
  context to the effective system prompt before the API call path.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:659` sends messages with
  prepended user context to the model call.
- `/Users/crxzy/Documents/claude-code-rev/src/services/api/claude.ts:1358`
  prepends attribution / CLI prefix / optional tool-search instructions to the
  system prompt.
- `/Users/crxzy/Documents/claude-code-rev/src/services/api/claude.ts:1376`
  converts system prompt strings into cacheable system prompt blocks.
- `/Users/crxzy/Documents/claude-code-rev/src/services/api/claude.ts:1699`
  builds the final Anthropic stream params.

CRXZipple implication: the final LLM preview should not show only XML. It should
show XML plus provider-native messages, mirrored tool schemas, system/developer
blocks, artifact mirrors, and runtime metadata.

## Effective System Prompt Priority

Claude Code has explicit priority rules for building the effective system prompt:

1. override prompt;
2. coordinator prompt;
3. agent prompt;
4. custom system prompt;
5. default system prompt;
6. append-only system prompt suffix when allowed.

Source map:

- `/Users/crxzy/Documents/claude-code-rev/src/utils/systemPrompt.ts:28`
  documents the priority order.
- `/Users/crxzy/Documents/claude-code-rev/src/utils/systemPrompt.ts:41`
  implements `buildEffectiveSystemPrompt(...)`.

CRXZipple implication: Context Workspace needs equally explicit authority order:
runtime contract first, then agent home, then current user/session, then
workspace/task resources, then visible owner-module nodes and tool results. The
order should be visible in the tree and repeated in the runtime contract.

## Default Prompt Content

Claude Code's default prompt is broad but highly directional. It identifies the
agent as an interactive software engineering agent, then adds sections for
system reminders, doing tasks, safe actions, tool usage, session-specific
guidance, and optional skill/tool discovery.

Source map:

- `/Users/crxzy/Documents/claude-code-rev/src/constants/prompts.ts:176`
  starts the intro.
- `/Users/crxzy/Documents/claude-code-rev/src/constants/prompts.ts:186`
  builds the system reminder section.
- `/Users/crxzy/Documents/claude-code-rev/src/constants/prompts.ts:199`
  builds the task behavior section.
- `/Users/crxzy/Documents/claude-code-rev/src/constants/prompts.ts:255`
  builds action-safety guidance.
- `/Users/crxzy/Documents/claude-code-rev/src/constants/prompts.ts:269`
  builds tool-use guidance.
- `/Users/crxzy/Documents/claude-code-rev/src/constants/prompts.ts:352`
  builds session-specific guidance.
- `/Users/crxzy/Documents/claude-code-rev/src/constants/prompts.ts:444`
  composes static and dynamic prompt sections.

Behavioral effect:

- The model is not left to infer that it should inspect a codebase. It is told
  what kinds of work are expected and how to proceed.
- The prompt emphasizes reading, diagnosis, and verification more than
  conversational completion.
- Tool guidance is tied to concrete tools, reducing attention loss.

CRXZipple implication: the runtime contract should include a domain-general
equivalent: for browser/API/code/external systems, prefer evidence paths that can
verify facts; if a visible surface fails, inspect related state, code, requests,
storage, traces, or alternate tools before declaring the task blocked.

## User Context And System Context

Claude Code separates durable user context from runtime system context:

- User context is prepended as a meta user message.
- System context is appended to the system prompt.
- Context values include memory files, current date, git state, and cache
  breakers.

Source map:

- `/Users/crxzy/Documents/claude-code-rev/src/context.ts:116` builds system
  context such as git state.
- `/Users/crxzy/Documents/claude-code-rev/src/context.ts:155` builds user
  context from memory and date.
- `/Users/crxzy/Documents/claude-code-rev/src/utils/api.ts:437` appends system
  context.
- `/Users/crxzy/Documents/claude-code-rev/src/utils/api.ts:449` prepends user
  context.

CRXZipple implication: Context Tree nodes should preserve the source and
authority of each context item. Agent home files, session transcript, workspace
resources, and memory recall should not collapse into a single anonymous
instruction block.

## Tool Schemas And Deferred Tools

Claude Code builds filtered tool schemas for the API. Deferred tools can be
announced as a small model-visible list without loading every full schema.

Source map:

- `/Users/crxzy/Documents/claude-code-rev/src/services/api/claude.ts:1180`
  starts the model call request assembly.
- `/Users/crxzy/Documents/claude-code-rev/src/services/api/claude.ts:1328`
  handles deferred tools.
- `/Users/crxzy/Documents/claude-code-rev/src/services/api/claude.ts:1338`
  prepends available deferred tool names as meta context.

Behavioral effect:

- Tool availability remains discoverable without flooding the model with every
  schema.
- The model can discover or load more capability when needed.

CRXZipple implication: source-first tool bundle nodes are aligned with this
pattern. The tree should initially show capability/source summaries and only
mirror function schemas after the relevant group is expanded or pinned.

## Streaming Tool Execution And Continuation

Claude Code's query loop turns each model/tool cycle into an explicit recursive
state transition:

1. prepare `messagesForQuery` after compact/collapse/budget passes;
2. call the model with system prompt, user context, messages, and tools;
3. collect assistant messages and tool-use blocks during streaming;
4. execute tools, normalize tool results into user messages;
5. inject attachments, memory prefetch results, and skill prefetch results;
6. recurse with `messages = previous + assistantMessages + toolResults`.

Source map:

- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:365` builds
  `messagesForQuery` from the post-compact boundary.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:659` calls the model.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:826` records streamed
  assistant messages.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:829` extracts tool-use
  blocks, and `:841` queues them for streaming execution.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:851` consumes completed
  streaming tool results.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:1380` runs remaining
  tools after model streaming.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:1395` normalizes tool
  result messages into model-visible user messages.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:1580` injects queued
  attachments.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:1600` consumes memory
  prefetch results.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:1620` consumes skill
  discovery prefetch results.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:1715` creates the next
  recursive state with prior messages, assistant messages, and tool results.

Behavioral effect:

- Tool results are not interpreted by UI glue; they become the next model input.
- Memory/skill attachments get a chance to enter after actual tool activity,
  which makes them more task-relevant than static up-front dumps.
- The model can keep working without the user issuing "continue" after every
  tool batch.

CRXZipple implication: background tool completion and execution-chain resumption
should converge into a single continuation path. The next LLM call should see
tool results and relevant attachments through session/Context Workspace, not via
ad hoc run metadata.

## Error Recovery And Message Ordering

Claude Code protects the tool/result invariant aggressively. It withholds some
recoverable model/API errors while it tries context-collapse or reactive
compaction, synthesizes missing tool results on abort, and only injects regular
attachments after tool calls are resolved. The code comments explicitly warn
that tool result messages must not be interleaved with ordinary user messages.

Source map:

- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:742` clones streamed
  assistant messages only for observable tool input backfill; the original
  assistant message is kept unchanged for prompt-cache stability.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:788` withholds
  recoverable errors such as prompt-too-long, max-output-tokens, and media-size
  errors until recovery paths can run.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:1011` consumes remaining
  streaming tool results or yields synthetic missing tool results on abort.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:1062` starts the
  prompt-too-long / media recovery path when no normal follow-up is pending.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:1535` notes that tool
  results must be completed before regular user attachments are added.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:1580` injects queued
  command attachments after tool results.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:1592` injects settled
  memory prefetch attachments after tool results.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:1617` injects skill
  discovery attachments after tool results.

Behavioral effect:

- The model never sees a dangling tool call without a corresponding result just
  because streaming was aborted or a tool failed midway.
- Recovery attempts happen before the runtime gives up, so long tasks can keep
  moving after context pressure.
- Attachments enter the conversation at a predictable boundary, which reduces
  role/order confusion in the next model call.

CRXZipple implication: execution-chain continuation should preserve a strict
ordering contract: assistant tool call intent, owner-module terminal result,
then follow-up attachments. Session and Context Workspace can expose this as a
tree, but provider messages still need a valid native order.

## Memory And Skill Prefetch

Claude Code starts relevant memory prefetch once per user turn and skill
discovery prefetch per loop iteration. These run around the main model loop so
that relevant information can be available without making every prompt
construction path synchronous and expensive.

Source map:

- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:301` starts memory
  prefetch.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:331` starts skill
  discovery prefetch.
- `/Users/crxzy/Documents/claude-code-rev/src/constants/prompts.ts:333`
  describes skill discovery guidance.

CRXZipple implication: memory/skill owner modules should own retrieval and
readiness, while Context Workspace controls how their handles and selected
results enter the visible tree. Do not make orchestration invent skill or memory
truth.

## Context Budgeting And Compaction

Claude Code applies several context controls before the model call:

- aggregate tool result budget;
- history snip;
- microcompact;
- context collapse;
- autocompact.

Source map:

- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:379` applies tool result
  budget.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:401` applies history
  snip.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:413` applies
  microcompact.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:440` applies context
  collapse.
- `/Users/crxzy/Documents/claude-code-rev/src/query.ts:453` enters
  autocompact.

Behavioral effect:

- Long sessions are not simply chopped.
- Tool-heavy turns can continue without drowning the model in raw output.
- Collapse state can persist across turns while still projecting a model-visible
  view.

CRXZipple implication: Context Workspace should own prompt-visible folding,
estimation, and snapshotting. Session owns historical facts; Context Workspace
decides what is rendered for this run.

## Plan, Todo, And Agent Tool Shaping

Claude Code's planning and task-management behavior is not only model habit. It
is reinforced by tool descriptions:

- task creation is recommended for complex multi-step work, plan mode, explicit
  user requests, and newly received requirements;
- task updates forbid marking work completed when tests fail, implementation is
  partial, or unresolved errors remain;
- plan mode is a tool-mediated state for non-trivial implementation ambiguity;
- broad research should use the Agent tool or specialized Explore/Plan agents.

Source map:

- `/Users/crxzy/Documents/claude-code-rev/src/tools/TaskCreateTool/prompt.ts:16`
  describes task-list purpose.
- `/Users/crxzy/Documents/claude-code-rev/src/tools/TaskCreateTool/prompt.ts:21`
  lists proactive use cases.
- `/Users/crxzy/Documents/claude-code-rev/src/tools/TaskUpdateTool/prompt.ts:13`
  describes completion rules and non-completion cases.
- `/Users/crxzy/Documents/claude-code-rev/src/tools/EnterPlanModeTool/prompt.ts:23`
  describes plan mode entry.
- `/Users/crxzy/Documents/claude-code-rev/src/tools/EnterPlanModeTool/prompt.ts:57`
  says pure research should use the Agent tool instead.
- `/Users/crxzy/Documents/claude-code-rev/src/tools/AgentTool/prompt.ts:80`
  describes when to fork.
- `/Users/crxzy/Documents/claude-code-rev/src/tools/AgentTool/prompt.ts:101`
  describes how to brief another agent.
- `/Users/crxzy/Documents/claude-code-rev/src/tools/AgentTool/prompt.ts:190`
  can move the dynamic agent list into conversation attachments so the Agent
  tool description remains cache-stable.

Behavioral effect:

- The main model gets explicit operational choices: plan, make tasks, delegate
  research, or execute.
- "Plan/check/summary" is not a hidden universal cycle; it is a set of tools,
  prompts, and continuation states that the model can choose or the runtime can
  enforce in specific modes.
- Dynamic capability lists can be made visible without constantly invalidating
  the tool schema cache.

CRXZipple implication: if CRXZipple wants browser/API investigation behavior, it
should not only say "be investigative" in the runtime contract. It should expose
clear agent-facing workflows: inspect page state, inspect network/script,
summarize evidence, promote a reusable skill, continue with tool results.

## Explore And Plan Subagents

Claude Code has built-in subagents for exploration and planning. Their prompts
are read-only and tool-specific, which pushes broad investigation away from the
main conversation context.

Source map:

- `/Users/crxzy/Documents/claude-code-rev/src/tools/AgentTool/built-in/exploreAgent.ts:13`
  defines the Explore agent system prompt.
- `/Users/crxzy/Documents/claude-code-rev/src/tools/AgentTool/built-in/planAgent.ts:21`
  defines the Plan agent system prompt.

Behavioral effect:

- The main model can delegate broad search without carrying all raw results.
- Exploration is framed as analysis, not immediate mutation.
- Planning is explicitly separated from execution.

CRXZipple implication: a future CRXZipple equivalent can be implemented as
agent-facing tools or skills, but it should still use Context Workspace as the
surface for discovered evidence and summaries.

## CRXZipple Current Cross-Check

The current CRXZipple request path has already moved in the same direction as
Claude Code's layered request:

- `src/crxzipple/modules/orchestration/application/runtime_llm_request_draft.py`
  defines `RuntimeLlmRequestDraftCollector` as a collector, not the final
  provider renderer.
- `src/crxzipple/modules/orchestration/application/runtime_llm_request.py`
  builds the runtime request envelope from Context Slice items, active Tool
  Surface, runtime policy, and provider options.
- `src/crxzipple/modules/llm/infrastructure/adapters/*_renderer.py` owns
  provider-specific rendering.
- `src/crxzipple/app/integration/context_workspace_orchestration/adapter.py`
  records the Context Snapshot / Context Slice for a run.
- `src/crxzipple/modules/orchestration/application/engine.py` carries Context
  Snapshot / Tool Surface refs through the run and invocation metadata.
- `src/crxzipple/modules/context_workspace/application/prompts/runtime_contract.md:1`
  is the current runtime-level behavior contract.
- `src/crxzipple/modules/llm/application/services.py:436` records
  `LlmInvocation` messages, tool schemas, response format, overrides, and
  metadata before the adapter call.
- `src/crxzipple/modules/llm/infrastructure/adapters/anthropic_messages.py:95`
  extracts system messages, `:100` builds provider `messages`, `:113` writes the
  provider `system` field, and `:115` mirrors tool schemas.
- `src/crxzipple/modules/llm/infrastructure/adapters/openai_chat_compatible.py:74`
  combines system messages before building OpenAI-compatible `messages`.

Observed gap:

- Claude Code has explicit pre-model context controls for tool result budget,
  snip, microcompact, collapse, and autocompact. CRXZipple's intended equivalent
  is Context Workspace render/fold/estimate plus session segment compaction; any
  remaining direct provider transcript replay would weaken the tree as the
  single prompt surface.
- Claude Code's Explore/Plan agents create an obvious investigation path. In
  CRXZipple, the analogous path should be surfaced through Context Tree tool
  groups, browser workbench tools, skills, and possibly explicit
  investigation-oriented agent-facing workflows.

## Why Claude Code Leans Toward Investigation

The behavior difference is produced by several reinforcements:

- system identity says the agent is doing software engineering work;
- default guidance says to read/investigate before proposing;
- tool schemas are concrete and specialized;
- tool descriptions explicitly teach planning, task tracking, delegation, and
  completion rules;
- broader exploration has an explicit subagent path;
- memory/skill prefetch can surface relevant context;
- tool result budgeting and compaction protect long execution chains;
- final API request preserves separate system, user context, messages, tools,
  and cacheable blocks.

For CRXZipple, the lesson is not to become Claude Code. The lesson is to make the
runtime's desired behavior concrete at the same engineering layers:

- a stable runtime contract;
- source-tagged Context Tree nodes;
- visible capability groups before full tool schemas;
- browser/API/code evidence paths stated in the contract;
- prompt previews that show every provider layer;
- compaction and history delivery controlled by Context Workspace.
