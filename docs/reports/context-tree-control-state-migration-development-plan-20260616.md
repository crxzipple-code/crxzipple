# Context Tree Control-State Migration Development Plan

日期：2026-06-16

关联目标设计：[context-tree-control-state-target-design-20260616.md](context-tree-control-state-target-design-20260616.md)

## 目标

把 Context Tree 从“debug snapshot + 部分 tool schema mirror”收敛为会话级上下文控制面，也就是 runtime 的 Context Hydration Layer。

最终链路：

```text
Owner modules
  Session / Orchestration / Tool / LLM / Skills / Memory / Artifacts / Workspace
        ↓ owner refs + query surfaces
Context Workspace
  Context Tree control state
  Context Slice Builder
  active Tool Surface
  omitted / budget / loss report
        ↓
LLM provider renderer
  provider-native input / tools / files / images
        ↓
Provider
```

核心原则：

- Tree owns selection, not truth.
- Tree 只保存控制状态和 owner_ref，不保存 owner raw content。
- LLM 默认只看到 Context Slice，不看到完整 Context Tree。
- Provider-specific render 只发生在 LLM renderer / adapter 边界。
- Orchestration 只推进 loop，不直接拼 session history、skills catalog、tool schema、artifact blocks。
- 不兼容旧结构，不双轨并行；数据库可清空重建。
- 不做任务特化，不把无法形成准确结论的诊断/裁判/路径偏置发送给 LLM。

## 现状摘要

当前 Context Workspace 已有：

- `ContextWorkspace` / `ContextNode` / `ContextTreeOperation` / `ContextSnapshot`。
- owner node providers：Session、Tool、Skills、Memory、Artifacts、Agent、Workspace。
- debug tree render。
- provider attachment mirror。
- tool schema mirror。

当前主要缺口：

- Orchestration 仍直接 `session_service.build_replay_window(...)`，session history 没有经过 Tree selection。
- `SessionInstance` 在 tree adapter 中被命名为 `session_segment`，instance / segment 层级混淆。
- Turn / Step / StepItem 没有成为 session 子树下的稳定层级。
- LLM response item 还容易被理解为直接挂树；目标应是 runtime semantics projection。
- Skills / Memory / Artifacts / Workspace 仍有 direct injection/materialization 路径，未完全收敛到 Context Slice。
- Tool source/group expand 到 active provider tool schema 的闭环不够硬。
- Debug body、snapshot metadata、provider request slice 的职责还没有完全拆开。

## 目标模块职责

### Context Workspace

拥有：

- Context Tree 活状态。
- Context Slice Builder。
- owner_ref resolve orchestration。
- node state：expanded、pinned、opened、schema_enabled、summary_mode、included flags、status。
- request-time render report：included、omitted、budget、loss、active tool surface refs。
- context tools：read / expand / collapse / pin / enable_tool_schema / diff。

不拥有：

- Session item 原文。
- Tool schema truth。
- Tool result raw payload。
- LLM raw response。
- Skill.md 全文。
- Memory 原文。
- Artifact bytes。
- Workspace file 全文。

### Session

拥有会话事实：

- Session。
- SessionInstance。
- SessionItem。
- model_visible / user_visible / protocol-required view。
- compaction / archived item metadata。

需要提供给 Context Workspace 的 query surface：

- active instance。
- list instances。
- list items by instance / sequence range / model visibility。
- current model-visible frontier。
- compacted summary refs。
- item range metadata and estimates。

目标上，Context Tree 中的 session 层级为：

```text
Session -> Instance -> Segments -> Segment -> Turn -> Step -> Item
```

如果 Session module 当前没有独立 Segment/Turn 实体，Context Workspace 可先通过 owner_ref 组合 SessionItem + Orchestration run/step facts 生成控制节点，但节点 kind 必须按目标语义命名，不能继续把 `SessionInstance` 伪装成 `session_segment`。

### Orchestration

拥有运行事实：

- run lifecycle。
- execution chain。
- execution step。
- execution step item。
- approval / waiting / pending tool。
- loop advancement。

需要改：

- 不再直接决定 provider transcript。
- 调 LLM 前请求 `ContextWorkspace.build_slice(run_id, session_key)`。
- 把 run / chain / step / step item 作为 owner refs 输入 Context Workspace。
- tool call/result 是否进入下一轮 LLM context 由 Context Slice 决定。

### LLM

拥有 provider 事实：

- invocation。
- raw provider request/response preview。
- normalized `LlmResponseItem`。
- provider renderer。
- provider capability/profile/transport。

需要改/确认：

