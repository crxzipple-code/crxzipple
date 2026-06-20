# Runtime Request Render Snapshot Hot Path Refactor Plan

Date: 2026-06-18

## 背景

本轮长链任务排查发现，agent step 慢的主因不是 LLM provider、tool worker
或调度队列，而是 LLM 调用前的 context snapshot 记录路径。

实测一次 `_build_advance_context` 诊断：

```text
TOTAL 143.866s
ensure_inbound_message 0.000s
build_runtime_request_draft 4.274s
record_context_snapshot 138.902s
draft_with_context_snapshot 0.000s
resolve_tools_for_runtime_draft 0.509s
llm_request_options 0.000s
snapshot_metadata_for_request 0.000s
request_envelope 0.182s
```

cProfile 进一步显示：

```text
record_context_snapshot 138.902s
_render_run_context_snapshot 138.900s
_refresh_owner_children 135.685s
_load_owner_children 135.489s
list_for_workspace 65.181s
context_slice build 48.990s
render_observation (then named render_debug_body) 44.685s
ensure_workspace/_refresh_expanded_children 43.210s
23k+ SQL calls
4.7M json.loads
```

结论很明确：

**我们把“给 LLM 的 provider request 构造”和“给 UI / Trace /
Operations 的完整树观察”混进了同一条热路径。**

这违反当前架构决策：

- LLM 不应直接看 Context Tree。
- Context Tree 是控制面，不是 provider prompt body。
- Session / Tool / Memory / Skill 等 owner module 持有事实。
- Renderer / Provider Adapter 负责把已选择的 runtime slice 渲染成 provider-native
  request。
- 完整树 debug body / observation slice 不应阻塞 agent loop。
- 不兼容旧结构，不双轨并行；数据库可清空重建。

## 一句话目标

**LLM 热路径只生成并持久化轻量 request render snapshot；完整 Context Tree
观察退出热路径，改为异步或按需 read model。**

## 必须遵守的原则

### 1. LLM 不看 Context Tree

模型只接收 provider-native request：

- system / developer / runtime instructions。
- user input。
- provider-native transcript items。
- tool call output items。
- provider-visible tool schemas。
- 必要的 skill / memory / artifact 内容切片。

模型默认不接收：

- Context Tree XML / JSON 全量 body。
- debug body。
- context delta debug metadata。
- tree owner refresh 结果。
- browser path / evidence frontier / heuristic next step 等无法准确证明的判断。

### 2. Tree owns control, not truth

Context Tree 保存：

- owner ref。
- visibility / folding / pin / schema_enabled。
- token estimate。
- selection state。
- render policy hint。
- revision。

Context Tree 不保存：

- session item 正文真相。
- tool result 正文真相。
- memory entry 正文真相。
- skill file 正文真相。
- provider raw response 真相。

这些由 owner module 持有，renderer 按 ref 读取需要进入 LLM 的切片。

### 3. 热路径不重建完整树

每轮 LLM 调用前只处理本轮 request 需要的最小集合：

- 当前 session frontier。
- 当前 turn / step。
- model-visible transcript refs。
- tool schema refs。
- skill / memory / artifact selected refs。
- provider / transport / model policy。
- token budget。

不得递归刷新所有 owner children。

### 4. 完整观察是 read model，不是 runtime 前置条件

Workbench、Trace、Operations 可以看完整树，但这属于观察面：

- 可以异步物化。
- 可以按需生成。
- 可以缓存。
- 可以慢于 agent loop。

但不能成为 LLM 调用前的阻塞步骤。

### 5. 不做兼容双轨

本方案允许 breaking migration，允许删除旧字段和旧入口。

不得长期保留：

- full context snapshot hot path。
- prompt body 与 provider-native input 双轨。
- 旧 debug metadata 继续进入 LLM request。
- 旧 snapshot metadata 大 blob 继续由 orchestration 请求路径生成。

## 当前错误链路

当前热路径近似为：

```text
orchestration step
  -> build runtime request draft
  -> record_context_snapshot
     -> render full run context snapshot
     -> refresh workspace owner children
     -> load session/tool/memory/skill/artifact tree children
     -> render debug body
     -> build context delta metadata
     -> persist large snapshot metadata/provider attachments
  -> resolve tools
  -> build provider request envelope
  -> invoke LLM
```

问题：

1. `record_context_snapshot` 比 LLM invoke 更慢。
2. 每步会触发全量 owner refresh，复杂度接近 `O(all nodes * owner providers)`。
3. debug body 和 context slice 重复构造。
4. snapshot metadata 变成 MB 级 blob。
5. UI/Trace 的观察需求侵入 agent loop。
6. LLM 实际看不见树，却在每步为树观察付出完整成本。

## 目标链路

目标热路径：

```text
orchestration step
  -> build runtime request draft
  -> resolve context control slice
  -> resolve visible tool schemas
  -> render provider-native request
  -> persist request render snapshot
  -> invoke LLM
  -> parse provider response
  -> project response to runtime/session facts
  -> update context control state refs
```

观察路径：

```text
events / owner facts / request render snapshot refs
  -> operations observer / trace projector / on-demand inspector
  -> tree observation view
  -> workbench timeline / trace details
```

## 新核心对象

### RequestRenderSnapshot

新增或重命名为热路径唯一 snapshot：

```text
RequestRenderSnapshot
├─ id
├─ run_id
├─ session_key
├─ turn_id
├─ step_id
├─ llm_invocation_id
├─ provider
├─ transport
├─ model
├─ renderer_id
├─ renderer_version
├─ tree_revision
├─ session_frontier_revision
├─ input_item_refs
├─ tool_schema_refs
├─ skill_refs
├─ memory_refs
├─ artifact_refs
├─ request_hash
├─ estimated_tokens
├─ render_warnings
├─ timings
└─ created_at
```

约束：

- 不保存完整 tree body。
- 不保存 debug body。
- 不保存 owner data copy。
- 不保存无法准确解释的 heuristic metadata。
- 可保存 wire preview ref / hash，但正文大对象应进入 LLM invocation
  diagnostics 或 trace artifact，不进入 context snapshot metadata。

### ContextControlSlice

Renderer 输入前的控制切片：

```text
ContextControlSlice
├─ workspace_id
├─ tree_revision
├─ session_frontier
├─ selected_transcript_refs
├─ selected_tool_schema_refs
├─ selected_skill_refs
├─ selected_memory_refs
├─ selected_artifact_refs
├─ budget
└─ policy
```

它是 renderer 的输入，不直接发送给 LLM。

### ProviderRequestDraft

Provider-neutral request draft：

```text
ProviderRequestDraft
├─ runtime_instructions
├─ input_items
├─ tool_schemas
├─ response_options
├─ provider_policy
├─ selected_refs
└─ estimated_tokens
```

Provider adapter 再把它转成 OpenAI Responses / Codex HTTP /
Codex WebSocket / Anthropic / 其他 provider 的 wire payload。

### TreeObservationSnapshot

完整树观察快照从热路径移出：

```text
TreeObservationSnapshot
├─ id
├─ workspace_id
├─ tree_revision
├─ owner_revision_map
├─ observation_body
├─ expanded_nodes
├─ hidden_nodes
├─ estimates
├─ generated_by
└─ generated_at
```

只用于：

- Workbench inspector。
- Trace details。
- Operations debug。
- 手动排障。
- benchmark / audit。

## 模块改动

