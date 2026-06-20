# Context Tree Observation Slice Visibility Refactor Plan

日期：2026-06-17

## 背景

本轮讨论确认：`SessionItemVisibility` 与 Context Tree 节点可见性存在功能重复。

过去的实现把 `SessionItem` 同时当成会话事实、模型 replay 候选、用户时间线素材和 trace 素材，因此在 Session item 上放了：

```text
model_visible
user_visible
chat_visible
trace_visible
```

但目标架构已经收敛为：

```text
Owner modules
  Session / Tool / Memory / Skill / Artifact / Workspace / LLM / Orchestration
        ↓ facts + refs
Context Tree
        ↓ observation slices
LLM renderer / UI timeline / Trace / Operations / Debug
```

因此可见性不应继续作为 owner fact 的固有属性。模块拥有事实；Context Tree 组织事实引用；不同观察者通过不同 slice 观察同一棵树。

## 核心结论

### 1. 模块不拥有 visibility

Session、Tool、Memory、Skill、Artifact、Workspace 等 owner module 只保证：

- 数据完整。
- 结构稳定。
- 来源可追溯。
- 可被引用。
- 可被估算。
- 可被 owner query service 读取。
- 可被授权 / redaction policy 约束。

它们不判断：

- 这条事实本轮是否给 LLM。
- 这条事实是否出现在用户 timeline。
- 这条事实是否在 trace 中展开。
- 这条事实是否进入 Operations summary。

### 2. Context Tree 拥有组织关系

Context Tree 是 runtime context control plane。它拥有：

- owner refs。
- active session / instance / segment / turn / step 状态。
- collapsed / pinned / consumed / archived / loaded / opened。
- tool schema enabled state。
- context budget estimate。
- slice inclusion state。
- omitted / collapsed / unresolved refs。

Context Tree 不复制 owner raw truth。

### 3. Slice / Renderer 拥有可见性

不同观察者对应不同 slice：

```text
llm_request_slice
user_timeline_slice
trace_timeline_slice
debug_tree_slice
operations_projection_slice
```

每个 slice 明确记录：

- audience。
- included node refs。
- omitted node refs。
- collapsed node refs。
- redacted node refs。
- unresolved refs。
- render policy。
- budget report。
- loss report。

Provider adapter / renderer 只消费 `llm_request_slice`，并按 provider / transport / model 能力翻译成 wire input。

## 当前问题

### Session visibility 与 Context Tree visibility 重复

当前代码中：

- `SessionItemVisibility.model_visible` 是 Session item 字段。
- `RuntimeReplayWindowBuilder` 会先按 `item.visibility.model_visible` 过滤。
- Context Workspace 又通过 `tree_snapshot_visible_nodes(...)` 和 `_node_included_in_slice(...)` 生成 context slice。

这导致两个控制面都在回答“模型能看到什么”。

### LLM request 有多条上下文来源

当前链路仍存在：

```text
session_service.build_replay_window(...)
  -> RuntimeReplayWindowBuilder
  -> draft.messages / draft.input_items

context_snapshot.context_slice.items
  -> RuntimeLlmRequest.transcript.items
```

当 context slice 存在时优先使用 slice；否则回退 draft/session item。这种 fallback 让施工结果难以判断。

### UI 可见与模型可见混在 SessionItem 上

`user_visible`、`chat_visible`、`trace_visible` 是观察面需求，不是 Session 事实本身。它们作为 SessionItem 固有字段会让 Session module 参与 UI/LLM/Trace 的展示策略。

## 目标状态

### Owner facts

Session item 目标字段应收敛为事实属性：

```text
SessionItem
  id
  session_key
  session_instance_id
  sequence_no
  kind
  role
  phase
  content_payload
  source_module
  source_kind
  source_id
  provider_item_id
  provider_item_type
  call_id
  tool_name
  metadata
  created_at
```

不再包含：

```text
model_visible
user_visible
chat_visible
trace_visible
```

如确有安全边界需求，另建 owner fact policy，而不是 observation visibility：

```text
content_policy
  model_use: allowed | redacted | forbidden
  user_display: allowed | redacted | forbidden
  trace_display: allowed | redacted | forbidden
```

第一阶段如果没有真实 redaction 需求，可以先不引入 `content_policy`。

### Context Tree node state

Context Tree 继续维护控制状态：

```text
ContextNode.state
  snapshot_visible
  collapsed
  pinned
  loaded
  opened
  consumed
  archived
  schema_enabled
  render_priority
  render_reason
```

其中：

- `snapshot_visible` 表示节点是否进入某次 snapshot 候选。
- `collapsed` 表示节点正文不展开，只保留摘要 / handle。
- `pinned` 表示后续 slice 优先保留。
- `consumed` 表示可降级为摘要。
- `archived` 表示保留追溯但默认不进主动 slice。
- `schema_enabled` 仅用于 tool schema mirror。

### Observation slice

新增统一 slice 概念：

```text
ContextObservationSlice
  id
  workspace_id
  session_key
  run_id
  audience
  items
  tool_refs
  included_node_ids
  omitted_node_ids
  collapsed_refs
  redacted_refs
  unresolved_refs
  budget
  loss
  created_at
```

`audience` 固定为：

```text
llm_request
user_timeline
trace_timeline
debug_tree
operations_projection
```

### LLM request

LLM request 只从 `llm_request_slice` 生成：

```text
Context Tree
  -> build_slice(audience="llm_request")
  -> RuntimeLlmRequest
  -> provider renderer
  -> provider wire input
```

Orchestration 不再直接从 Session replay window 构造模型输入。

## Compact 处理原则

