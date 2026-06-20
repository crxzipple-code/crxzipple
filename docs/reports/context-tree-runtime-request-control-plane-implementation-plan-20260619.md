# Context Tree Runtime Request Control Plane Implementation Plan

日期：2026-06-19

## 背景

这份文档不是重新设计 Context Tree。已有设计已经明确：

- `docs/context-workspace-prompt-tree-design.md`
- `docs/context-workspace-prompt-tree-development.md`
- `docs/reports/context-tree-control-state-target-design-20260616.md`
- `docs/reports/context-tree-control-state-migration-development-plan-20260616.md`
- `docs/reports/runtime-request-render-snapshot-hot-path-refactor-plan-20260618.md`

当前要解决的是实现偏移：代码里已经有 Context Tree、render snapshot、request render snapshot、provider renderer 等部件。第一轮施工已经把普通 LLM 请求从 session replay / draft transcript 直通收回到 Context Slice 投影；第二轮已经把 provider renderer 的正式输入收口到 `ProviderRenderInput` 快照。剩余重点是继续清理维护模式和 tool surface 的历史旁路，避免旧 replay/debug/evidence 重新进入 provider-visible 输入。

目标是把已经设计好的 Context Tree 真正升格为 runtime request control plane：

```text
Owner modules own facts
  -> Context Tree owns selection/control state and refs
  -> Context Model Slice resolves selected refs
  -> Runtime request builder freezes ProviderRenderInput
  -> Provider Renderer emits provider-native request
  -> LLM Provider
```

## 不可变原则

- 不兼容旧结构，不做双轨并行；数据库可以清空重建。
- 不做任务特化，不为东航、浏览器、票价、天气等单一场景加入内核判断。
- 不把无法形成准确结论的 debug、trace、路径猜测、证据裁判发送给 LLM。
- Context Tree 不存 owner raw truth，只存 owner refs、控制状态、预算和呈现策略。
- Session 是会话账本；Tool、LLM、Memory、Skills、Artifact、Workspace 各自拥有事实。
- Context Tree 是控制面；Renderer / Provider Adapter 是翻译面。
- Orchestration 只推进 loop、记录引用、处理等待和生命周期，不拼 provider prompt。

## 当前偏移

### 1. LLM input 曾从 Session Replay 直出，现已在普通路径收口

旧路径中 `RuntimeLlmRequestDraftCollector.build()` 会读取 session replay window：

- `src/crxzipple/modules/orchestration/application/runtime_llm_request_draft.py`
- `session_service.build_replay_window(...)`
- `_build_runtime_replay_window(...)`
- `runtime_replay_window_builder.build_from_session_items(...)`

这意味着模型实际看到的历史主要由 Session replay policy 决定，而不是由 Context Tree 的节点展开、折叠、pin、schema_enabled、summary_mode、budget frontier 决定。

当前状态：

- 普通 `NORMAL_TURN` / `SESSION_START` draft 只保留 current inbound 最小事实。
- 正式 provider input 由 request render snapshot 的 `projected_input_items` 接管。
- `session_service.build_replay_window(...)` 已不在 orchestration 普通 runtime request 主路径中使用；`MEMORY_FLUSH` / compaction 等专门模式也不再通过 `build_maintenance_window(...)` 端口消费 replay window，而是显式读取 active session item facts 后在 orchestration 本地构造维护 transcript 报告。

### 2. `llm_request` control slice 有绕过树的快路

当前 Context Workspace 在 `audience == "llm_request"` 且 `read_only` 或 `protocol_required_refs` 存在时，会走 `_build_llm_request_control_slice(...)`。

该路径只把 protocol refs 转成 control refs，metadata 里还标记 `tree_scan_performed=False`。它保证了 protocol pair 不丢，但没有执行树选择、预算和可见工具状态。

### 3. Request Render Snapshot 已记录树切片投影，Provider Renderer 已收口到正式快照

旧路径中 `ContextWorkspaceRunSnapshotAdapter` 会：

- 从 draft 提取 direct session item refs。
- control slice 有 selected refs 就用 selected refs，否则 fallback 到 direct session refs。
- `included_node_ids=()`。
- `mirrored_node_ids=()`。
- `debug_body=""`。

当前状态：

- 持久化 request render snapshot 时必须有 Context Slice builder；缺失时直接失败。
- snapshot 已记录 `context_slice_id`、`context_slice_projected_input_item_count`、`projected_input_items`、`tool_schema_refs`、`included_node_ids` 等树切片投影。
- `RuntimeLlmRequestBuilder` 要求 transcript-required 模式提供 request render snapshot，且 snapshot 必须包含 Context Slice 投影出的 `projected_input_items`；draft transcript fallback 已退场。
- control slice 只保留为观察/诊断控制摘要，不能成为 provider-visible input refs 或 tool schema refs。
- LLM HTTP invoke/test/stream 边界要求调用方显式提交 canonical `input_items`；messages-only 请求必须被 422 拒绝，不能穿透到 provider renderer 或 domain invariant。
- 当前状态：Provider Renderer 不直接读取完整 Context Tree 或整块 Context Slice，而是消费由 runtime request builder / adapter 边界冻结出的 `ProviderRenderInput`。`ProviderRenderInput` 只包含 provider wire 所需的 canonical input items、provider context、tool schemas、request policy、provider options、response format、transport 和 continuation。
- 剩余差距：维护模式和 tool surface 的历史旁路还需要继续收口；默认 provider request 主路径已经不再从 `messages`、debug/context slice 或 evidence 类内容反推 provider input。