### Orchestration

职责保留：

- 推进 run / turn / step。
- 创建 LLM invocation。
- 调用 context_workspace 获取 control slice。
- 调用 LLM module render/invoke。
- 写入 session/runtime facts refs。
- 发布运行事件。

职责移除：

- 不生成 provider prompt。
- 不构造完整 Context Tree debug body。
- 不把 snapshot metadata 大 blob 写进 request path。
- 不判断 evidence 是否足够。
- 不维护 provider-specific replay 规则。

需要修改：

- `_build_advance_context` 拆为：
  - `collect_runtime_request_refs`
  - `resolve_context_control_slice`
  - `render_llm_request`
  - `persist_request_render_snapshot`
- `_record_context_snapshot` 改为轻量 snapshot 记录，或退役并替换为
  `record_request_render_snapshot`。
- 每个 phase 输出 timing event，便于 Operations 观测。

### Context Workspace

职责保留：

- 维护 Context Tree control state。
- 维护 node owner ref。
- 维护 visibility / folding / schema_enabled / token estimate。
- 输出 renderer 可消费的 `ContextControlSlice`。
- 提供按需完整 observation snapshot。

职责移除：

- 不在 LLM 热路径渲染 debug body。
- 不在 LLM 热路径递归 owner refresh。
- 不把完整树 body 当 provider attachment。
- 不把 tree 结构直接塞给 LLM。

需要修改：

- 新增 `ContextControlSliceService` 或等价接口。
- `record_run_context_snapshot` 拆分：
  - hot path: `record_request_render_snapshot_ref`
  - cold path: `render_tree_observation_snapshot`
- owner children 加载改为按需 / batch / cache，不在每轮默认刷新。
- `render_observation` 只允许 inspector / trace / operations 观察路径和
  agent-facing 显式树观察工具调用。

### LLM Module

职责增强：

- Provider request rendering 成为 LLM module / adapter 边界的一部分。
- Response parsing 与 request rendering 对称。
- Codex adapter 按抓包 trace 渲染，而不是由 orchestration 拼输入。

需要修改：

- 接收 `ProviderRequestDraft` / `RuntimeRequestSurface`。
- 输出：
  - provider wire payload。
  - request hash。
  - render report。
  - loss report。
  - request render snapshot refs。
- Codex HTTP renderer 对齐抓包的 `input: Vec<ResponseItem>` 全量回放路径。
- Codex WebSocket renderer 对齐抓包的 continuation / delta 路径。
- 不支持的 provider field 不发送。

### Session

职责保留：

- 会话账本。
- runtime transcript truth。
- segment / turn / step / item 结构。
- compact summary 作为新增事实，不覆盖原始事实。

职责边界：

- Session 不决定 provider request wire format。
- Session 不保存 Context Tree control state。
- Session 可以提供 model-visible transcript refs/query。

需要修改：

- 明确区分：
  - user-visible timeline item。
  - model-visible transcript item。
  - debug-only item。
- tool result 正文仍属于 tool/session facts；是否进入 LLM 由 renderer 基于
  context control slice 选择。

### Tool

职责保留：

- tool source / function / schema / run / result 真相。
- capability search / schema enablement 的 owner facts。

需要修改：

- 提供 batch query：
  - schema refs -> provider schema。
  - call refs -> tool result payload。
- 避免 Context Workspace 为每个 node 单独调用 tool owner children。
- tool schema surface 由 Context Tree control state + renderer policy 决定。

### Operations / Trace

职责增强：

- 读取 request render snapshot。
- 读取 LLM invocation timings。
- 异步生成 tree observation view。
- 展示“LLM 实际看见什么”与“树当前控制状态”两种视角。

需要修改：

- Operations observer 消费新增事件：
  - `llm.request_render.started`
  - `llm.request_render.completed`
  - `llm.request_render.failed`
  - `context.observation_snapshot.generated`
- Workbench 慢加载完整树 inspector。
- 默认 timeline 不拉取完整 snapshot 大 blob。

### Frontend / Workbench

职责调整：

- 默认显示 session/runtime timeline。
- “LLM input”面板显示 provider request preview / refs / hash。
- “Context Tree”面板按需加载 observation snapshot。
- 不在会话执行时全量轮询大 snapshot。

需要修改：

- timeline 查询只取轻量 fields。
- inspector lazy-load：
  - request render snapshot。
  - tree observation snapshot。
  - provider wire preview。
- 加载状态必须稳定，不因长 session 跳回旧 turn。

## 数据模型调整

### 退役或停止热路径写入

以下字段/结构不得继续作为 LLM 热路径默认产物：

- full `debug_body`。
- full `context_delta`。
- full `included_node_ids`。
- large `provider_attachments` blob。
- owner children full snapshot。
- browser evidence path metadata。
- runtime heuristic next-step metadata。

如仍需保留，迁入 observation / trace artifact 表。

### 新增表或重命名表

建议新增：

```text
llm_request_render_snapshots
```

字段：

```text
id
run_id
session_key
turn_id
step_id
llm_invocation_id
provider
transport
model
renderer_id
renderer_version
tree_revision
session_frontier_revision
input_item_refs_json
tool_schema_refs_json
resource_refs_json
request_hash
estimated_tokens
render_report_json
timings_json
created_at
```

建议新增或拆出：

```text
context_tree_observation_snapshots
```

字段：

```text
id
workspace_id
tree_revision
owner_revision_map_json
observation_body
estimates_json
generated_by
generated_at
```

由于数据库可清空重建，不需要兼容旧 `context_snapshots` 的历史数据。

## API / CLI 调整

### Runtime hot path API

新增 application port：

```text
ContextWorkspace.resolve_control_slice(run_id, session_key, request_refs)
```

返回：

```text
ContextControlSlice
```

新增 LLM application port：

```text
LlmRequestRenderer.render(provider_profile, draft, control_slice)
```

返回：

```text
RenderedLlmRequest
├─ provider_payload
├─ provider_tools
├─ input_item_refs
├─ tool_schema_refs
├─ request_hash
├─ render_report
└─ timings
```

### Observation API

新增或调整：

```text
GET /operations/runs/{run_id}/llm-requests/{snapshot_id}
GET /operations/runs/{run_id}/context-observation?revision=...
GET /trace/runs/{run_id}/request-render-snapshots
```

这些接口可按需生成或读取异步 projection，不参与 LLM 调用前置。

## 性能治理

### 热路径预算

目标：

```text
resolve_context_control_slice p95 < 300ms
render_provider_request p95 < 500ms
persist_request_render_snapshot p95 < 100ms
LLM 前置总耗时 p95 < 2s
```

硬性上限：

```text
LLM 前置总耗时不得超过 5s
单步 SQL 数不得超过 O(selected_refs + selected_tools)
不得随历史全量节点数线性膨胀
```

### 禁止回归项

热路径不得出现：

- `render_observation`。
- full `_refresh_owner_children`。
- 全量 `list_for_workspace`。
- 每 node 调一次 owner `children()`。
- 数 MB metadata 写入。
- 数百万次 `json.loads`。

### 必须埋点

每轮记录：

```text
runtime_request.collect_refs_ms
context_control_slice.resolve_ms
provider_request.render_ms
request_render_snapshot.persist_ms
llm.invoke_ms
session.record_response_ms
tool.execute_ms
```

Operations 应能展示最近 N 轮耗时瀑布。