LLM compact 结果不替换 Session 原始事实。

目标行为：

```text
原始 SessionItem 保留
compact response 作为新的 SessionItem / Context fact 追加
Context Tree 将旧范围 archived / collapsed
llm_request_slice 默认使用 compact summary
debug / trace slice 仍可追溯原始范围
```

这样既保留账本完整性，又让 LLM 上下文由 Context Tree 控制。

## 迁移步骤

### Phase 1: 术语收敛

- [x] 将文档中的 `SessionItemVisibility.model_visible` 标记为旧口径。
- [x] 将 `model_visible item` 改称为 `session fact candidate` 或 `session item ref`。
- [x] 将 `visible` 在 Context Tree 语境中限定为 `slice visible` / `snapshot visible`。
- [x] 在 `AGENTS.md` 或当前主设计文档中补充原则：owner modules do not own visibility。

### Phase 2: Context Slice 成为唯一 LLM 输入来源

- [x] 移除 `RuntimeLlmRequest` 对 draft/session item 投影的 fallback。
- [x] Context snapshot 缺失或 `llm_request_slice` 为空时，按 run mode 明确失败，不静默回退。
- [x] `runtime_llm_request.py` 只从 `context_snapshot.context_slice.items` 构建 `LlmInputItem`。
- [x] 删除 `_input_items_for_draft_messages(...)` 的 LLM 主路径使用。
- [x] 清理 request summary / baseline 中的 `structured_replay` / `message_projection` 旧输入模式统计。
- [x] 保留 provider preview 的 slice -> wire mapping，不暴露完整 slice body。

### Phase 3: Session 去 visibility

- [x] 删除 `SessionItemVisibility` value object。
- [x] 删除 `session_items` 表上的 `model_visible/user_visible/chat_visible/trace_visible` 字段。
- [x] 更新 Session DTO / HTTP / CLI / repository 查询参数。
- [x] Session application service 不再提供 `list_model_visible_items()` / `list_chat_visible_items()` / `list_trace_visible_items()`。
- [x] 所有 UI/Trace/LLM 读取改走 Context Workspace slice service。
- [x] 接受数据库重建，不提供旧字段兼容 shim。

### Phase 4: 建立 observation slice service

- [x] 在 Context Workspace 增加 `BuildContextObservationSliceInput`。
- [x] 支持 `audience=llm_request`。
- [x] 支持 `audience=user_timeline`。
- [x] 支持 `audience=trace_timeline`。
- [x] 支持 `audience=debug_tree`。
- [x] 支持 `audience=operations_projection`。
- [x] 每种 slice 输出 included / omitted / collapsed / unresolved / budget / loss report。
- [x] `llm_request` slice 输出 included / omitted / collapsed / unresolved / budget / loss report。
- [x] Slice item 只保存 owner refs 与已解析的渲染摘要，不保存 owner raw truth。

### Phase 5: Workbench / Trace 迁移

- [x] Workbench run detail 暴露 `user_timeline` observation slice 摘要，不依赖 runtime request preview 才能看到 slice 状态。
- [x] Workbench timeline 从 `SessionItem.user_visible/chat_visible` 迁移到 `user_timeline_slice` gate：timeline 内容来自 owner facts，展示资格由 slice refs 控制。
- [x] Trace timeline 从 `SessionItem.trace_visible` 迁移到 `trace_timeline_slice`。
- [x] Operations projection 从 owner module read model + observation slice 聚合，不读取 Session visibility。
- [x] UI 展示“为什么可见/为什么折叠/为什么省略”的 slice report。

### Phase 6: Compact 与 archive

- [x] Compact result 写入 Session 下方的新 fact，不覆盖原始 facts。
- [x] Context Tree 对 compact 覆盖范围生成 archive/collapse 状态。
- [x] `llm_request_slice` 默认包含 compact summary 和必要 frontier。
- [x] `debug_tree_slice` 可展开原始 item range。
- [x] Trace 展示 compact 前后关系和 replacement refs。

### Phase 7: Provider renderer 对齐

- [x] OpenAI / Codex Responses renderer 从 `llm_request_slice` 生成 provider-native `input` items。
- [x] Anthropic Messages renderer 从同一 slice 生成 messages/tool_use/tool_result。
- [x] Provider native continuation 只基于 renderer 后的 provider input 判断 delta，不读取 Session visibility。
- [x] Renderer 输出 mapping report：slice item id -> provider wire item。
- [x] Renderer 不接收不确定诊断、debug tree body、history budget noise。

## 删除项

以下路径目标上应删除或停用：

- `SessionItemVisibility`
- Session repository visibility filters
- Session API visibility query parameters
- Session CLI visibility options
- `list_model_visible_items`
- `list_chat_visible_items`
- `list_trace_visible_items`
- LLM request 中基于 session replay window 的 fallback
- RuntimeTranscript 中“普通 turn 直接从 SessionItem 决定当前历史”的主路径

## 保留项

以下能力应保留，但改由 slice 承担：

- 用户时间线展示。
- Chat 可见消息。
- Trace 展示。
- LLM request 上下文。
- Tool call/result protocol pairing。
- Context budget / loss report。
- Compact summary frontier。

## 验收标准

- [x] Session item schema 不包含 visibility 字段。
- [x] 新会话 LLM request metadata 能指向一个 `llm_request_slice_id`。
- [x] LLM actual request 中每个 input item 都能追溯到 slice item 或 provider renderer 生成原因。
- [x] Workbench timeline 不直接读取 Session visibility。
- [x] Trace timeline 不直接读取 Session visibility。
- [x] Context Tree debug body 不默认进入 provider request。
- [x] Compact 后原始 Session items 仍可追溯，但默认 LLM slice 只包含 compact summary/frontier。
- [x] 没有 context slice 时 normal turn 不静默退回 session direct replay。
- [x] 单测覆盖 owner fact -> slice -> renderer 的主链路。