### 4. Tool schema 仍能从 draft surface 进入 provider request

当前 visible tool schemas 由 draft tool schemas、render metadata、tree service、surface contract 混合解析。目标状态下，provider 可见 tool schema 必须由 Context Tree 的 active tool surface 控制；工具 catalog 是 owner fact，是否暴露给模型由树节点状态决定。

## 目标形态

### Runtime 主链路

```text
Turn submitted
  -> Session appends user/session facts
  -> Orchestration creates run/step facts
  -> Context Workspace updates tree refs and control nodes
  -> Orchestration asks Context Workspace for ContextModelSlice
  -> ContextModelSlice resolves owner refs live
  -> LLM Provider Renderer renders provider-native request
  -> LLM Provider returns raw response
  -> LLM adapter normalizes response items
  -> Runtime response projector maps response items to runtime semantics
  -> Session records ledger items
  -> Context Workspace updates tree refs/control state
  -> Operations/Workbench/Trace observe via events/read models
```

### Tree 负责什么

Context Tree 回答控制问题：

- 当前在哪个 session / instance / segment / turn / step？
- 哪些 session item 对模型可见？
- 哪些 tool call/result 是 protocol-required？
- 哪些历史已经 compacted / archived？
- 哪些 summary 替代了旧 ranges？
- 哪些工具 source/group/function 可见？
- 哪些 function schema enabled，会进入下一轮 provider tools？
- 哪些 skill handle 可见，哪些 `SKILL.md` 已打开？
- 哪些 memory/artifact/workspace refs 被 pin、opened、omitted？
- 当前 request slice 的预算、omission、loss report 是什么？

Tree 不回答业务事实本身：

- 不保存 session item 原文。
- 不保存 tool result raw output。
- 不保存 LLM raw provider response。
- 不保存 artifact bytes。
- 不保存 memory 原文。
- 不保存 skill.md 全文。

### Provider Renderer 负责什么

Renderer 接收 provider-neutral `ContextModelSlice`，输出 provider-native payload：

- OpenAI Responses/Codex：`input` / response item replay / tool result item / tool schemas / continuation 参数。
- Anthropic Messages：messages blocks / tool_use / tool_result / tool schemas。
- Gemini：contents / function declarations / tool responses。
- Chat-compatible：messages / tool messages / functions or tools。

Provider-specific prompt、history replay、tool protocol pair、continuation 只在 renderer / adapter 边界处理，不回流污染 Context Tree。

## 数据结构调整

### ContextModelSlice

新增或正式化 Context Workspace application DTO：

```python
@dataclass(frozen=True, slots=True)
class ContextModelSlice:
    slice_id: str
    session_key: str
    run_id: str
    tree_revision: int
    audience: Literal["llm_request"]
    provider_profile: str
    runtime_refs: tuple[ContextSliceRef, ...]
    task_refs: tuple[ContextSliceRef, ...]
    session_refs: tuple[ContextSliceRef, ...]
    protocol_required_refs: tuple[ContextSliceRef, ...]
    tool_schema_refs: tuple[ContextToolSchemaRef, ...]
    skill_refs: tuple[ContextSliceRef, ...]
    memory_refs: tuple[ContextSliceRef, ...]
    artifact_refs: tuple[ContextSliceRef, ...]
    workspace_refs: tuple[ContextSliceRef, ...]
    compacted_refs: tuple[ContextSliceRef, ...]
    omitted_refs: tuple[ContextSliceRef, ...]
    budget: ContextSliceBudget
    report: ContextSliceReport
```

### ContextSliceRef

```python
@dataclass(frozen=True, slots=True)
class ContextSliceRef:
    node_id: str
    node_kind: str
    owner: str
    owner_ref: Mapping[str, object]
    visibility: Literal["model", "user", "trace", "operations"]
    render_policy: Literal[
        "provider_replay",
        "summary",
        "handle_only",
        "tool_schema",
        "tool_result",
        "omitted",
    ]
    priority: int
    protocol_required: bool = False
```

### RequestRenderSnapshot

Request render snapshot 应记录“本轮渲染结果的索引”，不是完整树：

- `slice_id`
- `tree_revision`
- `included_node_ids`
- `input_item_refs`
- `projected_input_items`
- `tool_schema_refs`
- `protocol_required_refs`
- `omitted_refs`
- `estimated_tokens`
- `renderer_id`
- `renderer_version`
- `provider_request_preview_ref`

不记录或不发送：

- full tree debug body。
- 不确定的 evidence path。
- internal debug metadata。
- task-specific verdict。

## 树更新机制

### Session item append

当 Session module 发布 `session.item.appended`：

