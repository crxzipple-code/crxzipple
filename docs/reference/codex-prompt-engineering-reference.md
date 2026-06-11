# Codex Prompt Engineering Reference

> External reference captured on 2026-06-06 from
> `/Users/crxzy/Documents/Codex`. This is not a CRXZipple implementation
> contract. Use it to compare final LLM request shape, prompt layering, and
> behavior-shaping mechanisms.

## Why This Reference Exists

The comparison target is not "what text does Codex put in a prompt" in the
abstract. The useful question for CRXZipple is why the same model family behaves
more like a coding/runtime agent in Codex: it reads files, investigates source,
checks assumptions, uses tools deliberately, and verifies outcomes instead of
getting trapped in a single visible surface.

The answer is a combination of request shape, context layering, tool schema
surface, and continuity rules.

## Final LLM Request Shape

Codex does not send one flattened prompt string. The Responses request is built
from a `Prompt` object:

```text
ResponsesApiRequest {
  model,
  instructions: prompt.base_instructions.text,
  input: prompt.get_formatted_input(),
  tools: create_tools_json_for_responses_api(prompt.tools),
  tool_choice: "auto",
  parallel_tool_calls,
  reasoning,
  text / output_schema,
  stream,
  prompt_cache_key
}
```

Source map:

- `/Users/crxzy/Documents/Codex/codex-rs/core/src/client.rs:743` builds the
  Responses request.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/client.rs:752` sends base
  instructions as the API `instructions` field.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/client.rs:753` formats model
  input separately.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/client.rs:754` serializes tool
  specs separately.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/session/turn.rs:970` builds
  the internal `Prompt`.

CRXZipple implication: Context Tree XML can remain the visible prompt body, but
provider-specific mirrors for tools, images, files, and output schemas should be
treated as protocol attachments. They should not mutate the semantic prompt tree.

## Base Instructions

Codex's base instructions are a stable behavioral constitution. The checked
template starts by identifying the agent as a coding agent operating in a shared
workspace, then gives durable expectations for collaboration, file edits,
verification, frontend work, reviews, and long-running tasks.

Source map:

- `/Users/crxzy/Documents/Codex/codex-rs/core/templates/model_instructions/gpt-5.2-codex_instructions_template.md:1`
  defines the identity.
- `/Users/crxzy/Documents/Codex/codex-rs/core/templates/model_instructions/gpt-5.2-codex_instructions_template.md:38`
  starts the general engineering behavior section.

Behavioral effect:

- The model is not asked to be a neutral assistant. It is framed as a runtime
  actor that should inspect code, make changes, verify, and report accurately.
- It is repeatedly told to read before proposing and to diagnose failed actions
  before switching tactics.
- The prompt is broad enough to apply to unfamiliar tasks, but specific enough
  to bias the model toward evidence-gathering and implementation.

CRXZipple implication: `runtime_contract.md` should play this constitution role.
Agent home files can add identity and local preferences, but the runtime-level
operating contract must be explicit and always present.

## Context Layering

Codex separates several context families:

- Developer/runtime instructions: permissions, collaboration mode, personality,
  apps, skills, and plugin availability.
- User-context items: repository instructions such as `AGENTS.md` and the
  environment context.
- Turn input and prior model-visible history.
- Tool schemas visible for the current model call.

Source map:

- `/Users/crxzy/Documents/Codex/codex-rs/core/src/session/mod.rs:2768`
  assembles developer context sections.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/session/mod.rs:2897`
  assembles contextual user sections such as repo instructions and environment.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/context/user_instructions.rs:9`
  renders repo instructions as user-context content.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/context/environment_context.rs:420`
  builds environment context from the current turn context.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/context/available_skills_instructions.rs:23`
  renders available skills as developer instructions.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/context/apps_instructions.rs:20`
  renders app/plugin instructions.

CRXZipple implication: a single Context Tree can own the visible prompt, but it
still needs clear authority bands. Runtime contract, agent home, session,
workspace, tools, skills, memory, and artifacts should appear as distinct nodes
with explicit priority and purpose, not as one undifferentiated markdown blob.

## Initial Context And Diffs

Codex records full reference context at the start and then records updates as
diffs. This preserves continuity without repeatedly injecting the entire
environment contract.

Source map:

- `/Users/crxzy/Documents/Codex/codex-rs/core/src/session/mod.rs:2996`
  records context updates and manages the reference context item.

Behavioral effect:

- The model keeps seeing durable constraints.
- The runtime can change environment/tool/skill availability without pretending
  every turn is a fresh session.
- Prompt cost stays lower than replaying every context layer verbatim.

CRXZipple implication: Context Workspace render snapshots and node revisions
should be used as the equivalent. The tree is the truth; snapshots make each run
reproducible, while node hashes/revisions allow diffs and UI inspection.

## Tool Surface

Codex builds model-visible tool specs every sampling request:

- `built_tools(...)` constructs the tool router for the current turn.
- `router.model_visible_specs()` becomes the prompt's tool schema list.
- Parallel tool calls are enabled from model/turn capability.

Source map:

- `/Users/crxzy/Documents/Codex/codex-rs/core/src/session/turn.rs:999` enters a
  sampling request.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/session/turn.rs:1009` builds
  tools.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/session/turn.rs:978` exposes
  model-visible specs on the prompt.

Behavioral effect:

- The model sees concrete action affordances, not merely prose telling it tools
  exist.
- Tool visibility is recalculated for the turn, so runtime context and
  permissions can affect what the model attempts.

CRXZipple implication: Context Workspace's visible tool function nodes should be
the only source for provider tool schemas on interactive turns. Source-first
groups should bias attention before exposing many individual functions.

## History And Compaction

Codex reuses initial input for the first loop iteration, then uses session
history formatted for the model's input modalities on later retries/continuation.
It also runs compaction before sampling when thresholds require it.

Source map:

- `/Users/crxzy/Documents/Codex/codex-rs/core/src/session/turn.rs:1027` keeps
  initial input for the first loop iteration.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/session/turn.rs:1032` falls
  back to formatted history after the initial input.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/session/turn.rs:146` enters
  pre-sampling compaction flow.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/session/turn.rs:784` contains
  auto-compact execution.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/context_manager/history.rs:100`
  records only API-message items into history.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/context_manager/history.rs:115`
  normalizes history before sending it to the model and strips image content
  when the current model cannot accept images.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/context_manager/history.rs:165`
  removes the matching call/output counterpart when dropping the oldest item.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/context_manager/history.rs:471`
  defines API messages to include user/assistant messages, reasoning, tool
  calls, tool outputs, shell calls, web-search calls, and image-generation
  calls, while excluding system messages and compaction triggers.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/compact.rs:51` defines
  `InitialContextInjection`; mid-turn compaction injects initial context before
  the last real user message, while manual/pre-turn compaction clears the
  reference and lets the next turn re-inject.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/compact.rs:251` trims oldest
  history first when compaction itself overflows the context window.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/compact.rs:289` builds the
  replacement compacted history and stores it as the new session history.

Behavioral effect:

- Long sessions can continue without losing the operating contract.
- History is not merely truncated; it is actively transformed and reintroduced.
- Tool calls and tool results remain paired even when history is trimmed.
- Modality-specific content such as images is preserved only when the target
  model can actually consume it.

CRXZipple implication: Session history should remain a Context Workspace concern
for delivery. Session keeps facts; Context Workspace decides visible history,
folded history, summaries, and provider attachments for each run.

Additional CRXZipple implication: prompt compaction should be represented as a
Context Workspace tree operation with explicit placement rules. It should not be
an opaque transcript page-drop, because that is exactly how tool results,
initial context, or recently summarized session facts become invisible to the
next run.

## Sampling Loop And Tool Results

Codex's model loop is not a one-shot request followed by a caller-side if/else.
The sampling request streams model output, detects tool calls as response items,
dispatches them through a tool runtime, records tool outputs into conversation
history, and marks the turn as needing a follow-up model request.

Source map:

- `/Users/crxzy/Documents/Codex/codex-rs/core/src/session/turn.rs:247` calls
  `run_sampling_request(...)` for a turn.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/session/turn.rs:293` performs
  mid-turn auto-compaction when the token limit is reached and the model still
  needs follow-up.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/session/turn.rs:1744` drains
  in-flight tool futures and records tool outputs into conversation history.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/session/turn.rs:1811` creates
  the in-flight tool future queue for one streaming response.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/session/turn.rs:1871` handles
  streamed response events.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/session/turn.rs:1950` pushes
  tool futures, and `:1956` accumulates `needs_follow_up`.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/session/turn.rs:2072` handles
  response completion and honors `end_turn == false` as another follow-up signal.

Behavioral effect:

- Tool results are part of the conversation substrate, not out-of-band UI facts.
- Multiple tool calls can be active in one model response, but their outputs are
  normalized back into the next prompt.
- Continuation is driven by model/tool state, token state, and pending input,
  rather than by the UI manually asking the model to continue.

CRXZipple implication: execution chain step items should remain the durable
owner references, but the next LLM request must receive completed tool results
through Context Workspace/session history in a deterministic order.

## Tool Runtime And Parallelism

Codex supports parallel tool execution with per-tool gating. Tools that support
parallelism take a shared read lock; tools that do not take an exclusive write
lock. Tool failures are converted into model-visible tool outputs instead of
always terminating the whole turn.

Source map:

- `/Users/crxzy/Documents/Codex/codex-rs/core/src/tools/parallel.rs:31` defines
  `ToolCallRuntime`.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/tools/parallel.rs:88` checks
  whether the tool supports parallel execution.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/tools/parallel.rs:113` spawns
  the tool task.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/tools/parallel.rs:115` uses
  shared/exclusive locking for parallel vs non-parallel tools.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/tools/parallel.rs:186` builds
  a model-visible failure response.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/tools/router.rs:96` turns
  response items into internal tool calls.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/tools/router.rs:170` dispatches
  tool calls to the registry and terminal-outcome machinery.

CRXZipple implication: tool worker scheduling can be separate from
orchestration, but orchestration must still see a stable terminal outcome and a
model-visible result item. A failed tool should usually become evidence for the
next model step, not a silent run-level collapse.

## Planning And Goal Tools

Codex does not appear to run a hidden planning model before every main model
call. Planning behavior is exposed as tools and collaboration mode:

- `update_plan` is a model-visible tool with explicit statuses.
- goal tools are separate, opt-in primitives for persistent thread goals.
- plan-mode streaming has a separate UI/state path, but it is still part of the
  same turn loop.

Source map:

- `/Users/crxzy/Documents/Codex/codex-rs/core/src/tools/handlers/plan_spec.rs:7`
  defines `update_plan`.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/tools/handlers/goal_spec.rs:16`
  defines goal read/create/update specs.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/session/turn.rs:1208` defines
  ephemeral plan-mode stream state.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/session/turn.rs:1302` starts a
  streamed plan item, and `:1331` completes it.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/context/collaboration_mode_instructions.rs:24`
  renders collaboration mode instructions as developer-context fragments.

Behavioral effect:

- The model is encouraged to plan when useful, but the runtime does not force
  every request through a separate planner.
- Plan state is visible to the user and the runtime; it is not merely hidden
  chain-of-thought.

CRXZipple implication: do not add a mandatory "plan before every main model"
layer as the first fix. Prefer making investigation/planning affordances visible
through Context Tree tools, skills, and run modes, then evaluate whether a
separate planning pass is needed for specific high-risk tasks.

## Prompt Debugging

Codex has a prompt debug helper, but it primarily returns model-visible `input`.
It is not the entire final API request because base instructions and tools are
separate request fields.

Source map:

- `/Users/crxzy/Documents/Codex/codex-rs/core/src/prompt_debug.rs:24` starts the
  prompt debug helper.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/prompt_debug.rs:84` builds the
  prompt.