## 施工记录

### 2026-06-17

- Phase 2 主链路已收敛为 `context_snapshot.context_slice.items -> LlmInputItem`，normal turn 不再静默 fallback 到 Session replay。
- Phase 3 已删除 Session item visibility value object、schema 字段、repository filter、HTTP/CLI 参数和 application service 可见性 helper。
- Session tools / tests 改为读取 Session facts；用户/模型/trace 可见性不再由 Session item 字段表达。
- Context Workspace slice 会从 Session owner fact 补齐 `role/tool_call_id/tool_name` 等确定引用，避免 tool result 在 provider protocol 过滤中被误判为孤儿。
- `session.items.current` 摘要会携带 active segment 与最近 tool interaction 的确定事实，保证 follow-up turn 能看到上一轮工具调用链路。
- Tool Context Tree provider 对工具目录读取失败降级为空工具观察切片，不让观察面故障阻断 LLM 主链路。
- Orchestration runtime preview 保留 provider-neutral `image_ref/file_ref`，附件物化与非视觉降级留给 provider renderer。
- Context Workspace 增加 `BuildContextObservationSliceInput`，`llm_request` observation slice 带 `ctxslice_*` 身份、`audience`、included/omitted/collapsed/unresolved/budget/loss report。
- Orchestration 通过 `BuildContextObservationSliceInput(audience="llm_request")` 构造 Context Slice，Runtime LLM request metadata 暴露 `llm_request_slice_id` 与 `context_slice_summary.slice_id`。
- Provider renderer preview 增加 `input_item_mapping_coverage`，每个 canonical input item 标记 `context_slice_item` / `input_item_source` / `provider_renderer_generated_or_unattributed`，用于审查 actual request 的来源完整性。
- Provider preview 顶层暴露 `llm_request_slice_id` / `context_slice_id` / `context_slice_audience`，避免 Workbench / Operations 为定位 LLM request slice 深挖 provider payload。
- Operations LLM detail 将 `llm_request_slice_id`、`provider_input_item_mapping_coverage` 和 provider mapping row 的 `trace_status/trace_reason` 投到 runtime summary / mapping table，UI 可直接审查切片与 provider input 的关系。
- Context Slice Builder 增加 audience 边界策略：`user_timeline` 只取会话/用户可读事实，`trace_timeline` 取审计节点与工具面，`debug_tree` 包含全部树节点，`operations_projection` 保留运维聚合需要的 runtime/session/tool 事实。
- Workbench run read model 接入 Context Slice Builder，生成 `audience=user_timeline` 的 run-level `context_slice_summary`；前端 Context 面板在没有 runtime request preview 时 fallback 展示该摘要，只展示 slice id/audience/计数/loss，不展示 owner raw truth。
- RuntimeResponseProjector 不再用 LLM response item 的 `model_visible/user_visible` 决定是否落 Session；已识别 response item 按语义事实投影，用户/模型可见性统一交给 Context Tree slice。
- Session Context Tree adapter 修复 `session.items.current` 聚合摘要：已消费/折叠工具历史只输出摘要、引用和 digest，不再通过父级 `recent_tool_interactions` 泄漏 raw tool result。
- Session HTTP / Conversation history 将 compact/archive 派生字段从 `visibility_state` 改为 `lifecycle_state`，避免 Session API 暗示自己拥有用户/模型观察可见性。
- Workbench timeline 接入 `user_timeline` slice gate：Context Slice 中存在 `session_item_id`、`llm_response_item_id`、`tool_run_id`、`execution_item_id`、`call_id` 等窄 refs 时，timeline item 必须命中 refs 才展示；slice 尚无可匹配 refs 时只展示摘要、不误清空 owner timeline。
- Trace UI route 接入 `trace_timeline` slice gate：Trace 事件事实仍来自 Events read model，展示资格由 Context Slice 中的窄 refs 控制；summary 基于过滤后的事件重算，避免 events 列表和摘要计数不一致。
- Trace gate 测试使用真实 Session owner fact 生成 Context Tree 节点，不手工伪造 session 子节点，避免绕过 owner module -> Context Workspace 的目标链路。
- Context Workspace Operations projection 接入 `operations_projection` slice：Operations 页面新增 `Observation Slices` 表，只展示 slice id/audience/session/run/revision/items/tools/included/omitted/collapsed/unresolved/token 计数，不投放完整 slice body 或 owner raw truth。
- Operations projection materializer 仍物化 owner module read model；Context Slice Builder 作为 Context Workspace read model 的观察面依赖注入，不让 Operations materializer 理解 Session visibility。
- Workbench Context 面板新增 Slice Report：展示 included / omitted node ids、collapsed refs、unresolved refs 及默认原因；后端只返回有限 handle 和可追溯 id，不返回 owner raw truth。
- Compact/archive 收口：Session compaction 保留原始 item 并追加 summary fact；Context Tree 将 archived Session item、archived range、archived tool interaction 标为 archived；`llm_request_slice` 排除 archived 明细但保留 compacted segment summary，`debug_tree` 仍可展开原始 item range。
- Context Slice Report 与 Context Snapshot metadata 增加 `archived_refs` / `archived_ref_count`，只记录稳定 owner refs、summary/compaction refs 和原因，不携带 archived 原文；Workbench Slice Report 与 Trace Snapshot 摘要展示 archive/replacement 关系。
- Phase 7 Provider renderer 边界收口：Codex websocket native continuation 的 delta 判定基于 renderer 生成后的 provider input fingerprint、instructions fingerprint 和 tool schema fingerprint；HTTP 路径保持 full replay 且不发送 `previous_response_id`。
- Provider wire payload 边界测试覆盖 Codex / Anthropic：`debug_body`、diagnostics、raw slice report、history budget raw note 不进入 actual provider payload；provider preview 只保留计数、mapping coverage 和安全预算摘要。
- 文档术语收口：`SessionItemVisibility.model_visible` 明确为旧口径，Context Tree 文档将 visible 限定为 `slice-visible` / `snapshot_visible`；`AGENTS.md` 增加 owner module 不拥有观察可见性的硬约束。
- 验证：
  - `python -m compileall -q src tools/sessions/local.py`
  - `python -m compileall -q src`
  - `PYTHONPATH=src pytest -q tests/unit/test_provider_renderer_canonical_request_integration.py tests/unit/test_provider_request_renderer_protocol.py tests/unit/test_openai_codex_renderer.py tests/unit/test_anthropic_renderer.py tests/unit/test_provider_protocol_render_router.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_operations_llm_read_model.py tests/unit/test_llm.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_openai_codex_renderer.py tests/unit/test_anthropic_renderer.py tests/unit/test_provider_request_renderer_protocol.py tests/unit/test_provider_renderer_canonical_request_integration.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_operations_llm_read_model.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_llm.py tests/unit/test_openai_codex_renderer.py tests/unit/test_provider_renderer_canonical_request_integration.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_trace_summary_and_events_use_event_read_model tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_trace_events_are_gated_by_trace_timeline_slice_refs`
  - `PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_workbench_run_and_steps_use_orchestration_read_model tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_workbench_displays_user_input_and_final_answer_timeline tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_trace_summary_and_events_use_event_read_model tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_trace_events_are_gated_by_trace_timeline_slice_refs tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_workspace_session_adapter.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_operations_context_workspace_read_model.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_operations_context_workspace_read_model.py tests/unit/test_operations_observation.py::OperationsObservationTestCase::test_operations_state_projection_maintenance_covers_all_modules tests/unit/test_operations_observation.py::OperationsObservationTestCase::test_projection_materializer_publishes_operations_invalidation`
  - `cd frontend && npm run typecheck`
  - `PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_workbench_run_and_steps_use_orchestration_read_model tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_workbench_displays_user_input_and_final_answer_timeline tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_trace_summary_and_events_use_event_read_model tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_trace_events_are_gated_by_trace_timeline_slice_refs tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_operations_context_workspace_read_model.py tests/unit/test_operations_observation.py::OperationsObservationTestCase::test_operations_state_projection_maintenance_covers_all_modules tests/unit/test_operations_observation.py::OperationsObservationTestCase::test_projection_materializer_publishes_operations_invalidation`
  - `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_workbench_run_and_steps_use_orchestration_read_model`
  - `PYTHONPATH=src pytest -q tests/unit/test_runtime_response_projector.py tests/unit/test_orchestration_runtime_llm_request_builder.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_conversations_http.py tests/unit/test_turns_http.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_workbench_run_and_steps_use_orchestration_read_model tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_workbench_displays_user_input_and_final_answer_timeline tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_workspace_session_adapter.py`
  - `cd frontend && npm run typecheck`
  - `PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_runtime_llm_request_builder.py`
  - `cd frontend && npm run typecheck`
  - `rg -n "SessionItemVisibility|list_model_visible_items|list_chat_visible_items|list_trace_visible_items|model_visible_item_count|model_visible_items|chat_visible|trace_visible|active_visible_item_count|visible_item_count|message_visibility|structured_replay" src tools frontend tests/unit`
  - `PYTHONPATH=src pytest -q tests/unit/test_conversations_http.py tests/unit/test_session_cli.py tests/unit/test_db_cli.py tests/unit/test_context_workspace_http.py tests/unit/test_runtime_llm_request.py tests/unit/test_operations_llm_read_model.py tests/unit/test_llm.py tests/unit/test_orchestration_context.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_sessions_tool_http.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_orchestration_memory.py::OrchestrationMemoryTestCase::test_request_memory_flush_records_durable_memory_without_transcript_reply tests/unit/test_turns_http.py::TurnsHttpTestCase::test_turn_compaction_endpoint_creates_compaction_run tests/unit/test_orchestration_tools.py::OrchestrationToolsTestCase::test_codex_websocket_provider_native_continuation_falls_back_to_full_input_when_slice_changes tests/unit/test_orchestration_tools.py::OrchestrationToolsTestCase::test_process_next_orchestration_assignment_exposes_skill_tools_via_context_tree_surface`
  - `PYTHONPATH=src pytest -q tests/unit/test_session.py tests/unit/test_session_http.py tests/unit/test_runtime_response_projector.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_session_segment_compaction.py tests/unit/test_runtime_transcript.py tests/unit/test_orchestration_runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_context_workspace_snapshot_boundary.py tests/unit/test_orchestration_loop_regression_baseline.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_sessions_tool_http.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py::test_session_segment_compaction_slice_uses_summary_not_archived_range`
  - `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tree_service.py::test_context_slice_builder_applies_audience_boundaries tests/unit/test_context_workspace_tree_service.py::test_context_slice_builder_resolves_session_item_text_from_owner tests/unit/test_context_workspace_tree_service.py::test_context_slice_builder_reports_unresolved_session_item_refs_only`
  - `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tree_service.py::test_context_slice_builder_applies_audience_boundaries tests/unit/test_workbench_read_model.py::test_workbench_context_slice_summary_uses_user_timeline_without_raw_text`
  - `cd frontend && npm run typecheck`
  - `python -m compileall -q src`
  - `PYTHONPATH=src pytest -q tests/unit/test_openai_codex_renderer.py tests/unit/test_anthropic_renderer.py tests/unit/test_provider_request_renderer_protocol.py tests/unit/test_provider_renderer_canonical_request_integration.py tests/unit/test_provider_protocol_render_router.py tests/unit/test_orchestration_runtime_llm_request_builder.py::test_request_envelope_accepts_snapshot_without_context_slice_items_when_transcript_exists`
  - `PYTHONPATH=src pytest -q tests/unit/test_orchestration_runtime_llm_request_builder.py::test_request_envelope_prefers_runtime_transcript_over_context_slice tests/unit/test_orchestration_runtime_llm_request_builder.py::test_request_envelope_uses_message_fallback_when_structured_transcript_is_absent`
  - `PYTHONPATH=src pytest -q tests/unit/test_provider_renderer_canonical_request_integration.py::test_provider_wire_payload_excludes_context_diagnostics_and_debug_body`
  - `PYTHONPATH=src pytest -q tests/unit/test_provider_renderer_canonical_request_integration.py tests/unit/test_openai_codex_renderer.py tests/unit/test_openai_codex_transport_wire_contract.py tests/unit/test_provider_protocol_render_router.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py::OrchestrationToolsTestCase::test_codex_websocket_provider_native_continuation_falls_back_to_full_input_when_slice_changes tests/unit/test_orchestration_tools.py::OrchestrationToolsTestCase::test_provider_native_tool_result_continuation_uses_previous_response_delta`