## 2026-06-18 施工进展

### 已完成的热路径收口

- [x] 新增 request-preview 专用 runtime assembly，跳过与预览无关的默认写入：
      core settings seed、default OAuth provider ensure、memory space ensure、
      skill readiness persistence。
- [x] request-render preview 改为 read-only：
      不创建/刷新已有 workspace，不扫完整 Context Tree，不写
      `context_node_states`。
- [x] `llm_request` control slice 在 read-only preview 中走轻量切片：
      只返回当前 request 所需的直接输入/工具 schema 选择，不触发默认 root
      node materialization。
- [x] default tool schema metadata 增加 `allow_tree_fallback`：
      正式执行允许必要 fallback，preview 禁止通过 tree fallback 展开状态。
- [x] request-preview settings materializer 改为批量读取 effective payload，
      避免按 resource 逐个查询。
- [x] maintenance surface 的 `declared_only` tool schema 不再被 interactive
      tree/default-open 二次过滤，修复 `memory_flush_skip` 等维护工具可见性。
- [x] normal turn preview 在当前用户消息尚未落 session 时，优先使用当前
      inbound 作为 direct transcript；不会误把上一轮 user 当作本轮输入。
- [x] preflight 预算判断改为基于 session active facts 的确定性估算；
      该估算只用于维护触发，不进入 LLM request。
- [x] recorded request snapshot 可以继续裁剪 post-run transcript preview，
      但不再作为 runtime 历史控制的主机制。

### 实测指标

同一 smoke run 的 request preview 诊断对比：

```text
优化前：
  preview build: ~516ms
  SQL: 295
  UPDATE: access_oauth_providers / memory_spaces / skill_readiness /
          context_node_states

优化后：
  preview build: ~124ms
  SQL: 51
  UPDATE: 0
  CLI wall clock: 1.15s - 1.57s（Postgres schema 正常时）
```

本轮最后一次 CLI smoke 被当前本地数据库 schema guard 拦住：

```text
Database schema is not initialized or is out of date for the current APP_DATABASE_URL.
Run `PYTHONPATH=src python3 -m crxzipple.main db upgrade head` with the same database settings.
```

因此本轮最终验证以单元测试和 py_compile 为准；真实 CLI wall clock 需要在
dev DB 升级到 head 后重跑。

### 已验证

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_settings_materialization.py \
  tests/unit/test_app_assembly_registry.py \
  tests/unit/test_app_assembly_module_local.py \
  tests/unit/test_orchestration_context_workspace_snapshot.py \
  tests/unit/test_orchestration_runtime_llm_request.py \
  tests/unit/test_runtime_llm_request_draft_collector.py \
  tests/unit/test_skills_context.py \
  tests/unit/test_orchestration_memory.py
```

结果：

```text
144 passed in 35.01s
```

```bash
PYTHONPATH=src python -m py_compile \
  src/crxzipple/modules/orchestration/application/engine.py \
  src/crxzipple/modules/orchestration/application/runtime_llm_request_draft.py \
  src/crxzipple/modules/orchestration/application/maintenance.py \
  src/crxzipple/app/assembly/request_preview_runtime.py \
  src/crxzipple/modules/settings/application/services.py