- Provider raw response 不直接成为 Tree node。
- response side 经 runtime response projector 映射为 runtime semantics：
  - `runtime.assistant_progress`
  - `runtime.assistant_message`
  - `runtime.assistant_tool_call`
  - `runtime.final_answer`
  - `runtime.blocked_state`
- request side renderer 只消费 Context Slice + active Tool Surface。

### Tool

拥有工具事实：

- source / bundle / group / function catalog。
- schema。
- readiness / auth / runtime requirements。
- execution target binding。
- tool run / result envelope / raw output handles。

需要提供：

- source-first runtime request catalog。
- function schema query。
- default target resolution，例如 OpenAPI remote。
- tool run summary and read handles。

Context Tree 只保存：

- source/group/function refs。
- schema_enabled。
- included_in_next_tool_surface。
- status/readiness summary。

### Skills

拥有 skill catalog / package / readiness。

需要提供：

- available skill handles。
- summary/readiness。
- read `SKILL.md` surface。

Context Tree 控制：

- skill visible。
- skill loaded。
- skill.md opened。
- skill included in next slice。

### Memory

拥有 memory truth / retrieval。

需要提供：

- visible scopes。
- recall query result refs。
- memory item summary/read surface。

Context Tree 控制：

- recalled refs。
- opened/pinned/summary_mode。
- included in next slice。

### Artifacts

拥有 artifact metadata / variants / storage。

需要提供：

- metadata。
- mime / size / variants。
- LLM materialization candidate。

Context Tree 控制：

- artifact handle visible。
- opened/pinned。
- included as text/file/image/omitted。

### Workspace / Agent

拥有 workspace file handles / agent home config。

需要提供：

- safe resource handles。
- summary/read surface。

Context Tree 控制：

- resource visible。
- file opened/pinned。
- agent home included/omitted.

### Operations / Workbench / Trace

需要展示：

- current tree revision。
- current context slice。
- active tool surface。
- included / omitted / budget / loss report。
- node owner refs。
- mapping from slice -> provider wire payload。
- turn -> step -> item -> owner detail drilldown。

## 新增核心数据结构

### ContextSlice

建议作为 Context Workspace application DTO：

```python
@dataclass(frozen=True, slots=True)
class ContextSlice:
    session_key: str
    run_id: str
    tree_revision: int
    task: ContextSliceSection
    runtime: ContextSliceSection
    history: ContextSliceSection
    tool_results: ContextSliceSection
    skills: ContextSliceSection
    memory: ContextSliceSection
    artifacts: ContextSliceSection
    workspace: ContextSliceSection
    active_tools: tuple[ContextSliceToolRef, ...]
    omitted: tuple[ContextSliceOmittedRef, ...]
    budget: ContextSliceBudget
    loss_report: ContextSliceLossReport
    source_node_ids: tuple[str, ...]
```

### ContextSliceItem

```python
@dataclass(frozen=True, slots=True)
class ContextSliceItem:
    node_id: str
    owner: str
    kind: str
    owner_ref: dict[str, object]
    content_kind: str
    content: object
    visibility: str
    summary_mode: str | None
    estimate: dict[str, object]
    metadata: dict[str, object]
```

`content` 是 renderer-ready projection，不是 owner raw truth。比如 Session item 可以是 model-visible text/content blocks，Tool result 可以是 summary + read handle，Artifact 可以是 materialization candidate。

### ContextSliceToolRef

```python
@dataclass(frozen=True, slots=True)
class ContextSliceToolRef:
    node_id: str
    tool_id: str
    source_id: str
    schema_name: str
    schema_ref: dict[str, object]
    target: str
    readiness: str
    estimate: dict[str, object]
```

Tool schema truth 仍由 Tool module 提供；slice 只带 schema ref 或 request-time copied schema payload。

### ContextSliceReport

用于 Operations/Trace：

```json
{
  "included_node_ids": [],
  "omitted_refs": [],
  "active_tool_schema_names": [],
  "budget": {},
  "loss_report": {},
  "owner_resolution_errors": []
}
```

## 目标树形

完整目标树形见关联目标设计文档。施工时至少收敛以下关键层级：

```text
context.root
├─ runtime
├─ task
├─ session
│  ├─ session.frontier
│  └─ session.instances
│     └─ session.instance.*
│        └─ session.segments
│           └─ session.segment.*
│              └─ session.turns
│                 └─ session.turn.*
│                    └─ session.steps
│                       └─ session.step.*
│                          └─ runtime/session/tool refs
├─ capabilities
│  ├─ tools
│  ├─ skills
│  └─ model
├─ knowledge
│  ├─ memory
│  ├─ workspace
│  └─ artifacts
└─ render
   ├─ render.current_slice
   ├─ render.active_tool_surface
   ├─ render.omitted
   ├─ render.budget
   └─ render.loss_report
```