## 风险

- UI 迁移期间可能短暂缺少 timeline 数据。由于本轮接受数据库重建，不做旧结构兼容。
- Slice service 会成为关键路径，需要对空 slice、未解析 ref、预算超限做明确错误。
- 去掉 Session visibility 后，现有 Operations/Workbench 查询需要同步迁移，否则页面会空。

## 非目标

- 不引入任务特化 evidence gate。
- 不在内核维护 keyword trigger / semantic route map。
- 不让 Session/Tool/Memory/Skill 根据 audience 判断可见性。
- 不把完整 Context Tree XML 作为默认 LLM prompt。
- 不为了历史数据兼容保留双轨字段。

## 2026-06-17 深度清理补充

本轮按“正式化 / 退役”处理前序改造中的临时处置：

- 退役 `build_model_visible_session_item_runtime_window(...)` 旧入口，正式入口为
  `build_session_fact_runtime_window(...)`。
- 删除 Context Workspace Session adapter 中基于“最近 tool result / 最新
  llm invocation batch”的 implicit frontier 推断。没有明确 execution
  consumption fact 时，tool interaction 只作为 observed/folded fact，不展开为
  frontier，也不暴露 result 正文。
- Protocol required refs 中的 `visibility=model_visible` 改为
  `render_scope=provider_replay`，表达 provider replay 渲染范围，不再表达
  Session/用户/模型可见性。