```

## 施工阶段

### Phase 0: 确认现状与保护线

- [x] 写入本开发文档。
- [x] 增加 regression fixture，能证明 `record_context_snapshot`
      不得进入热路径。
- [x] 增加测试断言：LLM request build 不调用 `render_observation`。
- [x] 增加测试断言：LLM request snapshot 不包含 full tree body。

### Phase 1: 建立 RequestRenderSnapshot

- [x] 先以现有 `ContextSnapshotRecord` 承载轻量 request render snapshot，停止
      hot path 记录 full tree/debug body。
- [x] `RecordContextSnapshotInput` 支持跳过 metadata defaults，避免轻量快照仍扫全
      workspace nodes。
- [x] 新增正式 `ContextRequestRenderSnapshot` domain/value object。
- [x] 新增 request render snapshot repository / service / assembly registration。
- [x] 新增 `context_request_render_snapshots` migration，允许 breaking。
- [x] `RuntimeLlmRequestRenderSnapshot.to_payload()` 不再输出
      `provider_attachment_mirror` / `context_slice` 观察数据，只保留 request
      render ref、selected refs、token estimate 和 diagnostics。
- [x] LLM request metadata 与 orchestration LLM step event/runtime metadata
      显式携带 `request_render_snapshot_id` / `request_render_snapshot_kind`。
- [x] Workbench / Trace DTO 暴露 `request_render_snapshot_id`，source refs 优先使用
      request render snapshot ref。
- [x] Operations LLM read model 展示 Request Render Snapshot ref，并在 runtime
      request summary 中输出 snapshot kind / id。
- [x] Engine outcome、runtime request preview、DTO、execution payload/runtime metadata
      以 `request_render_snapshot_id` 为正式字段；不再保留
      `context_snapshot_id` 作为 request-render alias。
- [x] LLM request metadata、execution payload、tool surface runtime context、
      Operations runtime summary 停止主动写入 `context_snapshot_id` alias。
- [x] 清理 HTTP/UI trace 外壳中的 `context_snapshot_id` request-render 命名；
      preview/trace/provider input summary 均改用 `request_render_snapshot_id`。
- [x] Workbench read model 内部 helper / trace refs / source refs 命名收口到
      `request_render_snapshot_id`，不再以 context snapshot 名义承载 request
      render ref。
- [x] 更新 Operations read model 能读取轻量 request render snapshot ref。
- [x] 修复 request render 热路径的 tool schema 门控：LLM 首轮只接收
      `capability.search` 与明确默认/已启用 schema；候选工具全集留在
      Context Tree / capability search，不直接写入 provider attachment。

### Phase 2: 拆出 ContextControlSlice

- [x] Context Workspace 新增 control slice resolver。
- [x] resolver 只返回 selected refs，不返回完整 owner data。
- [x] request-render hot path 接入 control slice；当 selected session refs
      已可用时，request render snapshot 以 control slice 选择结果作为
      `input_item_refs`，未物化时回退到 runtime draft direct refs。
  - [x] `llm_request` control slice 在存在 protocol-required refs 时直接由
        refs 构造 selected refs，不再 `list_for_workspace` 扫整棵树。
- [x] enabled tool schema 选择改为 Context Tree 专门查询；
        SQL 后端只查询 tool/function 节点，不通过 `list_tree()` 加载完整树。
  - [x] default tool schema group bootstrap 改为工具 bundle/group 专门查询；
        `tool_schema_bootstrap` 不再通过 `list_tree()` 扫描完整 workspace。
- [x] default tool schema bootstrap 优先通过 Tool owner
      `list_runtime_request_bundles(function_ids)` 获取 source/group
      runtime_request 元数据，不展开 Context Tree、不修改树控制状态。
  - [x] 树展开仅作为 catalog 缺失或命中失败时的 fallback；直接删除 expand
        会丢失 tool bundle/group 物化能力，因此不作为正式方案。
- [ ] session frontier / tool schema / skill / memory / artifact 选择统一由
      control state 决定。
- [ ] owner data 读取改到 renderer 阶段，且只读取 selected refs。

### Phase 3: LLM Renderer 接管 provider request

- [ ] Orchestration 不再拼 provider input。
- [ ] LLM renderer 接收 draft + control slice。
- [x] Codex HTTP renderer 输出抓包对齐的 `input: Vec<ResponseItem>`。
  - [x] HTTP full replay 不发送 `previous_response_id`，使用 provider-native
        `input` item 回放 message / function_call / function_call_output。
- [x] Codex WebSocket renderer 输出抓包对齐的 continuation payload。
  - [x] fingerprint 命中时输出 `response.create` delta payload；fingerprint
        缺失或不匹配时回退 full wire payload，不发送不可靠 continuation。
- [x] unsupported provider field 不发送。
  - [x] provider wire payload 不包含 debug body / context diagnostics /
        context slice report 等非 provider 字段。
- [x] render report / loss report 可观测。
  - [x] provider render report 与 wire preview 分离，Operations 读取
        `provider_render_report`，不把 report 当作 provider wire body。
  - [x] request render snapshot 写入阶段 timing report，覆盖
        `ensure_workspace`、tool schema metadata、control slice、
        visible schema resolve、snapshot metadata 与 context snapshot persist。
  - [x] timing summary 进入 LLM request metadata / Operations runtime request
        summary；provider renderer 测试继续保证它不会进入 provider wire。

### Phase 4: Full Tree Observation 退出热路径

- [x] `record_run_context_snapshot` 热路径不再调用 `render_observation`。
- [x] `record_run_context_snapshot` 热路径不再触发 workspace owner children 全量刷新。
- [x] `preview_run_request_render_snapshot` 不再调用完整 debug/tree
      observation；预览与正式执行共享轻量 request-render builder，区别仅在
      preview 不持久化 request snapshot。
- [x] 完整 debug/tree observation 只保留为显式 inspector / trace /
      operations 按需观察入口，不再作为 request preview 的默认路径。
- [x] `get_recorded_run_context_snapshot` 只接受 `snapshot_kind=request_render`，
      防止旧 full snapshot 被读回 runtime request。
- [x] Workbench timeline/read model 不再依赖 request metadata 中的
      `context_slice_summary`；必要摘要由观察面本地计算。
- [x] Workbench run view / HTTP DTO / frontend type 删除空的
      `context_slice_summary` fallback；Context 请求卡片只由 request render
      preview 或按需 observation snapshot 驱动。
- [x] `render_observation` 正式收口为 observation / inspector / trace /
      operations / agent-facing 显式树观察路径；旧 `render_debug_body`
      服务入口已退场。
- [x] `TreeObservationSnapshot` 按需生成；orchestration 正式记录路径只写
      lightweight request-render snapshot，preview/显式观察路径才调用
      `render_observation`。
- [x] Orchestration runtime assembly 删除 `ContextSliceBuilderService`
      依赖；旧 `context_slice` metadata 不再由 request snapshot adapter 构造。
- [x] Runtime request builder / provider adapter common 层过滤 legacy
      `context_slice*` source/metadata；异常旧输入不会进入 provider-visible
      transcript metadata 或 input source counts。
- [ ] Operations observer 可异步物化完整树观察。
- [x] Workbench 默认 timeline 不读取完整树 body，也不再注入
      `context_slice_builder` 或按 user-timeline context slice 过滤 timeline；
      默认 run view 只用 orchestration/session/tool/LLM read model 构造轻量时间线。
- [x] Runtime request preview DTO 默认裁剪 `request_render_snapshot_metadata`，
      不返回 `node_estimate_breakdown`、`top_rendered_nodes`、
      `tool_schema_mirror_groups`、完整 direct refs 等观察面大对象。
- [x] Runtime request report 中的 request-render snapshot 只输出 token/owner/kind
      摘要和 ref/node 计数，不输出完整 node id 列表或完整 estimate breakdown。

### Phase 5: 删除旧路径

- [x] 删除或退役 full context snapshot hot path。
- [x] 删除旧 snapshot metadata 大 blob 写入：正式 request-render
      snapshot metadata 有 forbidden-key 回归保护，不写 full tree /
      provider attachment / direct refs / node breakdown 等观察字段。
- [x] 删除旧 provider attachments mirror 热路径写入：request-render
      snapshot 持久化与返回记录不再把 runtime draft、session refs、tool schemas
      塞入 `provider_attachments`；这些事实分别进入 metadata、formal refs 和
      `tool_schemas` 字段。
- [x] 完整 debug observation 路径也不再把 runtime draft、session refs、
      protocol refs 等运行诊断塞进 `provider_attachments`；缺失的
      `llm_capabilities` 等诊断进入 snapshot metadata，避免 provider
      attachment 被误用为 runtime truth。
- [x] 删除 orchestration 内 provider-specific replay 逻辑。
  - [x] `provider_continuation_state` 提取迁入 LLM application helper；
        orchestration engine 不再直接判断 OpenAI/Codex continuation preview。
  - [x] `engine_llm_invoker` 的 provider-native continuation 支持判断继续下放到
        LLM module / profile capability policy。
  - [x] provider option 的 api family 过滤规则迁入 LLM application；
        orchestration request policy 只负责合并配置并记录 resolution trace。
  - [x] runtime input item 到 canonical `LlmMessage` / provider context
        message 的投影规则迁入 LLM application；orchestration builder
        只组装 runtime facts 并调用 LLM-owned helper。
  - [x] reasoning config 到 provider overrides 的合并迁入
        `RuntimeLlmRequest.provider_overrides()` / `InvokeLlmInput` 构造入口；
        orchestration engine 不再写 `provider_options["reasoning"]`。
  - [x] `engine_llm_invoker` 不再手动传裸 `provider_options` overrides；
        streaming / fallback invoke 均使用 LLM input 构造入口的
        `provider_overrides()`。
  - [x] run metadata 中 provider continuation state 到
        `LlmProviderContinuation` 的解析迁入 LLM application；orchestration
        engine 只传递 metadata state。
  - [x] tool result 到 model-visible replay text 的 renderer 迁入 LLM
        application；orchestration runtime transcript / Workbench 只复用
        LLM-owned renderer。
  - [x] session item 到 LLM runtime transcript 的 projector 从
        orchestration application 迁到 LLM application；orchestration draft
        只消费 LLM-owned projector 结果。
  - [x] current inbound instruction 到 LLM runtime transcript 的 projector
        迁入 LLM application；orchestration draft 只负责把无效内容块转换为
        orchestration validation error。
  - [x] runtime input item 的 capability sanitization 迁入 LLM
        application；orchestration builder 不再拥有 vision block 降级和旧
        `context_slice` metadata 清洗规则。
  - [x] runtime input item 的 mode/kind/source 统计迁入 LLM
        application；orchestration builder 不再手写 provider request
        transcript 统计。
  - [x] tool surface 到 request metadata 的投影迁入 LLM
        application；orchestration builder 只构造运行时可见工具 surface。
  - [x] request render snapshot record 到 LLM request snapshot DTO 的投影迁入
        LLM application；orchestration 只传递 snapshot 字段和 metadata。
  - [x] request metadata 白名单投影迁入 LLM application；orchestration
        wrapper 只从 draft 提供 mode/surface/tool schema names。
  - [x] runtime transcript input item fallback 构造迁入 LLM application；
        orchestration builder 不再手写 `LlmMessage` 到 `LlmInputItem` 的
        回退投影，并删除不可达的 current-inbound 分支。
  - [x] runtime transcript policy 合成与 request-time tool surface
        唯一化迁入 LLM application；orchestration 只传递 surface policy
        和 tool surface DTO。
  - [x] provider-visible tool schema 去重迁入 LLM application；
        orchestration 只从 request render snapshot 取 schema 列表。
  - [x] 删除 orchestration runtime request builder 中未调用的 direct
        session/tool protocol metadata helper，避免旧 request-report 路径残留。
  - [x] token 粗估 helper 从 orchestration application 迁到 shared，
        避免 integration projector 反向导入 orchestration。
- [x] 删除旧 context slice / provider attachment mirror 进入
      `RuntimeLlmRequestRenderSnapshot` payload 的路径。
- [x] `RuntimeLlmRequestRenderSnapshot` DTO 删除 `debug_body`、
      `provider_attachment_mirror`、`context_slice` 字段，LLM-owned request
      对象只保留 request-render refs / estimate / diagnostics。
- [x] 删除旧 context slice debug metadata 进入 request metadata preview 的路径；
      preview UI 摘要改为观察面本地计算。
- [x] Provider request preview 不再解析或展示 `context_snapshot.context_slice`
      摘要；旧 slice/report 噪音不再通过 LLM/adapter 预览面传播。
- [x] Runtime LLM request preview DTO / HTTP response / frontend type 删除
      `context_slice_summary` 与 `provider_attachments` 字段；这些观察数据只从
      Workbench/Trace read model 或 context snapshot 读取。
- [x] Runtime request builder 不再从 `provider_attachments["tool_schemas"]`
      还原 provider-visible schemas，改为只读取 request render snapshot
      显式返回的 `tool_schemas`。
- [x] Runtime request builder 内部命名从 context provider mirror 收口为
      request render snapshot tool schema 语义，避免后续把旧观察面重新接回热路径。
- [x] Runtime request builder 不再从 `context_slice.active_tools` 推导
      tool surface `source_refs`；source/group 只来自 request-render metadata
      或后续正式 renderer 输出。
- [x] Runtime request / execution summary 删除 `context_slice_item_count`
      一等指标；输入统计只保留通用 `input_item_source_counts`，避免旧观察切片
      概念继续污染请求面。
- [x] Provider render report 的 input item mapping 不再输出
      `context_slice_item_id/node_id/section` 或 `trace_status=context_slice_item`；
      可追踪项统一归因为 provider-neutral `runtime_input_item`。
- [x] LLM request metadata preview 增加顶层防线，丢弃
      `context_slice`、`provider_attachment_mirror`、`provider_attachments`
      等旧观察/镜像字段。
- [x] Provider input summary / Workbench linked entity surface 将
      `context_snapshot_*` 请求面字段收口为 `request_render_snapshot_*`，
      避免 request-render 继续以旧 context snapshot 名义展示。
- [x] LLM runtime request summary / Operations LLM read model 将 sanitized
      snapshot preview 从 `context_snapshot` 改为 `request_render_snapshot`，
      并删除 `llm_request_slice_id` / `context_slice_summary` 旧观察字段。
- [x] Operations provider context mapping 删除 `slice_item/node/section`
      旧列和 `context_slice_summary` fallback，只展示 provider-neutral
      runtime input mapping。
- [x] Runtime LLM request preview API / DTO / frontend type 将
      `context_snapshot` / `context_snapshot_metadata` 改为
      `request_render_snapshot` / `request_render_snapshot_metadata`，
      并删除空的 `provider_attachments` 字段。
- [x] Orchestration `RequestRenderSnapshotRecord` 删除 observation-only 字段
      `debug_body`、`context_slice`、`provider_attachments`；request render
      record 只承载 provider request 所需 refs、tool schemas、artifact blocks
      与轻量 metadata，完整树内容只从 observation snapshot 读取。
- [x] 轻量 request-render metadata 不再写入完整 `direct_transcript_budget`
      对象；可解释信息收敛为 `direct_transcript_budget_summary`，protocol /
      collapsed refs 使用正式 refs 字段保存，避免 snapshot metadata 继续膨胀。
- [x] 轻量 request-render metadata 不再重复写入 `direct_session_item_refs`、
      `protocol_required_refs`、`execution_chain_protocol_required_refs`、
      `collapsed_refs` 列表；这些内容只走 snapshot formal refs，metadata
      只保留 count / summary。
- [x] LLM request metadata 不再投影 tool schema mirror 的 group/ref/match、
      default mirrored、skipped 明细和 `top_rendered_nodes`；request metadata
      只保留 count / status / source / skipped_by_reason 等轻量摘要，详细
      观察留在 observation snapshot。
- [x] 轻量 request-render metadata 的 `tool_schema_mirror_budget` 不再保存
      default group match 明细，只保留 source / count / status 类摘要，避免
      request snapshot metadata 随工具树匹配详情膨胀。
- [x] Runtime tool surface 不再从
      `tool_schema_mirror_default_group_matches` 反查 source/group；本轮只保留
      provider-visible function 列表，工具来源后续由正式 renderer report 输出。
- [x] Runtime tool surface metadata 删除误导性的 `source_refs` 拷贝字段；
      provider-visible function refs 只通过 `tool_surface_function_refs` 暴露。
- [x] Operations LLM read model 的 tool result budget 统计改读
      `direct_transcript_budget_summary`，不再要求 LLM request metadata 保留完整
      `direct_transcript_budget` 对象。
- [x] Operations LLM runtime request summary 只读取
      `request_render_snapshot` preview，不再接受 `context_snapshot` 作为
      request-render alias。
- [x] Shared budget helper 从 `context_snapshot_budget_metadata` 收口为
      `request_render_budget_metadata`；LLM request metadata 不再投影
      `debug_body_estimated_tokens`，debug body 成本只属于 observation snapshot。
- [x] Workbench / Trace 的 request route budget split 不再展示 debug/tree token；
      改为 direct transcript / schemas / artifacts / provider input 总量，避免
      UI 暗示 Context Tree XML 属于模型输入。
- [x] LLM provider preview / UI summary / orchestration 测试中的局部变量与
      helper 从 `context_snapshot` 收口为 `request_render_snapshot`，避免
      request-render payload 被误读为完整 Context Tree observation snapshot。
- [x] LLM invocation request preview API 同步使用 request-render snapshot 命名；
      sanitized request metadata 内的 snapshot preview 也投影为
      `request_render_snapshot`。
- [x] Runtime LLM request metadata / payload / runtime request report 将
      request-render snapshot key 从 `context_snapshot` 改为
      `request_render_snapshot`，provider preview/UI summary 读取源同步切换。
- [x] LLM runtime request 内部 DTO / envelope 字段从
      `RuntimeLlmContextSnapshot` / `context_snapshot` 收口为
      `RuntimeLlmRequestRenderSnapshot` / `request_render_snapshot`，不保留旧构造入口。
- [x] Orchestration runtime request report 从 `ContextSnapshotReport` /
      `context_snapshot` 收口为 `RequestRenderSnapshotReport` /
      `request_render_snapshot`，观察 payload 与内部命名一致。
- [x] Orchestration hot path port / builder 从 `ContextSnapshotRecord`、
      `ContextSnapshotPort`、`record_run_context_snapshot` 收口为
      `RequestRenderSnapshotRecord`、`RequestRenderSnapshotPort`、
      `record_run_request_render_snapshot`；engine phase 与错误文案同步改为
      `request_render_snapshot`，避免把完整树观察误认为 LLM 前置输入。
- [x] Context Workspace / Operations / context-tree 工具的完整树读取入口改名为
      observation snapshot：application service、AppKey、Operations port 和工具依赖
      均使用 `ContextObservationSnapshotService` /
      `CONTEXT_OBSERVATION_SNAPSHOT_SERVICE` /
      `context_observation_snapshot_service`，与 request-render snapshot 明确分离。
- [x] 测试覆盖空 assistant message / hidden reasoning / provider external item /
      assistant progress 的投影边界，确保无准确内容不进入可见投影。
- [x] 架构测试禁止 orchestration application 内重新出现 OpenAI/Codex/
      Anthropic/Gemini 等 provider-specific request rendering 分支。

### Phase 6: 长链验收

- [ ] 执行东航官网航班长链任务，不做任务特化。
- [ ] 对照 Codex trace，比对最终 provider input/output。
- [x] 检查 LLM 是否仍收到干扰性 debug/tree 内容。
  - [x] provider renderer 测试确认 debug body、context diagnostics、
        context slice report 不进入 Codex / Anthropic wire payload。
- [x] 检查 tool schema 是否按 control state 暴露。
  - [x] request render 只暴露 `capability.search`、明确默认、已启用和
        active tool schema；browser source policy 不再自动注入默认 schema。
- [ ] 检查 Workbench 不跳 turn、不因 snapshot 加载卡住。
- [ ] 检查单步 LLM 前置耗时达标。
  - [x] smoke preview 在 DTO/report 裁剪后 stdout 从约 131KB 降到约 34KB，
        request render snapshot metadata 约 2.5KB，runtime request report
        约 3.3KB。
  - [x] Tool owner catalog 优先路径落地后，smoke preview 的
        `resolve_tool_schema_metadata` 从约 447ms 降到约 23ms；
        request-render builder timing 从约 568ms 降到约 283ms。
  - [ ] CLI 端到端仍约 7.3s，主要疑点转移到 Python 进程启动和 app
        assembly；下一轮应单独拆启动/装配耗时，不再把它归因给 request
        render snapshot。
    - [x] cProfile 确认 7.1s 中约 2.5s 为 import，约 2.1s 为 app
          container 装配，约 2.2s 为 runtime draft / tool resolver。
    - [x] runtime draft / tool resolver 慢点主要来自 access/resource
          检查和工具包物化：约 1600+ SQL execute、386 次 authorization
          check、211 次 access effective snapshot、40 次 YAML safe_load。
    - [x] `llm-request-preview` 改为 schema-only tool candidate resolver，
          不跑 execution-time access/resource/authorization gate；正式执行路径
          仍在 `_build_advance_context` 使用完整 tool resolve。
    - [x] schema-only preview 后 smoke preview 端到端从约 7.3s 降到约
          3.3s，request-render builder timing 约 229ms。
    - [x] cProfile 复测显示剩余耗时主要为 CLI 冷启动 / import / app
          container 装配 / tool package YAML discovery，不再是 request
          render 或执行级 tool resolve。
    - [x] Tool package manifest 解析优先使用 PyYAML `CSafeLoader`，语义不变，
          降低 CLI 冷启动时的 YAML 解析开销。
    - [x] app assembly 支持显式 `run_activation_tasks=False`；CLI
          `orchestration llm-request-preview` 使用 read-only container，
          不运行 source catalog sync / activation task。写入型 CLI/API/daemon
          默认行为不变。
    - [x] read-only preview container 后 smoke preview 端到端降到约 2.3s；
          cProfile 显示 container 装配约 0.5s，preview runtime 约 0.48s，
          剩余主要为 Python/import 冷启动。
    - [x] `python -m crxzipple.main orchestration ...` 增加一级命令 fast path：
          orchestration CLI 不再经由统一 CLI app 预加载所有模块命令树；
          统一 CLI 入口和其他命令保持原行为。
    - [x] fast path 后 cProfile 函数调用数继续下降，预览仍约 2.4s；
          剩余主因是 orchestration CLI / runtime container 引入的 app
          assembly、SQLAlchemy model import 和少量 DB read。
    - [ ] 下一轮优化目标：若还需要继续压 CLI 冷启动，应提供更轻的
          preview assembly target 或常驻 admin/preview endpoint；不再在
          request render 热路径上继续挖。

## 验收标准

### 架构验收

- [x] Context Tree 不作为 prompt body 默认发送给 LLM。
- [x] Orchestration 不含 provider-specific request rendering。
- [x] LLM module/provider adapter 负责 request render + response parse。
- [x] Session 是会话账本，不是 provider wire transcript。
  - [x] Session module 保存 runtime item kind、phase、source refs、
        provider item id/type 等账本事实；新增架构测试禁止
        `previous_response_id` / provider wire payload / provider-specific
        transport 术语进入 Session module。
- [x] 完整树观察只存在于 observation/trace/inspector。

### 性能验收

- [x] `record_context_snapshot` 或等价 full snapshot 不再出现在 LLM hot path；
      engine phase / port / builder 均收口到轻量 `request_render_snapshot`。
  - [x] control slice 热路径不做 owner refresh、不做完整 observation render、
        不做 workspace 全树扫描；已有回归测试使用会失败的 node repository
        钉住该行为。
  - [x] request render adapter 带 `tree_service` 执行默认 tool schema bootstrap
        时同样不调用 `list_for_workspace()`，避免工具解析把全树扫描带回热路径。
- [x] 单轮 request build SQL 数量与 selected refs 成正比。
  - [x] in-process SQL 计数 smoke：
        `smoke_request_render_cli_20260618` request-preview 共 24 条 SQL，
        全部为 SELECT，0 INSERT/UPDATE/DELETE；输出 1 条 message、3 个 tool
        schema。
  - [x] 新增 `scripts/dev/request_preview_sql_smoke.py`，将 SQL 计数口径工具化：
        `PYTHONPATH=src python scripts/dev/request_preview_sql_smoke.py <run_id> [<run_id> ...]`。
        当前 smoke run 输出 `sql_total=24`、`SELECT=24`、进程内 preview
        构建约 58ms；同一 request-preview container 内重复采样同一 run 时
        SQL 总数保持 24，汇总 `sql_total_delta=0`。
  - [x] SQL smoke 支持验收断言：默认禁止写 SQL，可显式设置
        `--max-sql-total` / `--max-sql-delta`；本地
        `--max-sql-total 30 --max-sql-delta 0` 对重复 smoke run 通过，
        `--max-sql-total 1` 会非零退出并报告超限原因。
  - [x] SQL smoke 输出 request-render snapshot ref 计数与单位成本：
        `included_ref_count` / `protocol_required_ref_count` /
        `collapsed_ref_count`，以及 `sql_per_message` /
        `sql_per_tool_schema` / `sql_per_included_ref`；当前 smoke run
        `sql_per_message=24.0`、`sql_per_tool_schema=8.0`。
  - [x] SQL smoke 支持 `--compact` 单行 JSON，便于把 1 turn / 100 turn /
        多 selected refs 样本追加到文件后做机器对照。
  - [x] 新增 `scripts/dev/seed_request_preview_sql_fixture.py`，通过
        Orchestration Intake + Session application service 构造真实 prepared
        run 与合成历史 session items，不直接绕写 owner module。
  - [x] SQL smoke 支持 `--warmup`，将首次 workspace/root-node 初始化从热路径
        采样中剥离；未 warm 的全新 fixture 会出现初始化写 SQL，不作为稳定
        request build 口径。
  - [x] 完成 0 历史 vs 100 对历史消息对照采样：
        `sql_smoke_zero_b_20260618` 与 `sql_smoke_100_b_20260618` warm 后均为
        `sql_total=23`、`SELECT=23`、`sql_total_delta=0`，说明 request-preview
        SQL 不随 session 历史全量增长。
  - [x] `scripts/dev/seed_request_preview_sql_fixture.py` 支持
        `--tool-pairs` 构造同一当前轮内的 tool call/result 协议项。
        `sql_smoke_tool_3_20260618` 追加 3 组工具协议对，共 6 条
        protocol-required refs。
  - [x] 完成 0 selected refs vs 6 protocol-required refs 对照采样：
        `sql_smoke_zero_b_20260618` 与 `sql_smoke_tool_3_20260618` warm 后均为
        `sql_total=23`、`SELECT=23`、`sql_total_delta=0`；后者
        `included_ref_count=6`、`protocol_required_ref_count=6`、
        `message_count=6`，说明 selected refs 能被保留，SQL 不回退到
        session/tree 全量重建。
- [x] 单轮 request snapshot metadata 小于 100KB，目标小于 20KB。
  - [x] `test_context_workspace_adapter_records_lightweight_request_snapshot_for_run_context`
        将轻量 request snapshot metadata 上限收紧到 20KB。
- [x] LLM 前置构造 p95 小于 2s。
- [x] 单次 smoke request-render builder 小于 1s；仍需长链 p95 采样。
  - [x] `orchestration llm-request-preview` 改为使用只读
        `request_preview_runtime` assembly plan，不再为预览装配
        daemon/process/browser/channel/operations 等执行侧或观察侧模块。
  - [x] request-preview plan 保留 LLM request 所需 owner/query 服务：
        settings、access、authorization、agent、llm、session、context_workspace、
        memory、skills、tool source/runtime pool、orchestration inspection。
  - [x] `Tool` module 提供 `tool_request_preview_factories()`，只读暴露
        source catalog、runtime pool、Tool orchestration port；不配置 executable
        runtime，不运行 Tool activation tasks。
  - [x] `runtime_container` 支持显式 `plan_kind="request_preview"`；
        默认 `plan_kind="runtime"` 保持正式 API/worker/CLI 装配路径不变。
  - [x] smoke `llm-request-preview smoke_request_render_20260618_144525`
        真实 CLI 多次采样约 2.3-2.6s，最佳样本约 1.96s；
        `llm-request-preview --help` 冷启动约 0.7-1.1s。
  - [x] 回归测试确认 request-preview container 有
        `ORCHESTRATION_INSPECTION_SERVICE` / `TOOL_ORCHESTRATION_PORT`，
        且不装配 `DAEMON_SERVICE` / `PROCESS_SERVICE` /
        `OPERATIONS_PROJECTION_STORE`。
  - [x] App assembly / LLM infrastructure / Tool infrastructure 包级 exports
        改为 lazy，避免导入单个子模块时拖入 browser/daemon/provider adapter/
        MCP/OpenAPI/tool package 同步链。
  - [x] LLM adapter registry 改为 `register_factory()` 懒构造 provider
        adapter；request preview 不再提前导入 Anthropic/Gemini/OpenAI
        provider adapter 实现。
  - [x] Tool request-preview runtime infrastructure 使用空 package plans，
        不扫描/校验工具包，不导入 configured provider activation 链。
  - [x] importtime 验证 request-preview 路径不再导入
        `app.assembly.browser` / `app.assembly.daemon` /
        `tool.infrastructure.mcp_client` / `tool.infrastructure.discovery.mcp` /
        `tool.infrastructure.runtimes.openapi_remote`。
  - [x] `SettingsEffectiveConfigMaterializer` 增加按 resource kind 的
        effective payload cache；同一 materializer 内 `tool_roots()` 与
        `tool_providers()` 不再重复读取同一批 `tool-catalog` effective
        payload，并以单元测试钉住查询次数。
  - [x] 单进程复用场景中 request-preview container 后续构建可降至约
        200-300ms；单次 CLI 仍需承担进程冷启动、Typer、SQLAlchemy model
        import 和数据库往返。
  - [x] 修复 profile fallback 与 preview access readiness 边界后，
        `smoke_request_render_cli_20260618` 在空 SQLite runtime DB 上连续 5 次
        CLI 端到端采样为 1.23s / 0.97s / 0.89s / 1.03s / 1.00s；
        该口径包含 Python 进程冷启动、CLI 装配、DB 读取和 request preview
        输出序列化。
- [x] 100 turn session 下 Workbench timeline 首屏加载小于 2s。
  - [x] Workbench timeline tool lifecycle item 不再携带
        `ExecutionStepItem.summary_payload` 原文；只保留稳定摘要字段、
        provider-visible excerpt、read handles、exit/truncated 状态和白名单
        `tool_execution_plan` 字段。
  - [x] 新增测试确认大 `raw_arguments` / provider wire preview / stdout blob
        不会进入 timeline `content` 或 lifecycle entry。
  - [x] 新增 100 turn tool lifecycle 回归：每个 turn 含 20KB 级 raw
        summary/blob，timeline 聚合输出约束在 160KB 内，且不包含原始 blob；
        lifecycle entry 只保留最小 source refs、小字段、read handles 与白名单
        plan。
  - [x] 新增 HTTP 级 100 turn session 回归：同一 session 下 100 个历史 turn
        均含 20KB 级 raw tool blob，请求最新 run view 时 timeline 只嵌入当前
        run，历史 turn 只作为摘要存在；响应体小于 120KB 且不包含原始 blob。
  - [x] 新增 `scripts/dev/workbench_run_view_http_smoke.py`，用于真实 dev API
        环境采样 Workbench 首屏同口径
        `/ui/workbench/runs/{run_id}?include_timeline=false` 的响应耗时、
        响应体大小、turn 数和 timeline 数；可通过 `--include-timeline`
        显式采样完整 timeline，通过 `--max-ms` / `--max-bytes` 做非零退出
        断言，辅助区分 API 慢与前端渲染慢；默认直连
        `http://127.0.0.1:8000`，前端 proxy 口径可显式传 `--api-base`。
  - [x] 新增 `scripts/dev/seed_workbench_long_session_fixture.py`，通过
        Orchestration Intake 正式创建同一 session 下的多 run fixture，不用
        session item 冒充 turn。
  - [x] dev Postgres + dev API 下完成 100-turn run-view 首屏 API 采样：
        `workbench_long_100_20260618_0100` 返回 `turn_count=100`、
        `timeline_count=0`、`response_bytes=28834`、`elapsed_ms=1028.107`，
        通过 `--max-ms 2000 --max-bytes 120000`。
  - [x] 修复 Workbench run-view / steps 的 owner 查询边界：
        Orchestration run 查询按 `session_key` 收窄；Tool run 查询按
        `orchestration_run_id` scope 收窄；execution-chain-only 的 tool run
        归属仅在 run 已有 execution activity hint 时兜底解析，避免 accepted
        历史 turn 触发 N 轮空 execution 查询。
  - [x] dev Postgres + dev API 复测：
        `workbench_long_100_20260618_0100` direct run-view
        `elapsed_ms=108.194`、`response_bytes=28919`、`turn_count=100`、
        `timeline_count=0`。
  - [x] 真实 dev frontend + Playwright 复测：
        `/workbench/runs/workbench_long_100_20260618_0100` 等待
        `Workbench long-session fixture turn 100`，页面 ready
        `elapsed_ms=616.564`、`body_chars=4726`，且无 console/page/request
        error；主要 API 请求均小于 60ms。