## 关键运行流程

### Request side

```text
Orchestration reaches LLM step
  -> ContextWorkspace.build_slice(run_id, session_key)
     -> ensure tree roots
     -> refresh owner handles
     -> resolve selected nodes live from owner modules
     -> produce ContextSlice + active ToolSurface + report
  -> LLM RuntimeRequest.from_context_slice(...)
  -> Provider renderer maps to provider wire payload
  -> LLM invoke
```

### Response side

```text
Provider raw response
  -> LLM adapter normalize LlmResponseItem
  -> Runtime response projector emits runtime semantics
  -> owner facts written:
     - LLM invocation / response item
     - Session runtime items
     - Orchestration step items
     - Tool run requests
  -> Context Tree state updated or refreshed by refs
  -> next build_slice sees new runtime facts
```

### Context tool side

```text
model calls context.expand("tools.source.open_meteo")
  -> Tree state changes
  -> function nodes loaded/opened
  -> schema_enabled policy applies
  -> next build_slice active tools include weather functions
```

```text
model calls context.pin("tool.result.call_abc")
  -> Tree state changes
  -> next build_slice includes compact result summary or selected payload
```

## Phased Construction

### Phase 0: Freeze Decisions

- [x] Keep target design doc as current source of truth.
- [x] Mark older “Context Tree as prompt body” docs as historical or superseded where they conflict.
- [x] Confirm database reset is acceptable for Context Workspace schema changes.

Acceptance:

- Docs clearly say Tree is control state, not owner truth.
- Docs clearly say LLM sees Context Slice, not full tree.

### Phase 1: Domain Model Cleanup

Context Workspace:

- [x] Add node state fields or metadata conventions:
  - `summary_mode`
  - `included_in_next_slice`
  - `included_in_next_tool_surface`
  - `status`
  - `render_priority`
  - `render_reason`
- [x] Add `ContextSlice` DTOs.
- [x] Add `ContextSliceBuilder` service interface.
- [x] Separate debug render result from Context Slice result.

Session adapter:

- [x] Stop naming `SessionInstance` as `session_segment`.
- [x] Introduce node kinds:
  - [x] `session_instance`
  - [x] `session_segments_root`
  - [x] `session_segment`
  - [x] `session_turn`
  - [x] `session_steps_root`
  - [x] `session_step`
  - [x] `session_item`
- [x] Keep owner refs stable and owner-owned.

Acceptance:

- Unit test can render a tree with `session.instance.active -> session.segments -> session.segment.active`.
- No new tree node stores full session/tool/llm raw content.

### Phase 2: Session and Orchestration Resolver Surfaces

Session:

- [x] Provide active instance query.
- [x] Provide item range query by instance and sequence range.
- [x] Provide model-visible/user-visible frontier query.
- [x] Provide compacted/archived summary query.

Orchestration:

- [x] Provide run turn metadata query.
- [x] Provide execution chain/step/item query for a turn.
- [x] Provide pending/waiting/approval/tool status query.

Context Workspace:

- [x] Build `session.turn.*` from Session items + Orchestration run refs.
- [x] Build `session.step.*` from ExecutionStep.
- [x] Attach runtime semantic refs under steps.

Acceptance:

- Tree can answer current active instance, current turn, current step.
- Tree can show completed/running/waiting tool calls by owner refs.

### Phase 3: Context Slice Builder

- [x] Implement `build_slice(session_key, run_id, provider_profile)` in Context Workspace application.
- [x] Expose `ContextSliceBuilderService` from app assembly as the runtime slice service.
- [x] Attach context slice payload to Context Workspace snapshot records and LLM runtime request payload.
- [x] Runtime request builder projects Context Slice into neutral `LlmInputItem` / active Tool Surface before provider render.
- [x] Provider renderers do not turn `context_snapshot.context_slice` metadata into extra system/provider context text.
- [x] Provider request preview exposes context slice item/tool counts without exposing slice body.
- [x] Resolve owner refs according to owner-specific control policy.
  - [x] Session item refs resolve through Session owner service at slice-build time.
  - [x] Tool / skill / memory / artifact / workspace refs stay handle-only in the kernel slice unless explicitly opened or read through their owner tool/query flow.
  - [x] Slice item metadata records `owner_resolution` as `owner_resolved`, `owner_unresolved`, `handle_only`, or `embedded`.