- Tool result envelope 字段从 `model_visible_payload` /
  `user_visible_payload` 正式化为 `provider_replay_payload` /
  `user_summary_payload`。Tool 只提供事实和摘要，是否进入 provider 输入或
  UI timeline 由 Context Slice / renderer 决定。
- LLM response item 字段从 `model_visible` / `user_visible` 正式化为
  `provider_replay_candidate` / `user_timeline_candidate`。这是 provider
  response item 的后续投影候选属性，不是 Session visibility。
- Alembic `0072_llm_response_items` 使用新列名；
  `0080_normalize_context_snapshot_table` 改为 no-op schema marker，不再做旧
  context render snapshot / prompt body 兼容迁移。
- Active Context Workspace 文档中的 runtime-facing API 从旧 prompt body 口径
  收口到 Context Snapshot / observation slice / provider renderer。

清理后的主范围残留扫描：

```bash
rg -n "\bmodel_visible\b|\buser_visible\b|model_visible_payload|user_visible_payload|Model Visible|User Visible|build_model_visible_session_item_runtime_window|_fallback_frontier_tool_call_ids|fallback_frontier_tool_call_ids|\"visibility\": \"model_visible\"|render_prompt_body|ContextRenderService|prompt_body|structured_replay|message_visibility" src tests frontend alembic tools docs/context-workspace-prompt-tree-design.md docs/context-workspace-prompt-tree-development.md AGENTS.md docs/agents/hosted-agent-operating-contract.md -g '!docs/archive/**'
```

结果：无匹配。

本轮新增验证：

```bash
PYTHONPATH=src python -m compileall -q src tools/command/local.py alembic/versions/0080_normalize_context_snapshot_table.py
PYTHONPATH=src pytest -q tests/unit/test_runtime_transcript.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py
PYTHONPATH=src pytest -q tests/unit/test_llm.py tests/unit/test_llm_adapters.py tests/unit/test_runtime_response_projector.py tests/unit/test_operations_llm_read_model.py tests/unit/test_workbench_read_model.py tests/unit/test_orchestration_execution_chain.py
PYTHONPATH=src pytest -q tests/unit/test_command_tools.py tests/unit/test_tool_result_model_text.py tests/unit/test_tool_execution.py tests/unit/test_tool_source_service.py tests/unit/test_runtime_transcript.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py
```

结果：通过。

## 2026-06-17 Orchestration / Skills / Progress 收口

前序深度清理后暴露的 3 个剩余失败已正式收口：