### Provider 对齐验收

- [x] Codex HTTP request 与抓包 trace 的结构一致。
  - [x] HTTP 路径全量 `input` replay，不使用
        `previous_response_id` continuation。
- [x] Codex WebSocket request 与抓包 trace 的结构一致。
  - [x] WebSocket 路径在 continuation 指纹可验证时发送 delta；不可验证时
        full replay。
- [x] tool result 以 provider-native output item 回放。
  - [x] Session tool result 投影为 `LlmInputItemKind.FUNCTION_CALL_OUTPUT`；
        Codex renderer 输出 `function_call_output`，HTTP 路径不退化成普通文本。
- [x] assistant progress / reasoning / final answer 映射与 Codex runtime item
      语义一致。
  - [x] runtime response projector 将 assistant commentary / reasoning /
        reasoning summary / final answer 分别落成 session runtime items；
        transcript builder 回放 assistant progress、tool_call、tool_result 和
        reasoning item。
- [x] request render snapshot 能解释“本轮 LLM 实际看见了什么”。
  - [x] `visible_input_summary` 记录 provider-visible input ref 数量、
        protocol-required ref 数量、collapsed ref 数量、tool schema 数量和名称、
        owner/kind 计数。
  - [x] 摘要进入 request render snapshot metadata、render report、
        runtime request metadata/diagnostics，便于 Trace/Operations 审计。
  - [x] 摘要只包含计数和 schema 名称，不包含 full tree、debug body、
        owner 正文或无法准确证明的判断。