- `/Users/crxzy/Documents/Codex/codex-rs/core/src/prompt_debug.rs:99` returns
  formatted input.

CRXZipple implication: a "show prompt" UI must display all final request layers:
runtime contract / tree XML, provider-native messages, mirrored tool schemas,
artifact/image attachments, output schema, and context snapshot metadata.

## CRXZipple Current Cross-Check

The current CRXZipple implementation already has the same broad separation as
Codex: collection, tree rendering, provider mirror, and final provider request
are different steps.

Source map:

- `src/crxzipple/modules/orchestration/application/prompt_input.py:115`
  defines `RunPromptInputCollector`; its docstring says it collects run inputs and
  does not render the final prompt body.
- `src/crxzipple/modules/orchestration/application/prompt_input.py:167`
  reads agent profile and `:169` reads the active session bundle.
- `src/crxzipple/modules/orchestration/application/prompt_input.py:189`
  builds provider input transcript for the current run.
- `src/crxzipple/modules/orchestration/application/prompt_input.py:201`
  resolves the LLM profile, and `:245` resolves the skill prompt catalog.
- `src/crxzipple/modules/orchestration/application/prompt_input.py:331`
  carries initially resolved tool schemas, but this is later narrowed by Context
  Workspace visibility.
- `src/crxzipple/modules/orchestration/application/engine.py:535` records the
  Context Workspace render snapshot for a run.