1. Context Workspace 只读取 item metadata 和 owner ref。
2. 在 active `session.instance -> segment -> turn -> step` 下创建或更新 item 控制节点。
3. 根据 item kind 设置默认状态：
   - user request：current turn pinned，model-visible。
   - assistant progress：user-visible；是否 model-visible 由 policy 决定，默认只进入可渲染 progress summary，不作为完整聊天消息。
   - assistant message/final：model-visible + user-visible。
   - tool call/tool result：protocol-required 成对保留，直到 provider renderer 确认 pair 已被覆盖或 compacted。
   - compaction summary：model-visible，替代旧 range。

### LLM invocation / response

LLM module 拥有 raw invocation 和 raw provider response。Runtime response projector 将 normalized response item 映射为 runtime semantics：

- `runtime.assistant_progress`
- `runtime.assistant_message`
- `runtime.assistant_tool_call`
- `runtime.final_answer`
- `runtime.blocked_state`

Context Tree 只挂这些 runtime semantics node 的 owner refs，不直接挂 provider raw item。

### Tool lifecycle

Tool module 发布 tool call/run/result 状态后：

1. Context Workspace 更新对应 `tool.call` / `tool.run` / `tool.result` 节点。
2. `tool.call` 与 `tool.result` 的 protocol pair 必须始终可追踪。
3. 大结果默认 handle-only 或 summary，raw output 由 owner read surface 读取。

### Capability search / tool enable

`capability.search` 是一次性能力发现与启用入口，不拆成 search + enable 两步。

当模型调用 capability search：

1. Tool owner 返回 source/group/function refs 和 schema refs。
2. Context Workspace 将匹配节点标记为 `opened` / `schema_enabled`。
3. 下一轮 ContextModelSlice 的 `tool_schema_refs` 包含这些 enabled function。
4. Provider renderer 将其渲染成 provider-native tool schema。

### Compaction / segment rollover

当 segment 被 compact：

1. Session module 记录 compacted summary item。
2. Context Workspace 将旧 range 节点标记为 `archived` 或 `collapsed`。
3. active slice 默认使用 summary node。
4. protocol-required 未闭合 pair 不允许被 summary 替代。

## 模块施工方案

### Phase 0. 现状保护与入口审计

- [x] 固化当前 request trace 对照样本：新增 `tests/unit/fixtures/provider_request_traces/` 下的 CRXZipple failed-run shape provider preview、Codex HTTP provider preview、Codex WebSocket provider preview 摘要 fixture，并由 `tests/unit/test_provider_request_trace_fixtures.py` 回归；真实本地 Codex JSONL lifecycle 仍由 `tests/unit/test_codex_trace_fixture.py` 在 trace 文件存在时校验。
- [x] 标出所有进入 provider request 的入口：canonical `input_items`、provider context/instructions、request render snapshot `tool_schema_refs`、structured `runtime_context`、provider attachments；旧 `messages` 只保留为 compatibility projection，不作为正式 provider input 来源，`flow_hint`/skill metadata 不再绕过 Context Slice 直接形成 provider-visible 内容。
- [x] 增加断言：默认 LLM request 不允许包含 full tree debug body、debug/context slice、evidence verdict、browser evidence path；当前 metadata 只传 `request_context_source/context_slice_id/count` 摘要，不传整块 `context_slice`。
- [x] 增加 request render metadata 字段：正式 provider request 只接受 `request_context_source=context_slice`；preview/diagnostic 无切片时可记录 `missing_context_slice`，但不能形成 provider-visible input 或 tool schema。

### Phase 1. Context Tree 控制节点补齐

- [x] 修正 `SessionInstance` / `Segment` 命名混淆，树节点 kind 不再把 instance 伪装成 segment；当前 active/closed instance 均使用 `session_instance`，segment 节点使用 `session_segment`。
- [x] 补齐 `Session -> Instance -> Segments -> Segment -> Turn -> Step -> Item` 控制层级；现有 session adapter 已维护 `session.current -> session.instance.* -> session.segments.* -> session.segment.* -> session.turn.current -> session.steps.current -> session.step.* -> session.step.item.*`。
- [x] 补齐 runtime semantic nodes：assistant progress/message/tool call/final/blocked；execution item `runtime_semantic_kind` 已映射为 `runtime_assistant_progress`、`runtime_assistant_message`、`runtime_assistant_tool_call`、`runtime_final_answer`、`runtime_blocked_state` 等树节点。
- [x] 补齐 active tool surface nodes：source/group/function/schema_enabled；`tools.available -> tool_bundle -> tool_bundle_group -> tool_function` 已由 Context Workspace 维护，`schema_enabled`/`included_in_next_tool_surface` 进入 Context Slice active tools。
- [x] 所有节点只保存 owner refs、状态、估算，不保存 raw truth。
  - [x] Tool function 节点不再保存 `provider_schema`；树只保存 `tool_id/source_id/runtime_key` 等 owner refs 与控制状态，provider schema 由 request render 从 owner-resolved schema candidates 按树状态过滤。
  - [x] Agent home 文件节点改为 handle-only：树只保存文件名、角色、路径、长度和摘要，不再持久化或渲染文件正文；需要正文时通过 agent owner/query/tool 显式读取。
  - [x] Context Slice 和 debug XML 对 handle-only owners（tool/skills/memory/artifacts/workspace/agent）统一禁止从 `ContextNode.content` 生成正文输出；即使节点误带正文，也只输出 handle/summary。
  - [x] Context Slice 对未知 owner 默认 handle-only，不从 `ContextNode.content` 生成模型文本；只有 `context_workspace/llm/orchestration/runtime` 控制 owner 明确允许内联控制内容。