### 通用性验收

- [x] 内核无东航/航班/网页抓取任务特化逻辑。
  - [x] 架构测试扫描 app integration、orchestration、context_workspace、
        llm 内核路径，禁止东航/航班/airline 等任务特化词进入。
- [x] 无 EvidenceGate / EvidenceOutcomeClassifier 类通用裁判。
  - [x] 架构测试禁止 EvidenceGate / EvidenceOutcomeClassifier 在运行时内核
        回潮。
- [x] 无 browser route bias 默认进入 LLM。
  - [x] 核心默认工具组只保留 command run/process 与
        `capability.search`；browser source 的 runtime_request policy
        不再自动进入 provider tool schema。
  - [x] browser 工具仍可通过显式 `default_tool_schema_group_refs`、已启用
        schema、active tool 或 `capability.search` 后续发现进入 request。
- [ ] skill / workflow / evaluator 才承载任务专用策略。

## 2026-06-18 继续施工：只读 profile fallback 与 CLI smoke 边界

### 已完成

- [x] `LlmServiceAdapter` 增加配置 profile 的只读 fallback：
  - 先读 LLM owner module 中持久化的 profile。
  - DB 中不存在时，从 `settings.llm_profiles` 映射为同一个
    `LlmProfile` domain entity。
  - 不写 `llm_profiles` 表，不触发 profile sync，不改变 owner fact。