- Orchestration runtime draft 新增 `SkillRuntimeRequestResolutionPort`，通过
  Skills owner 解析 runtime request skill readiness，只携带 metadata 给
  Context Workspace，不把 skill 内容或 prompt 文本塞回 LLM request。
- Context Workspace run metadata 新增 `available_skill_names` /
  `resolved_skills` / `skill_runtime_request`。Skill ContextNodeProvider
  因此按本轮 runtime readiness 展示 skill，不再在没有 metadata 时误回退为
  “全部 skill 可见”。
- Skills module 在每次 runtime request resolution 完成时发出
  `skills.resolution.completed`。该事件表示“本轮解析完成”；readiness changed
  事件仍只表示 owner readiness 语义发生变化。
- Execution chain 的 assistant progress session item 摘要改为 item 粒度：
  `assistant_progress_item_ids` 只记录当前 item id，不再把 step 级 progress id
  集合复制到每条 session item execution fact。

新增验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py
# 36 passed

PYTHONPATH=src python -m compileall -q src tools/command/local.py alembic/versions

PYTHONPATH=src pytest -q tests/unit/test_runtime_transcript.py \
  tests/unit/test_context_workspace_session_adapter.py \
  tests/unit/test_orchestration_context_workspace_snapshot.py \
  tests/unit/test_llm.py tests/unit/test_llm_adapters.py \
  tests/unit/test_runtime_response_projector.py \
  tests/unit/test_operations_llm_read_model.py \
  tests/unit/test_workbench_read_model.py
# 191 passed

PYTHONPATH=src pytest -q tests/unit/test_command_tools.py \
  tests/unit/test_tool_result_model_text.py \
  tests/unit/test_tool_execution.py \
  tests/unit/test_tool_source_service.py
# 48 passed

PYTHONPATH=src pytest -q tests/unit/test_skills_context.py \
  tests/unit/test_context_workspace_skill_adapter.py \
  tests/unit/test_skills_owner_catalog_persistence.py \
  tests/unit/test_context_workspace_tree_service.py \
  tests/unit/test_context_tree_tool.py
# 76 passed
```

## 2026-06-17 LLM Request Input Boundary 收口

审查最新长链 run `obs_codex_like_longchain_20260617_153754` 后确认：

- 最终 LLM 请求仍包含 `run.goal`，所以不是用户目标丢失。
- 最终 provider input 长到约 116KB，混入大量 `session.step.*`、
  `runtime_llm_invocation`、`runtime_tool_run` 等 Context Tree 观察节点。
- 模型最后把“确认可用入口”误当作任务交付，返回
  `phase=final_answer`，provider continuation 为 `needs_follow_up=false`。

因此问题根因是：Context Tree observation slice 被当成 provider transcript
输入使用，控制面/观察面信息淹没了 session runtime transcript。

正式边界调整：

```text
Session runtime transcript
  -> RuntimeLlmRequest.transcript.items
  -> provider renderer input

Context snapshot / observation slice
  -> context snapshot refs
  -> tool schema mirror
  -> Operations / Trace / Workbench debug
```

`RuntimeLlmRequestBuilder.request_envelope(...)` 不再使用
`context_snapshot.context_slice.items` 覆盖 `draft.input_items`。正常交互请求的
provider input 以 session/runtime transcript 为准；Context Tree 仍负责 snapshot、
tool schema mirror、metadata、trace refs，但不把每个观察节点渲染为模型消息。

新增/调整验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_runtime_llm_request_builder.py \
  tests/unit/test_orchestration_runtime_llm_request.py \
  tests/unit/test_provider_renderer_canonical_request_integration.py
# 36 passed

PYTHONPATH=src pytest -q tests/unit/test_codex_trace_fixture.py \
  tests/unit/test_runtime_response_projector.py \
  tests/unit/test_workbench_read_model.py \
  tests/unit/test_operations_llm_read_model.py \
  tests/unit/test_operations_llm_render_report.py \
  tests/unit/test_openai_codex_renderer.py \
  tests/unit/test_openai_codex_transport_wire_contract.py \
  tests/unit/test_provider_renderer_canonical_request_integration.py \
  tests/unit/test_orchestration_runtime_llm_request.py \
  tests/unit/test_orchestration_runtime_llm_request_builder.py
# 66 passed
```

## 2026-06-17 Runtime Transcript 当前 Turn 边界收口

继续审查同一长链 run 后确认：切回 session/runtime transcript 后，provider
input 不再吃 Context Tree observation slice，但 replay window 仍可能把同一
session 中上一任务的成对 tool call/result 带入当前任务。示例中当前任务用户消息在
`sequence_no=42`，旧天气能力测试的 tool pair 从 `sequence_no=4` 开始仍被保留，
导致 provider transcript 跨任务污染。

正式边界调整：

- Normal turn / session start 的 provider replay 只保留当前用户消息之后的
  session facts：当前 assistant progress、成对 tool call/result、
  provider external activity。
- 上一 turn 的原始 tool protocol 不再自动进入下一 turn。跨 turn 需要的历史应由
  session compaction、memory、context slice summary 或用户显式提问后的检索提供，
  而不是 raw tool transcript 常驻。
- `RuntimeReplayWindowBuilder._filter_current_protocol_items(...)` 将 tool
  result index 和 tool call 选择都限制在当前用户消息之后。

同时收掉 response-item 化后的旧兜底重复：

- `LLM response_items -> SessionItem` 是主路径。
- `engine._assistant_items_for_tool_calls(...)` 只在没有 response item projection
  时作为旧 provider fallback 使用。
- 后续新运行不再同时写入 response-item assistant progress 和
  invocation 聚合 assistant message。旧运行中已持久化的重复 item 不做历史兼容清理。