### Phase 2. ContextModelSlice Builder

- [x] 新增 `ContextModelSliceBuilder` 或将现有 `build_control_slice` 正式升级为 model slice builder；当前已接入 `ContextSliceBuilderService` 作为 request snapshot 的主 slice 来源。
- [x] 对 `llm_request` audience 执行真实树选择，不再以 `protocol_required_refs` 快路替代树扫描。
- [x] `protocol_required_refs` 改为硬约束输入：强制纳入 slice，但不能替代普通树选择。
- [x] Builder 解析 owner refs live，生成 provider-neutral refs，不拼 provider messages；Context Slice session refs 解析为 `projected_input_items`，provider messages 只由 provider renderer 从 canonical input items 降级生成。
- [x] Context Slice session owner refs 已在 request render snapshot 中投影为 provider-neutral `projected_input_items`，并只使用 owner live item 内容，不使用树节点 stale content。
- [x] Context Slice 对 session owner 不再从 `ContextNode.content` 回退；session item resolver 缺失或失败时只记录 unresolved loss，不把树上的旧文本发送给模型。
- [x] Builder 输出 budget、omitted、archived/collapsed/unresolved、loss report；request render snapshot 记录对应摘要字段，供 Trace/Operations 观察，不进入 provider input。

### Phase 3. Provider Renderer 接管 request payload