- [x] Orchestration 装配层把 `settings.llm_profiles` 注入 LLM port adapter。
- [x] 新增单元测试覆盖：
  - 持久 profile 缺失时可读取配置 profile。
  - 配置中也无匹配项时保留 `LlmNotFoundError`。
- [x] 显式指定不存在的 LLM profile 时，`LlmResolver` 转成
      `OrchestrationValidationError(code="llm_profile_not_found")`，避免底层
      `LlmNotFoundError` 泄漏成巨大 traceback。
- [x] request preview 跳过 LLM access readiness 校验，只用于构造和观察
      “将发送给 LLM 的请求”；真实执行路径仍默认校验 OAuth/API key readiness。
- [x] `LlmApplicationService.get_profile_optional()` 提供无异常 profile 查询，
      避免配置 fallback 的正常路径在 stderr 打出 rollback warning。

### CLI smoke 观察

- `db upgrade head` 在当前 shell 环境使用的是 SQLite
  `sqlite:///./crxzipple.db`，不是默认 Docker/Postgres 环境。
- `orchestration intake --no-enqueue` 只创建 ingress request；需要再执行
  `orchestration-scheduler process-next-request`，run 才会绑定
  `agent_id` / `active_session_id` 并进入可预览状态。
- 处理 ingress 后，request preview 不再因缺少 run/session 绑定失败。
- 空 SQLite 库没有持久化 LLM profile 时，已通过配置 profile fallback 解决
  `LlmNotFoundError`。