新增/调整验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_runtime_transcript.py \
  tests/unit/test_orchestration_runtime_llm_request_builder.py \
  tests/unit/test_orchestration_runtime_llm_request.py \
  tests/unit/test_orchestration_execution_chain.py
# 73 passed
```

## 2026-06-17 旧 Context Slice Input 路径退役

为避免“双轨并行”，继续清理 runtime request 构造器中的旧路径：

- 删除 `context_snapshot.context_slice.items -> LlmInputItem` 的投影函数族。
- Provider renderer 仍接收 canonical `input_items`，但这些 item 应来自
  runtime transcript/session facts，而不是 Context Tree slice。
- Context snapshot / context slice metadata 仍可进入 request metadata 供
  Operations、Trace、Workbench 观察，但 provider wire payload 的 `input` 不读取它。
- Loop regression baseline 指标从 `llm_context_slice_*` 迁移为
  `llm_runtime_transcript_*`，避免把已退役路径当作成功指标。

同时补齐两个通用边界：

- 当 session 中存在旧工具项但 normal-turn protocol replay 被过滤为空时，
  `RuntimeLlmRequestDraftCollector` 回退到当前 inbound transcript，避免当前用户消息丢失。
- `RuntimeLlmRequestBuilder` 根据 LLM capabilities 清洗 runtime transcript；
  非 `VISION_INPUT` 模型不会接收 `image` / `image_ref` blocks，保留可读文本和
  `[image omitted: model does not support vision input]` 占位。

新增/调整验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_openai_codex_renderer.py \
  tests/unit/test_provider_request_renderer_protocol.py \
  tests/unit/test_provider_renderer_canonical_request_integration.py \
  tests/unit/test_orchestration_context.py \
  tests/unit/test_llm.py \
  tests/unit/test_operations_llm_read_model.py \
  tests/unit/test_runtime_llm_request.py \
  tests/unit/test_orchestration_loop_regression_baseline.py \
  tests/unit/test_runtime_transcript.py \
  tests/unit/test_orchestration_runtime_llm_request.py \
  tests/unit/test_orchestration_runtime_llm_request_builder.py \
  tests/unit/test_orchestration_execution_chain.py
# 135 passed
```

## 2026-06-17 LLM Request Metadata 安全预览收口

继续审查 Workbench 变慢和运行面混乱后确认：provider input 已不再读取
Context Tree slice，但 `RuntimeLlmRequest.request_metadata()` 仍会把
`RuntimeLlmContextSnapshot.to_payload()` 整包写入 LLM invocation metadata。
旧 payload 包含 `debug_body`、完整 `context_slice.items[*].text/content`、
provider attachment mirror 的完整 schema/文件镜像。它们虽然不进入 provider
wire input，但会进入持久化、Operations read model、Workbench/Trace 预览，
造成观察面膨胀，并让调试字段看起来像 runtime 输入。

正式边界调整：

- Context Workspace 继续持有完整 snapshot record，包括 debug body、完整
  observation slice 和 provider attachments。
- LLM request envelope / invocation metadata 只保存安全预览：
  - `snapshot_id`、node ids、refs、estimate、diagnostics。
  - `context_slice` 只保留 slice/run/session 引用、item refs、active tool refs、
    report 计数，不保留正文内容。
  - `provider_attachment_mirror` 只保留计数、schema names、runtime request draft
    摘要，不保留完整 tool schema/file/artifact payload。
- `context_snapshot_preview_payload(...)` 与
  `RuntimeLlmContextSnapshot.to_payload()` 使用同一类安全摘要，避免手工构造的
  metadata 在 provider preview / runtime request summary 中绕过过滤。
- 完整上下文调试仍通过 Context Workspace snapshot/read model 查看，不通过 LLM
  invocation metadata 搬运。

新增/调整验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request.py \
  tests/unit/test_orchestration_runtime_llm_request.py \
  tests/unit/test_context_workspace_snapshot_boundary.py \
  tests/unit/test_orchestration_runtime_llm_request_builder.py \
  tests/unit/test_orchestration_context_workspace_snapshot.py \
  tests/unit/test_openai_codex_renderer.py \
  tests/unit/test_provider_request_renderer_protocol.py \
  tests/unit/test_llm.py
# 97 passed

PYTHONPATH=src pytest -q tests/unit/test_openai_codex_renderer.py \
  tests/unit/test_provider_request_renderer_protocol.py \
  tests/unit/test_provider_renderer_canonical_request_integration.py \
  tests/unit/test_orchestration_context.py \
  tests/unit/test_llm.py \
  tests/unit/test_operations_llm_read_model.py \
  tests/unit/test_runtime_llm_request.py \
  tests/unit/test_orchestration_loop_regression_baseline.py \
  tests/unit/test_runtime_transcript.py \
  tests/unit/test_orchestration_runtime_llm_request.py \
  tests/unit/test_orchestration_runtime_llm_request_builder.py \
  tests/unit/test_orchestration_execution_chain.py \
  tests/unit/test_context_workspace_snapshot_boundary.py
# 136 passed

rg -n "input_mode.*context_slice|source=\"context_slice\"|llm_context_slice_steps|llm_context_slice_item_count|_input_items_for_context_snapshot" src tests -g '*.*'
# no matches

rg -n "payload\\[\\\"context_snapshot\\\"\\]\\[\\\"debug_body\\\"\\]|context_snapshot.*raw_tree_body|request_metadata.*raw_tree_body|request_metadata.*debug_body" src tests -g '*.py'
# only debug_body_estimated_tokens budget metric remains