- [x] Produce sections:
  - [x] runtime
  - [x] task
  - [x] history
  - [x] tool_results
  - [x] skills
  - [x] memory
  - [x] artifacts
  - [x] workspace
  - [x] active_tools
  - [x] omitted/loss/budget
- [x] Do not include unresolved/uncertain owner content in model-visible slice.
- [x] Record unresolved refs in loss report only.

Acceptance:

- Current user request appears through task/session slice, not direct orchestration transcript stitching.
- Old compacted segment appears as summary unless expanded.
- Pinned result appears even if older than normal history window.

### Phase 4: Tool Surface Closure

Tool:

- [x] Expose source/group/function schema and execution binding query.
- [x] Expose preferred execution target based on supported environments.

Context Workspace:

- [x] `expand tools.source/group` loads function nodes.
- [x] Define policy: expand-to-function does not auto-enable schema except reserved context-tree tools; provider-callable tools require explicit schema enablement or explicit next-surface inclusion.
- [x] Active Tool Surface comes from `tool_function.schema_enabled=true` or `included_in_next_tool_surface=true`.
- [x] Store active tool refs in Context Slice and render report.
- [x] Runtime request builder projects provider-visible `tool_schemas` from `ContextSlice.active_tools`, not from legacy snapshot mirror fields.
- [x] Interactive resolved tool bindings are filtered by the active slice tool schema names.
- [x] Legacy `context_snapshot.tool_schemas` is not used as a fallback provider tool surface.

Acceptance:

- Expanding Open-Meteo source produces concrete function nodes.
- Enabling weather function makes next LLM request include `open_meteo_weather.forecast_weather`.
- Tool execution binding uses supported target, not accidental local default.

### Phase 5: LLM Request Integration

LLM:

- [x] Add `RuntimeLlmRequest.from_context_slice(...)` or equivalent factory.
- [x] Provider renderers consume neutral input items, active Tool Surface and provider profile produced from Context Slice.
- [x] Provider payload preview includes slice mapping and render report without exposing slice body or unresolved refs.
- [x] Provider renderers ignore `context_snapshot.debug_body` for wire payloads; debug body remains audit/tool-output only.
- [x] Context Slice handle-only owner refs can render bounded read hints, but owner metadata/body is not projected into `LlmInputItem`.

Orchestration:

- [x] Replace full direct session replay provider input path with Context Slice path.
  - [x] Normal turns keep only current frontier/protocol-required replay in direct transcript.
  - [x] Session replay window remains available for routing, tree projection and audit metadata, not as primary provider input.
- [x] Stop direct skills catalog injection into provider context messages.
- [x] Stop direct agent profile instruction injection into provider context messages; `agent_instruction` enters through Context Snapshot / `agent.identity`.
- [x] Remove `skills_catalog` from `RuntimeLlmRequestDraft`; orchestration draft no longer resolves Skills owner catalog.
- [x] Stop direct tool schema injection except through active Tool Surface.
- [x] Remove hard `memory_flush` tool-call forcing; maintenance tools remain visible, but runtime no longer converts missing tool calls into a protocol failure.
- [x] Remove runtime inspection hook that mutates memory-flush transcript budget; maintenance budget is fixed in draft collector.
- [x] Keep orchestration as loop owner only.

Acceptance:

- Provider request input can be traced back to Context Slice items.
- `context_snapshot.debug_body` is not default provider input.
- Session replay window is no longer the primary provider input source for normal turns.

### Phase 6: Response Projection Into Runtime Semantics

LLM:

- [x] Preserve provider response item id, phase, type and raw payload in LLM truth.
- [x] Normalize to `LlmResponseItem`.

Runtime response projector:

- [x] Map provider/LLM items to runtime semantics:
  - [x] `runtime.assistant_progress`
  - [x] `runtime.assistant_message`
  - [x] `runtime.assistant_tool_call`
  - [x] `runtime.final_answer`
  - [ ] `runtime.blocked_state` (deferred until provider/runtime emits an explicit blocked/refusal/needs-user item; do not infer from assistant text)
- [x] Write owner facts through Session/Orchestration/Tool, not directly into Tree raw data.
- [x] Persist `runtime_semantic_kind` on projected Session items for tree/workbench projection.

Context Workspace:

- [x] Under `session.step.llm`, attach runtime semantic ref nodes.
- [x] Under `session.step.tool_batch`, attach tool call/run/result refs.

Acceptance:

- Tree has no provider-native `llm.response_item.*` node kind.
- Tree nodes can trace to `llm_invocation_id` and `llm_response_item_id` through owner_ref.
- Workbench can show runtime semantics while Trace can drill into raw LLM response.