- [x] Provider renderer 输入改为正式 `ProviderRenderInput` 快照；Context Slice 仍由 request render snapshot / RuntimeLlmRequestBuilder 投影为 canonical `projected_input_items`，renderer 不直接认识完整 Context Tree，也不接收整块 `context_slice`。
- [x] Provider protocol 新增正式 `ProviderRenderInput`，统一承载 `profile/request/runtime_context/runtime_route/runtime_policy`；`ProviderProtocolRenderRouter.preview_input()` / `render_input()` 已作为正式入口，旧 `preview(profile, request)` / `render_request(profile, request)` 仅保留薄代理。
- [x] `ProviderRenderInput` 显式携带 renderer 所需模型切片字段：`input_items/provider_context_messages/tool_schemas/request_policy/provider_options/response_format/provider_transport/continuation`；renderer preview/input mapping 与首批 input/tool alias 读取已改用该正式快照，不再只能翻原始 adapter request。
- [x] Provider renderer 内部的主输入读取继续收口：OpenAI Responses/Codex、Anthropic、Gemini、Chat-compatible 已从 `ProviderRenderInput` 读取 canonical input、provider context、tool schemas、request policy、provider options、response format；原始 adapter request 的 provider-visible 字段读取只保留在 `ProviderRenderInput.from_request(...)` 构造边界，renderer preview 仅通过 `render_input.request` 读取 request metadata / runtime context 摘要。
- [x] OpenAI Codex WebSocket continuation/delta/`previous_response_id` 路径改为消费 `ProviderRenderInput` 的 continuation、transport、input/tool schema 快照；旧 request helper 仅作为 adapter/tests 的薄边界入口。
- [x] OpenAI Responses provider-native continuation 也改为消费 `ProviderRenderInput.continuation`；旧 request helper 只保留为边界代理，不再参与 renderer 核心 payload 构造。
- [x] OpenAI Responses / Codex adapter 的 preview、tool alias、transport 与 continuation fallback 判断基于 `ProviderRenderInput` 快照；adapter 不再在主路径上各自散装读取 provider-visible tool schema/transport 选项。
- [x] Anthropic、Gemini、OpenAI Chat-compatible adapter 的 preview 入口改为 `preview_input(ProviderRenderInput)`；各 provider 的观察预览与正式 renderer 输入入口保持一致。
- [x] OpenAI Codex renderer 增加 `build_input_items_input` / `build_full_input_items_input`，正式路径直接从 `ProviderRenderInput` 构造 provider input；旧 request helper 仅保留为历史测试/边界代理。
- [x] OpenAI Responses / Codex renderer 增加 `build_payload_input`，正式 payload 构造直接消费 `ProviderRenderInput`；旧 `build_payload(profile, request, ...)` 仅作为薄边界代理。
- [x] OpenAI Responses / Codex / Chat-compatible / Anthropic / Gemini adapter 的 vision capability check 改为从 canonical `input_items` 投影出的消息判断，不再读取 legacy `request.messages` 或二次 renderer 输出作为 provider 输入旁路。
- [x] OpenAI Responses / Codex adapter 的 send/header/wire request 路径支持复用已组装的 `ProviderRenderInput`；Codex WebSocket provider-native continuation fallback 会为去除 continuation 的请求显式重建 render input，避免复用错误快照。
- [x] Anthropic、Gemini、OpenAI Chat-compatible adapter 的 send/header/wire request 路径也支持复用已组装的 `ProviderRenderInput`；vision check 与 wire preview/render 均使用同一份 canonical input 快照。
- [x] OpenAI Responses renderer 退役未使用的 request-based continuation helper；正式 continuation 判断/注入只保留 `ProviderRenderInput` 版本和内部私有函数。
- [x] OpenAI Codex renderer 退役 request-based instructions/input/continuation/websocket payload helper；正式 input、delta、`previous_response_id` 注入只保留 `ProviderRenderInput` 版本。
- [x] OpenAI Responses/Codex、Anthropic、Gemini、Chat-compatible adapter 内部 wire request 构造先组装 `ProviderRenderInput`，再进入 provider renderer；adapter 边界不再各自散装 route/context/policy。
- [x] OpenAI Responses/Codex、Anthropic、Gemini、Chat-compatible renderer 均新增 `render_input()` / `preview_input()` 作为核心实现入口；旧 `render(profile, request)` / `preview(profile, request)` 仅代理到正式 input 入口，provider router 与 adapter 已优先调用正式入口。
- [x] Provider renderer 不再从 `request.messages` 反推 provider input；OpenAI Responses/Codex、Anthropic、Gemini、Chat-compatible renderer 只消费 canonical `request.input_items`，system/provider context 走独立 provider context/instructions 通道。
- [x] OpenAI Responses / Codex renderer 的 `instructions` 只来自 provider context 与 canonical system `input_items`；legacy `request.messages` 不再影响 provider payload，system input item 只进入 instructions/system 字段，不重复进入 provider `input` 或 input mapping。
- [x] LLM HTTP invoke/test/stream 边界要求 canonical `input_items` 必填且至少一个；messages-only 请求返回 422，不再在 service/domain 层变成 500。
- [x] Provider renderer 的 input item metadata 改为白名单投影，只保留 `node_id/owner/kind/session_item_id/sequence_no/tool_call_id/tool_name/tool_run_id/llm_response_item_id` 等追踪和协议字段；debug/context_slice/evidence_path/raw_trace 不进入 render mapping 或 provider payload。
- [x] OpenAI Codex renderer 对齐抓包 trace，渲染 provider-native response item replay / tool result / tool schemas；HTTP full input 与 WebSocket fingerprint delta 已覆盖，Codex ResponsesApiRequest 基础 wire shape 已补齐。
- [x] Provider preview/render report 输出 `request_context_source/context_slice_id` 摘要与 provider input item -> Context Tree `node_id` 映射，不泄露整块 slice/debug body。
- [x] Provider preview/render report 输出 provider-visible tool name -> runtime tool surface / Context Tree `node_id/tool_ref_id/source_id` 映射，支持 OpenAI/Codex tool name alias 后仍可追踪来源。
- [x] Operations LLM detail 展示 Provider Tool Mapping 摘要，保留完整 `provider_render_report`，不把 render report 混入 provider wire preview。
- [x] Operations runtime request summary 展示 Context Slice 安全摘要字段（source/id/item/included/omitted/tool/projected/loss counts），不展示整块 `context_slice`。
- [x] Runtime request metadata 输出 `runtime_input_filter` 摘要，说明本轮 input 是否由 request render session refs 过滤、过滤前后 item 数量。
- [x] Request snapshot 输出 `context_slice_projected_input_item_count`，Trace/preview 可确认 provider input 是否来自 Context Slice 投影。
- [x] Request render snapshot 持久化 `projected_input_items`，recorded snapshot replay 能恢复同一份投影输入，避免回退到 draft replay。
- [x] `request_context_source=context_slice` 时强制要求 `projected_input_items`；缺失投影会失败，不再静默回退到 session replay/draft input。
- [x] Request render snapshot 的 `projected_input_items` 只来自 Context Slice 投影，不再合并 draft `input_items`；draft 可保留当前 inbound 最小事实和诊断口径，但不能作为正式 provider 输入补丁。
- [x] `projected_input_items` -> canonical `LlmInputItem` 的解析下沉到 LLM application，Orchestration 不再维护 provider-neutral input item 解析细节。
- [x] `tool_schema_refs` -> canonical `ToolSchema` 的解析下沉到 LLM application，Orchestration 只传递 Context Slice/tool surface refs。
- [x] `LlmAdapterRequest` 增加结构化 `runtime_context` 摘要，Provider renderer/preview 优先从 adapter request 读取 slice/snapshot/tool surface 上下文，不再只能从 metadata 反查。
- [x] LLM application 增加 `RuntimeRequestRenderContext`，由 `RuntimeLlmRequest.renderer_context()` 从正式 request envelope 生成 renderer-facing 安全摘要；`InvokeLlmInput.from_runtime_request` / `StreamLlmInput.from_runtime_request` 传递该对象投影，手工调用才回退 metadata 解析。
- [x] LLM application 增加 `RuntimeRequestRoute` / `RuntimeRequestRenderPolicy`，由 `RuntimeLlmRequest.renderer_route()` / `renderer_policy()` 生成 renderer-facing route/policy 投影；`LlmAdapterRequest` 承接 `runtime_route` / `runtime_policy`，Provider preview 统一展示该观察摘要，但不改变 provider wire payload。
- [x] Workbench linked entity detail 展示 Context Slice 安全摘要（source/id/item/projected/omitted/unresolved），不展示整块 `context_slice`。
- [x] Anthropic/Gemini/Chat-compatible renderer 各自实现对应 wire payload；当前 renderer 均消费 canonical `input_items`，再投影为各自 provider wire 格式。
- [x] Renderer 负责处理 provider continuation、tool protocol pair、tool schema 格式；provider-native continuation 按 provider/transport capability 生效，不支持的 provider 不伪造 continuation。
- [x] Orchestration 不再拼 `LlmMessage` transcript 作为主输入；transcript-required 请求必须从 request render snapshot `projected_input_items` 构造 provider input。