- `src/crxzipple/modules/orchestration/application/engine.py:579` merges the
  context snapshot back into the prompt surface.
- `src/crxzipple/modules/orchestration/application/engine.py:631` mirrors visible
  tool schemas, `:645` inserts Context Workspace XML as a system message, and
  `:668` mirrors opened artifact attachments as user content blocks.
- `src/crxzipple/modules/context_workspace/application/services.py:537` builds
  the `runtime.contract` tree node from the file-backed runtime contract.
- `src/crxzipple/modules/llm/application/services.py:436` stores each
  `LlmInvocation` with `messages`, `tool_schemas`, response format, overrides,
  and request metadata before adapter execution.
- `src/crxzipple/modules/llm/infrastructure/persistence/models.py:47` persists
  invocation messages and `:52` persists tool schemas.
- `src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses.py:258`
  builds the Codex Responses payload, with system messages resolved into
  `instructions` at `:292` and non-system messages converted into `input` at
  `:302`.

Observed gap:

- CRXZipple has the layering, but its final prompt/debug view must expose all
  layers together. Showing only the XML body can hide provider-native messages,
  tool mirrors, artifact mirrors, and output schema.
- The runtime contract has browser evidence-path instructions, but the behavior
  still depends on whether high-level browser/code/network tools are visible as
  concrete affordances before the model gives up on the first DOM snapshot.

## Why Codex Leans Toward Source Investigation

The observed behavior difference is not caused by one magic instruction. It is
the result of stacked bias:

- The identity is a coding agent in a workspace.
- The base contract repeatedly rewards reading, diagnosing, editing, and
  verifying.
- Repository instructions and environment context are prominent.
- Tools are concrete and model-visible.
- The loop records tool results, preserves context across retries, and compacts
  without dropping initial context.
- Debug/trace paths make final input reproducible.

For CRXZipple, the analogous target is not "copy Codex's coding prompt." It is:

- make the runtime-level behavior contract unavoidable;
- make the current task's evidence paths visible;
- surface browser/code/network/request tools as concrete affordances;
- ensure tool results and session history come back through the same Context
  Tree surface;
- make the final LLM request inspectable as a layered artifact.