### Phase 7: Skills / Memory / Artifacts / Workspace Slices

Skills:

- [x] Replace direct skills catalog provider injection with skills slice.
  - [x] Remove orchestration draft direct skill catalog resolution.
- [x] `skill.md` enters slice only when opened/loaded/pinned or policy requires.

Memory:

- [x] Memory recall results enter slice by tree state.
- [x] Memory raw content remains in Memory owner.

Artifacts:

- [x] Artifact handles enter tree.
- [x] Provider attachments generated only from opened/pinned/included artifact nodes.
- [x] Remove orchestration draft artifact body materialization; draft keeps refs and slice controls provider materialization.

Workspace:

- [x] Workspace files enter slice as handles by default.
- [x] File body enters slice only after explicit open/read and budget check.

Acceptance:

- LLM request can explain why a skill/memory/artifact/workspace item was included or omitted.

### Phase 8: Operations / Workbench / Trace

Operations:

- [x] Show tree revision, slice id, included/omitted counts.
- [x] Show active tool surface.
- [x] Show budget/loss report.
- [x] Show node status counts by owner/kind.
- [x] Runtime request summary carries sanitized `context_slice_summary` with item/tool/report refs and no slice body.

Workbench:

- [x] Show current context slice beside timeline.
- [x] Show step -> runtime semantic nodes.
- [x] Drill owner refs to Session/LLM/Tool/Orchestration details.

Trace:

- [x] Show slice item -> provider payload mapping.
- [x] Show provider payload -> response item -> runtime semantic mapping.

Acceptance:

- User can answer: “模型这轮看到了什么？为什么没看到天气工具？哪个 tool result 进入了下一轮？”

### Phase 9: Cleanup

- [x] Remove or archive old prompt body / direct transcript builders.
- [x] Remove old `Context Tree as provider prompt XML` assumptions.
- [x] Remove duplicate provider context message injections.
- [x] Remove fallback paths that bypass Context Slice.
- [x] Update docs and tests to current terms.

Acceptance:

- Only one request assembly path remains: Context Slice -> Provider Renderer.
- No module outside Context Workspace decides context selection.

## Test Matrix

Context Workspace:

- [x] Build tree roots with runtime/task/session/capabilities/knowledge/render.
- [x] Render session instance -> segments -> segment -> turn -> step.
- [x] Expanded source changes next active tool surface.
- [x] Pinned old tool result enters next slice.
- [x] Omitted/unresolved refs stay out of model-visible content.

Session:

- [x] Instance and sequence range queries.
- [x] Model-visible frontier.
- [x] Compacted segment summary and range handles.

Orchestration:

- [x] LLM step uses Context Slice.
- [x] Tool result replay controlled by slice.
- [x] Waiting/approval state visible as tree control state.

LLM:

- [x] Provider renderer consumes Context Slice-derived neutral input items.
- [x] Codex/OpenAI Responses input matches ResponseItem-style replay where appropriate.
- [x] Chat-compatible renderer maps slice to messages/tools.
- [x] Raw response item does not become tree node kind.

Tool:

- [x] OpenAPI weather function schema enters provider tools after expansion/enable.
- [x] Remote-supported OpenAPI tool uses supported execution target.

Operations/Workbench/Trace:

- [x] Context slice visible.
- [x] Provider request preview links to slice item ids.
- [x] Runtime semantic nodes link back to raw LLM response and session items.

## Risks

- Over-modeling the tree can recreate a second data warehouse.
  - Mitigation: owner_ref only; live resolve; no raw owner content.
- Hidden dual path can keep old behavior alive.
  - Mitigation: remove direct transcript/tool/skill injection after slice path lands.
- Provider renderers can leak tree internals.
  - Mitigation: render only slice; tree debug body stays debug-only.
- Tool discovery can become UI-only.
  - Mitigation: expand/enable must mutate active Tool Surface for next request.
- Session hierarchy can exceed current owner model.
  - Mitigation: use owner_ref composition initially, but target node kinds remain correct.

## Definition of Done

- A normal turn LLM request is built from Context Slice, not direct session replay.
- Context Tree persists only control state and refs.
- Provider request preview can show exact slice -> wire mapping.
- Current active tools are derived from tree/tool surface state.
- Session hierarchy exposes instance -> segment -> turn -> step.
- Runtime response items are projected into runtime semantics before tree nodes.
- No provider raw item, raw tool result, raw session content, artifact bytes, memory raw text, or skill.md full body is stored as tree truth.
- Tests prove weather/tool expansion, session compaction, tool result inclusion, and provider render mapping.