### Phase 4. 退役 session replay 旁路

- [x] 普通 `NORMAL_TURN` / `SESSION_START` 的 draft transcript 不再由 `session_service.build_replay_window(...)` 直出；draft 只保留当前 inbound 最小事实，正式 provider 输入由 Context Slice 投影接管。
- [x] Orchestration 不再依赖 `session_service.build_replay_window(...)`；维护模式也不再通过 `build_maintenance_window(...)` 端口读取 replay window，普通 request 主输入语义与 session replay API 解耦。
- [x] `build_maintenance_window(...)` 从 orchestration runtime request 端口退场；`MEMORY_FLUSH` / compaction 等专门模式改为显式 `get_session_with_items(active_session_only=True)` 读取 session owner facts，并在 orchestration 内构造维护 transcript report，不再暴露“维护 LLM 直接消费 replay window”的边界。
- [x] 保留 session query surface 供 ContextModelSlice Builder resolve refs，不供 Orchestration 直接拼 prompt；Orchestration 普通 turn 只读取 session binding/current inbound 最小事实，正式 provider input 必须来自 request render snapshot `projected_input_items`。
- [x] 移除 `_build_runtime_replay_window(...)` 在普通 LLM request 主路径上的 session-item replay 使用；普通 turn 直接构造 current inbound transcript。
- [x] `RuntimeLlmRequestBuilder.request_envelope()` 要求 transcript-required 模式提供 request render snapshot，且 snapshot 必须投影出 `projected_input_items`；draft transcript fallback 已退场，避免正式运行绕过 Context Slice。
- [x] 删除 `included_refs = context_slice_refs or control_selected_refs` 这种无声 fallback；正式持久化路径只使用 Context Slice refs/node ids，缺少 Context Slice builder 直接失败。control slice 不再作为 provider input/tool surface fallback。
- [x] `RequestRenderSnapshotRecord.included_node_ids` 优先来自 `context_slice.report.included_node_ids`，没有 slice 时才退回 control slice selected node ids。
- [x] Provider request snapshot 持久化路径缺 Context Slice builder 时直接失败，不再静默落回 control/draft request source。
- [x] Operations/Workbench/Trace 用户可见口径把旧 `direct_transcript_*` 展示为 Draft Input，避免误导为最终 provider 历史。
- [x] Request/render snapshot metadata 统一迁移到 `draft_input_*` / `draft_input_sequence_range` 口径；旧 `direct_transcript_*` 只保留在测试缺失断言中，防止回流。

### Phase 5. Tool schema 从树状态出发

- [x] Draft 不再作为最终 provider-visible `tool_schemas` 的来源；engine/request envelope 均从 request render snapshot `tool_schema_refs` 恢复最终工具面，draft 中残留 schema 仅作为 Context Workspace 候选输入与统计来源。
- [x] Tool owner 只提供 catalog/query；Context Workspace 通过 `ToolRuntimeRequestCatalog.list_runtime_request_bundles(...)` 与 `ToolContextService.get_tools(...)` resolve owner facts，树节点保存 refs/control state，provider-visible schema 仍由 Context Slice `tool_schema_refs` 选择。
- [x] Draft 侧 `tool_schemas` 在运行工作区 metadata 中改名为 `candidate_tool_schema_count` / Candidate tool schemas，避免把候选工具误称为 provider-visible 工具面。
- [x] Context Tree active tool surface 决定 `schema_enabled`；Context Slice active tool refs 只携带函数引用，request render 用这些 refs 过滤 owner-resolved `ToolSchema`。
- [x] Request render snapshot 的 `tool_schema_refs` 在 Context Slice 可用时记录 `source=context_slice`、`node_id/source_id/tool_ref_id`，不再把树选出的 schema 标成 draft 来源；Runtime tool surface 也会携带这些函数级来源元数据。
- [x] Provider renderer 只消费 request render snapshot 的 `tool_schema_refs[*].schema`；裸 `tool_schemas` 没有来源 ref 时不再进入 provider-visible tool set。
- [x] Orchestration engine 不再读取 `draft.tool_schemas` 来 resolve provider-visible tools；interactive 工具 resolve 改为读取 request render snapshot refs。
- [x] Context Slice 存在时 adapter 不再让 draft/control schema 自行获得 provider 可见性；draft/tool resolver 只提供 owner-resolved schema candidates，最终 visible schemas 由 Context Slice active refs、tree `schema_enabled` 和 runtime default policy 过滤。
- [x] `capability.search` 结果更新树状态，并影响下一轮 schema set；`enable=true` 直接触发 `ENABLE_TOOL_SCHEMA`，Context Tree enabled schema 名单和 request render 工具面由同一树状态驱动。