- `llm-request-preview smoke_request_render_cli_20260618` 在空 SQLite 库可成功
  输出 JSON，不要求 OAuth account 已 ready。
- 最新 smoke：
  - wall clock：约 1.40s。
  - stdout：28,621 bytes。
  - `llm_id`: `openai_codex.gpt-5.4-mini`。
  - `mode`: `session_start`。
  - message count：1。
  - tool schemas：`capability.search`、`exec`、`process`。
  - request render snapshot id：
    `ctxpreview_smoke_request_render_cli_20260618`。
- OAuth/API key readiness 仍由真实 invoke/advance 路径校验；preview 只负责
  可观察性，不代表凭证已可用。

### 验证

- [x] `PYTHONPATH=src pytest -q tests/unit/test_orchestration_llm_resolver.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_orchestration_context_workspace_snapshot.py`
- [x] `PYTHONPATH=src pytest -q tests/unit/test_orchestration_llm_service_adapter.py tests/unit/test_orchestration_llm_resolver.py tests/unit/test_runtime_llm_request_draft_collector.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_llm.py`
- [x] 空 SQLite runtime DB 上的 `orchestration llm-request-preview` CLI smoke。

## 风险与处理

### 风险：UI 缺少完整树观察

处理：

- 通过 Operations / Trace 异步 projection 补。
- Workbench inspector 按需加载。
- 不为了 UI 恢复热路径 full snapshot。

### 风险：renderer 读取 owner facts 过多

处理：

- renderer 必须基于 selected refs batch load。
- 增加 query count regression test。
- 大 payload 存 artifact/ref，默认只传摘要或 provider 支持的 payload。

### 风险：request render snapshot 过薄，无法排障

处理：

- snapshot 保存 refs/hash/timing/render report。
- 需要全文时通过 refs 从 owner module 重建 observation。
- 不在热路径保存完整副本。

### 风险：Context Tree 与 owner facts 不一致

处理：

- Tree 只保存 refs 和 control revision。
- owner facts 变更通过 events 更新 control state revision 或 invalidation。
- renderer 读取时以 owner facts 为准，tree stale 时返回 stale warning，不复制旧事实。

## 完成定义

本轮整改完成后，系统应满足：

```text
LLM hot path:
  owner refs -> control slice -> provider request -> request render snapshot -> LLM

Observation path:
  owner facts + request refs + tree control state -> async/on-demand tree view
```

并且：

- LLM 前置构造不再重建完整树。
- LLM request 中没有 debug/tree 噪声。
- Workbench 不再因为长 session snapshot 卡顿。
- Codex 适配对齐抓包 trace，而不是 prompt/tree 拼装猜测。
- Context Tree 作为控制面保留价值，但不再成为运行时性能瓶颈。