git diff --check
# passed
```

## 2026-06-17 Workbench / Trace Debug Body 按需查看

上一节把 Context Snapshot 的 `debug_body` 改为默认不返回后，Workbench / Trace
原先的 XML 面板会显示空请求内容。为保持“默认轻量、调试按需”的用户体验，继续补齐
显式加载入口。

正式边界调整：

- Workbench / Trace 默认刷新仍只加载 snapshot 摘要。
- API client 的 `load*ContextSnapshot(...)` / `load*ContextSnapshotById(...)`
  增加 `includeDebugBody` 可选参数，默认 `false`。
- XML tab 无正文时显示“加载 Debug XML”按钮；用户点击后才调用
  `include_debug_body=true`。
- 点击加载后的完整 `debug_body` 只存在当前页面状态中，不改变默认刷新策略。
- `debug_body` 前端类型改为可选字段，避免页面假设历史 snapshot 总有正文。

新增/调整验证：

```bash
cd frontend && npm run typecheck
# passed

PYTHONPATH=src pytest -q tests/unit/test_context_workspace_http.py \
  tests/unit/test_runtime_llm_request.py \
  tests/unit/test_llm_http.py \
  tests/unit/test_operations_llm_read_model.py
# 18 passed

cd frontend && npm run build
# passed

git diff --check
# passed
```

## 2026-06-17 Context Snapshot Debug Body 默认按需加载

继续检查 Workbench / Trace 加载慢的问题后确认：即使 LLM invocation metadata 已做
安全投影，前端仍会在加载运行上下文时自动调用
`/context-workspaces/runs/{run_id}/snapshot` 或 `/context-workspaces/snapshots/{id}`，
而 snapshot DTO 默认包含完整 `debug_body`。这会绕过 metadata 收口，把完整树体
随首屏/刷新请求带回 UI。

正式边界调整：

- Context Workspace snapshot 仍持久化完整 `debug_body`。
- `POST /context-workspaces/by-session/{session_key}/render` 仍显式返回 debug body；
  这是主动渲染/调试接口。
- `GET /context-workspaces/runs/{run_id}/snapshot` 和
  `GET /context-workspaces/snapshots/{snapshot_id}` 默认只返回摘要，不返回
  `debug_body`。
- 读取历史 snapshot 如确实需要完整正文，必须显式传
  `include_debug_body=true`。
- Workbench / Trace 类型将 `debug_body` 改为可选；默认自动加载路径不请求正文。

新增/调整验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_http.py \
  tests/unit/test_runtime_llm_request.py \
  tests/unit/test_llm_http.py \
  tests/unit/test_operations_llm_read_model.py
# 18 passed

cd frontend && npm run typecheck
# passed

PYTHONPATH=src pytest -q tests/unit/test_context_workspace_http.py \
  tests/unit/test_context_workspace_tree_service.py \
  tests/unit/test_context_workspace_session_adapter.py \
  tests/unit/test_context_workspace_tool_adapter.py \
  tests/unit/test_orchestration_context_workspace_snapshot.py \
  tests/unit/test_runtime_llm_request.py \
  tests/unit/test_llm_http.py \
  tests/unit/test_operations_llm_read_model.py
# 124 passed

git diff --check
# passed
```

## 2026-06-17 Runtime Request Preview 出口投影收口

继续追踪 UI 慢和“观察数据像运行输入”的问题后确认：即使新 invocation 的
`request_metadata` 已经变轻，HTTP preview / Operations detail 仍可能把旧运行或
手工调用中保存的原始 `invocation.request_metadata` 原样返回给前端。这样会把
历史 `debug_body`、`context_slice.items[*].text`、完整 tool schema/file mirror
重新带回 Workbench / Trace / Operations。

正式边界调整：

- 新增 `request_metadata_preview_payload(...)` 作为统一出口投影：
  - `context_snapshot` 使用 `context_snapshot_preview_payload(...)`。
  - `tool_surface` 只保留 surface id、function count、function names、mirrored
    schema names。
  - 顶层和嵌套结构跳过 `debug_body`、`raw_tree_body`、`text`、`content`、
    `messages`、`input`、`tool_schemas`、`files`、artifact blocks 等大字段。
  - 复杂字典/列表按有限深度和数量裁剪，避免旧 metadata 膨胀 UI payload。
- `/llms/{id}/invocations/{invocation_id}/runtime-request-preview` 返回的
  `provider_request_options.request_metadata` 改为安全投影。
- Operations LLM detail 的 `request_payload.request_metadata` 改为安全投影。
- 持久化层不做历史兼容迁移；旧数据在读出口被投影，新结构写入时自然是轻量摘要。

新增/调整验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_runtime_llm_request.py \
  tests/unit/test_llm_http.py \
  tests/unit/test_operations_llm_read_model.py \
  tests/unit/test_llm.py
# 34 passed

PYTHONPATH=src pytest -q tests/unit/test_openai_codex_renderer.py \
  tests/unit/test_provider_request_renderer_protocol.py \
  tests/unit/test_provider_renderer_canonical_request_integration.py \
  tests/unit/test_orchestration_context.py \
  tests/unit/test_llm.py \
  tests/unit/test_llm_http.py \
  tests/unit/test_operations_llm_read_model.py \
  tests/unit/test_runtime_llm_request.py \
  tests/unit/test_orchestration_loop_regression_baseline.py \
  tests/unit/test_runtime_transcript.py \
  tests/unit/test_orchestration_runtime_llm_request.py \
  tests/unit/test_orchestration_runtime_llm_request_builder.py \
  tests/unit/test_orchestration_execution_chain.py \
  tests/unit/test_context_workspace_snapshot_boundary.py
# 145 passed

git diff --check
# passed
```