### Phase 6. Observation 与 UI 收口

- [x] Workbench timeline 显示 session ledger + runtime semantics projection，不等同 provider request；timeline 优先消费 LLM response item runtime semantic nodes 与 tool lifecycle projection，provider request/wire preview 只在 linked detail/trace 面展示。
- [x] Operations 显示 request render snapshot、slice id、tree revision、included/omitted counts。
- [x] Trace 能 drill down：slice ref -> owner fact -> provider wire item；Trace/linked entity detail 已暴露 provider input mapping、tool mapping、session/LLM/tool owner refs 和 provider wire preview 的受控摘要。
- [x] Trace provider input detail 展示 provider-visible tool name -> runtime tool surface / Context Tree 来源映射摘要。
- [x] Runtime LLM request preview API 输出 canonical `input_items` 与结构化 `runtime_context`，观察面不再只能看 draft `messages`。
- [x] UI 不直接展示内部 debug metadata；Workbench linked LLM detail 的 `provider_wire_preview` 已收成安全摘要，过滤 `payload_preview/input/messages/contents/tools` 等 raw provider body，debug/raw payload 只保留在 Operations/Trace 受控观察面。

### Phase 7. 删除临时结构

- [x] 清理任务路径遗留。
  - [x] 清理 `structured_replay` 遗留；当前生产代码/工具定义已无该输入模式入口，仅历史报告保留术语背景。
  - [x] 清理 `browser evidence path` 遗留；生产代码已删除 evidence path ladder，browser tool content、observe guidance、action trace summary 与 `browser_evidence` metadata 均不再输出 `evidence_path_*` 路径裁判字段，只保留 URL、selector、request id、payload/result shape、runtime globals、source request 等可验证事实。
  - [x] 清理 `probe_client` 遗留；当前生产代码/工具定义已无 `browser.runtime.probe_client` / `browser.runtime.call_client` 入口，仅保留负向断言和历史报告背景。
- [x] 清理所有 legacy prompt/prompting builder 路径；当前源码已无旧 `prompt_input` / `prompt_transcript` / `prompting` builder，剩余命名均为 provider request preview / renderer 正式边界。
- [x] 清理 metadata 中混入业务判断或 debug-only 的字段；`request_render_timings` 已从顶层 LLM request metadata 移出，只保留在 request render snapshot diagnostics/Operations 观察面；旧 `direct_tool_protocol_*` 观察字段退场，tool protocol 观察改由 provider render report 的 `runtime_input_filter` 摘要承载。
- [x] 清理 orchestration adapter 中未被调用的 observation snapshot preview 分支；provider request preview/record 只走 request render snapshot / Context Slice 投影路径，避免旧 `ContextObservationRenderInput` / delta debug helper 与正式 LLM request 边界混用。
- [x] 清理 recorded request snapshot 的旧 provider attachment mirror 恢复分支；即使历史 snapshot metadata/provider attachments 带有旧 tool schema mirror，也不会被恢复为正式 provider-visible tool set。
- [x] Recorded request snapshot 恢复必须存在正式 RequestRenderSnapshot 实体；只有旧 ContextSnapshot 或缺少 request snapshot repository 时返回 `None`，避免产生没有 input/tool refs 的空壳 provider request record。
- [x] 清理旧测试中依赖 session replay 直出的断言；当前 direct transcript / direct tool protocol 只保留负向断言，用户可见标签改为 Draft Input / Draft Sequence Range。

## 验收标准

- [x] 最新 run 的 runtime request report 显示 `request_context_source=context_slice` 或最终命名的 `context_model_slice`；单元路径已覆盖 request metadata、preview runtime context 和 Operations summary。
- [x] `request_render_snapshot.included_node_count > 0`；runtime snapshot payload、provider preview、Operations summary 均已展示 count 口径。
- [x] `request_render_snapshot.input_item_refs` 均能追溯到 Context Tree node id 和 owner ref；orchestration record 已携带 `input_item_refs`，持久化 request render snapshot 保留 `node_id/session_item_id/owner_*`。
- [x] Provider request 中没有 full tree debug body、debug/context slice、evidence verdict；preview/request metadata 只保留安全摘要，browser evidence path 已从 browser observe/tool metadata 和模型可见文本中退场。
- [x] Tool schema set 来自 Context Tree active tool surface；provider-visible schemas 从 request render snapshot `tool_schema_refs` 恢复，裸 draft schema 不再进入 provider-visible set。
- [x] protocol-required tool call/result pair 无孤儿、无丢失；runtime request filter 只丢弃无结果的 orphan `function_call`，保留 provider continuation 所需的 `function_call_output`。
- [x] 普通长链任务中没有任务特化工具或硬编码判断；生产路径已无东航/航班城市/票价等任务词硬编码，browser script insight 的排序词已收敛为通用 API/client/request/data/navigation 关键词，剩余 `pre-flight/in-flight` 仅为预检/并发语义。
- [x] Session 增长不会导致 provider request 线性全量膨胀；旧 segment 通过 summary/range 控制，LLM slice 不展开 archived range，request builder 在 projected input 存在时只采用 snapshot 投影输入，不再让长 draft replay 进入 provider transcript。
- [x] Workbench 不再因热路径全量重建 snapshot 明显卡顿；首屏先落 runtime request preview / request render snapshot 摘要，完整 Context Tree 后置加载，snapshot 默认不返回 `debug_body`，仅用户展开时按需加载。
- [x] Codex renderer 输出与抓包 trace 在结构层面一致；HTTP full input 不发送 `previous_response_id`，WebSocket fingerprint delta 才发送 `previous_response_id`，wire shape 对齐 Codex ResponsesApiRequest 的 `tools/tool_choice/parallel_tool_calls/include` 基础字段，profile/transport/client metadata 等差异由 provider 配置或 request overrides 承载。

## 测试计划

新增或调整单元测试：

- `test_context_tree_model_slice_from_session_items`
- `test_context_tree_model_slice_preserves_protocol_pairs`
- `test_runtime_request_uses_context_model_slice_not_session_replay`
- `test_request_render_snapshot_records_node_ids`
- `test_provider_renderer_consumes_slice_refs`
- `test_codex_renderer_matches_trace_shape`
- `test_capability_search_updates_active_tool_surface`
- `test_compaction_preserves_unclosed_tool_protocol_pairs`
- `test_no_debug_or_evidence_verdict_in_provider_request`

回归测试：

```bash
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py \
  tests/unit/test_context_tree_tool.py \
  tests/unit/test_orchestration_context_workspace_snapshot.py \
  tests/unit/test_runtime_llm_request.py \
  tests/unit/test_provider_request_renderer_protocol.py \
  tests/unit/test_openai_codex_renderer.py
```

本轮已执行的收口回归：

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py \
  tests/unit/test_orchestration_runtime_llm_request.py \
  tests/unit/test_orchestration_runtime_llm_request_builder.py \
  tests/unit/test_runtime_llm_request.py \
  tests/unit/test_runtime_llm_request_draft_collector.py \
  tests/unit/test_provider_renderer_canonical_request_integration.py \
  tests/unit/test_provider_request_renderer_protocol.py \
  tests/unit/test_openai_codex_renderer.py \
  tests/unit/test_anthropic_renderer.py \
  tests/unit/test_context_workspace_snapshot_boundary.py \
  tests/unit/test_context_workspace_tool_adapter.py \
  tests/unit/test_context_tree_tool.py \
  tests/unit/test_tool_providers.py \
  tests/unit/test_ui_operations_http.py
# 208 passed
```

长链验收：

```bash
make dev-up
python -m crxzipple.main db upgrade head
python -m crxzipple.main daemon status
```

然后提交一个无 browser 特化、无任务特化的长链任务，观察：

- request build 耗时。
- included node count。
- provider request wire preview。
- tool schema set 是否由 capability/tree 控制。
- 模型是否能通过通用工具探索和纠错。

## 风险与处理

- **风险：树状态跟不上 owner facts。**  
  处理：树只保存 refs，更新失败必须可重放；Context Workspace 提供按 session/run 重建控制节点的维护命令，但重建不进入 LLM 热路径。

- **风险：移除 session replay 后首轮输入为空。**  
  处理：user request / task.current_goal / current turn 必须作为 pinned control nodes；缺失时直接 fail fast，提示具体 owner fact 缺失。

- **风险：protocol pair 被 compaction 误折叠。**  
  处理：protocol-required refs 是硬约束，未闭合 pair 不允许被 summary 替代。

- **风险：provider renderer 再次开始理解业务。**  
  处理：renderer 只做结构翻译，不做 evidence gate、任务路线判断或工具选择。

- **风险：Operations/Workbench 继续依赖旧字段。**  
  处理：UI 消费 read model；read model 从 request render snapshot 和 owner query surface 投影，不直接拼 provider payload。

## 施工顺序建议

1. 先补 ContextModelSlice 和 request report 标识，不改 provider 行为，用测试证明 slice 能完整表达当前请求。
2. 再切 OpenAI Codex renderer，让它从 slice 渲染 provider request。
3. 删除 session replay fallback，确保失败能暴露真实缺失节点。
4. 扩展到其他 provider renderer。
5. 最后清理 UI/Operations/Trace 的旧观察字段。

核心判断标准很简单：**LLM 最终看到的 provider request，必须能从 Context Tree slice 解释；Context Tree slice，必须能追溯到 owner module facts；任何不能准确解释的内容，都不进入 provider request。**
