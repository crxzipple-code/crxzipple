# Runtime Code Quality Audit - 2026-06-21

## Scope

本次审查对象是当前工作区中 Runtime / LLM / Orchestration / Context Workspace / Workbench 相关的大重构 diff，重点检查：

- 是否引入任务特化逻辑、兼容双轨、临时 shim 或调试字段侵入 LLM input。
- Context Workspace、LLM renderer/provider adapter、Orchestration、Session/Workbench 的职责边界是否继续收敛。
- 当前新增正式层是否降低了大文件和热路径复杂度，是否还有需要继续拆分的结构热点。

本报告不把历史旧代码的全部问题重新摊开；只记录当前重构后仍会影响可维护性、运行清晰度或后续治理的风险。

## Findings

### P1 - Workbench read model 仍然承担过重的跨模块补偿查询

位置：

- `src/crxzipple/modules/workbench/application/read_models.py`
- `src/crxzipple/modules/workbench/application/run_projector.py`
- `src/crxzipple/modules/workbench/application/timeline_projector.py`
- `src/crxzipple/modules/workbench/application/thread_projector.py`

现象：

- 文件审查基线为 `4959` 行；本轮已拆到 `181` 行，并拆出 thread/run/timeline/step/step-detail/run-summary/execution/inspector/action/tool-artifact/tool-run projectors、`view_models.py`、`trace_context_projection.py`、`step_view_factory.py` 以及通用 `projection_helpers.py`。`read_models.py` 已从大 read model 聚合文件收敛为 Workbench provider 编排入口；Trace provider 也已拆为 alias、context filter、summary 三个投影 helper。
- `get_run_view()` 中同时聚合 run、session、tool、llm、artifact、agent、trace 等视图数据。
- Workbench 侧原 `_tool_runs_with_execution_fallback()` 已退役；tool run 展示只消费 Tool owner scoped query 和 `ToolRun.metadata["orchestration_run_id"]` 归属事实。
- `_TIMELINE_DEBUG_PAYLOAD_KEYS` 已退场；Workbench timeline 改为按 response item kind 白名单投影用户可见 content，`debug_body`、`provider_wire_preview`、`runtime_request_summary` 不再作为通用 timeline payload 进入页面。

风险：

- Workbench 继续消费多个 owner query，但 tool-run 补偿查询和 timeline debug 黑名单已经退场。
- 当前页面慢、timeline 回跳、长链观察混乱这类问题仍需通过长链实测确认是否已缓解。

建议：

- 将 Workbench run timeline 拆成独立 projector：`WorkbenchRunTimelineProjector`、`WorkbenchThreadListProjector`、`WorkbenchRunDetailProjector`。
- 保持 Workbench 不再执行 execution fallback；缺 tool run 时由 Tool/Operations owner query 或 projection 补 owner 事实。
- `debug/provider/request render` 字段不再作为通用 payload 进入 timeline；实体详情中的 inspection payload 保持按需读取。

### P1 - Context request snapshot pipeline 已形成，Context owner service 已拆出 projection、tree maintenance 与 tree action

位置：

- `src/crxzipple/app/integration/context_workspace_orchestration/request_render_snapshot_pipeline.py`
- `src/crxzipple/app/integration/context_workspace_orchestration/context_slice_projection.py`
- `src/crxzipple/app/integration/context_workspace_orchestration/draft_input_projection.py`
- `src/crxzipple/modules/context_workspace/application/context_control_projection.py`
- `src/crxzipple/modules/context_workspace/application/context_control_slice_builder.py`
- `src/crxzipple/modules/context_workspace/application/context_observation_slice_builder.py`
- `src/crxzipple/modules/context_workspace/application/context_slice_item_projection.py`
- `src/crxzipple/modules/context_workspace/application/context_slice_refs.py`
- `src/crxzipple/modules/context_workspace/application/context_slice_selection.py`
- `src/crxzipple/modules/context_workspace/application/context_tool_surface_projection.py`
- `src/crxzipple/modules/context_workspace/application/context_tree_actions.py`
- `src/crxzipple/modules/context_workspace/application/context_tree_maintenance.py`
- `src/crxzipple/modules/context_workspace/application/services.py:475`

现象：

- `ContextWorkspaceRunSnapshotAdapter` 已退回薄 port adapter，主体逻辑迁入 `RequestRenderSnapshotPipeline`。
- request render 的 workspace binding、tool schema mirror、control slice、observation slice、projection、metadata build、snapshot persist、recorded snapshot loader 已拆成正式文件。
- 本轮补齐了 draft current inbound projection，避免 request snapshot 有 slice 但没有 provider input items。
- 本轮补齐了 `tool_interaction` -> provider `function_call` / `function_call_output` 投影；带媒体候选的 tool interaction 不自动进入非视觉 provider transcript。
- 本轮已把 audience 归一化、request metadata ref 匹配、LLM/user/trace/operations slice 节点选择规则拆入 `context_slice_selection.py`。
- 本轮已把 control ref projection、protocol-required control synthetic ref 和 protocol ref -> session item id 解析拆入 `context_control_projection.py`。
- 本轮已把 control slice report/metadata/selected refs orchestration 拆入 `context_control_slice_builder.py`。
- 本轮已把 observation slice 选节点、session item 批量预取、protocol-required item 投影、active tool projection、report/metadata/timing 汇总拆入 `context_observation_slice_builder.py`。
- 本轮已把 context slice item projection、session item owner resolution、protocol-required slice item projection 拆入 `context_slice_item_projection.py`。
- 本轮已把 collapsed/archive refs 和 slice metadata ref parsing 拆入 `context_slice_refs.py`。
- 本轮已把 active tool surface projection 和 tool function name 解析拆入 `context_tool_surface_projection.py`。
- 本轮已把 default root refresh、owner child refresh、orphan prune、seed materialization 和 action state helper 拆入 `context_tree_maintenance.py`。
- 本轮已把 apply action / upsert nodes / operation log 写入拆入 `context_tree_actions.py`。
- 本轮已补齐 session owner ref 的 `source_id/source_module` 投影，并按 provider protocol identity 去重 projected input；同一 `tool_call_id` 的 `function_call_output` 不会再因 `tool_interaction` 与独立 `tool_result` 两条切片路径重复进入 LLM request。
- 本轮已把 request render 的 observation slice 改为只读切片：LLM 调用前不再全量 `refresh_owner_children()`；Context Tree 作为控制面，provider input 只消费当前树状态和 protocol-required refs。
- 本轮已为 request render 增加 stage timing 和 `context_slice_builder_timings`，并把该字段暴露到 request preview 观察面；字段只用于诊断，不进入 provider input。
- 本轮已把 session item owner resolution 改为批量预取，避免 Context Slice 根据 refs 逐条读取 session item。
- 本轮已让 tool schema mirror 只有在请求的 tool function 节点缺失时才刷新/展开工具树；已存在的默认工具面不再每轮重建。
- `context_workspace/application/services.py` 已经降到 `621` 行，主要保留 workspace/tree/snapshot/slice facade 编排。

风险：

- request snapshot 热路径已经比原 adapter 清晰；本轮实测确认 observation slice 本身已从秒级降到毫秒级，但首次 materialize 默认 tool schema 节点仍有一次性成本。
- Context Workspace owner service 已明显瘦身；剩余风险主要转为首次工具树 materialization 和 Workbench/Operations 观察面投影耗时，而不再是每轮 LLM 请求全量刷新树。

建议：

- 保持 adapter 薄边界，后续新增 provider render 字段只能进 projection/pipeline/renderer，不能回流到 adapter。
- 下一轮把重构焦点转回 Workbench legacy step/detail helper、Operations LLM 投影复查和长链能力回归。
- 继续保证完整 Context Tree/debug snapshot 不进入热路径；request snapshot 只记录 LLM 实际需要的 slice、refs、tool schema、projected input 和 render report。

### P2 - LLM application service 已收口为 facade，runner 覆盖继续补齐

位置：

- `src/crxzipple/modules/llm/application/services.py:190`
- `src/crxzipple/modules/llm/application/services.py:306`
- `src/crxzipple/modules/llm/application/services.py:321`
- `src/crxzipple/modules/llm/application/services.py:344`
- `src/crxzipple/modules/llm/application/llm_invocation_runner.py`
- `src/crxzipple/modules/llm/application/llm_streaming_invocation_runner.py`

现象：

- `services.py` 已从大约三千行级别降到 `340` 行，已经抽出 `LlmProfileService`、`LlmInvocationService`、`LlmAdapterRequestBuilder`、`ProviderRequestPreviewRecorder`、streaming completion recorder、`llm_invocation_inputs.py`、`llm_profile_config.py`、`LlmInvocationRunner` 和 `LlmStreamingInvocationRunner`。
- 同步 invoke、异步 invoke、test profile 已进入 `LlmInvocationRunner`。
- 同步 streaming、异步 streaming 已进入 `LlmStreamingInvocationRunner`，主 service 只保留 profile/warmup/query 和入口 delegation。

风险：

- runner 拆分后主流程已集中；本轮已补 streaming incomplete 与 adapter failure 终态回归，锁定 failed invocation 与 failed response event 持久化。
- 本轮已补异步 stream 入口桥接同步 stream adapter 的回归，锁定 `stream_invoke_async()` 的 sync fallback 行为。
- 本轮已补异步 streaming completed payload 的 `response_items` / `continuation` 保真回归，锁定 async native stream 不退化为纯文本完成。
- `LlmStreamingInvocationRunner` 现在约 `290` 行，后续如果继续增长，应再拆 stream event reducer / adapter stream resolver。

建议：

- 保持 `LlmApplicationService` facade 边界，不再把 provider render/request preview/event 写回 service。
- 补 runner-level 单元测试，直接锁定 start/preview/succeed/fail/continuation/event sequence。
- 验收标准：新增一个 provider render 字段时，只需改 request builder/renderer/preview recorder，不需要改 invoke/stream service 入口。

### Resolved - Tool execution 批处理主流程已迁入 `ToolExecutionBatchRunner`

位置：

- `src/crxzipple/modules/orchestration/application/engine_tool_executor.py`
- `src/crxzipple/modules/orchestration/application/tool_execution_batch_runner.py`

现象：

- `engine_tool_executor.py` 已降到 `211` 行，保留同步入口、async runner 委派和 approved replay target 解析。
- `ToolExecutionBatchRunner` 承接 `execute_tool_calls_async()` 原批处理主流程，包括 tool call message flush、approval handling、resource conflict grouping、run dispatch guard、tool execution、result session item append、yield/terminal control。
- `ToolExecutionBatchState` 已承接批处理内的 call/result item ids、inline/background runs、tool run links、execution plans、prepared executions、pending call messages 和 yield/stop 标记，`execute()` 不再依赖一组裸 list/nonlocal 状态拼 outcome。
- tool call / tool result session record 写入已抽为 `_append_tool_call_session_records()` 和 `_append_tool_result_session_records()`，主流程只保留 flush 时机控制。
- approval request 构造已抽为 `_pending_approval_request()`，主流程不再内联 `PendingApprovalRequest` 字段拼装。
- prepared tool execution 分组已抽为 `tool_execution_grouping.py`，resource conflict batching 和 terminal plan control tool 隔离不再嵌在 runner。
- tool dispatch 运行状态门禁已抽为 `ToolDispatchGuard`，runner 不再直接判断 run terminal/running 状态。
- tool result 的 yield / terminal stop 判定已抽为 `tool_execution_control.py`，runner 不再直接解析 `session_control` 和 `terminal_plan` metadata。
- tool execution result recording 已抽为 `tool_execution_result_recorder.py`，background/inline 分类、`ToolRunLink` 构造、result message item 准备和 control decision 应用不再嵌在 runner。
- resource policy、probe observation、execution records 继续保持独立正式文件。

风险：

- 长链关键路径已从 executor 分离，batch state、session record 写入、approval request 构造、prepared execution grouping、dispatch guard、yield decision 和 result recording 都已正式化；runner 本身降到 `636` 行，后续重点转为 prepared execution 构造和主循环验证分支。

建议：

- 后续把 prepared execution 构造和主循环验证分支做成独立小服务或 dataclass reducer。
- 保持现有通用工具语义，不新增 browser/flight 任务特化分支。

### Resolved - Browser tool facts 已从 runtime 通用路径移除专有 metadata key

位置：

- `src/crxzipple/modules/orchestration/application/tool_execution_records.py:148`
- `src/crxzipple/modules/orchestration/application/tool_execution_records.py:160`
- `src/crxzipple/app/integration/context_workspace_session.py`
- `src/crxzipple/modules/llm/application/tool_result_replay_fields.py`
- `tools/browser/local.py`

现象：

- 新的 `tool_execution_records.py` 已经把执行记录和 lifecycle 抽取从 executor 中拆出来，这是正确方向。
- `tool_lifecycle_sources()` 已只读取 owner 输出的通用 `tool_lifecycle` / `evidence_lifecycle` / metadata/details lifecycle 字段，不再直接读取 `result_payload.metadata.browser_evidence`。
- Context/Session 集成层不再读取 `browser_evidence` 或 `browser_*` artifact/profile/target fallback。
- LLM tool-result replay 只读取通用 `artifact_ids`，不再读取 `browser_artifact_ids`。
- Browser tool package 对外 `ToolRunResult.metadata` 不再写入 `browser_evidence` / `browser_artifact_ids`，改为直接暴露通用事实 key。

风险：

- Orchestration / LLM / Context integration 侧 browser-specific lifecycle 固化风险已消除。
- Browser capability 可以继续有内部实现细节，但跨模块结果 metadata 必须保持通用事实结构。

建议：

- Tool owner 统一输出 `tool_lifecycle` 或 `evidence_lifecycle` 嵌套结构。
- Orchestration / Context Session 只读取通用嵌套 lifecycle key；不要重新读取扁平 lifecycle 字段或 browser-specific key。

### Resolved - `ToolExecutionPlan.from_prepared()` duck typing 已退场

位置：

- `src/crxzipple/modules/orchestration/application/tool_execution_records.py:61`
- `src/crxzipple/modules/orchestration/application/engine_tool_executor.py:58`

现象：

- `_PreparedToolExecution` 已提升为正式 application record：`PreparedToolExecution`。
- `ToolExecutionPlan.from_prepared(prepared: object)` 已删除，改为 `ToolExecutionPlan.from_execution(prepared: PreparedToolExecution)`，不再通过 duck typing 读取字段。
- `ToolRunLink`、`ToolExecutionPlan`、`ToolExecutionBatchOutcome`、`PreparedToolExecution` 和 lifecycle 抽取集中在 `tool_execution_records.py`，`engine_tool_executor.py` 只消费正式 record。

风险：

- 已消除原来的静态不可检查风险。

建议：

- 后续继续推进 `ToolExecutionBatchRunner`，把 `execute_tool_calls_async()` 的批处理流程拆出。
- Tool lifecycle 输出统一仍需按 E 项继续推进。

### P3 - 大文件热点仍然存在，需要继续分批治理

当前扫描行数热点：

- `src/crxzipple/modules/workbench/application/read_models.py`：审查基线 `4959` 行，当前 `181` 行。
- `src/crxzipple/modules/workbench/application/view_models.py`：`240` 行。
- `src/crxzipple/modules/workbench/application/trace.py`：`71` 行。
- `src/crxzipple/modules/workbench/application/trace_context_filter.py`：`162` 行。
- `src/crxzipple/modules/workbench/application/trace_summary_projection.py`：`67` 行。
- `src/crxzipple/modules/workbench/application/trace_alias_projection.py`：`37` 行。
- `src/crxzipple/modules/workbench/application/projection_helpers.py`：`51` 行。
- `src/crxzipple/modules/workbench/application/trace_context_projection.py`：`41` 行。
- `src/crxzipple/modules/workbench/application/step_view_factory.py`：`98` 行。
- `src/crxzipple/modules/workbench/application/run_session_projection.py`：`83` 行。
- `src/crxzipple/modules/workbench/application/runtime_ref_projection.py`：`83` 行。
- `src/crxzipple/modules/context_workspace/application/services.py`：`621` 行。
- `src/crxzipple/modules/context_workspace/application/context_observation_slice_builder.py`：`255` 行。
- `src/crxzipple/modules/context_workspace/application/context_tree_actions.py`：`130` 行。
- `src/crxzipple/modules/context_workspace/application/context_tree_maintenance.py`：`396` 行。
- `src/crxzipple/modules/context_workspace/application/context_control_slice_builder.py`：`120` 行。
- `src/crxzipple/modules/context_workspace/application/context_control_projection.py`：`127` 行。
- `src/crxzipple/modules/context_workspace/application/context_slice_item_projection.py`：`452` 行。
- `src/crxzipple/modules/context_workspace/application/context_slice_refs.py`：`69` 行。
- `src/crxzipple/modules/context_workspace/application/context_slice_selection.py`：`245` 行。
- `src/crxzipple/modules/context_workspace/application/context_tool_surface_projection.py`：`86` 行。
- `src/crxzipple/modules/orchestration/application/execution_chain_lifecycle.py`：`62` 行。
- `src/crxzipple/modules/llm/application/services.py`：`340` 行。
- `src/crxzipple/modules/llm/application/runtime_request.py`：`242` 行。
- `src/crxzipple/modules/orchestration/application/engine.py`：`1113` 行。
- `src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses.py`：`378` 行。
- `src/crxzipple/modules/orchestration/application/engine_tool_executor.py`：`211` 行。
- `src/crxzipple/modules/orchestration/application/tool_execution_batch_runner.py`：`662` 行。
- `src/crxzipple/modules/orchestration/application/runtime_llm_request_draft.py`：`833` 行。
- `src/crxzipple/modules/operations/application/projections.py`：`179` 行。
- `src/crxzipple/modules/operations/application/projection_materializer_payloads.py`：`272` 行。

建议：

- 不要因为“文件大”机械拆分；优先拆热路径和职责混合点。
- 下一轮优先级：Workbench legacy step/detail helper、Operations LLM 投影复查、长链验证。

## Positive Findings

- 当前 diff 显著减少了若干核心文件体积：
  - `context_workspace_orchestration/adapter.py` 净删约 `1462` 行。
  - `llm/application/services.py` 净删约 `1290` 行。
  - `engine_tool_executor.py` 净删约 `507` 行。
  - `runtime_llm_request_draft.py` 净删约 `490` 行。
- 新增的正式层基本符合当前架构方向：
  - LLM：`llm_profile_service.py`、`llm_invocation_service.py`、`llm_adapter_request_builder.py`、`provider_request_preview_recorder.py`、`llm_invocation_events.py`。
  - Orchestration：`runtime_step_budget_policy.py`、`runtime_tool_schema_policy.py`、`runtime_request_report_builder.py`、`tool_resource_policy.py`、`tool_execution_records.py`。
  - Context integration：`run_workspace_binding.py`、`tool_schema_mirror.py`、`request_render_snapshot_metadata.py`、`request_render_snapshot_recorder.py`、`context_slice_projection.py`。
- 源码扫描未发现新的 `CEAir`、`东航`、`flight` 任务特化逻辑进入 `src`。
- 未发现 `probe_client`、`structured_replay`、`evidence_frontier` 这类此前要求退场的概念在当前目标路径中复活。
- `debug_body` 在 request snapshot 持久化时为空，说明完整 debug body 没有继续塞入热路径快照。
- Operations read model 中 Workbench trace link 拼装已收口到
  `operations.application.read_models.routes.workbench_trace_route()` /
  `normalize_workbench_trace_route()`；Access、Daemon、Events、Channels、
  Tool run table/detail 不再各自手拼 `/workbench/traces/...` 或自行替换旧
  `/ui/trace/...` 路径。

## Verification

已知最近一次全量 Runtime 相关矩阵通过：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_runtime_llm_request_draft_collector.py \
  tests/unit/test_runtime_context_message.py \
  tests/unit/test_orchestration_context_workspace_snapshot.py \
  tests/unit/test_runtime_transcript.py \
  tests/unit/test_llm.py \
  tests/unit/test_llm_adapters.py \
  tests/unit/test_tool_providers.py \
  tests/unit/test_orchestration_tools.py
```

结果：`233 passed in 220.47s`。

本次审查额外执行了静态扫描：

```bash
rg -n "TODO|FIXME|temporary|临时|compat|shim|probe_client|structured_replay|evidence_frontier|CEAir|东航|flight" ...
rg -n "fallback|browser_evidence|debug_body|provider_wire_preview|previous_response_id|input_baseline_count|input_delta_count|<context_tree>|runtime_request_summary" ...
find ... -name '*.py' -print0 | xargs -0 wc -l | sort -nr | head -30
git diff --stat -- ...
git status --short
```

本次没有重新跑完整测试矩阵；原因是审查任务以静态质量报告为主，且当前工作区已有最新矩阵通过记录。进入下一轮代码清理后，应重新跑上面的 Runtime 矩阵。

## Recommended Next Pass

1. 先拆 Workbench read model：把 timeline/debug/request inspection 从主 run view 聚合里分离。
2. 再拆 LLM invoke runner：统一 sync/async/streaming 的 request preview、event、continuation、response item 写入。
3. 转入 Tool execution batch runner：降低 `execute_tool_calls_async()` 的局部状态复杂度。
4. 清理 `browser_evidence` 通用层命名，把 browser/tool 历史输出归一化责任放回 Tool owner。

## Remediation Checklist

### A. Workbench Read Model 收口

- [x] 拆出 `WorkbenchThreadListProjector`，只负责 thread list / active thread / filters。
  - [x] `latest_runs_by_session`、thread summary、active run selection、thread filters 和 thread activity 已从 `read_models.py` 迁入 `thread_projector.py`，首页 thread list 不再回读 `models._thread_*` 私有 helper。
- [x] 拆出 `WorkbenchRunDetailProjector`，承接 run header、agent/model/artifact summary 和现有 embedded timeline 编排。
- [x] 拆出 `run_session_projection.py`，承接 session run selection、safe run list 和 turn summary；`run_projector.py` 不再回读 `models._session_runs_for_run` / `models._turn_summaries` 私有 helper。
- [x] 拆出 `runtime_ref_projection.py`，承接 agent/model runtime ref 和 run -> LLM invocation lookup；run/step projector 不再回读 `models._agent_ref` / `models._llm_ref` / `models._llm_invocation_for_run` 私有 helper。
- [x] 拆出 `WorkbenchRunStepProjector`，承接 run step view 主流程和 legacy fallback step 编排。
  - [x] 已迁移 execution chain step view helper、assistant progress step、continuation decision step、approval step、missing access step 和 generic execution step。
- [x] 拆出 `step_detail_projection.py`，承接 failure guidance、missing access 和 approval detail/entity/summary projection。
- [x] 拆出 `run_summary_projection.py`，承接 run title/instruction summary、LLM summary、status strip、metrics、duration 和 turn/id helpers。
- [x] 拆出 `execution_projection.py`，承接 execution chain bundle、summary payload、tool/LLM id extraction、execution item status 和 LLM invocation lookup helpers。
- [x] 拆出 `inspector_projector.py`，承接 inspector overview/debug/memory/agent 面板、timeline diagnostics 和 loop health section。
- [x] 拆出 `action_projection.py`，承接 Workbench trace route、linked entities、step actions 和 run actions。
- [x] 拆出 `tool_artifact_projection.py`，承接 tool status/badge/summary、artifact preview 和 cover artifact projection。
- [x] 拆出 `WorkbenchRunTimelineProjector`，承接 run view 内 embedded timeline 入口编排。
  - [x] 已迁移 `_timeline_items_from_steps()`、`_timeline_items_from_llm_response_items()`、`_timeline_items_with_tool_lifecycle()` 三个 timeline 入口函数。
  - [x] 已迁移 response item timeline 内容过滤、debug payload key 过滤和 timeline 可见性/去重 helper。
  - [x] 已迁移 step timeline item 构造、tool interaction merge、tool interaction lifecycle compact helper。
  - [x] 已迁移 execution item -> tool timeline projection、tool result excerpt/read handles 和 tool execution plan compact helper。
  - [x] 已迁移 timeline diagnostics 计数 helper。
  - [x] 已拆出 `step_diagnostics.py`，承接 LLM step diagnostics、tool-only streak、diagnostic badges/summary。
  - [x] 已拆出 `tool_run_projection.py`，承接 display tool run、source run scope 和 child run linkage。
  - [x] 已拆出 `projection_helpers.py`，承接 `optional_text`、`optional_int`、`optional_positive_int`、`optional_url`、`truncate`、`metadata_str`、`metadata_dict`；Workbench application 中不再通过 `models._optional*` / `models._truncate` / `models._metadata_str` / `models._metadata_dict` 回读 read model 私有 helper。
  - [x] 已拆出 `trace_context_projection.py`，承接 run/turn/step/tool/llm 等引用到 `TraceContext` 的投影；run/timeline lifecycle projector 不再回读 `models._trace_for_run`。
  - [x] 已拆出 `step_view_factory.py`，承接 `TurnStepView` 组装、`TraceContext` 投影、linked entity/action 默认生成和时间格式化；step projector 不再回读 `models._step`。
  - [x] Workbench application 中 `models._*` 私有别名回读已清零；execution/run-summary/tool/action/detail/step helper 均改为直接依赖正式 projector/factory API。
  - [x] `read_models.py` 中旧 helper re-export 导入已退役；该文件不再转发 projection/action/execution/tool helper，只保留 Workbench read model 数据结构、port protocol 和 provider 编排。
  - [x] Workbench projector 内公开 helper 的无意义下划线 alias 已清理，依赖名和 owner 文件保持一致。
  - [x] 已拆出 `view_models.py`，承接 Workbench 纯视图 dataclass；projector 改为依赖 `view_models`，不再从 `read_models.py` 获取 UI 类型。
  - [x] Workbench projector 对 `view_models` 的依赖已提升到文件顶层，依赖关系不再藏在函数内局部导入。
  - [x] 已拆出 `trace_alias_projection.py`、`trace_context_filter.py`、`trace_summary_projection.py`，`trace.py` 只保留 Workbench trace provider 编排。
  - [x] `read_models.py` 不再导入或转发 `_timeline_*` 私有 helper；timeline projection 通过正式 `timeline_projector` / `timeline_refs` / `timeline_response_items` / `timeline_tool_lifecycle` API 暴露。
  - [x] 剩余 Workbench 治理已从私有 helper 回读转为较小的 projector 内部复杂度治理；不再属于 read model 私有 alias 问题。
- [x] 从 `WorkbenchReadModelService.get_run_view()` 中移除直接拼接所有 owner module 数据的长流程。
- [x] 退役 `_tool_runs_with_execution_fallback()`；Workbench 不再从 orchestration execution items 反查缺失 tool run。
  - [x] `display_tool_runs()` 只使用 Tool owner metadata 归属事实；缺 `orchestration_run_id` 的 tool run 不进入 Workbench run 视图。
- [x] 将 request render / provider wire / debug inspection 从主 timeline payload 中剥离；LLM response timeline content 改为按 item kind 白名单投影。
- [x] 增加 Workbench projector 单元测试，覆盖 run view、timeline、空态、缺 owner query 的稳定行为。
  - [x] 已覆盖 thread list projector 的 latest-session-run、active run、filter count。
  - [x] 已覆盖 thread list projector 的空态连接状态、filter count 和 active run/thread 空值。
  - [x] 已覆盖 run detail projector 在缺 tool/artifact/llm/agent/session owner query 时仍能稳定返回 run view，并只触碰 orchestration owner query。
  - [x] 已覆盖 waiting approval run 的顶层 actions 投影，确保 Workbench detail 能直接展示 `allow_once` / `allow_for_session` / `always_for_agent` / `deny`。
  - [x] 已覆盖 merged tool interaction timeline item 的 trace 锚点，确保 `tool_call_id` / `tool_run_id` / `session_item_id` 不只存在于 `source_refs`。
  - [x] 已通过现有 Workbench timeline 和 UI HTTP 回归覆盖 run detail / embedded timeline 行为。
  - [x] 已覆盖 tool run projection 不触发 execution fallback。

验收：

- [x] `src/crxzipple/modules/workbench/application/read_models.py` 不再继续增长，主 service 只做 projector 编排。
- [x] Workbench timeline 不需要靠过滤 `_TIMELINE_DEBUG_PAYLOAD_KEYS` 才能隐藏内部调试字段。
  - [x] `_TIMELINE_DEBUG_PAYLOAD_KEYS` 已删除；`timeline_user_payload_for_response_item()` 按 response item kind 白名单投影用户可见字段。
- [x] 最新长链会话 timeline 不再因为补偿查询造成跳回旧 turn 或加载明显变慢。
  - [x] Workbench read model 已不再从 execution chain 补偿查询缺失 tool run。
  - [x] 2026-06-23 smoke run `76053c665b6f4fccabbe2447a6167290` 验证 approval -> tool resume -> final answer 闭环，Workbench timeline 未回跳旧 turn。
  - [x] 2026-06-23 smoke run `87d7ba96026c4656b2bca0c7efd4d0e7` 验证多次 `exec` tool call / tool result / final answer 时间轴稳定；最终 preview 包含 5 个 provider input items 与 3 个 tool schemas。

### B. Context Request Snapshot Pipeline 收口

- [x] 新增 `RequestRenderSnapshotPipeline`。
- [x] 将 workspace binding、tool schema mirror、control slice、observation slice、metadata build、snapshot persist 拆成明确 stage。
- [x] `ContextWorkspaceRunSnapshotAdapter` 只保留 orchestration-facing port 方法和参数转换。
- [x] 保留轻量 request render snapshot；不得恢复完整 Context Tree/debug snapshot 热路径。
- [x] request snapshot metadata 只记录 LLM 实际 input slice、tool schema refs、provider render report 和 timing。
- [x] 补齐 current inbound draft projection，避免 request snapshot 投影为空。
- [x] 补齐 `tool_interaction` provider 协议投影，并保留孤儿 function item 过滤。
- [x] 媒体候选 tool interaction 不自动进入非视觉 provider transcript。
- [x] 拆出 `context_slice_selection.py`，承接 audience 归一化、request metadata ref 匹配和 LLM/user/trace/operations slice 节点选择规则。
- [x] 拆出 `context_control_projection.py`，承接 control ref projection、protocol-required synthetic control ref 和 protocol ref -> session item id 解析。
- [x] 拆出 `context_control_slice_builder.py`，承接 control slice report/metadata/selected refs orchestration。
- [x] 拆出 `context_slice_item_projection.py`，承接 context slice item projection、session item owner resolution 和 protocol-required slice item projection。
- [x] 拆出 `context_slice_refs.py`，承接 collapsed/archive refs 和 slice metadata ref parsing。
- [x] 拆出 `context_tool_surface_projection.py`，承接 active tool surface projection 和 tool function name 解析。
- [x] 拆出 `context_tree_maintenance.py`，承接 default root refresh、owner child refresh、orphan prune、seed materialization 和 action state helper。
- [x] 拆出 `context_tree_actions.py`，承接 apply action / upsert nodes / operation log 写入。
- [x] 为 preview 和 persist 两种模式补充/回归 pipeline 测试。
- [x] request render 的 observation slice 已改为只读切片，LLM 请求前不再刷新所有 owner children。
- [x] request render timings 已拆出 `sync_requested_tool_schema_nodes_ms`，避免把工具 schema 同步误记到 `build_context_slice_ms`。
- [x] Context Slice Builder 已输出 `context_slice_builder_timings`，request preview 可直接展示 `require_workspace/list_nodes/prefetch_session_items/project_active_tools` 等阶段耗时。
- [x] Tool schema mirror 已从“每轮 full refresh”改为“缺 requested tool function nodes 时才刷新/展开”；默认工具节点已存在时同步耗时为毫秒级。
- [x] Session item resolver 已支持 `get_many()`，Context Slice projection 可批量预取 protocol-required session items。

验收：

- [x] `adapter.py` 中不再有一个方法顺序编排全部 snapshot 细节。
- [x] LLM 调用前热路径不会重建完整树观察面。
- [x] 现有 `test_orchestration_context_workspace_snapshot.py` 继续通过。
- [x] 2026-06-23 smoke run `87d7ba96026c4656b2bca0c7efd4d0e7` 最终 request render：`build_context_slice_ms=14.484`、`refresh_owner_children_ms=0.009`、`total_before_request_render_snapshot_ms=438.762`；provider input 为 `message -> function_call/output -> function_call/output`，tool schema 为 `capability.search/exec/process`。

### C. LLM Invocation Runner 收口

- [x] 拆出 `llm_invocation_inputs.py`，承接 `InvokeLlmInput`、`StreamLlmInput`、warmup input/result 和 runtime request -> invocation input 转换。
- [x] 拆出 `llm_profile_config.py`，承接 profile import/config 解析、默认 capability 推导和 config -> profile 转换。
- [x] 新增 `LlmInvocationRunner`，统一非 streaming invoke 路径。
- [x] 新增 `LlmStreamingInvocationRunner`，统一 streaming invoke 路径。
- [x] 把非 streaming 的 request builder、provider request preview、concurrency、start/succeed/fail event、continuation 写入收进 runner 固定流程。
- [x] `LlmApplicationService` 退回 facade：profile CRUD、invoke/stream 调用入口、query delegation。
  - [x] 非 streaming invoke/test profile 已退回 runner delegation。
  - [x] streaming invoke 已退回 streaming runner delegation。
- [x] 删除 sync/async/streaming 之间重复的 preview 和 completion 记录逻辑。
  - [x] 非 streaming sync/async preview 和 completion 记录已去重。
  - [x] streaming sync/async event/completion 记录已进入 streaming runner。
- [x] 补充 streaming runner 终态与桥接回归。
  - [x] stream 未输出 `completed` 时失败为 `stream_incomplete`，并持久化 failed invocation / failed response event。
  - [x] stream 中途抛 adapter 异常时失败为 `adapter_error`，并保留已输出 delta event。
  - [x] `stream_invoke_async()` 可桥接只有同步 `stream_invoke()` 的 adapter。
  - [x] async streaming completed payload 的 `response_items` / `continuation` 保真已覆盖。
- [x] 补充 provider continuation / response item 保真测试，覆盖 Codex websocket、Codex http fallback、OpenAI responses、chat-compatible。
  - [x] Codex websocket continuation fallback 现在断言 fallback full request 的 assistant `response_items` 和 terminal continuation。
  - [x] Codex websocket continuation fallback 现在保留具体 fallback error metadata，避免只看到 `fallback=true` 却无法判断 provider/native continuation 失败原因。
  - [x] Chat-compatible tool-call 响应现在映射 `LlmContinuationReason.TOOL_CALL` 与 follow-up，sync/async completed event 均携带 continuation payload。
  - [x] OpenAI Responses / Codex HTTP / Codex renderer / transport wire 合同使用现有 targeted suite 回归覆盖。

验收：

- [x] 新增 provider render 字段时，不需要同时改四条 invoke 流。
- [x] `tests/unit/test_llm.py`、`tests/unit/test_llm_adapters.py`、`tests/unit/test_openai_codex_renderer.py` 继续通过。
- [x] Operations LLM render report 仍能看到 request preview、response items、continuation 状态。

### D. Tool Execution Batch Runner 收口

- [x] 新增 `ToolExecutionBatchRunner`，承接 `execute_tool_calls_async()` 内部批处理流程。
- [x] 将批处理内局部状态提升为 `ToolExecutionBatchState`，集中 outcome 拼装和 yield/stop 标记。
- [x] 将 tool call / result session record 写入从 `execute()` 闭包抽为 runner 私有方法。
- [x] 将 approval request 构造从 `execute()` 主流程抽为 `_pending_approval_request()`。
- [x] 将 resource conflict grouping / terminal plan control tool 隔离抽为 `tool_execution_grouping.py`。
- [x] 将 run terminal/running 状态门禁抽为 `ToolDispatchGuard`。
- [x] 将 yield / terminal stop 判定抽为 `tool_execution_control.py`。
- [x] 将 background/inline result recording 抽为 `tool_execution_result_recorder.py`。
- [x] 将 prepared execution 构造抽为 `_prepared_execution()`，将 tool surface / resolved tool 校验抽为 `_resolved_tool_for_call()`，主循环不再内联大段验证和 plan 构造。
- [x] 将 `_PreparedToolExecution` 提升为正式 application record：`PreparedToolExecution`。
- [x] 删除 `ToolExecutionPlan.from_prepared(prepared: object)` 的 duck typing，改为 typed `from_execution()`。
- [x] 保持 tool execution 内核通用，不新增 browser、flight、CEAir 等任务分支。
- [x] 补充 approval、background tool、terminal control tool、resource conflict batching 的 runner/grouping 单元测试。

验收：

- [x] `engine_tool_executor.py` 中不再有超长局部状态批处理主流程。
- [x] `tests/unit/test_orchestration_tools.py` 和 `tests/unit/test_orchestration_tool_resource_policy.py` 继续通过。
- [x] `tests/unit/test_tool_execution_grouping.py` 覆盖 parallel batch、serial resource conflict 和 terminal plan control tool 隔离。
- [x] 长链任务中 tool call、tool result、yield/approval 状态都能稳定写入 session/timeline。
  - [x] 2026-06-23 smoke run 已验证 `exec` tool call、approval request、tool result session item、tool resume 和 final answer 均进入 Workbench timeline。
  - [x] 2026-06-23 smoke run `87d7ba96026c4656b2bca0c7efd4d0e7` 验证两次 `exec` 调用、两组 tool result、approval resume 和 final answer 均可由 Workbench timeline/trace 串联。
  - [ ] 仍需用东航类多工具长链验证 background/浏览器/CDP/网络请求组合场景；该项属于能力回归，不阻塞本轮 runtime request 热路径收口。

### E. Tool Lifecycle 命名归一

- [x] Tool owner 输出统一 `tool_lifecycle` 或 `evidence_lifecycle` 嵌套结构；Orchestration / Context Session 不再读取扁平 lifecycle 字段。
- [x] Browser tool output 不再向跨模块 `ToolRunResult.metadata` 写入 `browser_evidence` 或 `browser_artifact_ids`；Browser 事实以通用 `artifact_ids`、`payload_shape`、`result_shape`、`runtime_globals`、`api_client_path`、`source_request_id` 等 key 暴露。
- [x] Orchestration 不再直接读取 `result_payload.metadata.browser_evidence`。
- [x] Context/Session 集成层不再读取 `browser_evidence`、`browser_*` artifact/profile/target fallback；通用层只消费 `artifact_ids`、`payload_shape`、`result_shape`、`request_id`、`verified_ref`、`tool_result_envelope` 等稳定字段。
- [x] 更新相关测试，确保 lifecycle 状态仍能进入 tool run link，但不保留 browser-specific key。

验收：

- [x] `rg -n "browser_evidence" src/crxzipple/modules/orchestration src/crxzipple/modules/llm src/crxzipple/app/integration` 无结果。
- [x] 通用嵌套 tool lifecycle 仍能表达 superseded、replacement、terminal control 等状态。
- [x] 扁平 `superseded` / `lifecycle_status` / `superseded_by_tool_call_id` 不再被 Orchestration lifecycle 抽取器当作正式事实。

### F. 大文件治理

- [x] `workbench/application/read_models.py` 拆分后低于 `3000` 行。
- [x] `llm/application/services.py` 拆分后低于 `900` 行。
- [x] `context_workspace/application/services.py` 已从原 owner 大文件收敛到 `621` 行；slice selection、control projection、control slice builder、observation slice builder、slice item projection、tool surface projection、tree maintenance、tree action 均已迁出。
- [x] `runtime_request.py` 已拆至 `242` 行，当前不再作为大文件治理目标。
- [x] `openai_codex_responses.py` 已拆至 `378` 行，当前不再作为大文件治理目标。

验收：

- [x] 拆分后的文件名表达稳定职责；当前未发现泛用 `helpers.py`、`utils.py` 兜底桶，保留的 helper 文件均带明确领域前缀。
- [x] 每个新文件都有对应 owner module 层级，不跨 DDD 边界放置。
  - [x] 已通过架构守卫覆盖 domain purity、projection layer 不写 persistence、Workbench/Operations owner fact sources、任务特化逻辑禁入等边界。
  - [x] 新增文件命名扫描仅剩领域限定的 `*_common` / `*_helpers` 文件，未发现跨模块泛用桶。

### G. 回归验证

- [x] 运行 Runtime 请求/Context/LLM/Tool 全矩阵：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_runtime_llm_request_draft_collector.py \
  tests/unit/test_runtime_context_message.py \
  tests/unit/test_orchestration_context_workspace_snapshot.py \
  tests/unit/test_runtime_transcript.py \
  tests/unit/test_llm.py \
  tests/unit/test_llm_adapters.py \
  tests/unit/test_tool_providers.py \
  tests/unit/test_orchestration_tools.py
```

结果：首次运行暴露 chat-compatible adapter 未填 `continuation`；已补 `LlmContinuationSignal` 映射后重跑通过，`235 passed in 247.89s`。

- [x] 运行 Workbench/API 相关测试：

```bash
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py tests/unit/test_operations_llm_render_report.py
```

结果：`32 passed in 27.31s`。

- [x] 已运行 Workbench read model / UI HTTP 目标测试：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_workbench_read_model.py \
  tests/unit/test_workbench_projection_diagnostics.py \
  tests/unit/test_ui_http.py \
  tests/unit/test_ui_operations_http.py
```

结果：`74 passed in 35.77s`。

- [x] 已运行 LLM service/profile/interface + Workbench/UI 组合回归：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_llm.py \
  tests/unit/test_llm_settings_integration.py \
  tests/unit/test_llm_http.py \
  tests/unit/test_llm_cli.py \
  tests/unit/test_access_llm_integration.py \
  tests/unit/test_authorization.py \
  tests/unit/test_workbench_read_model.py \
  tests/unit/test_ui_http.py
```

结果：`108 passed in 45.16s`。

- [x] 已运行 LLM runner 拆分后的 service/profile/interface 回归：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_llm.py \
  tests/unit/test_llm_settings_integration.py \
  tests/unit/test_llm_http.py \
  tests/unit/test_llm_cli.py \
  tests/unit/test_access_llm_integration.py \
  tests/unit/test_authorization.py
```

结果：`68 passed in 28.41s`。

- [x] 本轮补充 streaming runner 终态/桥接回归后，已重跑 LLM owner 单测：

```bash
PYTHONPATH=src pytest -q tests/unit/test_llm.py
```

结果：`34 passed in 10.52s`。

- [x] 已运行 LLM runtime/render/report 目标回归：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_llm_runtime_request_factory_builder.py \
  tests/unit/test_openai_codex_renderer.py \
  tests/unit/test_operations_llm_render_report.py
```

结果：`47 passed in 1.22s`。

- [x] 已运行 LLM render/report + Workbench/UI 组合回归：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_llm_runtime_request_factory_builder.py \
  tests/unit/test_openai_codex_renderer.py \
  tests/unit/test_operations_llm_render_report.py \
  tests/unit/test_workbench_read_model.py \
  tests/unit/test_ui_http.py
```

结果：`87 passed in 17.33s`；本轮复跑结果：`87 passed in 15.86s`。

- [x] 已运行 Context request snapshot / runtime draft / runtime transcript 回归：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_orchestration_context_workspace_snapshot.py \
  tests/unit/test_runtime_llm_request_draft_collector.py \
  tests/unit/test_runtime_context_message.py \
  tests/unit/test_runtime_transcript.py
```

结果：`68 passed in 0.67s`。

- [x] 已运行 Orchestration context / Operations render report / UI HTTP 回归：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_orchestration_context.py \
  tests/unit/test_operations_llm_render_report.py \
  tests/unit/test_ui_http.py
```

结果：`47 passed in 42.62s`。

- [x] 已运行 Context Workspace service / orchestration snapshot / orchestration context 回归：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_context_workspace_tree_service.py \
  tests/unit/test_orchestration_context_workspace_snapshot.py \
  tests/unit/test_orchestration_context.py
```

结果：`85 passed in 26.69s`。

- [x] 已重新运行 Context Workspace service/http/tool / orchestration snapshot / runtime request sanitizer 回归：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_runtime_llm_request.py::test_request_metadata_preview_payload_sanitizes_nested_runtime_payloads \
  tests/unit/test_context_workspace_tree_service.py \
  tests/unit/test_context_workspace_http.py \
  tests/unit/test_context_tree_tool.py \
  tests/unit/test_orchestration_context_workspace_snapshot.py
```

结果：`90 passed in 5.22s`。

- [x] 已运行架构守卫回归：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_app_assembly_architecture.py \
  tests/unit/test_module_architecture_guards.py
```

结果：`50 passed in 3.51s`。

- [x] 已运行 Tool execution / resource policy 回归：

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_tool_resource_policy.py
```

结果：`37 passed in 194.89s`；`9 passed in 0.72s`。

- [x] 已运行 Tool lifecycle / execution chain / Workbench read model 回归：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_orchestration_execution_chain.py \
  tests/unit/test_workbench_read_model.py
```

结果：`37 passed in 1.55s`。

- [x] 已运行 LLM runner / adapter / Codex renderer / Operations render report 矩阵：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_llm.py \
  tests/unit/test_llm_adapters.py \
  tests/unit/test_openai_codex_renderer.py \
  tests/unit/test_operations_llm_render_report.py
```

结果：`117 passed in 9.48s`。

- [x] 已运行 Context/Session browser-specific evidence cleanup 回归：

```bash
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_http.py tests/unit/test_runtime_transcript.py --tb=short
python -m ruff check src/crxzipple/app/integration/context_workspace_session.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_http.py tests/unit/test_runtime_transcript.py --ignore F401,I001,E501
rg -n "browser_evidence" src/crxzipple/modules/orchestration src/crxzipple/modules/llm src/crxzipple/app/integration || true
```

结果：`59 passed in 7.17s`；ruff passed；通用 runtime/LLM/app integration 路径无 `browser_evidence` 命中。

- [x] 已运行 Browser tool output / LLM replay 通用 metadata 回归：

```bash
PYTHONPATH=src pytest -q tests/unit/test_browser_tool_http.py tests/unit/test_browser_tool_http_advanced.py tests/unit/test_tool_providers.py tests/unit/test_browser_result_facts.py tests/unit/test_runtime_transcript.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_http.py --tb=short
python -m ruff check tools/browser/local.py src/crxzipple/modules/llm/application/tool_result_replay_fields.py src/crxzipple/app/integration/context_workspace_session.py tests/unit/test_browser_tool_http.py tests/unit/test_browser_tool_http_advanced.py tests/unit/test_tool_providers.py tests/unit/test_browser_result_facts.py tests/unit/test_runtime_transcript.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_http.py --ignore F401,I001,E501
rg -n 'browser_evidence|browser_artifact_ids' src/crxzipple/modules/orchestration src/crxzipple/modules/llm src/crxzipple/app/integration tools/browser/local.py tests/unit/test_browser_tool_http.py tests/unit/test_browser_tool_http_advanced.py tests/unit/test_tool_providers.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_http.py tests/unit/test_runtime_transcript.py tests/unit/test_browser_result_facts.py || true
```

结果：`147 passed in 43.11s`；ruff passed；上述 runtime/tool output/provider replay 路径无 `browser_evidence` / `browser_artifact_ids` 命中。

- [x] 已运行 provider continuation / response item 保真回归：

```bash
PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py -k 'response_items or continuation or tool_calls or end_turn_false' --tb=short
PYTHONPATH=src pytest -q tests/unit/test_llm.py -k 'response_item or continuation' --tb=short
PYTHONPATH=src pytest -q tests/unit/test_openai_codex_transport_wire_contract.py tests/unit/test_openai_codex_renderer.py -k 'previous_response_id or full_replay or continuation or tool_output' --tb=short
python -m ruff check tests/unit/test_llm_adapters.py tests/unit/test_openai_codex_transport_wire_contract.py tests/unit/test_openai_codex_renderer.py --ignore F401,I001,E501
```

结果：`6 passed, 72 deselected`；`9 passed, 20 deselected`；`3 passed, 9 deselected`；ruff passed。

- [x] 已运行 Tool lifecycle 嵌套结构回归：

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py -k 'tool_lifecycle_from_tool_run or tool_lifecycle or execution_chain_snapshot_query_batches_items_for_long_chain' --tb=short
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py -k 'superseded or lifecycle or replacement' --tb=short
python -m ruff check src/crxzipple/modules/orchestration/application/tool_execution_records.py src/crxzipple/app/integration/context_workspace_session.py tests/unit/test_orchestration_execution_chain.py tests/unit/test_context_workspace_session_adapter.py --ignore F401,I001,E501
```

结果：`3 passed, 29 deselected`；`4 passed, 34 deselected`；ruff passed。

- [x] 已运行 Workbench tool-run fallback 退役回归：

```bash
PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py tests/unit/test_workbench_projection_diagnostics.py --tb=short
python -m ruff check src/crxzipple/modules/workbench/application/tool_run_projection.py src/crxzipple/modules/workbench/application/run_projector.py src/crxzipple/modules/workbench/application/read_models.py tests/unit/test_workbench_read_model.py tests/unit/test_workbench_projection_diagnostics.py --ignore F401,I001,E501
rg -n 'tool_runs_with_execution_fallback|_tool_runs_with_execution_fallback|_execution_tool_run_ids_for_run\(' src/crxzipple/modules/workbench/application tests/unit/test_workbench_read_model.py || true
```

结果：`14 passed in 1.52s`；ruff passed；Workbench application 路径无 fallback / execution tool-run id 反查命中。

- [x] 已运行 Workbench timeline 白名单投影回归：

```bash
PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py tests/unit/test_workbench_projection_diagnostics.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py -k 'response_item or workbench or timeline or projection_diagnostics' --tb=short
python -m ruff check src/crxzipple/modules/workbench/application/timeline_visibility.py src/crxzipple/modules/workbench/application/timeline_response_items.py src/crxzipple/modules/workbench/application/tool_run_projection.py src/crxzipple/modules/workbench/application/run_projector.py src/crxzipple/modules/workbench/application/read_models.py tests/unit/test_workbench_read_model.py tests/unit/test_ui_http.py --ignore F401,I001,E501
rg -n '_TIMELINE_DEBUG_PAYLOAD_KEYS|timeline_visible_payload|tool_runs_with_execution_fallback|_execution_tool_run_ids_for_run\(' src/crxzipple/modules/workbench/application tests/unit/test_workbench_read_model.py tests/unit/test_ui_http.py || true
```

结果：`14 passed in 1.74s`；`23 passed, 8 deselected`；ruff passed；Workbench application 路径无 timeline debug 黑名单和 tool-run fallback 命中。

- [x] 已运行 Workbench projector 稳定性回归：

```bash
PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py tests/unit/test_workbench_projection_diagnostics.py --tb=short
python -m ruff check tests/unit/test_workbench_read_model.py --ignore F401,I001,E501
```

结果：`16 passed in 1.23s`；ruff passed；覆盖 thread list 空态、run detail 缺 optional owner query、tool-run owner metadata 和 timeline 投影稳定性。

- [x] 已运行 Workbench projection helper 收口回归：

```bash
PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py tests/unit/test_workbench_projection_diagnostics.py
PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py tests/unit/test_workbench_projection_diagnostics.py tests/unit/test_ui_http.py tests/unit/test_ui_operations_http.py
PYTHONPATH=src pytest -q tests/unit/test_module_architecture_guards.py tests/unit/test_app_assembly_architecture.py
rg -n 'models\._optional|models\._truncate|models\._metadata_str|models\._metadata_dict' src/crxzipple/modules/workbench/application/*.py
rg -o 'models\._[A-Za-z0-9_]+' src/crxzipple/modules/workbench/application/*.py | sed 's/.*models\.//' | sort | uniq -c | sort -nr
```

结果：`17 passed in 1.14s`；`74 passed in 38.18s`；`50 passed in 3.48s`；Workbench application 路径无基础 helper 回读命中。

- [x] 已运行 Workbench step view factory 收口回归：

```bash
PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py tests/unit/test_workbench_projection_diagnostics.py tests/unit/test_ui_http.py tests/unit/test_ui_operations_http.py
PYTHONPATH=src pytest -q tests/unit/test_module_architecture_guards.py tests/unit/test_app_assembly_architecture.py
python -m compileall -q src/crxzipple/modules/workbench/application
git diff --check
rg -o 'models\._[A-Za-z0-9_]+' src/crxzipple/modules/workbench/application/*.py | sed 's/.*models\.//' | sort | uniq -c | sort -nr
```

结果：`74 passed in 35.34s`；`50 passed in 2.96s`；`compileall` passed；`git diff --check` passed；Workbench application 路径 `models._*` 私有回读清零，`read_models.py` helper re-export 残留清零。

- [x] 已运行 Workbench view model 拆分回归：

```bash
PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py tests/unit/test_workbench_projection_diagnostics.py
PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py tests/unit/test_workbench_projection_diagnostics.py tests/unit/test_ui_http.py tests/unit/test_ui_operations_http.py
PYTHONPATH=src pytest -q tests/unit/test_module_architecture_guards.py tests/unit/test_app_assembly_architecture.py
python -m ruff check src/crxzipple/modules/workbench/application tests/unit/test_workbench_read_model.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/workbench/application
```

结果：`17 passed in 1.24s`；`74 passed in 37.41s`；`50 passed in 3.56s`；ruff passed；compileall passed；`workbench.application.read_models` 外部引用只剩 application package 导出 `WorkbenchReadModelProvider`。

- [x] 已运行 Workbench trace provider 拆分回归：

```bash
PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py tests/unit/test_workbench_projection_diagnostics.py tests/unit/test_ui_http.py tests/unit/test_ui_operations_http.py
PYTHONPATH=src pytest -q tests/unit/test_module_architecture_guards.py tests/unit/test_app_assembly_architecture.py
python -m ruff check src/crxzipple/modules/workbench/application tests/unit/test_workbench_read_model.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/workbench/application
```

结果：`74 passed in 41.40s`；`50 passed in 3.38s`；ruff passed；compileall passed。

- [x] 已运行 Operations trace route presenter 收口回归：

```bash
PYTHONPATH=src pytest -q tests/unit/test_operations_presenters.py tests/unit/test_operations_tool_run_tables.py tests/unit/test_operations_tool_run_details.py tests/unit/test_operations_tool_run_artifacts.py tests/unit/test_operations_tool_run_contexts.py
PYTHONPATH=src pytest -q tests/unit/test_operations_browser_read_model.py tests/unit/test_operations_daemon_read_model.py tests/unit/test_operations_observation.py tests/unit/test_ui_operations_http.py
python -m ruff check src/crxzipple/modules/operations/application/read_models/routes.py src/crxzipple/modules/operations/application/read_models/tool_run_tables.py src/crxzipple/modules/operations/application/read_models/tool_run_details.py src/crxzipple/modules/operations/application/read_models/access.py src/crxzipple/modules/operations/application/read_models/daemon.py src/crxzipple/modules/operations/application/read_models/events.py src/crxzipple/modules/operations/application/read_models/channels.py tests/unit/test_operations_presenters.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models
```

结果：`16 passed in 1.44s`；`86 passed in 24.20s`；ruff passed；compileall passed；Operations read model 路径中手拼 Workbench trace route 仅剩统一 route helper 和 action endpoint 模板。

- [x] 已运行 Operations Channels read model 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/channels.py src/crxzipple/modules/operations/application/read_models/channels_common.py src/crxzipple/modules/operations/application/read_models/channels_models.py src/crxzipple/modules/operations/application/read_models/channels_events.py src/crxzipple/modules/operations/application/read_models/channels_tables.py src/crxzipple/modules/operations/application/read_models/channels_details.py src/crxzipple/modules/operations/application/read_models/channels_health.py src/crxzipple/modules/operations/application/read_models/__init__.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/channels.py src/crxzipple/modules/operations/application/read_models/channels_common.py src/crxzipple/modules/operations/application/read_models/channels_models.py src/crxzipple/modules/operations/application/read_models/channels_events.py src/crxzipple/modules/operations/application/read_models/channels_tables.py src/crxzipple/modules/operations/application/read_models/channels_details.py src/crxzipple/modules/operations/application/read_models/channels_health.py src/crxzipple/modules/operations/application/read_models/__init__.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py::UiOperationsHttpTestCase::test_ui_operations_channels_page_uses_runtime_and_event_state tests/unit/test_ui_operations_http.py::UiOperationsHttpTestCase::test_ui_operations_channels_health_ignores_historical_failed_interactions --tb=short
```

结果：ruff passed；compileall passed；`2 passed in 3.03s`。`operations/application/read_models/channels.py` 从 2312 行收口到 348 行，模型、common presenter、event collection、tables/contracts、details、health/charts 已拆到 focused helper modules。

- [x] 已运行 Operations Skills read model 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/skills.py src/crxzipple/modules/operations/application/read_models/skills_common.py src/crxzipple/modules/operations/application/read_models/skills_events.py src/crxzipple/modules/operations/application/read_models/skills_models.py src/crxzipple/modules/operations/application/read_models/skills_health.py src/crxzipple/modules/operations/application/read_models/skills_catalog_tables.py src/crxzipple/modules/operations/application/read_models/skills_requirement_tables.py src/crxzipple/modules/operations/application/read_models/skills_details.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/skills.py src/crxzipple/modules/operations/application/read_models/skills_common.py src/crxzipple/modules/operations/application/read_models/skills_events.py src/crxzipple/modules/operations/application/read_models/skills_models.py src/crxzipple/modules/operations/application/read_models/skills_health.py src/crxzipple/modules/operations/application/read_models/skills_catalog_tables.py src/crxzipple/modules/operations/application/read_models/skills_requirement_tables.py src/crxzipple/modules/operations/application/read_models/skills_details.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py::UiOperationsHttpTestCase::test_ui_operations_skills_page_uses_skill_catalog_state tests/unit/test_operations_observation.py::OperationsObservationTestCase::test_skills_operations_uses_readiness_changed_events tests/unit/test_operations_observation.py::OperationsObservationTestCase::test_skills_operations_reads_declared_skill_topics_without_bus_scan tests/unit/test_operations_observation.py::OperationsObservationTestCase::test_skills_operations_top_used_is_runtime_usage_from_events tests/unit/test_operations_observation.py::OperationsObservationTestCase::test_skills_operations_projects_authoring_backlog_and_failures --tb=short
```

结果：ruff passed；compileall passed；`5 passed in 3.15s`。`operations/application/read_models/skills.py` 从 1905 行收口到 349 行，page models、common presenter/status helpers、event/readiness/authoring projection、health/chart/actions、table projection、detail projection 已拆到 focused helper modules。

- [x] 已运行 Operations Browser read model 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/browser.py src/crxzipple/modules/operations/application/read_models/browser_runtime_facts.py src/crxzipple/modules/operations/application/read_models/browser_tones.py src/crxzipple/modules/operations/application/read_models/browser_values.py src/crxzipple/modules/operations/application/read_models/browser_events.py src/crxzipple/modules/operations/application/read_models/browser_rows.py src/crxzipple/modules/operations/application/read_models/browser_tables.py src/crxzipple/modules/operations/application/read_models/browser_health.py src/crxzipple/modules/operations/application/read_models/browser_models.py src/crxzipple/modules/operations/application/read_models/__init__.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/browser.py src/crxzipple/modules/operations/application/read_models/browser_runtime_facts.py src/crxzipple/modules/operations/application/read_models/browser_tones.py src/crxzipple/modules/operations/application/read_models/browser_values.py src/crxzipple/modules/operations/application/read_models/browser_events.py src/crxzipple/modules/operations/application/read_models/browser_rows.py src/crxzipple/modules/operations/application/read_models/browser_tables.py src/crxzipple/modules/operations/application/read_models/browser_health.py src/crxzipple/modules/operations/application/read_models/browser_models.py src/crxzipple/modules/operations/application/read_models/__init__.py
PYTHONPATH=src pytest -q tests/unit/test_operations_browser_read_model.py tests/unit/test_operations_observation.py::OperationsObservationTestCase::test_materializer_maps_browser_events_to_browser_and_daemon tests/unit/test_operations_observation.py::OperationsObservationTestCase::test_operations_observer_static_events_include_browser_events --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_browser_read_model.py tests/unit/test_ui_operations_http.py -k browser --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k browser --tb=short
```

结果：ruff passed；compileall passed；历史 Browser owner/event 回归 `12 passed`；Browser read-model/UI scoped 回归 `10 passed, 26 deselected`；Operations observation Browser scoped 回归 `2 passed, 47 deselected`。`operations/application/read_models/browser.py` 从 1336 行收口到 253 行；旧 `browser_common.py` 已退役，不保留转发层。runtime/proxy/daemon instance 选择迁入 `browser_runtime_facts.py`（163 行），status/health tone 规则迁入 `browser_tones.py`（73 行），通用 value/time/byte/filter/label helpers 迁入 `browser_values.py`（127 行）。

- [x] 已运行 Operations Memory read model 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/memory.py src/crxzipple/modules/operations/application/read_models/memory_common.py src/crxzipple/modules/operations/application/read_models/memory_events.py src/crxzipple/modules/operations/application/read_models/memory_event_tables.py src/crxzipple/modules/operations/application/read_models/memory_records.py src/crxzipple/modules/operations/application/read_models/memory_health.py src/crxzipple/modules/operations/application/read_models/memory_tables.py src/crxzipple/modules/operations/application/read_models/memory_details.py src/crxzipple/modules/operations/application/read_models/memory_models.py src/crxzipple/modules/operations/application/read_models/__init__.py src/crxzipple/modules/operations/application/read_models/facade.py src/crxzipple/modules/operations/application/read_models/projection_payloads.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/memory.py src/crxzipple/modules/operations/application/read_models/memory_common.py src/crxzipple/modules/operations/application/read_models/memory_events.py src/crxzipple/modules/operations/application/read_models/memory_event_tables.py src/crxzipple/modules/operations/application/read_models/memory_records.py src/crxzipple/modules/operations/application/read_models/memory_health.py src/crxzipple/modules/operations/application/read_models/memory_tables.py src/crxzipple/modules/operations/application/read_models/memory_details.py src/crxzipple/modules/operations/application/read_models/memory_models.py src/crxzipple/modules/operations/application/read_models/__init__.py src/crxzipple/modules/operations/application/read_models/facade.py src/crxzipple/modules/operations/application/read_models/projection_payloads.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py::UiOperationsHttpTestCase::test_ui_operations_memory_page_uses_file_memory_runtime_state tests/unit/test_operations_observation.py::OperationsObservationTestCase::test_memory_materializer_stores_file_details_outside_page_projection tests/unit/test_operations_observation.py::OperationsObservationTestCase::test_operations_observer_static_events_include_memory_events tests/unit/test_operations_observation.py::OperationsObservationTestCase::test_memory_operations_write_flush_uses_remember_events --tb=short
```

结果：ruff passed；compileall passed；`4 passed in 2.99s`；后续 Memory event-table 拆分复跑 UI Memory `1 passed, 25 deselected`、Operations observation Memory `3 passed, 46 deselected`。`operations/application/read_models/memory.py` 从 1516 行收口到 205 行，page models、status/format helpers、event collection/projection、event-backed tables、context record/query helpers、health/chart/action sections、owner-state table projections、file detail projection 已拆到 focused helper modules；`memory_tables.py` 从 485 行收口到 278 行，事件表迁入 `memory_event_tables.py`。

- [x] 已运行模块架构边界守卫：

```bash
PYTHONPATH=src pytest -q tests/unit/test_module_architecture_guards.py --tb=short
```

结果：`16 passed in 2.29s`；覆盖 module domain purity、Workbench/Operations 投影层不写 persistence、owner fact source 声明、site-specific task logic 禁入等边界。

- [x] 已运行 Tool execution runner / grouping 回归：

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_execution_grouping.py tests/unit/test_orchestration_tool_resource_policy.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_orchestration_approval.py -k 'approval_does_not_persist_unprocessed_tool_calls_from_same_invocation or background_tool_call_can_wait_for_approval_then_transition_to_tool_wait or approval_replay_fails_if_stored_target_is_no_longer_supported' --tb=short
PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py -k 'sessions_yield_stops_inline_tool_auto_continue or background_approval' --tb=short
python -m ruff check src/crxzipple/modules/orchestration/application/tool_execution_batch_runner.py src/crxzipple/modules/orchestration/application/tool_execution_grouping.py tests/unit/test_tool_execution_grouping.py tests/unit/test_orchestration_tool_resource_policy.py --ignore F401,I001,E501
```

结果：`14 passed`；`3 passed, 14 deselected`；`1 passed, 36 deselected`；ruff passed。

- [x] 继续运行新增 projector / pipeline / runner 全矩阵：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_workbench_read_model.py \
  tests/unit/test_workbench_projection_diagnostics.py \
  tests/unit/test_orchestration_context_workspace_snapshot.py \
  tests/unit/test_runtime_llm_request_draft_collector.py \
  tests/unit/test_runtime_context_message.py \
  tests/unit/test_runtime_transcript.py \
  tests/unit/test_tool_execution_grouping.py \
  tests/unit/test_orchestration_tool_resource_policy.py \
  --tb=short
```

结果：`99 passed in 1.35s`。

- [x] 已运行 Workbench approval action / tool interaction trace 投影回归：

```bash
PYTHONPATH=src pytest -q tests/unit/test_workbench_read_model.py tests/unit/test_workbench_projection_diagnostics.py --tb=short
python -m ruff check \
  src/crxzipple/modules/workbench/application/action_projection.py \
  src/crxzipple/modules/workbench/application/timeline_tool_lifecycle.py \
  tests/unit/test_workbench_read_model.py \
  --ignore F401,I001,E501
```

结果：`17 passed in 1.47s`；ruff passed。

- [x] 已运行 runtime smoke 长链：

```bash
source scripts/dev/infra-env.sh
PYTHONPATH=src python -m crxzipple.main ask \
  "RUNTIME_SMOKE_20260623B：请使用可用的本地命令工具查看当前工作目录和当前日期时间，然后用一句话总结你调用了什么工具、看到了什么。必须至少调用一次工具，不要访问外网。" \
  --agent crxzipple \
  --llm-id openai_codex.gpt-5.4-mini \
  --main-key runtime-smoke-20260623b \
  --max-steps 6 \
  --wait-timeout-seconds 180 \
  --poll-interval-seconds 0.2
curl -sS 'http://127.0.0.1:8000/ui/workbench/runs/76053c665b6f4fccabbe2447a6167290?include_timeline=true' | jq '...'
```

结果：run `76053c665b6f4fccabbe2447a6167290` completed；Workbench detail 顶层 actions 包含 approval 四动作；timeline 包含 user input、reasoning summary、tool interaction、approval、tool resume、final answer；tool interaction trace 已携带 `tool_call_id`、`tool_run_id`、`session_item_id`。

观察：approval resume 的 provider continuation 记录了 `fallback=true` / `fallback_reason=websocket_continuation_failed_before_output`，但最终通过 fallback 路径完成。已补充 Codex websocket fallback error metadata，后续 Workbench/Operations 能直接看到真实异常摘要；该 metadata 只用于诊断投影，不进入 LLM request。

- [x] 已运行 Codex websocket fallback 诊断回归：

```bash
PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py -k 'codex_websocket' --tb=short
python -m ruff check \
  src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses.py \
  src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_event_projection.py \
  tests/unit/test_llm_adapters.py \
  --ignore F401,I001,E501
```

结果：`14 passed, 64 deselected in 1.51s`；ruff passed。

- [x] 已运行 request render 热路径回归：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_orchestration_context_workspace_snapshot.py \
  tests/unit/test_context_workspace_tree_service.py \
  tests/unit/test_context_workspace_session_adapter.py \
  -k 'slice or render or session or request_render or context_workspace_adapter' \
  --tb=short
python -m ruff check \
  src/crxzipple/modules/orchestration/interfaces/dto.py \
  src/crxzipple/app/integration/context_workspace_orchestration/request_render_snapshot_pipeline.py \
  src/crxzipple/app/integration/context_workspace_orchestration/request_render_snapshot_metadata.py \
  src/crxzipple/modules/context_workspace/application/services.py \
  tests/unit/test_orchestration_context_workspace_snapshot.py \
  --ignore F401,I001,E501
```

结果：`86 passed, 23 deselected in 1.23s`；ruff passed。

- [x] 已拉起一次长链任务，检查 LLM request preview、response items、tool call/result、Workbench timeline。

```bash
source scripts/dev/infra-env.sh
PYTHONPATH=src python -m crxzipple.main ask \
  "RUNTIME_CHAIN_20260623H：请完成本地两步检查：1) 用命令查看当前工作目录；2) 用命令查看当前日期时间。最后用中文一句话说明你用了哪些工具和看到了什么。必须至少调用一次工具，不要访问外网。" \
  --agent crxzipple \
  --llm-id openai_codex.gpt-5.4-mini \
  --main-key runtime-chain-20260623h \
  --max-steps 6 \
  --wait-timeout-seconds 180 \
  --poll-interval-seconds 0.2 \
  --json
curl -sS \
  'http://127.0.0.1:8000/ui/workbench/runs/87d7ba96026c4656b2bca0c7efd4d0e7/llm-request-preview' \
  | jq '{input_count:(.input_items|length), input_types:[.input_items[]?.kind], tool_names:[.tool_schemas[]?.name], request_timings:.request_render_snapshot_metadata.request_render_timings, builder_timings:.request_render_snapshot_metadata.context_slice_builder_timings}'
```

结果：run `87d7ba96026c4656b2bca0c7efd4d0e7` completed；最终 provider input 为 5 项 `message/function_call/function_call_output/function_call/function_call_output`；tool schemas 为 `capability.search/exec/process`；`build_context_slice_ms=14.484`、`refresh_owner_children_ms=0.009`、`total_before_request_render_snapshot_ms=438.762`。本次没有 `provider_continuation_state.fallback`。

- [x] Operations LLM 投影代码结构已复查并收口：`llm.py` 从 1474 行降到 460 行，页面 provider 只保留取数和 section 编排；详情投影移到 `llm_invocation_details.py`，run/trace 定位移到 `llm_run_contexts.py`，页面/详情 dataclass 移到 `llm_models.py`。验证：

```bash
python -m ruff check \
  src/crxzipple/modules/operations/application/read_models/llm.py \
  src/crxzipple/modules/operations/application/read_models/llm_invocation_details.py \
  src/crxzipple/modules/operations/application/read_models/llm_run_contexts.py \
  src/crxzipple/modules/operations/application/read_models/llm_models.py \
  --ignore I001,E501
PYTHONPATH=src pytest -q \
  tests/unit/test_operations_llm_read_model.py \
  tests/unit/test_operations_llm_render_report.py \
  tests/unit/test_operations_llm_projection_diagnostics.py \
  tests/unit/test_operations_llm_invocation_facts.py \
  tests/unit/test_operations_llm_provider_request_diagnostics.py \
  tests/unit/test_operations_llm_detail_tables.py \
  tests/unit/test_operations_llm_invocation_tables.py \
  tests/unit/test_operations_llm_lifecycle_events.py \
  tests/unit/test_operations_llm_overview_sections.py \
  tests/unit/test_operations_llm_provider_sections.py \
  tests/unit/test_operations_llm_rate_limiter_sections.py \
  tests/unit/test_operations_llm_resolver_sections.py \
  tests/unit/test_operations_llm_response_events.py \
  tests/unit/test_operations_llm_runtime_metrics.py \
  tests/unit/test_operations_llm_stream_sections.py \
  tests/unit/test_operations_llm_usage_sections.py \
  tests/unit/test_ui_operations_http.py
```

结果：ruff passed；`65 passed`。

- [x] Operations LLM lifecycle event section 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/llm.py src/crxzipple/modules/operations/application/read_models/llm_lifecycle_events.py src/crxzipple/modules/operations/application/read_models/llm_lifecycle_event_sources.py src/crxzipple/modules/operations/application/read_models/llm_lifecycle_event_rows.py src/crxzipple/modules/operations/application/read_models/llm_detail_tables.py tests/unit/test_operations_llm_lifecycle_events.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/llm.py src/crxzipple/modules/operations/application/read_models/llm_lifecycle_events.py src/crxzipple/modules/operations/application/read_models/llm_lifecycle_event_sources.py src/crxzipple/modules/operations/application/read_models/llm_lifecycle_event_rows.py src/crxzipple/modules/operations/application/read_models/llm_detail_tables.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_lifecycle_events.py tests/unit/test_operations_llm_read_model.py tests/unit/test_ui_operations_http.py -k llm --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_detail_tables.py tests/unit/test_operations_llm_invocation_tables.py tests/unit/test_operations_llm_response_events.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k llm --tb=short
```

结果：ruff passed；compileall passed；LLM lifecycle/read-model/UI scoped 回归 `7 passed, 23 deselected`；LLM detail/invocation/response event 回归 `9 passed`；Operations observation LLM scoped 回归 `1 passed, 48 deselected`。`operations/application/read_models/llm_lifecycle_events.py` 从 440 行收口到 66 行；LLM lifecycle event collection/dedupe 迁入 `llm_lifecycle_event_sources.py`，transport/continuation/input-delta/payload/tone row projection 迁入 `llm_lifecycle_event_rows.py`。

- [x] Operations Events 投影完成当前 hotspot scope 拆分：`events.py` 从 1908 行降到 382 行；近期事件表和事件详情投影迁出到 `events_event_details.py`，consumer/observer/subscription/observer coverage section 迁出到 `events_observer_sections.py`，topic/contract/route projection 与匹配逻辑迁出到 `events_contract_sections.py`，dead-letter table projection 迁出到 `events_dead_letters.py`；原 aggregate `events_state.py` 已退役，近期事件摘要、subscription/topic 状态、observer runtime 状态、共享 cursor/display/json helper 分别迁入 focused Events state modules。主 provider 现在只保留 owner/query 事实收集、health 汇总和页面 section 编排。验证：

```bash
python -m ruff check \
  src/crxzipple/modules/operations/application/read_models/events.py \
  src/crxzipple/modules/operations/application/read_models/events_state_common.py \
  src/crxzipple/modules/operations/application/read_models/events_recent_state.py \
  src/crxzipple/modules/operations/application/read_models/events_subscription_state.py \
  src/crxzipple/modules/operations/application/read_models/events_observer_runtime_state.py \
  src/crxzipple/modules/operations/application/read_models/events_contract_sections.py \
  src/crxzipple/modules/operations/application/read_models/events_observer_sections.py \
  src/crxzipple/modules/operations/application/read_models/events_event_details.py \
  src/crxzipple/modules/operations/application/read_models/events_overview_sections.py \
  src/crxzipple/modules/operations/application/read_models/events_models.py \
  src/crxzipple/modules/operations/application/read_models/events_filters.py \
  --ignore I001,E501
python -m compileall -q \
  src/crxzipple/modules/operations/application/read_models/events.py \
  src/crxzipple/modules/operations/application/read_models/events_state_common.py \
  src/crxzipple/modules/operations/application/read_models/events_recent_state.py \
  src/crxzipple/modules/operations/application/read_models/events_subscription_state.py \
  src/crxzipple/modules/operations/application/read_models/events_observer_runtime_state.py \
  src/crxzipple/modules/operations/application/read_models/events_contract_sections.py \
  src/crxzipple/modules/operations/application/read_models/events_observer_sections.py \
  src/crxzipple/modules/operations/application/read_models/events_event_details.py \
  src/crxzipple/modules/operations/application/read_models/events_overview_sections.py \
  src/crxzipple/modules/operations/application/read_models/events_models.py \
  src/crxzipple/modules/operations/application/read_models/events_filters.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k events --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k events --tb=short
```

结果：ruff passed；compileall passed；UI Operations Events scoped 回归 `6 passed, 20 deselected`；Operations observation Events scoped 回归 `19 passed, 30 deselected`；scoped `git diff --check` passed。

- [x] Operations Events dead-letter table 拆分复跑：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/events.py src/crxzipple/modules/operations/application/read_models/events_dead_letters.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/events.py src/crxzipple/modules/operations/application/read_models/events_dead_letters.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k events --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k events --tb=short
PYTHONPATH=src pytest -q tests/unit/test_events.py::EventsModuleTestCase::test_event_definition_registry_covers_tool_and_llm_lifecycle_events tests/unit/test_events.py::EventsModuleTestCase::test_event_definition_registry_covers_operations_observer_subscriptions --tb=short
```

结果：ruff passed；compileall passed；Events observation scoped 回归 `19 passed, 30 deselected`；UI Events scoped 回归 `6 passed, 20 deselected`；event registry checks `2 passed`。`operations/application/read_models/events.py` 当前收口到 382 行；dead-letter table row/id/display/column projection 迁入 `events_dead_letters.py`。

- [x] Operations Daemon 投影完成当前 hotspot scope 拆分：`daemon.py` 从 2442/2370/2082/1424/1004/642 行继续降到 277 行；页面 view model 移到 `daemon_models.py`，共享显示/status/currentness helper 移到 `daemon_common.py`，Daemon/Process 事件采集和事件表投影移到 `daemon_events.py`，service/instance/lease/process/dependency table 投影移到 `daemon_tables.py`，instance/lease/process detail 投影移到 `daemon_details.py`，health/metric/tab/chart/drain sections 移到 `daemon_health.py`，runtime facts/filter/page action/link helpers 移到 focused helper modules。主 provider 现在只保留 owner fact collection 和页面组装。验证：

```bash
python -m ruff check \
  src/crxzipple/modules/operations/application/read_models/daemon.py \
  src/crxzipple/modules/operations/application/read_models/daemon_runtime_facts.py \
  src/crxzipple/modules/operations/application/read_models/daemon_filters.py \
  src/crxzipple/modules/operations/application/read_models/daemon_page_helpers.py \
  src/crxzipple/modules/operations/application/read_models/daemon_models.py \
  src/crxzipple/modules/operations/application/read_models/daemon_events.py \
  src/crxzipple/modules/operations/application/read_models/daemon_common.py \
  src/crxzipple/modules/operations/application/read_models/daemon_tables.py \
  src/crxzipple/modules/operations/application/read_models/daemon_details.py \
  src/crxzipple/modules/operations/application/read_models/daemon_health.py \
  src/crxzipple/modules/operations/application/read_models/__init__.py \
  src/crxzipple/modules/operations/application/read_models/facade.py \
  tests/unit/test_operations_daemon_read_model.py \
  --ignore I001,E501
python -m compileall -q \
  src/crxzipple/modules/operations/application/read_models/daemon.py \
  src/crxzipple/modules/operations/application/read_models/daemon_runtime_facts.py \
  src/crxzipple/modules/operations/application/read_models/daemon_filters.py \
  src/crxzipple/modules/operations/application/read_models/daemon_page_helpers.py \
  src/crxzipple/modules/operations/application/read_models/daemon_models.py \
  src/crxzipple/modules/operations/application/read_models/daemon_events.py \
  src/crxzipple/modules/operations/application/read_models/daemon_common.py \
  src/crxzipple/modules/operations/application/read_models/daemon_tables.py \
  src/crxzipple/modules/operations/application/read_models/daemon_details.py \
  src/crxzipple/modules/operations/application/read_models/daemon_health.py \
  src/crxzipple/modules/operations/application/read_models/__init__.py \
  src/crxzipple/modules/operations/application/read_models/facade.py
PYTHONPATH=src pytest -q tests/unit/test_operations_daemon_read_model.py tests/unit/test_ui_operations_http.py::UiOperationsHttpTestCase::test_ui_operations_daemon_overview_reads_projection_without_runtime_refresh tests/unit/test_ui_operations_http.py::UiOperationsHttpTestCase::test_ui_operations_daemon_page_uses_materialized_runtime_state tests/unit/test_ui_operations_http.py::UiOperationsHttpTestCase::test_ui_operations_daemon_page_reports_missing_process_sessions tests/unit/test_ui_operations_http.py::UiOperationsHttpTestCase::test_ui_operations_daemon_health_ignores_historical_process_failures tests/unit/test_operations_observation.py -k daemon --tb=short
```

结果：ruff passed；compileall passed；Daemon read-model/UI/observation scoped 回归 `6 passed, 48 deselected`；scoped `git diff --check` passed。

- [ ] Operations LLM freshness 仍需长链观察：此前 `/operations/llm?run_id=...` 观察到 projection freshness 滞后和 owner call 耗时，本轮先完成 read model 分层清理，后续需要用实际 run 对 observer/materializer 延迟做针对性采样。
- [ ] 对比 Codex trace：provider input items、tool schema、response item projection、visible assistant progress 的差异必须可解释。

- [x] Operations Access read model 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/access.py src/crxzipple/modules/operations/application/read_models/access_common.py src/crxzipple/modules/operations/application/read_models/access_events.py src/crxzipple/modules/operations/application/read_models/access_inventory.py src/crxzipple/modules/operations/application/read_models/access_health.py src/crxzipple/modules/operations/application/read_models/access_tables.py src/crxzipple/modules/operations/application/read_models/access_details.py src/crxzipple/modules/operations/application/read_models/access_models.py src/crxzipple/modules/operations/application/read_models/__init__.py src/crxzipple/modules/operations/application/read_models/facade.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/access.py src/crxzipple/modules/operations/application/read_models/access_common.py src/crxzipple/modules/operations/application/read_models/access_events.py src/crxzipple/modules/operations/application/read_models/access_inventory.py src/crxzipple/modules/operations/application/read_models/access_health.py src/crxzipple/modules/operations/application/read_models/access_tables.py src/crxzipple/modules/operations/application/read_models/access_details.py src/crxzipple/modules/operations/application/read_models/access_models.py src/crxzipple/modules/operations/application/read_models/__init__.py src/crxzipple/modules/operations/application/read_models/facade.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k access --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k access --tb=short
```

结果：ruff passed；compileall passed；UI Access 回归 `1 passed, 25 deselected`；Access observation 回归 `3 passed, 46 deselected`。`operations/application/read_models/access.py` 从 1486 行收口到 211 行，page models、target/status helpers、inventory collection/filtering、access event collection、health/chart/action sections、table projections、target detail projection 已拆到 focused helper modules。

- [x] Operations Access table helper 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/access.py src/crxzipple/modules/operations/application/read_models/access_details.py src/crxzipple/modules/operations/application/read_models/access_tables.py src/crxzipple/modules/operations/application/read_models/access_event_tables.py src/crxzipple/modules/operations/application/read_models/access_detail_tables.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/access.py src/crxzipple/modules/operations/application/read_models/access_details.py src/crxzipple/modules/operations/application/read_models/access_tables.py src/crxzipple/modules/operations/application/read_models/access_event_tables.py src/crxzipple/modules/operations/application/read_models/access_detail_tables.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k access --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k access --tb=short
```

结果：ruff passed；compileall passed；UI Access 回归 `1 passed, 25 deselected`；Access observation 回归 `3 passed, 46 deselected`。`operations/application/read_models/access_tables.py` 从 619 行收口到 366 行；event/audit/fallback tables 已迁入 `access_event_tables.py`，target checks/usages/setup detail tables 已迁入 `access_detail_tables.py`，`access.py` 和 `access_details.py` 只依赖相应 focused table helper。

- [x] Operations Access table aggregate 退役回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/access.py src/crxzipple/modules/operations/application/read_models/access_target_tables.py src/crxzipple/modules/operations/application/read_models/access_requirement_tables.py src/crxzipple/modules/operations/application/read_models/access_usage_tables.py tests/unit/test_operations_observation.py tests/unit/test_ui_access_http.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/access.py src/crxzipple/modules/operations/application/read_models/access_target_tables.py src/crxzipple/modules/operations/application/read_models/access_requirement_tables.py src/crxzipple/modules/operations/application/read_models/access_usage_tables.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k access --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_access_http.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k access --tb=short
```

结果：ruff passed；compileall passed；Access observation scoped 回归 `3 passed, 46 deselected`；UI Access 回归 `10 passed`；UI Operations Access scoped 回归 `1 passed, 25 deselected`。旧 `access_tables.py` 已退役，不保留转发层；target/missing/provider/authentication tables 迁入 `access_target_tables.py`（173 行），credential requirement rows 迁入 `access_requirement_tables.py`（97 行），usage/setup/expiry tables 迁入 `access_usage_tables.py`（136 行）。`access.py` 直接依赖 focused table modules。

- [x] Operations Channels overview/page builder 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/channels.py src/crxzipple/modules/operations/application/read_models/channels_page_builder.py src/crxzipple/modules/operations/application/read_models/channels_overview_builder.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/channels.py src/crxzipple/modules/operations/application/read_models/channels_page_builder.py src/crxzipple/modules/operations/application/read_models/channels_overview_builder.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k channels --tb=short
```

结果：ruff passed；compileall passed；Operations observation 回归 `49 passed`；UI Operations Channels scoped 回归 `2 passed, 24 deselected`。`operations/application/read_models/channels.py` 从 358 行收口到 55 行；page fact reads、query normalization/filtering、table/chart/detail DTO assembly 迁入 `channels_page_builder.py`（334 行），overview projection 迁入 `channels_overview_builder.py`（50 行）。`pytest -k channels` 在 observation suite 无匹配用例会返回 exit 5，因此改跑完整 observation suite。

- [x] Operations Channels page filter 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/channels_page_builder.py src/crxzipple/modules/operations/application/read_models/channels_page_filters.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/channels_page_builder.py src/crxzipple/modules/operations/application/read_models/channels_page_filters.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k channels --tb=short
PYTHONPATH=src pytest -q tests/unit/test_channels_http.py::ChannelsHttpTestCase::test_web_channel_events_endpoint_streams_live_events --tb=short
```

结果：ruff passed；compileall passed；UI Operations Channels scoped 回归 `2 passed, 24 deselected`；Channels SSE live-event 回归 `1 passed`。`operations/application/read_models/channels_page_builder.py` 从 334 行收口到 254 行；query normalization、runtime record filters、event filters 和 interaction filters 迁入 `channels_page_filters.py`（96 行）。

- [x] Operations Skills overview/page builder 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/skills.py src/crxzipple/modules/operations/application/read_models/skills_page_builder.py src/crxzipple/modules/operations/application/read_models/skills_overview_builder.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/skills.py src/crxzipple/modules/operations/application/read_models/skills_page_builder.py src/crxzipple/modules/operations/application/read_models/skills_overview_builder.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k skills --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k skills --tb=short
PYTHONPATH=src pytest -q tests/unit/test_skills_http.py tests/unit/test_skills_context.py -k 'operations or list or validate or install or surface' --tb=short
```

结果：ruff passed；compileall passed；Skills observation scoped 回归 `5 passed, 44 deselected`；UI Operations Skills scoped 回归 `1 passed, 25 deselected`；Skills owner/http scoped 回归 `4 passed, 34 deselected`。`operations/application/read_models/skills.py` 从 353 行收口到 55 行；page fact reads、query normalization/filtering、SkillRecord readiness projection、table/chart/detail DTO assembly 迁入 `skills_page_builder.py`（327 行），overview projection 迁入 `skills_overview_builder.py`（53 行）。

- [x] Operations Skills page facts 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/skills.py src/crxzipple/modules/operations/application/read_models/skills_page_builder.py src/crxzipple/modules/operations/application/read_models/skills_page_facts.py src/crxzipple/modules/operations/application/read_models/skills_overview_builder.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/skills.py src/crxzipple/modules/operations/application/read_models/skills_page_builder.py src/crxzipple/modules/operations/application/read_models/skills_page_facts.py src/crxzipple/modules/operations/application/read_models/skills_overview_builder.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k skills --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k skills --tb=short
```

结果：ruff passed；compileall passed；UI Operations Skills scoped 回归 `1 passed, 25 deselected`；Operations observation Skills scoped 回归 `5 passed, 44 deselected`。`operations/application/read_models/skills_page_builder.py` 从 327 行收口到 149 行，只保留 page DTO/table/chart/detail assembly；query normalization、safe skill/tool/access reads、SkillRecord readiness projection、event buckets、filtering 和 health 迁入 `skills_page_facts.py`（252 行）。

- [x] Operations Daemon detail aggregate 退役回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/daemon.py src/crxzipple/modules/operations/application/read_models/daemon_detail_common.py src/crxzipple/modules/operations/application/read_models/daemon_instance_details.py src/crxzipple/modules/operations/application/read_models/daemon_lease_details.py src/crxzipple/modules/operations/application/read_models/daemon_process_details.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/daemon.py src/crxzipple/modules/operations/application/read_models/daemon_detail_common.py src/crxzipple/modules/operations/application/read_models/daemon_instance_details.py src/crxzipple/modules/operations/application/read_models/daemon_lease_details.py src/crxzipple/modules/operations/application/read_models/daemon_process_details.py
PYTHONPATH=src pytest -q tests/unit/test_operations_daemon_read_model.py tests/unit/test_ui_operations_http.py -k daemon --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k daemon --tb=short
```

结果：ruff passed；compileall passed；Daemon read-model/UI scoped 回归 `5 passed, 22 deselected`；Operations observation Daemon scoped 回归 `1 passed, 48 deselected`。旧 `daemon_details.py` 已退役，不保留转发层；instance details 迁入 `daemon_instance_details.py`（214 行），lease details 迁入 `daemon_lease_details.py`（68 行），process details 迁入 `daemon_process_details.py`（76 行），共享 metadata section 和 event matching helper 迁入 `daemon_detail_common.py`（53 行）。`daemon.py` 直接依赖 focused detail modules。

- [x] Operations Orchestration ingress state / row projection 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/orchestration_ingress_sections.py src/crxzipple/modules/operations/application/read_models/orchestration_ingress_rows.py src/crxzipple/modules/operations/application/read_models/orchestration_ingress_state.py src/crxzipple/modules/operations/application/read_models/orchestration_page_builder.py src/crxzipple/modules/operations/application/read_models/orchestration_overview_builder.py tests/unit/test_operations_orchestration_ingress_sections.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/orchestration_ingress_sections.py src/crxzipple/modules/operations/application/read_models/orchestration_ingress_rows.py src/crxzipple/modules/operations/application/read_models/orchestration_ingress_state.py src/crxzipple/modules/operations/application/read_models/orchestration_page_builder.py src/crxzipple/modules/operations/application/read_models/orchestration_overview_builder.py tests/unit/test_operations_orchestration_ingress_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_orchestration_ingress_sections.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_orchestration_ingress_sections.py tests/unit/test_operations_orchestration_overview_rows.py tests/unit/test_ui_operations_orchestration_http.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k orchestration --tb=short
```

结果：ruff passed；compileall passed；Ingress section 单测 `2 passed`；Orchestration ingress/overview/UI scoped 回归 `9 passed`；Operations observation Orchestration scoped 回归 `6 passed, 43 deselected`。`operations/application/read_models/orchestration_ingress_sections.py` 现在为 64 行，只保留 ingress queue table assembly；pending ingress selection 迁入 `orchestration_ingress_state.py`（35 行），source/status/dispatch/trace/action row projection 迁入 `orchestration_ingress_rows.py`（274 行）。

- [x] Operations Orchestration event-log row projection 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/orchestration_event_log_sections.py src/crxzipple/modules/operations/application/read_models/orchestration_event_log_rows.py src/crxzipple/modules/operations/application/read_models/orchestration_status_projection.py tests/unit/test_operations_orchestration_event_log_sections.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/orchestration_event_log_sections.py src/crxzipple/modules/operations/application/read_models/orchestration_event_log_rows.py src/crxzipple/modules/operations/application/read_models/orchestration_status_projection.py tests/unit/test_operations_orchestration_event_log_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_orchestration_event_log_sections.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_orchestration_event_log_sections.py tests/unit/test_operations_orchestration_ingress_sections.py tests/unit/test_operations_orchestration_overview_rows.py tests/unit/test_ui_operations_orchestration_http.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k orchestration --tb=short
```

结果：ruff passed；compileall passed；event-log section 单测 `2 passed`；Orchestration event-log/ingress/overview/UI scoped 回归 `11 passed`；Operations observation Orchestration scoped 回归 `6 passed, 43 deselected`。`operations/application/read_models/orchestration_event_log_sections.py` 从 329 行收口到 40 行；event time/source/summary/detail/tone/trace 和 row projection 迁入 `orchestration_event_log_rows.py`（300 行）。

- [x] Operations Tool model/page helper 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/tool_models.py src/crxzipple/modules/operations/application/read_models/tool_page_helpers.py src/crxzipple/modules/operations/application/read_models/__init__.py src/crxzipple/modules/operations/application/read_models/facade.py src/crxzipple/modules/operations/application/read_models/projection_payloads.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/tool_models.py src/crxzipple/modules/operations/application/read_models/tool_page_helpers.py src/crxzipple/modules/operations/application/read_models/__init__.py src/crxzipple/modules/operations/application/read_models/facade.py src/crxzipple/modules/operations/application/read_models/projection_payloads.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_read_model.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k tool --tb=short
```

结果：ruff passed；compileall passed；Tool read-model 回归 `4 passed`；UI Tool 回归 `4 passed, 22 deselected`。`operations/application/read_models/tool.py` 从 712 行收口到 488 行；Tool Operations page DTO 与 projection payload defer/find helper 已迁入 `tool_models.py`，provider-local table/filter/artifact/assignment wrappers 已迁入 `tool_page_helpers.py`，`tool.py` 只保留 public provider facade 与页面级事实编排。

- [x] Operations runtime HTTP DTO module 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/interfaces/http_models.py src/crxzipple/modules/operations/interfaces/http_models_runtime_pages.py src/crxzipple/modules/operations/interfaces/http_models_channels_pages.py src/crxzipple/modules/operations/interfaces/http_models_daemon_pages.py src/crxzipple/modules/operations/interfaces/http_models_events_pages.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/interfaces/http_models.py src/crxzipple/modules/operations/interfaces/http_models_runtime_pages.py src/crxzipple/modules/operations/interfaces/http_models_channels_pages.py src/crxzipple/modules/operations/interfaces/http_models_daemon_pages.py src/crxzipple/modules/operations/interfaces/http_models_events_pages.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k 'browser or channels or daemon or events' --tb=short
```

结果：ruff passed；compileall passed；UI Operations HTTP 回归 `26 passed`；Operations observation runtime-page scoped 回归 `19 passed, 30 deselected`。`operations/interfaces/http_models_runtime_pages.py` 从 605 行收口到 Browser-only 75 行；Channels、Daemon、Events page/detail response DTO 已分别迁入 `http_models_channels_pages.py`、`http_models_daemon_pages.py`、`http_models_events_pages.py`，`http_models.py` 保持统一 HTTP DTO 出口。

- [x] Operations HTTP DTO surface 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/interfaces/http_models.py src/crxzipple/modules/operations/interfaces/http_models_core.py src/crxzipple/modules/operations/interfaces/http_models_actions.py src/crxzipple/modules/operations/interfaces/http_models_support_pages.py src/crxzipple/modules/operations/interfaces/http_models_runtime_pages.py src/crxzipple/modules/operations/interfaces/http_models_channels_pages.py src/crxzipple/modules/operations/interfaces/http_models_daemon_pages.py src/crxzipple/modules/operations/interfaces/http_models_events_pages.py src/crxzipple/modules/operations/interfaces/http_models_tool_pages.py src/crxzipple/modules/operations/interfaces/http_models_llm_pages.py src/crxzipple/modules/operations/interfaces/http_models_orchestration_pages.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/interfaces/http_models.py src/crxzipple/modules/operations/interfaces/http_models_core.py src/crxzipple/modules/operations/interfaces/http_models_actions.py src/crxzipple/modules/operations/interfaces/http_models_support_pages.py src/crxzipple/modules/operations/interfaces/http_models_runtime_pages.py src/crxzipple/modules/operations/interfaces/http_models_channels_pages.py src/crxzipple/modules/operations/interfaces/http_models_daemon_pages.py src/crxzipple/modules/operations/interfaces/http_models_events_pages.py src/crxzipple/modules/operations/interfaces/http_models_tool_pages.py src/crxzipple/modules/operations/interfaces/http_models_llm_pages.py src/crxzipple/modules/operations/interfaces/http_models_orchestration_pages.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k 'access or memory or browser or channels or skills or daemon or events' --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_browser_read_model.py tests/unit/test_operations_daemon_read_model.py --tb=short
```

结果：ruff passed；compileall passed；`test_ui_operations_http.py` 为 `26 passed`；Operations observation scoped 回归为 `23 passed, 26 deselected`；Browser/Daemon read model 回归为 `11 passed`。`operations/interfaces/http_models.py` 从 2016 行收口到 151 行，shared primitives、action DTO、support/runtime/channel/daemon/event/tool/llm/orchestration page response 已拆到 focused HTTP DTO modules；HTTP contract 保持通过现有 UI/Operations 回归。

- [x] Operations execution HTTP DTO module 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/interfaces/http_models.py src/crxzipple/modules/operations/interfaces/http_models_tool_pages.py src/crxzipple/modules/operations/interfaces/http_models_llm_pages.py src/crxzipple/modules/operations/interfaces/http_models_orchestration_pages.py src/crxzipple/modules/operations/interfaces/http_projection_routes.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/interfaces/http_models.py src/crxzipple/modules/operations/interfaces/http_models_tool_pages.py src/crxzipple/modules/operations/interfaces/http_models_llm_pages.py src/crxzipple/modules/operations/interfaces/http_models_orchestration_pages.py src/crxzipple/modules/operations/interfaces/http_projection_routes.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k 'orchestration or operations_action' --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_read_model.py tests/unit/test_operations_llm_read_model.py tests/unit/test_ui_operations_orchestration_http.py --tb=short
```

结果：ruff passed；compileall passed；UI Operations HTTP 回归 `26 passed`；Operations observation execution/action scoped 回归 `9 passed, 40 deselected`；Tool/LLM/Orchestration focused HTTP/read-model 回归 `8 passed`。旧 `operations/interfaces/http_models_execution_pages.py` 已退役；Tool、LLM、Orchestration page/detail response DTO 已分别迁入 `http_models_tool_pages.py`、`http_models_llm_pages.py`、`http_models_orchestration_pages.py`。

- [x] Operations HTTP router helper 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/interfaces/http.py src/crxzipple/modules/operations/interfaces/http_runtime.py src/crxzipple/modules/operations/interfaces/http_action_helpers.py src/crxzipple/modules/operations/interfaces/http_models.py src/crxzipple/modules/operations/interfaces/http_models_core.py src/crxzipple/modules/operations/interfaces/http_models_actions.py src/crxzipple/modules/operations/interfaces/http_models_support_pages.py src/crxzipple/modules/operations/interfaces/http_models_runtime_pages.py src/crxzipple/modules/operations/interfaces/http_models_channels_pages.py src/crxzipple/modules/operations/interfaces/http_models_daemon_pages.py src/crxzipple/modules/operations/interfaces/http_models_events_pages.py src/crxzipple/modules/operations/interfaces/http_models_tool_pages.py src/crxzipple/modules/operations/interfaces/http_models_llm_pages.py src/crxzipple/modules/operations/interfaces/http_models_orchestration_pages.py tests/unit/test_operations_observation.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/interfaces/http.py src/crxzipple/modules/operations/interfaces/http_runtime.py src/crxzipple/modules/operations/interfaces/http_action_helpers.py src/crxzipple/modules/operations/interfaces/http_models.py src/crxzipple/modules/operations/interfaces/http_models_core.py src/crxzipple/modules/operations/interfaces/http_models_actions.py src/crxzipple/modules/operations/interfaces/http_models_support_pages.py src/crxzipple/modules/operations/interfaces/http_models_runtime_pages.py src/crxzipple/modules/operations/interfaces/http_models_channels_pages.py src/crxzipple/modules/operations/interfaces/http_models_daemon_pages.py src/crxzipple/modules/operations/interfaces/http_models_events_pages.py src/crxzipple/modules/operations/interfaces/http_models_tool_pages.py src/crxzipple/modules/operations/interfaces/http_models_llm_pages.py src/crxzipple/modules/operations/interfaces/http_models_orchestration_pages.py
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py::UiHttpTestCase::test_operations_page_responses_expose_projection_freshness tests/unit/test_events_http.py tests/unit/test_ui_operations_http.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k 'access or memory or browser or channels or skills or daemon or events or operations_action' --tb=short
```

结果：HTTP/UI/Event 组合回归 `34 passed`；Operations observation scoped/action 回归 `26 passed, 23 deselected`。`operations/interfaces/http.py` 从 1806 行收口到 1394 行，runtime status/SSE helper 移入 `http_runtime.py`，operation validation/audit/result summary helper 移入 `http_action_helpers.py`；route-group 分组在下一步拆分中完成。

- [x] Operations HTTP router route-group 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/interfaces/http.py src/crxzipple/modules/operations/interfaces/http_action_*.py src/crxzipple/modules/operations/interfaces/http_projection_*.py src/crxzipple/modules/operations/interfaces/http_runtime.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/interfaces/http.py src/crxzipple/modules/operations/interfaces/http_action_routes.py src/crxzipple/modules/operations/interfaces/http_action_routes_execution.py src/crxzipple/modules/operations/interfaces/http_action_routes_resources.py src/crxzipple/modules/operations/interfaces/http_action_routes_events.py src/crxzipple/modules/operations/interfaces/http_action_service.py src/crxzipple/modules/operations/interfaces/http_projection_routes.py src/crxzipple/modules/operations/interfaces/http_projection_helpers.py
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py::UiHttpTestCase::test_operations_page_responses_expose_projection_freshness tests/unit/test_events_http.py tests/unit/test_ui_operations_http.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k 'access or memory or browser or channels or skills or daemon or events or operations_action' --tb=short
```

结果：ruff passed；compileall passed；HTTP/UI/Event 组合回归 `34 passed`；Operations observation scoped/action 回归 `26 passed, 23 deselected`。`operations/interfaces/http.py` 进一步从 1394 行收口到 129 行，主 router 只保留 runtime status、projection-refresh SSE、action/projection sub-router composition；projection read routes、projection payload/error mapping、action service construction、execution/resource/event controlled-action routes 均拆入 focused interface modules。

- [x] Operations Orchestration read model status/failure/metric/action/runtime-fact split 回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/orchestration.py src/crxzipple/modules/operations/application/read_models/orchestration_actions.py src/crxzipple/modules/operations/application/read_models/orchestration_runtime_facts.py src/crxzipple/modules/operations/application/read_models/orchestration_metrics.py src/crxzipple/modules/operations/application/read_models/orchestration_status_sections.py src/crxzipple/modules/operations/application/read_models/orchestration_failure_sections.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/orchestration.py src/crxzipple/modules/operations/application/read_models/orchestration_actions.py src/crxzipple/modules/operations/application/read_models/orchestration_runtime_facts.py src/crxzipple/modules/operations/application/read_models/orchestration_metrics.py src/crxzipple/modules/operations/application/read_models/orchestration_status_sections.py src/crxzipple/modules/operations/application/read_models/orchestration_failure_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_orchestration_execution_chain_sections.py tests/unit/test_operations_orchestration_backpressure_sections.py tests/unit/test_operations_orchestration_event_log_sections.py tests/unit/test_operations_orchestration_ingress_sections.py tests/unit/test_operations_orchestration_queue_sections.py tests/unit/test_operations_orchestration_worker_sections.py tests/unit/test_operations_orchestration_overview_rows.py tests/unit/test_operations_orchestration_projection_diagnostics.py tests/unit/test_ui_operations_orchestration_http.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k orchestration --tb=short
```

结果：ruff passed；compileall passed；Orchestration focused Operations tests `18 passed`；Operations observation orchestration scoped tests `6 passed, 43 deselected`。`operations/application/read_models/orchestration.py` 从 1206 行继续收口到 574 行；scheduler status/policy limits 已迁入 `orchestration_status_sections.py`，repeated-probe/recent-failure sections 已迁入 `orchestration_failure_sections.py`，health/failure/ingress-rate/latency/observer metric projection 已迁入 `orchestration_metrics.py`，Operations action definitions 已迁入 `orchestration_actions.py`，owner fact reads 与 dispatch-task/run grouping helpers 已迁入 `orchestration_runtime_facts.py`；主 provider 只保留页面级事实装配和 section 编排。

- [x] Operations Skills table helper 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/skills.py src/crxzipple/modules/operations/application/read_models/skills_catalog_tables.py src/crxzipple/modules/operations/application/read_models/skills_requirement_tables.py src/crxzipple/modules/operations/application/read_models/skills_event_tables.py src/crxzipple/modules/operations/application/read_models/skills_authoring_tables.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/skills.py src/crxzipple/modules/operations/application/read_models/skills_catalog_tables.py src/crxzipple/modules/operations/application/read_models/skills_requirement_tables.py src/crxzipple/modules/operations/application/read_models/skills_event_tables.py src/crxzipple/modules/operations/application/read_models/skills_authoring_tables.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k skills --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k skills --tb=short
```

结果：ruff passed；compileall passed；UI Skills 回归 `1 passed, 25 deselected`；Operations observation Skills 回归 `5 passed, 44 deselected`。旧 `operations/application/read_models/skills_tables.py` 聚合文件已退役并删除；runtime skill usage / resolution logs / skill reads 已迁入 `skills_event_tables.py`，authoring backlog / failures 已迁入 `skills_authoring_tables.py`，installed/source/conflict/profile catalog 表迁入 `skills_catalog_tables.py`，missing/access/capability/resolver requirement 表迁入 `skills_requirement_tables.py`。

- [x] Operations Skills requirement table 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/skills_page_builder.py src/crxzipple/modules/operations/application/read_models/skills_requirement_tables.py src/crxzipple/modules/operations/application/read_models/skills_missing_tables.py src/crxzipple/modules/operations/application/read_models/skills_resolver_tables.py src/crxzipple/modules/operations/application/read_models/skills_catalog_tables.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/skills_page_builder.py src/crxzipple/modules/operations/application/read_models/skills_requirement_tables.py src/crxzipple/modules/operations/application/read_models/skills_missing_tables.py src/crxzipple/modules/operations/application/read_models/skills_resolver_tables.py src/crxzipple/modules/operations/application/read_models/skills_catalog_tables.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k skills --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k skills --tb=short
```

结果：ruff passed；compileall passed；UI Skills scoped 回归 `1 passed, 25 deselected`；Operations observation Skills scoped 回归 `5 passed, 44 deselected`。`operations/application/read_models/skills_requirement_tables.py` 从 346 行收口到 147 行，只保留 access/capability requirement tables 和 `access_values`；missing capability rows 迁入 `skills_missing_tables.py`（172 行），resolver detail/next-step projection 迁入 `skills_resolver_tables.py`（92 行）。

- [x] Operations fallback module overview helper 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/modules.py src/crxzipple/modules/operations/application/read_models/modules_daemon.py src/crxzipple/modules/operations/application/read_models/modules_events.py src/crxzipple/modules/operations/application/read_models/modules_channels.py src/crxzipple/modules/operations/application/read_models/modules_memory.py src/crxzipple/modules/operations/application/read_models/modules_skills.py src/crxzipple/modules/operations/application/read_models/modules_access.py src/crxzipple/modules/operations/application/read_models/modules_helpers.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/modules.py src/crxzipple/modules/operations/application/read_models/modules_daemon.py src/crxzipple/modules/operations/application/read_models/modules_events.py src/crxzipple/modules/operations/application/read_models/modules_channels.py src/crxzipple/modules/operations/application/read_models/modules_memory.py src/crxzipple/modules/operations/application/read_models/modules_skills.py src/crxzipple/modules/operations/application/read_models/modules_access.py src/crxzipple/modules/operations/application/read_models/modules_helpers.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py --tb=short
```

结果：ruff passed；compileall passed；UI Operations HTTP 回归 `26 passed`。`operations/application/read_models/modules.py` 从 1411 行收口到 156 行；通用 overview/table/format helper 已迁入 `modules_helpers.py`，Access/Memory/Skills/Channels/Events/Daemon fallback overview projection 分别迁入 focused `modules_*` 文件。`modules.py` 现在只保留 module query set、page DTO、provider facade 和 overview dispatch，不再承载 module-specific fallback projection。

- [x] Operations Tool scheduling section 拆分回归（历史中间态，当前 aggregate 已退役）：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool_scheduling_sections.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_rows.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_capacity.py src/crxzipple/modules/operations/application/read_models/tool_provider_sections.py tests/unit/test_operations_tool_scheduling_sections.py tests/unit/test_operations_tool_provider_sections.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool_scheduling_sections.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_rows.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_capacity.py src/crxzipple/modules/operations/application/read_models/tool_provider_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_scheduling_sections.py tests/unit/test_operations_tool_provider_sections.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
```

结果：ruff passed；compileall passed；Tool scheduling/provider 回归 `5 passed`；Tool scoped Operations HTTP/read-model 回归 `8 passed, 22 deselected`。这是 `tool_scheduling_sections.py` 仍存在时的中间态验证；该 aggregate 随后已在后续 “section aggregate 退役回归” 中删除。当前结构中 worker/capacity/concurrency 判断位于 `tool_scheduling_capacity.py`，waiting run / capability limit row 位于 `tool_scheduling_rows.py`，blocker row/reason/tone 位于 `tool_scheduling_blockers.py`，section assembly 位于 focused queue/capability/blocker section modules。

- [x] Operations Tool provider identity 归一回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool_provider_identity.py src/crxzipple/modules/operations/application/read_models/tool_provider_sections.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_rows.py src/crxzipple/modules/operations/application/read_models/tool_page_helpers.py src/crxzipple/modules/operations/application/read_models/tool_run_tables.py src/crxzipple/modules/operations/application/read_models/tool_run_details.py tests/unit/test_operations_tool_provider_sections.py tests/unit/test_operations_tool_scheduling_sections.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool_provider_identity.py src/crxzipple/modules/operations/application/read_models/tool_provider_sections.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_rows.py src/crxzipple/modules/operations/application/read_models/tool_page_helpers.py src/crxzipple/modules/operations/application/read_models/tool_run_tables.py src/crxzipple/modules/operations/application/read_models/tool_run_details.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_provider_sections.py tests/unit/test_operations_tool_scheduling_sections.py tests/unit/test_operations_tool_run_tables.py tests/unit/test_operations_tool_run_details.py --tb=short
```

结果：ruff passed；compileall passed；Tool provider/scheduling/run table/detail 回归 `12 passed`。`tool_provider_key()` 和 `provider_history_label()` 从 provider section / scheduling rows 的重复实现中抽出到 `tool_provider_identity.py`，Tool page filtering、run table、run detail、provider sections、scheduling rows 共享同一套 provider key/label 规则。

- [x] Operations Tool provider limiter projection 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool_provider_sections.py src/crxzipple/modules/operations/application/read_models/tool_provider_limits.py src/crxzipple/modules/operations/application/read_models/tool_provider_identity.py src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/tool_worker_details.py tests/unit/test_operations_tool_provider_sections.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool_provider_sections.py src/crxzipple/modules/operations/application/read_models/tool_provider_limits.py src/crxzipple/modules/operations/application/read_models/tool_provider_identity.py src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/tool_worker_details.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_provider_sections.py tests/unit/test_operations_tool_worker_details.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_provider_sections.py tests/unit/test_operations_tool_scheduling_sections.py tests/unit/test_operations_tool_run_tables.py tests/unit/test_operations_tool_run_details.py tests/unit/test_operations_tool_worker_details.py tests/unit/test_operations_tool_read_model.py --tb=short
```

结果：ruff passed；compileall passed；Tool provider/worker/read-model/UI scoped 回归 `12 passed, 22 deselected`；Tool provider/scheduling/run table/detail/worker/read-model 回归 `17 passed`。`tool_provider_sections.py` 从 797 行进一步收口到 232 行，只保留 provider history section；runtime registry/metrics/provider limiter 聚合和 worker provider limits 迁入 `tool_provider_limits.py`，调用方直接 import 新模块，不保留 section 文件转发层。

- [x] Operations Tool provider limiter fact/row helper 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool_provider_limits.py src/crxzipple/modules/operations/application/read_models/tool_provider_limit_facts.py src/crxzipple/modules/operations/application/read_models/tool_provider_limit_rows.py tests/unit/test_operations_tool_provider_sections.py tests/unit/test_operations_tool_worker_details.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool_provider_limits.py src/crxzipple/modules/operations/application/read_models/tool_provider_limit_facts.py src/crxzipple/modules/operations/application/read_models/tool_provider_limit_rows.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_provider_sections.py tests/unit/test_operations_tool_worker_details.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
```

结果：ruff passed；compileall passed；Tool provider/worker/read-model/UI scoped 回归 `12 passed, 22 deselected`。`operations/application/read_models/tool_provider_limits.py` 从 601 行收口到 218 行；runtime metric/registry snapshot、limiter configuration grouping 和 local capacity facts 迁入 `tool_provider_limit_facts.py`，provider limit rows、numeric coercion、duration/column formatting 迁入 `tool_provider_limit_rows.py`，provider limits public module 只保留 section assembly。

- [x] Operations Context Workspace row/table projection 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/context_workspace.py src/crxzipple/modules/operations/application/read_models/context_workspace_rows.py tests/unit/test_operations_context_workspace_read_model.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/context_workspace.py src/crxzipple/modules/operations/application/read_models/context_workspace_rows.py
PYTHONPATH=src pytest -q tests/unit/test_operations_context_workspace_read_model.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_context_workspace_read_model.py tests/unit/test_operations_observation.py -k context_workspace --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py --tb=short
```

结果：ruff passed；compileall passed；Context Workspace Operations read-model 回归 `2 passed`；Context Workspace projection/observation scoped 回归 `4 passed, 47 deselected`；UI Operations HTTP 回归 `26 passed`。`operations/application/read_models/context_workspace.py` 从 902 行收口到 337 行，只保留 provider facade、安全 owner 读取和 page assembly；workspace/node/snapshot/budget/diagnostic/metric/table 投影迁入 `context_workspace_rows.py`。

- [x] Operations Context Workspace row helper / snapshot row 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/context_workspace.py src/crxzipple/modules/operations/application/read_models/context_workspace_rows.py src/crxzipple/modules/operations/application/read_models/context_workspace_row_helpers.py src/crxzipple/modules/operations/application/read_models/context_workspace_snapshot_rows.py tests/unit/test_operations_context_workspace_read_model.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/context_workspace.py src/crxzipple/modules/operations/application/read_models/context_workspace_rows.py src/crxzipple/modules/operations/application/read_models/context_workspace_row_helpers.py src/crxzipple/modules/operations/application/read_models/context_workspace_snapshot_rows.py
PYTHONPATH=src pytest -q tests/unit/test_operations_context_workspace_read_model.py tests/unit/test_ui_operations_http.py -k 'context_workspace or operations_context_workspace' --tb=short
```

结果：ruff passed；compileall passed；Context Workspace/UI scoped 回归 `2 passed, 26 deselected`。`operations/application/read_models/context_workspace_rows.py` 从 587 行收口到 305 行；generic table/metadata/time/token helpers 迁入 `context_workspace_row_helpers.py`，snapshot/context-budget rows 迁入 `context_workspace_snapshot_rows.py`，`context_workspace.py` 直接 import focused modules，不再通过 rows 文件转发。

- [x] Operations Context Workspace page facts 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/context_workspace.py src/crxzipple/modules/operations/application/read_models/context_workspace_page_facts.py src/crxzipple/modules/operations/application/read_models/context_workspace_rows.py src/crxzipple/modules/operations/application/read_models/context_workspace_snapshot_rows.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/context_workspace.py src/crxzipple/modules/operations/application/read_models/context_workspace_page_facts.py src/crxzipple/modules/operations/application/read_models/context_workspace_rows.py src/crxzipple/modules/operations/application/read_models/context_workspace_snapshot_rows.py
PYTHONPATH=src pytest -q tests/unit/test_operations_context_workspace_read_model.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k context_workspace --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py tests/unit/test_operations_context_workspace_read_model.py --tb=short
```

结果：ruff passed；compileall passed；Context Workspace read-model 回归 `2 passed`；Context Workspace observation scoped 回归 `2 passed, 47 deselected`；UI Operations + Context Workspace 回归 `28 passed`。`operations/application/read_models/context_workspace.py` 从 342 行收口到 186 行，只保留 query/provider/overview/page assembly；safe owner reads、slice collection、page health 和 derived page facts 迁入 `context_workspace_page_facts.py`（235 行）。`tests/unit/test_ui_operations_http.py -k context` 无匹配用例会返回 exit 5，因此使用完整 UI Operations + Context Workspace read-model 回归替代。

- [x] Operations persistence store 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/infrastructure/persistence/projection_repository.py src/crxzipple/modules/operations/infrastructure/persistence/observation_repository.py src/crxzipple/modules/operations/infrastructure/persistence/action_audit_repository.py src/crxzipple/modules/operations/infrastructure/persistence/__init__.py src/crxzipple/modules/operations/infrastructure/__init__.py src/crxzipple/app/assembly/operations.py tests/unit/test_operations_observation.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/infrastructure/persistence/projection_repository.py src/crxzipple/modules/operations/infrastructure/persistence/observation_repository.py src/crxzipple/modules/operations/infrastructure/persistence/action_audit_repository.py src/crxzipple/modules/operations/infrastructure/persistence/__init__.py src/crxzipple/modules/operations/infrastructure/__init__.py src/crxzipple/app/assembly/operations.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py --tb=short
```

结果：ruff passed；compileall passed；Operations observation/projection/action-audit persistence 回归 `49 passed`。`operations/infrastructure/persistence/repositories.py` 从 774 行聚合仓库退役并删除；projection、observation、action audit 持久化分别迁入 `projection_repository.py`、`observation_repository.py`、`action_audit_repository.py`，assembly 直接 import 具体 store，不保留旧文件转发层。

- [x] Operations observation repository mapper/recording 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/infrastructure/persistence/observation_repository.py src/crxzipple/modules/operations/infrastructure/persistence/observation_repository_mappers.py src/crxzipple/modules/operations/infrastructure/persistence/observation_repository_recording.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/infrastructure/persistence/observation_repository.py src/crxzipple/modules/operations/infrastructure/persistence/observation_repository_mappers.py src/crxzipple/modules/operations/infrastructure/persistence/observation_repository_recording.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_events.py::EventsModuleTestCase::test_event_definition_registry_covers_operations_observer_subscriptions tests/unit/test_ui_operations_http.py -k operations --tb=short
```

结果：ruff passed；compileall passed；Operations observation 回归 `49 passed`；Events/UI Operations scoped 回归 `27 passed`。`operations/infrastructure/persistence/observation_repository.py` 从 500 行收口到 233 行；SQLAlchemy row/domain mapper 迁入 `observation_repository_mappers.py`，module summary / event bucket recording / recent event query helper 迁入 `observation_repository_recording.py`。repository 文件保留 store API、事务边界和查询入口。

- [x] Operations action-flow 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/actions.py src/crxzipple/modules/operations/application/action_results.py src/crxzipple/modules/operations/application/action_event_subscriptions.py src/crxzipple/modules/operations/application/action_channel_runtimes.py src/crxzipple/modules/operations/interfaces/http_action_routes_events.py src/crxzipple/modules/operations/interfaces/http_models_actions.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/actions.py src/crxzipple/modules/operations/application/action_results.py src/crxzipple/modules/operations/application/action_event_subscriptions.py src/crxzipple/modules/operations/application/action_channel_runtimes.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k 'action or channel_runtime or event_subscription' --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k 'operations_action or action or channel_runtime or event_subscription' --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_bootstrap_covers_operations_action_endpoints --tb=short
```

结果：ruff passed；compileall passed；Operations action/Channel runtime/event subscription scoped 回归 `5 passed, 44 deselected`；UI Operations action scoped 回归 `3 passed, 23 deselected`；UI bootstrap action endpoint 覆盖 `1 passed`。`operations/application/actions.py` 从 500 行收口到 297 行；action result DTO 迁入 `action_results.py`，event subscription cursor advancement 迁入 `action_event_subscriptions.py`，stale Channel runtime pruning 迁入 `action_channel_runtimes.py`。service 文件保留 action facade 和依赖 delegation。

- [x] Operations loop-regression diagnostics 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/diagnostics.py src/crxzipple/modules/operations/application/read_models/diagnostics_common.py src/crxzipple/modules/operations/application/read_models/diagnostics_response_metrics.py src/crxzipple/modules/operations/application/read_models/diagnostics_run_signals.py tests/unit/test_orchestration_loop_regression_baseline.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/diagnostics.py src/crxzipple/modules/operations/application/read_models/diagnostics_common.py src/crxzipple/modules/operations/application/read_models/diagnostics_response_metrics.py src/crxzipple/modules/operations/application/read_models/diagnostics_run_signals.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_loop_regression_baseline.py tests/unit/test_operations_observation.py --tb=short
```

结果：ruff passed；compileall passed；loop-regression baseline + Operations observation 回归 `54 passed`。`operations/application/read_models/diagnostics.py` 从 742 行收口到 177 行；公共取值/summary helper 迁入 `diagnostics_common.py`，LLM response/request metrics 与 tool-only streak health 迁入 `diagnostics_response_metrics.py`，run signal/final answer/missing-metric projection迁入 `diagnostics_run_signals.py`。

- [x] Operations LLM invocation detail projection 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/llm_invocation_details.py src/crxzipple/modules/operations/application/read_models/llm_invocation_detail_common.py src/crxzipple/modules/operations/application/read_models/llm_invocation_detail_runtime.py src/crxzipple/modules/operations/application/read_models/llm_invocation_detail_replay.py src/crxzipple/modules/operations/application/read_models/llm_invocation_detail_payloads.py tests/unit/test_operations_llm_read_model.py tests/unit/test_operations_llm_detail_tables.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/llm_invocation_details.py src/crxzipple/modules/operations/application/read_models/llm_invocation_detail_common.py src/crxzipple/modules/operations/application/read_models/llm_invocation_detail_runtime.py src/crxzipple/modules/operations/application/read_models/llm_invocation_detail_replay.py src/crxzipple/modules/operations/application/read_models/llm_invocation_detail_payloads.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_read_model.py tests/unit/test_operations_llm_detail_tables.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_read_model.py tests/unit/test_operations_llm_invocation_tables.py tests/unit/test_operations_llm_provider_request_diagnostics.py tests/unit/test_ui_operations_http.py -k llm --tb=short
```

结果：ruff passed；compileall passed；LLM detail/read-model 直接回归 `3 passed`；LLM scoped Operations/UI 回归 `9 passed, 23 deselected`。`operations/application/read_models/llm_invocation_details.py` 从 741 行收口到 399 行；runtime observation/tool protocol 标签迁入 `llm_invocation_detail_runtime.py`，replay input / tool-result label 迁入 `llm_invocation_detail_replay.py`，result payload preview/sanitizing 迁入 `llm_invocation_detail_payloads.py`，共享 label helper 迁入 `llm_invocation_detail_common.py`。

- [x] Operations Channels formatting helper 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/channels_common.py src/crxzipple/modules/operations/application/read_models/channels_formatting.py src/crxzipple/modules/operations/application/read_models/channels_health.py src/crxzipple/modules/operations/application/read_models/channels_events.py src/crxzipple/modules/operations/application/read_models/channels_details.py src/crxzipple/modules/operations/application/read_models/channels.py src/crxzipple/modules/operations/application/read_models/channels_tables.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/channels_common.py src/crxzipple/modules/operations/application/read_models/channels_formatting.py src/crxzipple/modules/operations/application/read_models/channels_health.py src/crxzipple/modules/operations/application/read_models/channels_events.py src/crxzipple/modules/operations/application/read_models/channels_details.py src/crxzipple/modules/operations/application/read_models/channels.py src/crxzipple/modules/operations/application/read_models/channels_tables.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k channels --tb=short
PYTHONPATH=src pytest -q tests/unit/test_channels_http.py::ChannelsHttpTestCase::test_web_channel_events_endpoint_streams_live_events --tb=short
```

结果：ruff passed；compileall passed；UI Operations Channels scoped 回归 `2 passed, 24 deselected`；Channels SSE live-event 单测复跑 `1 passed`。完整 `test_channels.py + test_channels_http.py` 首轮曾出现一次 SSE live-event 时序抖动，复跑目标用例通过，当前作为测试时序风险保留观察。`operations/application/read_models/channels_common.py` 从 686 行收口到 523 行；纯 display/time/status/payload formatting helper 迁入 `channels_formatting.py`，Channels page/health/event/detail/table 投影直接依赖该格式化模块，不再通过 `channels_common.py` 间接转发。

- [x] Operations Daemon runtime facts/filter/page helper 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/daemon.py src/crxzipple/modules/operations/application/read_models/daemon_runtime_facts.py src/crxzipple/modules/operations/application/read_models/daemon_filters.py src/crxzipple/modules/operations/application/read_models/daemon_page_helpers.py tests/unit/test_operations_daemon_read_model.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/daemon.py src/crxzipple/modules/operations/application/read_models/daemon_runtime_facts.py src/crxzipple/modules/operations/application/read_models/daemon_filters.py src/crxzipple/modules/operations/application/read_models/daemon_page_helpers.py
PYTHONPATH=src pytest -q tests/unit/test_operations_daemon_read_model.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py::UiOperationsHttpTestCase::test_ui_operations_daemon_overview_reads_projection_without_runtime_refresh tests/unit/test_ui_operations_http.py::UiOperationsHttpTestCase::test_ui_operations_daemon_page_uses_materialized_runtime_state tests/unit/test_ui_operations_http.py::UiOperationsHttpTestCase::test_ui_operations_daemon_page_reports_missing_process_sessions tests/unit/test_ui_operations_http.py::UiOperationsHttpTestCase::test_ui_operations_daemon_health_ignores_historical_process_failures --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k daemon --tb=short
```

结果：ruff passed；compileall passed；Daemon read-model 回归 `1 passed`；UI Operations Daemon scoped 回归 `4 passed`；Operations observation Daemon scoped 回归 `1 passed, 48 deselected`。后续 Daemon process-table 拆分复跑 Daemon read-model/UI scoped `5 passed, 22 deselected`、Operations observation Daemon `1 passed, 48 deselected`。`operations/application/read_models/daemon.py` 从 642 行收口到 279 行；owner-safe runtime fact reads、process row synthesis/currentness、query filtering、page action/link helpers分别迁入 `daemon_runtime_facts.py`、`daemon_filters.py`、`daemon_page_helpers.py`，Process Sessions table projection 迁入 `daemon_process_tables.py`，`daemon_tables.py` 从 453 行收口到 386 行；主 provider 只保留 owner fact collection 和 page assembly。

- [x] Operations Daemon process output detail 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/daemon_details.py src/crxzipple/modules/operations/application/read_models/daemon_process_output_details.py src/crxzipple/modules/operations/application/read_models/daemon.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/daemon_details.py src/crxzipple/modules/operations/application/read_models/daemon_process_output_details.py src/crxzipple/modules/operations/application/read_models/daemon.py
PYTHONPATH=src pytest -q tests/unit/test_operations_daemon_read_model.py tests/unit/test_ui_operations_http.py -k daemon --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k daemon --tb=short
```

结果：ruff passed；compileall passed；Daemon read-model/UI scoped 回归 `5 passed, 22 deselected`；Operations observation Daemon scoped 回归 `1 passed, 48 deselected`。`operations/application/read_models/daemon_details.py` 从 452 行收口到 353 行；Process stdout/stderr output read guard、payload shaping、output table projection 迁入 `daemon_process_output_details.py`，detail 文件只保留 instance/lease/process detail assembly。

- [x] Operations Tool Source aggregate section 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/tool_source_common.py src/crxzipple/modules/operations/application/read_models/tool_source_queries.py src/crxzipple/modules/operations/application/read_models/tool_source_catalog_sections.py src/crxzipple/modules/operations/application/read_models/tool_source_provider_sections.py tests/unit/test_operations_tool_source_sections.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/tool_source_common.py src/crxzipple/modules/operations/application/read_models/tool_source_queries.py src/crxzipple/modules/operations/application/read_models/tool_source_catalog_sections.py src/crxzipple/modules/operations/application/read_models/tool_source_provider_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_source_sections.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
```

结果：ruff passed；compileall passed；Tool Source focused 回归 `2 passed`；Tool read-model/UI scoped 回归 `8 passed, 22 deselected`。`operations/application/read_models/tool_source_sections.py` 从 630 行聚合文件退役并删除；owner-safe Tool Source/Function/Provider Backend 读取迁入 `tool_source_queries.py`，Source/Function catalog section 迁入 `tool_source_catalog_sections.py`，Provider Backend health projection 迁入 `tool_source_provider_sections.py`，共享 record/column helpers 迁入 `tool_source_common.py`，调用方直接 import focused modules。

- [x] Operations Tool Source catalog row 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool_source_catalog_sections.py src/crxzipple/modules/operations/application/read_models/tool_source_catalog_rows.py src/crxzipple/modules/operations/application/read_models/tool_page_tabs.py src/crxzipple/modules/operations/application/read_models/tool_page_builder.py tests/unit/test_operations_tool_source_sections.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool_source_catalog_sections.py src/crxzipple/modules/operations/application/read_models/tool_source_catalog_rows.py src/crxzipple/modules/operations/application/read_models/tool_page_tabs.py src/crxzipple/modules/operations/application/read_models/tool_page_builder.py tests/unit/test_operations_tool_source_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_source_sections.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_metrics.py tests/unit/test_operations_tool_provider_sections.py tests/unit/test_operations_tool_scheduling_sections.py --tb=short
```

结果：ruff passed；compileall passed；Tool Source focused 回归 `2 passed`；Tool read-model/UI scoped 回归 `8 passed, 22 deselected`；Tool metrics/provider/scheduling 回归 `7 passed`。`operations/application/read_models/tool_source_catalog_sections.py` 从 317 行收口到 115 行，只保留 Source Health、Discovery Failures、Function Catalog Risks、CLI Process Health section assembly；source row projection、source tab tone、endpoint/runtime labels、discovery failure rows、function catalog risk rows 和 health tone 迁入 `tool_source_catalog_rows.py`（255 行）。

- [x] Operations Tool Run detail helper 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool_run_details.py src/crxzipple/modules/operations/application/read_models/tool_run_detail_payloads.py src/crxzipple/modules/operations/application/read_models/tool_run_assignment_details.py src/crxzipple/modules/operations/application/read_models/tool_run_browser_details.py src/crxzipple/modules/operations/application/read_models/tool_run_tables.py src/crxzipple/modules/operations/application/read_models/tool_worker_details.py tests/unit/test_operations_tool_run_details.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool_run_details.py src/crxzipple/modules/operations/application/read_models/tool_run_detail_payloads.py src/crxzipple/modules/operations/application/read_models/tool_run_assignment_details.py src/crxzipple/modules/operations/application/read_models/tool_run_browser_details.py src/crxzipple/modules/operations/application/read_models/tool_run_tables.py src/crxzipple/modules/operations/application/read_models/tool_worker_details.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_run_details.py tests/unit/test_operations_tool_run_tables.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
```

结果：ruff passed；compileall passed；Tool Run detail/table/read-model/UI scoped 回归 `15 passed, 22 deselected`。`operations/application/read_models/tool_run_details.py` 从 617 行收口到 400 行；assignment history section 迁入 `tool_run_assignment_details.py`，invocation context/detail payload sanitizing 迁入 `tool_run_detail_payloads.py`，Browser run/profile display helpers 迁入 `tool_run_browser_details.py`。调用方直接 import focused modules，不保留从 `tool_run_details.py` 转发的兼容出口。

- [x] Operations Tool scheduling label helper 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool_scheduling_rows.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_labels.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_queue_sections.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_capability_sections.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_blocker_sections.py tests/unit/test_operations_tool_scheduling_sections.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool_scheduling_rows.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_labels.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_queue_sections.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_capability_sections.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_blocker_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_scheduling_sections.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
```

结果：ruff passed；compileall passed；Tool scheduling/read-model/UI scoped 回归 `10 passed, 22 deselected`。`operations/application/read_models/tool_scheduling_rows.py` 从 604 行收口到 375 行；source/trace/lease/queue/priority/column label helper 迁入 `tool_scheduling_labels.py`，section assembly 直接 import label module，row-projection module 不再作为通用标签出口。

- [x] Operations Tool scheduling blocker projection 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool_scheduling_rows.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_blockers.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_queue_sections.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_capability_sections.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_blocker_sections.py tests/unit/test_operations_tool_scheduling_sections.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool_scheduling_rows.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_blockers.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_queue_sections.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_capability_sections.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_blocker_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_scheduling_sections.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_metrics.py tests/unit/test_operations_tool_provider_sections.py --tb=short
```

结果：ruff passed；compileall passed；Tool scheduling/read-model/UI scoped 回归 `10 passed, 22 deselected`；Tool metrics/provider 回归 `5 passed`。`operations/application/read_models/tool_scheduling_rows.py` 从 375 行继续收口到 155 行；blocker row/reason/blocked-by/next-step/tone projection 迁入 `tool_scheduling_blockers.py`，等待队列 row 和 capability limit row 留在 row-projection module。

- [x] Operations Tool scheduling section aggregate 退役回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_queue_sections.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_capability_sections.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_blocker_sections.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_rows.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_blockers.py tests/unit/test_operations_tool_scheduling_sections.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_queue_sections.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_capability_sections.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_blocker_sections.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_rows.py src/crxzipple/modules/operations/application/read_models/tool_scheduling_blockers.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_scheduling_sections.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_metrics.py tests/unit/test_operations_tool_provider_sections.py --tb=short
```

结果：ruff passed；compileall passed；Tool scheduling/read-model/UI scoped 回归 `10 passed, 22 deselected`；Tool metrics/provider 回归 `5 passed`。`operations/application/read_models/tool_scheduling_sections.py` 已删除；queue summary/run/waiting-IO section 迁入 `tool_scheduling_queue_sections.py`，capability-limit section 迁入 `tool_scheduling_capability_sections.py`，run blocker diagnostic section 迁入 `tool_scheduling_blocker_sections.py`，调用方直接 import focused section modules。

- [x] Operations Tool runtime metric 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool_metrics.py src/crxzipple/modules/operations/application/read_models/tool_runtime_metrics.py tests/unit/test_operations_tool_metrics.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool_metrics.py src/crxzipple/modules/operations/application/read_models/tool_runtime_metrics.py tests/unit/test_operations_tool_metrics.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_metrics.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
```

结果：ruff passed；compileall passed；Tool metrics/read-model/UI scoped 回归 `10 passed, 22 deselected`。`operations/application/read_models/tool_metrics.py` 从 323 行收口到 209 行；runtime bootstrap policy metric card projection 和 runtime config parsing helper 迁入 `tool_runtime_metrics.py`（133 行）。

- [x] Operations Orchestration page DTO / port surface 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/orchestration.py src/crxzipple/modules/operations/application/read_models/orchestration_models.py src/crxzipple/modules/operations/application/read_models/orchestration_ports.py src/crxzipple/modules/operations/application/read_models/facade.py src/crxzipple/modules/operations/application/read_models/__init__.py src/crxzipple/modules/operations/interfaces/http_models_orchestration_pages.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/orchestration.py src/crxzipple/modules/operations/application/read_models/orchestration_models.py src/crxzipple/modules/operations/application/read_models/orchestration_ports.py src/crxzipple/modules/operations/application/read_models/facade.py src/crxzipple/modules/operations/application/read_models/__init__.py src/crxzipple/modules/operations/interfaces/http_models_orchestration_pages.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_orchestration_http.py tests/unit/test_operations_orchestration_overview_rows.py tests/unit/test_operations_observation.py -k orchestration --tb=short
```

结果：ruff passed；compileall passed；Orchestration/UI/observation scoped 回归 `13 passed, 43 deselected`。`operations/application/read_models/orchestration.py` 从 573 行收口到 512 行；`OrchestrationOperationsPage` 迁入 `orchestration_models.py`，Orchestration ingress/continuation/dispatch query ports 迁入 `orchestration_ports.py`，Operations observation port 复用通用 `ports.py`，主 provider 文件只保留 overview/page 装配。

- [x] Operations observation model / event projection 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/observation.py src/crxzipple/modules/operations/application/observation_models.py src/crxzipple/modules/operations/application/observation_event_projection.py src/crxzipple/modules/operations/application/observation_payloads.py src/crxzipple/modules/operations/application/__init__.py src/crxzipple/modules/operations/infrastructure/observation_store.py src/crxzipple/modules/operations/infrastructure/persistence/observation_repository.py src/crxzipple/modules/operations/infrastructure/persistence/projection_repository.py tests/unit/test_operations_observation.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/observation.py src/crxzipple/modules/operations/application/observation_models.py src/crxzipple/modules/operations/application/observation_event_projection.py src/crxzipple/modules/operations/application/observation_payloads.py src/crxzipple/modules/operations/application/__init__.py src/crxzipple/modules/operations/infrastructure/observation_store.py src/crxzipple/modules/operations/infrastructure/persistence/observation_repository.py src/crxzipple/modules/operations/infrastructure/persistence/projection_repository.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py --tb=short
```

结果：ruff passed；compileall passed；Operations observation/projection/runtime scoped 回归 `49 passed`。`operations/application/observation.py` 从 571 行收口到 82 行；observation DTO / payload round-trip 迁入 `observation_models.py`，event topic record -> `OperationsObservedEvent` 映射迁入 `observation_event_projection.py`，payload sanitizing / datetime / numeric helper 迁入 `observation_payloads.py`。内部 DTO 调用面改为直接依赖 `observation_models.py`，`observation.py` 只保留 store port 与 `OperationsEventObserver` 入口。

- [x] Operations Events overview chart / owner section 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/events.py src/crxzipple/modules/operations/application/read_models/events_overview_sections.py src/crxzipple/modules/operations/application/read_models/events_overview_charts.py src/crxzipple/modules/operations/application/read_models/events_owner_sections.py src/crxzipple/modules/operations/application/read_models/events_overview_helpers.py tests/unit/test_operations_observation.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/events.py src/crxzipple/modules/operations/application/read_models/events_overview_sections.py src/crxzipple/modules/operations/application/read_models/events_overview_charts.py src/crxzipple/modules/operations/application/read_models/events_owner_sections.py src/crxzipple/modules/operations/application/read_models/events_overview_helpers.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k events --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k events --tb=short
```

结果：ruff passed；compileall passed；Events observation scoped 回归 `19 passed, 30 deselected`；UI Operations Events scoped 回归 `6 passed, 20 deselected`。`operations/application/read_models/events_overview_sections.py` 从 549 行收口到 275 行；events overview chart projection 迁入 `events_overview_charts.py`，owner volume table section 迁入 `events_owner_sections.py`，overview health/status/tone/display helper 迁入 `events_overview_helpers.py`。`events.py` 直接 import focused modules，不通过 overview section 做转发出口。

- [x] Operations Events overview/page builder 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/events.py src/crxzipple/modules/operations/application/read_models/events_overview_builder.py src/crxzipple/modules/operations/application/read_models/events_page_builder.py tests/unit/test_operations_observation.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/events.py src/crxzipple/modules/operations/application/read_models/events_overview_builder.py src/crxzipple/modules/operations/application/read_models/events_page_builder.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k events --tb=short
PYTHONPATH=src pytest -q tests/unit/test_events.py tests/unit/test_events_http.py --tb=short
```

结果：ruff passed；compileall passed；Events observation scoped 回归 `19 passed, 30 deselected`；Events owner/http 回归 `42 passed`。`operations/application/read_models/events.py` 从 382 行收口到 56 行；overview projection 迁入 `events_overview_builder.py`（51 行），page assembly 迁入 `events_page_builder.py`。`tests/unit/test_operations_observation.py` 的内部 health 规则测试改为直接导入新的 owner 文件，不在 facade 上保留兼容 re-export。

- [x] Operations Events observer/subscription section aggregate 退役回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/events_page_builder.py src/crxzipple/modules/operations/application/read_models/events_observer_common.py src/crxzipple/modules/operations/application/read_models/events_subscription_sections.py src/crxzipple/modules/operations/application/read_models/events_observer_runtime_sections.py src/crxzipple/modules/operations/application/read_models/events_observer_coverage_sections.py tests/unit/test_operations_observation.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/events_page_builder.py src/crxzipple/modules/operations/application/read_models/events_observer_common.py src/crxzipple/modules/operations/application/read_models/events_subscription_sections.py src/crxzipple/modules/operations/application/read_models/events_observer_runtime_sections.py src/crxzipple/modules/operations/application/read_models/events_observer_coverage_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k events --tb=short
PYTHONPATH=src pytest -q tests/unit/test_events.py tests/unit/test_events_http.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k events --tb=short
```

结果：ruff passed；compileall passed；Events observation scoped 回归 `19 passed, 30 deselected`；Events owner/http 回归 `42 passed`；UI Operations Events scoped 回归 `6 passed, 20 deselected`。旧 `events_observer_sections.py` 已退役，不保留转发层；公共 display/sort helper 迁入 `events_observer_common.py`（76 行），consumer/subscription tables 迁入 `events_subscription_sections.py`（108 行），observer runtime/lag tables 迁入 `events_observer_runtime_sections.py`（168 行），observer coverage table 迁入 `events_observer_coverage_sections.py`（58 行）。`events_page_builder.py` 直接依赖 focused section modules。

- [x] Operations Events page facts 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/events_page_builder.py src/crxzipple/modules/operations/application/read_models/events_page_facts.py tests/unit/test_operations_observation.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/events_page_builder.py src/crxzipple/modules/operations/application/read_models/events_page_facts.py tests/unit/test_operations_observation.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k events --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k events --tb=short
```

结果：ruff passed；compileall passed；UI Operations Events scoped 回归 `6 passed, 20 deselected`；Operations observation Events scoped 回归 `19 passed, 30 deselected`。`events_page_builder.py` 从 346 行收口到 167 行，只保留 Events page DTO assembly；topic/contract/definition reads、subscription/observer state collection、recent-event selection、health calculation 和 derived page facts 迁入 `events_page_facts.py`（275 行）。`tests/unit/test_operations_observation.py` 的 Events health helper 测试已改为导入 facts owner，不在 builder 上保留私有转发。

- [x] Operations Events contract matching 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/events_contract_sections.py src/crxzipple/modules/operations/application/read_models/events_contract_matching.py src/crxzipple/modules/operations/application/read_models/events_recent_state.py src/crxzipple/modules/operations/application/read_models/events_subscription_state.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/events_contract_sections.py src/crxzipple/modules/operations/application/read_models/events_contract_matching.py src/crxzipple/modules/operations/application/read_models/events_recent_state.py src/crxzipple/modules/operations/application/read_models/events_subscription_state.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k events --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k events --tb=short
PYTHONPATH=src pytest -q tests/unit/test_events.py tests/unit/test_events_http.py --tb=short
```

结果：ruff passed；compileall passed；UI Operations Events scoped 回归 `6 passed, 20 deselected`；Operations observation Events scoped 回归 `19 passed, 30 deselected`；Events owner/http 回归 `42 passed`。`operations/application/read_models/events_contract_sections.py` 从 321 行收口到 221 行，只保留 topic/contract/route table assembly；topic/route contract matching、contract labels/statuses 和 contract payload extraction 迁入 `events_contract_matching.py`（129 行）。

- [x] Operations Tool lifecycle event source / row 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool_lifecycle_events.py src/crxzipple/modules/operations/application/read_models/tool_lifecycle_event_sources.py src/crxzipple/modules/operations/application/read_models/tool_lifecycle_event_rows.py src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/tool_run_details.py src/crxzipple/modules/operations/application/read_models/tool_worker_details.py tests/unit/test_operations_tool_lifecycle_events.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool_lifecycle_events.py src/crxzipple/modules/operations/application/read_models/tool_lifecycle_event_sources.py src/crxzipple/modules/operations/application/read_models/tool_lifecycle_event_rows.py src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/tool_run_details.py src/crxzipple/modules/operations/application/read_models/tool_worker_details.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_lifecycle_events.py tests/unit/test_operations_tool_run_details.py tests/unit/test_operations_tool_worker_details.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
```

结果：ruff passed；compileall passed；Tool lifecycle/run-detail/worker-detail/read-model/UI scoped 回归 `15 passed, 22 deselected`。`operations/application/read_models/tool_lifecycle_events.py` 从 541 行收口到 62 行；recent tool event bus/observation 聚合与 dedupe 迁入 `tool_lifecycle_event_sources.py`，Tool run / worker / lifecycle row projection 迁入 `tool_lifecycle_event_rows.py`。`tool.py`、run detail、worker detail 直接 import focused modules，不通过 lifecycle page section 文件转发。

- [x] Operations Tool Run table fact / row 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool_run_tables.py src/crxzipple/modules/operations/application/read_models/tool_run_table_facts.py src/crxzipple/modules/operations/application/read_models/tool_run_table_rows.py src/crxzipple/modules/operations/application/read_models/tool_page_helpers.py tests/unit/test_operations_tool_run_tables.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool_run_tables.py src/crxzipple/modules/operations/application/read_models/tool_run_table_facts.py src/crxzipple/modules/operations/application/read_models/tool_run_table_rows.py src/crxzipple/modules/operations/application/read_models/tool_page_helpers.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_run_tables.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
```

结果：ruff passed；compileall passed；Tool run table/read-model/UI scoped 回归 `11 passed, 22 deselected`。`operations/application/read_models/tool_run_tables.py` 从 533 行收口到 95 行；Tool Run fact/source/trace/progress projection 迁入 `tool_run_table_facts.py`，row/status/action/column projection 迁入 `tool_run_table_rows.py`，section 文件只保留 Recent/Active Tool Runs table assembly。

- [x] Operations Tool overview aggregate section 退役回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/tool_overview_actions.py src/crxzipple/modules/operations/application/read_models/tool_overview_risk.py src/crxzipple/modules/operations/application/read_models/tool_overview_rows.py src/crxzipple/modules/operations/application/read_models/tool_overview_type_sections.py src/crxzipple/modules/operations/application/read_models/tool_overview_execution_sections.py tests/unit/test_operations_tool_overview_sections.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/tool_overview_actions.py src/crxzipple/modules/operations/application/read_models/tool_overview_risk.py src/crxzipple/modules/operations/application/read_models/tool_overview_rows.py src/crxzipple/modules/operations/application/read_models/tool_overview_type_sections.py src/crxzipple/modules/operations/application/read_models/tool_overview_execution_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_overview_sections.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
```

结果：ruff passed；compileall passed；Tool overview/read-model/UI scoped 回归 `11 passed, 22 deselected`。`operations/application/read_models/tool_overview_sections.py` 从 526 行聚合文件退役并删除；runtime action 定义迁入 `tool_overview_actions.py`，risk 判定迁入 `tool_overview_risk.py`，queue/risk/worker rows 迁入 `tool_overview_rows.py`，Tool type chart projection 迁入 `tool_overview_type_sections.py`，Inline risk 与 strategy mix sections 迁入 `tool_overview_execution_sections.py`。调用方直接 import focused modules，不保留聚合转发出口。

- [x] Operations Channels common helper 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/channels.py src/crxzipple/modules/operations/application/read_models/channels_common.py src/crxzipple/modules/operations/application/read_models/channels_event_helpers.py src/crxzipple/modules/operations/application/read_models/channels_safe_access.py src/crxzipple/modules/operations/application/read_models/channels_sections.py src/crxzipple/modules/operations/application/read_models/channels_events.py src/crxzipple/modules/operations/application/read_models/channels_health.py src/crxzipple/modules/operations/application/read_models/channels_details.py src/crxzipple/modules/operations/application/read_models/channels_tables.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/channels.py src/crxzipple/modules/operations/application/read_models/channels_common.py src/crxzipple/modules/operations/application/read_models/channels_event_helpers.py src/crxzipple/modules/operations/application/read_models/channels_safe_access.py src/crxzipple/modules/operations/application/read_models/channels_sections.py src/crxzipple/modules/operations/application/read_models/channels_events.py src/crxzipple/modules/operations/application/read_models/channels_health.py src/crxzipple/modules/operations/application/read_models/channels_details.py src/crxzipple/modules/operations/application/read_models/channels_tables.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k channels --tb=short
PYTHONPATH=src pytest -q tests/unit/test_channels_http.py::ChannelsHttpTestCase::test_web_channel_events_endpoint_streams_live_events --tb=short
```

结果：ruff passed；compileall passed；UI Operations Channels scoped 回归 `2 passed, 24 deselected`；Channels SSE live-event 单测 `1 passed`。`operations/application/read_models/channels_common.py` 从 521 行收口到 181 行；safe owner/event 调用迁入 `channels_safe_access.py`，event routing/topic parsing/trace route/search/dedupe 迁入 `channels_event_helpers.py`，table/key-value/capability builders 迁入 `channels_sections.py`，`channels_common.py` 只保留 runtime、interaction、payload helper。

- [x] Operations observer runtime 聚合文件退役回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/observer_event_names.py src/crxzipple/modules/operations/application/observer_runtime_service.py src/crxzipple/modules/operations/application/observer_subscriptions.py src/crxzipple/modules/operations/application/__init__.py src/crxzipple/app/assembly/event_runtime.py tests/unit/test_operations_observation.py tests/unit/test_events.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/observer_event_names.py src/crxzipple/modules/operations/application/observer_runtime_service.py src/crxzipple/modules/operations/application/observer_subscriptions.py src/crxzipple/modules/operations/application/__init__.py src/crxzipple/app/assembly/event_runtime.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_events.py::EventsModuleTestCase::test_event_definition_registry_covers_operations_observer_subscriptions --tb=short
PYTHONPATH=src pytest -q tests/unit/test_orchestration_queue.py::OrchestrationQueueTestCase::test_orchestration_runtime_services_split_scheduler_and_operations_observer --tb=short
```

结果：ruff passed；compileall passed；Operations observation 回归 `49 passed`；Event registry observer subscription 覆盖 `1 passed`；scheduler/operations observer runtime 分离回归 `1 passed`。`operations/application/runtime.py` 从 517 行聚合文件退役并删除；observer event-name catalog 迁入 `observer_event_names.py`，subscription callback contracts/records 迁入 `observer_subscriptions.py`，durable event pump 迁入 `observer_runtime_service.py`。调用方直接 import focused modules，不保留旧 runtime 聚合出口。

- [x] Operations Orchestration execution-chain section 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/orchestration_execution_chain_sections.py src/crxzipple/modules/operations/application/read_models/orchestration_execution_chain_queries.py src/crxzipple/modules/operations/application/read_models/orchestration_execution_chain_diagnostics.py src/crxzipple/modules/operations/application/read_models/orchestration_execution_chain_rows.py tests/unit/test_operations_orchestration_execution_chain_sections.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/orchestration_execution_chain_sections.py src/crxzipple/modules/operations/application/read_models/orchestration_execution_chain_queries.py src/crxzipple/modules/operations/application/read_models/orchestration_execution_chain_diagnostics.py src/crxzipple/modules/operations/application/read_models/orchestration_execution_chain_rows.py
PYTHONPATH=src pytest -q tests/unit/test_operations_orchestration_execution_chain_sections.py tests/unit/test_ui_operations_orchestration_http.py tests/unit/test_operations_observation.py -k orchestration --tb=short
```

结果：ruff passed；compileall passed；Operations Orchestration execution-chain/UI/observation scoped 回归 `10 passed, 43 deselected`。`operations/application/read_models/orchestration_execution_chain_sections.py` 从 512 行收口到 80 行；candidate run/query safety 迁入 `orchestration_execution_chain_queries.py`，continuation/tool-only 诊断迁入 `orchestration_execution_chain_diagnostics.py`，row/cell/status/route 投影迁入 `orchestration_execution_chain_rows.py`。section 文件现在只保留表定义和 section 组装。

- [x] Operations Orchestration summary projection 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/orchestration.py src/crxzipple/modules/operations/application/read_models/orchestration_summary_sections.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/orchestration.py src/crxzipple/modules/operations/application/read_models/orchestration_summary_sections.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_orchestration_http.py tests/unit/test_operations_observation.py -k orchestration --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_orchestration_overview_rows.py tests/unit/test_operations_orchestration_execution_chain_sections.py --tb=short
```

结果：ruff passed；compileall passed；Orchestration/UI/observation scoped 回归 `9 passed, 43 deselected`；overview/execution-chain focused 回归 `5 passed`。`operations/application/read_models/orchestration.py` 从 512 行继续收口到 393 行；overview/page metric-card construction 和 page tab projection 迁入 `orchestration_summary_sections.py`，主 provider 进一步收敛为 owner fact read、section assembly 和 projection diagnostics。

- [x] Operations Orchestration overview/page builder 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/orchestration.py src/crxzipple/modules/operations/application/read_models/orchestration_overview_builder.py src/crxzipple/modules/operations/application/read_models/orchestration_page_builder.py tests/unit/test_operations_observation.py tests/unit/test_ui_operations_orchestration_http.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/orchestration.py src/crxzipple/modules/operations/application/read_models/orchestration_overview_builder.py src/crxzipple/modules/operations/application/read_models/orchestration_page_builder.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py tests/unit/test_ui_operations_orchestration_http.py -k orchestration --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_orchestration_execution_chain_sections.py tests/unit/test_operations_orchestration_overview_rows.py tests/unit/test_operations_orchestration_projection_diagnostics.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_orchestration_queue_sections.py tests/unit/test_operations_orchestration_worker_sections.py tests/unit/test_operations_orchestration_event_log_sections.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_orchestration_backpressure_sections.py tests/unit/test_operations_orchestration_ingress_sections.py --tb=short
```

结果：ruff passed；compileall passed；Orchestration/UI/observation scoped 回归 `9 passed, 43 deselected`；execution-chain/overview/diagnostics 回归 `6 passed`；queue/worker/event-log 回归 `5 passed`；backpressure/ingress 回归 `4 passed`。`operations/application/read_models/orchestration.py` 从 393 行收口到 63 行；overview fact reads 和 metric/queue/lane/executor assembly 迁入 `orchestration_overview_builder.py`（131 行），page fact reads 和 page DTO assembly 迁入 `orchestration_page_builder.py`（298 行）。

- [x] Operations Orchestration page facts 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/orchestration_page_builder.py src/crxzipple/modules/operations/application/read_models/orchestration_page_facts.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/orchestration_page_builder.py src/crxzipple/modules/operations/application/read_models/orchestration_page_facts.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_orchestration_http.py tests/unit/test_operations_observation.py -k orchestration --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_orchestration_execution_chain_sections.py tests/unit/test_operations_orchestration_projection_diagnostics.py tests/unit/test_ui_http.py::UiHttpTestCase::test_operations_page_responses_expose_projection_freshness --tb=short
```

结果：ruff passed；compileall passed；Orchestration/UI/observation scoped 回归 `9 passed, 43 deselected`；execution-chain/diagnostics/freshness 回归 `3 passed`。`operations/application/read_models/orchestration_page_builder.py` 从 300 行收口到 213 行，只保留 page DTO/section assembly；owner fact reads、run/lease/dispatch/observer 派生集合、health/capacity/count 计算迁入 `orchestration_page_facts.py`（182 行）。

- [x] Operations Tool tab projection 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/tool_page_tabs.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/tool_page_tabs.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
```

结果：ruff passed；compileall passed；Tool read-model/UI scoped 回归 `8 passed, 22 deselected`。`operations/application/read_models/tool.py` 从 504 行收口到 473 行；Tool page tab projection 迁入 `tool_page_tabs.py`，provider facade 不再内联 tab DTO 列表。

- [x] Operations Tool page builder 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/tool_page_builder.py tests/unit/test_operations_tool_read_model.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/tool_page_builder.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_scheduling_sections.py tests/unit/test_operations_tool_metrics.py tests/unit/test_operations_tool_provider_sections.py --tb=short
```

结果：ruff passed；compileall passed；Tool read-model/UI scoped 回归 `8 passed, 22 deselected`；Tool scheduling/metrics/provider 回归 `7 passed`。`operations/application/read_models/tool.py` 从 477 行收口到 59 行；Tool overview/page owner fact collection、section assembly、metrics/tabs/diagnostics 组装迁入 `tool_page_builder.py`，`ToolOperationsReadModelProvider` 只保留 dependency wiring 和 `overview/page` delegation。

- [x] Operations Tool page fact collection 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/tool_page_builder.py src/crxzipple/modules/operations/application/read_models/tool_page_facts.py tests/unit/test_operations_tool_read_model.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/tool_page_builder.py src/crxzipple/modules/operations/application/read_models/tool_page_facts.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_scheduling_sections.py tests/unit/test_operations_tool_metrics.py tests/unit/test_operations_tool_provider_sections.py --tb=short
```

结果：ruff passed；compileall passed；Tool read-model/UI scoped 回归 `8 passed, 22 deselected`；Tool scheduling/metrics/provider 回归 `7 passed`。`operations/application/read_models/tool_page_builder.py` 从 475 行收口到 377 行；Tool page owner fact reads、provider backend/source reads、derived active/waiting/failed/detail/filter sets、artifact/event counts、provider history、health 迁入 `tool_page_facts.py`。这是后续 Tool overview/page/fact 三层拆分前的中间状态。

- [x] Operations Tool overview/page/fact collection 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/tool_overview_builder.py src/crxzipple/modules/operations/application/read_models/tool_page_builder.py src/crxzipple/modules/operations/application/read_models/tool_page_facts.py tests/unit/test_operations_tool_read_model.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool.py src/crxzipple/modules/operations/application/read_models/tool_overview_builder.py src/crxzipple/modules/operations/application/read_models/tool_page_builder.py src/crxzipple/modules/operations/application/read_models/tool_page_facts.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_scheduling_sections.py tests/unit/test_operations_tool_metrics.py tests/unit/test_operations_tool_provider_sections.py --tb=short
```

结果：ruff passed；compileall passed；Tool read-model/UI scoped 回归 `8 passed, 22 deselected`；Tool scheduling/metrics/provider 回归 `7 passed`。`operations/application/read_models/tool.py` 从 59 行调整为 61 行；Tool overview fact reads 和 metric/queue/risk/worker assembly 迁入 `tool_overview_builder.py`，Tool page DTO assembly 保留在 `tool_page_builder.py`（316 行），Tool page owner-fact reads 和 derived run sets 保留在 `tool_page_facts.py`。

- [x] Operations Tool page section wiring 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool_page_builder.py src/crxzipple/modules/operations/application/read_models/tool_page_sections.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool_page_builder.py src/crxzipple/modules/operations/application/read_models/tool_page_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_source_sections.py tests/unit/test_operations_tool_metrics.py tests/unit/test_operations_tool_provider_sections.py tests/unit/test_operations_tool_scheduling_sections.py --tb=short
```

结果：ruff passed；compileall passed；Tool read-model/UI scoped 回归 `8 passed, 22 deselected`；Tool source/metrics/provider/scheduling 回归 `9 passed`。`operations/application/read_models/tool_page_builder.py` 从 316 行收口到 128 行，只保留 Tool page shell、metadata、metrics/tabs/actions 和 projection diagnostics；active run、queue、source/catalog、provider、readiness、worker、risk、artifact、lifecycle 和 detail section wiring 迁入 `tool_page_sections.py`（223 行）。

- [x] Operations LLM overview/page/fact collection 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/llm.py src/crxzipple/modules/operations/application/read_models/llm_overview_builder.py src/crxzipple/modules/operations/application/read_models/llm_page_builder.py src/crxzipple/modules/operations/application/read_models/llm_page_facts.py tests/unit/test_operations_llm_read_model.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/llm.py src/crxzipple/modules/operations/application/read_models/llm_overview_builder.py src/crxzipple/modules/operations/application/read_models/llm_page_builder.py src/crxzipple/modules/operations/application/read_models/llm_page_facts.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_read_model.py tests/unit/test_ui_operations_http.py -k llm --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_invocation_tables.py tests/unit/test_operations_llm_provider_sections.py tests/unit/test_operations_llm_lifecycle_events.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_detail_tables.py tests/unit/test_operations_llm_response_events.py tests/unit/test_operations_llm_error_sections.py --tb=short
```

结果：ruff passed；compileall passed；LLM read-model/UI scoped 回归 `4 passed, 23 deselected`；LLM invocation/provider/lifecycle 回归 `9 passed`；LLM detail/response/error 回归 `9 passed`。`operations/application/read_models/llm.py` 从 464 行收口到 56 行；LLM overview fact reads 和 metric/queue/executor assembly 迁入 `llm_overview_builder.py`，LLM page DTO assembly 迁入 `llm_page_builder.py`（279 行），owner-fact reads、observed/resolver/response event grouping、runtime snapshot、active/failed/streaming/detail/filter invocation sets、profile lookup 和 health/retention facts 迁入 `llm_page_facts.py`。

- [x] Operations Tool readiness risk projection 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool_readiness_sections.py src/crxzipple/modules/operations/application/read_models/tool_readiness_risk.py src/crxzipple/modules/operations/application/read_models/tool.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool_readiness_sections.py src/crxzipple/modules/operations/application/read_models/tool_readiness_risk.py src/crxzipple/modules/operations/application/read_models/tool.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_readiness_sections.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_metrics.py tests/unit/test_operations_tool_scheduling_sections.py tests/unit/test_operations_tool_provider_sections.py --tb=short
```

结果：ruff passed；compileall passed；Tool readiness/read-model/UI scoped 回归 `11 passed, 22 deselected`；Tool metrics/scheduling/provider 回归 `7 passed`。`operations/application/read_models/tool_readiness_sections.py` 从 452 行收口到 172 行；access/runtime readiness risk payload normalization 迁入 `tool_readiness_risk.py`，section 文件只保留 risk table row/section projection。

- [x] Operations Tool worker projection 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool_worker_sections.py src/crxzipple/modules/operations/application/read_models/tool_worker_projection.py src/crxzipple/modules/operations/application/read_models/tool_worker_details.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool_worker_sections.py src/crxzipple/modules/operations/application/read_models/tool_worker_projection.py src/crxzipple/modules/operations/application/read_models/tool_worker_details.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_worker_sections.py tests/unit/test_operations_tool_worker_details.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
```

结果：ruff passed；compileall passed；Tool worker/list/detail/read-model/UI scoped 回归 `11 passed, 22 deselected`。`operations/application/read_models/tool_worker_sections.py` 从 446 行收口到 229 行；worker registration status、runtime/provider/capability summaries、fallback run labels、success-rate 和 average-duration projection 迁入 `tool_worker_projection.py`，worker list 和 worker detail 共用同一套 worker projection 规则。

- [x] Operations Channels table row projection 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/channels_tables.py src/crxzipple/modules/operations/application/read_models/channels_table_rows.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/channels_tables.py src/crxzipple/modules/operations/application/read_models/channels_table_rows.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k channels --tb=short
PYTHONPATH=src pytest -q tests/unit/test_channels_http.py::ChannelsHttpTestCase::test_web_channel_events_endpoint_streams_live_events --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k channels --tb=short
```

结果：ruff passed；compileall passed；UI Operations Channels scoped 回归 `2 passed, 24 deselected`；Channels SSE live-event 单测 `1 passed`；Operations observation Channels scoped 命令没有匹配用例，返回 `49 deselected`。`operations/application/read_models/channels_tables.py` 从 437 行收口到 238 行；message/dead-letter/interaction/binding/profile/event/contract row projection 迁入 `channels_table_rows.py`，table 文件只保留 columns、totals、empty states 和 section id assembly。

- [x] Operations Orchestration status projection 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/orchestration_status_sections.py src/crxzipple/modules/operations/application/read_models/orchestration_status_projection.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/orchestration_status_sections.py src/crxzipple/modules/operations/application/read_models/orchestration_status_projection.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_orchestration_http.py tests/unit/test_operations_observation.py -k orchestration --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_orchestration_overview_rows.py tests/unit/test_operations_orchestration_execution_chain_sections.py --tb=short
```

结果：ruff passed；compileall passed；Orchestration UI/observation scoped 回归 `9 passed, 43 deselected`；overview/execution-chain focused 回归 `5 passed`。`operations/application/read_models/orchestration_status_sections.py` 从 420 行收口到 260 行；scheduler/policy status runtime-value parsing、duration/age/percentile/percentage labels、dispatch-task breakdown 和 observer-state labels 迁入 `orchestration_status_projection.py`。

- [x] Operations LLM provider request label 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/llm_provider_request_diagnostics.py src/crxzipple/modules/operations/application/read_models/llm_provider_request_labels.py src/crxzipple/modules/operations/application/read_models/llm_invocation_details.py src/crxzipple/modules/operations/application/read_models/llm_error_sections.py tests/unit/test_operations_llm_provider_request_diagnostics.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/llm_provider_request_diagnostics.py src/crxzipple/modules/operations/application/read_models/llm_provider_request_labels.py src/crxzipple/modules/operations/application/read_models/llm_invocation_details.py src/crxzipple/modules/operations/application/read_models/llm_error_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_provider_request_diagnostics.py tests/unit/test_operations_llm_error_sections.py tests/unit/test_operations_llm_read_model.py tests/unit/test_ui_operations_http.py -k llm --tb=short
```

结果：ruff passed；compileall passed；LLM provider request/error/read-model/UI scoped 回归 `9 passed, 23 deselected`。`operations/application/read_models/llm_provider_request_diagnostics.py` 从 406 行收口到 243 行；provider continuation/transport/renderer/render-report/tool mapping/input-delta/options labels 迁入 `llm_provider_request_labels.py`。

- [x] Operations LLM provider readiness 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/llm.py src/crxzipple/modules/operations/application/read_models/llm_provider_sections.py src/crxzipple/modules/operations/application/read_models/llm_provider_readiness.py tests/unit/test_operations_llm_provider_sections.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/llm.py src/crxzipple/modules/operations/application/read_models/llm_provider_sections.py src/crxzipple/modules/operations/application/read_models/llm_provider_readiness.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_provider_sections.py tests/unit/test_operations_llm_read_model.py tests/unit/test_ui_operations_http.py -k llm --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_provider_request_diagnostics.py tests/unit/test_operations_llm_error_sections.py tests/unit/test_operations_llm_detail_tables.py -k llm --tb=short
```

结果：ruff passed；compileall passed；LLM provider/read-model/UI scoped 回归
`7 passed, 23 deselected`；LLM provider request/error/detail scoped 回归
`7 passed`。`operations/application/read_models/llm_provider_sections.py` 从
381 行收口到 187 行；warmup event selection、warmup labels/actions、access
readiness、availability/credential/context/capability labels 和 latest-invocation
lookup 迁入 `llm_provider_readiness.py`。

- [x] Operations Tool Run detail summary 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool_run_details.py src/crxzipple/modules/operations/application/read_models/tool_run_detail_summary.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool_run_details.py src/crxzipple/modules/operations/application/read_models/tool_run_detail_summary.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_run_details.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
```

结果：ruff passed；compileall passed；Tool Run detail/read-model/UI scoped 回归 `12 passed, 22 deselected`。`operations/application/read_models/tool_run_details.py` 从 400 行收口到 153 行；Tool Run summary、assignment/lease labels、source/trace route projection、tool lookup/labels 和 status tone projection 迁入 `tool_run_detail_summary.py`。

- [x] Operations Tool Run artifact ref 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool_run_artifacts.py src/crxzipple/modules/operations/application/read_models/tool_run_artifact_refs.py src/crxzipple/modules/operations/application/read_models/tool_run_details.py src/crxzipple/modules/operations/application/read_models/tool_run_browser_details.py src/crxzipple/modules/operations/application/read_models/tool_run_table_facts.py src/crxzipple/modules/operations/application/read_models/tool_page_helpers.py tests/unit/test_operations_tool_run_artifacts.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool_run_artifacts.py src/crxzipple/modules/operations/application/read_models/tool_run_artifact_refs.py src/crxzipple/modules/operations/application/read_models/tool_run_details.py src/crxzipple/modules/operations/application/read_models/tool_run_browser_details.py src/crxzipple/modules/operations/application/read_models/tool_run_table_facts.py src/crxzipple/modules/operations/application/read_models/tool_page_helpers.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_run_artifacts.py tests/unit/test_operations_tool_run_details.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_run_tables.py tests/unit/test_operations_tool_run_contexts.py --tb=short
```

结果：ruff passed；compileall passed；Tool artifact/detail/read-model/UI scoped
回归 `14 passed, 22 deselected`；Tool run table/context 回归 `5 passed`。
`operations/application/read_models/tool_run_artifacts.py` 从 378 行收口到
141 行；result payload normalization、result summaries、artifact-ref extraction、
artifact-service enrichment、byte/dimension labels 和 optional value coercion 迁入
`tool_run_artifact_refs.py`。

- [x] Operations Tool Run table label 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool_run_table_facts.py src/crxzipple/modules/operations/application/read_models/tool_run_table_labels.py src/crxzipple/modules/operations/application/read_models/tool_page_helpers.py tests/unit/test_operations_tool_run_tables.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool_run_table_facts.py src/crxzipple/modules/operations/application/read_models/tool_run_table_labels.py src/crxzipple/modules/operations/application/read_models/tool_page_helpers.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_run_tables.py tests/unit/test_operations_tool_run_contexts.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_run_artifacts.py tests/unit/test_operations_tool_run_details.py --tb=short
```

结果：ruff passed；compileall passed；Tool table/read-model/UI scoped 回归
`13 passed, 22 deselected`；Tool artifact/detail 回归 `6 passed`。
`operations/application/read_models/tool_run_table_facts.py` 从 373 行收口到
132 行；source/trace/assignment/lease/progress/search labels 和
invocation-context metadata helpers 迁入 `tool_run_table_labels.py`。

- [x] Operations LLM invocation detail item 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/llm_provider_request_diagnostics.py src/crxzipple/modules/operations/application/read_models/llm_provider_request_labels.py src/crxzipple/modules/operations/application/read_models/llm_invocation_details.py src/crxzipple/modules/operations/application/read_models/llm_invocation_detail_items.py src/crxzipple/modules/operations/application/read_models/llm_error_sections.py tests/unit/test_operations_llm_provider_request_diagnostics.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/llm_provider_request_diagnostics.py src/crxzipple/modules/operations/application/read_models/llm_provider_request_labels.py src/crxzipple/modules/operations/application/read_models/llm_invocation_details.py src/crxzipple/modules/operations/application/read_models/llm_invocation_detail_items.py src/crxzipple/modules/operations/application/read_models/llm_error_sections.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_provider_request_diagnostics.py tests/unit/test_operations_llm_error_sections.py tests/unit/test_operations_llm_detail_tables.py tests/unit/test_operations_llm_read_model.py tests/unit/test_ui_operations_http.py -k llm --tb=short
```

结果：ruff passed；compileall passed；LLM provider request/error/detail-table/read-model/UI scoped 回归 `11 passed, 23 deselected`。`operations/application/read_models/llm_invocation_details.py` 从 399 行收口到 131 行；invocation summary items 和 request-context items 迁入 `llm_invocation_detail_items.py`，主文件只保留 detail model assembly。

- [x] Operations LLM detail table aggregate 退役回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/llm_response_item_tables.py src/crxzipple/modules/operations/application/read_models/llm_response_event_tables.py src/crxzipple/modules/operations/application/read_models/llm_policy_trace_tables.py src/crxzipple/modules/operations/application/read_models/llm_detail_payloads.py src/crxzipple/modules/operations/application/read_models/llm_invocation_details.py tests/unit/test_operations_llm_detail_tables.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/llm_response_item_tables.py src/crxzipple/modules/operations/application/read_models/llm_response_event_tables.py src/crxzipple/modules/operations/application/read_models/llm_policy_trace_tables.py src/crxzipple/modules/operations/application/read_models/llm_detail_payloads.py src/crxzipple/modules/operations/application/read_models/llm_invocation_details.py tests/unit/test_operations_llm_detail_tables.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_detail_tables.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_read_model.py tests/unit/test_ui_operations_http.py -k llm --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_response_events.py tests/unit/test_operations_llm_invocation_tables.py tests/unit/test_operations_llm_provider_request_diagnostics.py --tb=short
```

结果：ruff passed；compileall passed；LLM detail table regression `2 passed`；LLM read-model/UI scoped 回归 `4 passed, 23 deselected`；LLM response-event/provider-request regression `9 passed`。旧 `operations/application/read_models/llm_detail_tables.py` 已退役并删除；response item/runtime mapping tables 迁入 `llm_response_item_tables.py`（137 行），response/observed event tables 迁入 `llm_response_event_tables.py`（116 行），policy trace table 迁入 `llm_policy_trace_tables.py`（52 行），bounded JSON/table helper 迁入 `llm_detail_payloads.py`（62 行）。调用方直接 import focused modules，不保留聚合转发出口。

- [x] Operations projection materializer 路由 / payload helper 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/projections.py src/crxzipple/modules/operations/application/projection_modules.py src/crxzipple/modules/operations/application/projection_materializer_payloads.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/projections.py src/crxzipple/modules/operations/application/projection_modules.py src/crxzipple/modules/operations/application/projection_materializer_payloads.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py tests/unit/test_ui_operations_http.py -k operations --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_context_workspace_read_model.py tests/unit/test_operations_browser_read_model.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py tests/unit/test_events.py::EventsModuleTestCase::test_event_definition_registry_covers_operations_observer_subscriptions --tb=short
```

结果：ruff passed；compileall passed；Operations observation/UI projection 回归 `75 passed`；Context Workspace + Browser Operations projection 回归 `12 passed`；UI Operations + event registry 回归 `27 passed`。`operations/application/projections.py` 从 496 行收口到 179 行；模块路由迁入 `projection_modules.py`，page/table/detail JSON payload extraction 迁入 `projection_materializer_payloads.py`，materializer 文件只保留 write flow、projection freshness stamping、清理和 invalidation publish。

- [x] Operations projection payload / table filter 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/projection_payloads.py src/crxzipple/modules/operations/application/read_models/projection_detail_payloads.py src/crxzipple/modules/operations/application/read_models/projection_table_filters.py src/crxzipple/modules/operations/interfaces/http_projection_helpers.py src/crxzipple/modules/operations/interfaces/http_runtime.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/projection_payloads.py src/crxzipple/modules/operations/application/read_models/projection_detail_payloads.py src/crxzipple/modules/operations/application/read_models/projection_table_filters.py src/crxzipple/modules/operations/interfaces/http_projection_helpers.py src/crxzipple/modules/operations/interfaces/http_runtime.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py tests/unit/test_ui_http.py::UiHttpTestCase::test_operations_page_responses_expose_projection_freshness --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k operations --tb=short
```

结果：ruff passed；compileall passed；UI/projection HTTP 回归 `27 passed`；Operations observation scoped 回归 `49 passed`。`operations/application/read_models/projection_payloads.py` 从 342 行收口到 156 行；detail payload deferral 迁入 `projection_detail_payloads.py`，table/related projection filter rules 迁入 `projection_table_filters.py`。

- [x] Operations Channels chart projection 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/channels.py src/crxzipple/modules/operations/application/read_models/channels_health.py src/crxzipple/modules/operations/application/read_models/channels_charts.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/channels.py src/crxzipple/modules/operations/application/read_models/channels_health.py src/crxzipple/modules/operations/application/read_models/channels_charts.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k channels --tb=short
PYTHONPATH=src pytest -q tests/unit/test_channels_http.py::ChannelsHttpTestCase::test_web_channel_events_endpoint_streams_live_events --tb=short
```

结果：ruff passed；compileall passed；UI Operations Channels scoped 回归
`2 passed, 24 deselected`；Channels SSE live-event 单测 `1 passed`。
`operations/application/read_models/channels_health.py` 从 388 行收口到 265
行；message-flow、delivery-trend、top-channel、failure-category 和 shared chart
segment projection 迁入 `channels_charts.py`。

- [x] Operations Daemon table row projection 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/daemon_tables.py src/crxzipple/modules/operations/application/read_models/daemon_table_rows.py src/crxzipple/modules/operations/application/read_models/daemon.py src/crxzipple/modules/operations/application/read_models/daemon_details.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/daemon_tables.py src/crxzipple/modules/operations/application/read_models/daemon_table_rows.py src/crxzipple/modules/operations/application/read_models/daemon.py src/crxzipple/modules/operations/application/read_models/daemon_details.py
PYTHONPATH=src pytest -q tests/unit/test_operations_daemon_read_model.py tests/unit/test_ui_operations_http.py -k daemon --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k daemon --tb=short
```

结果：ruff passed；compileall passed；Daemon read-model/UI scoped 回归
`5 passed, 22 deselected`；Operations observation Daemon scoped 回归
`1 passed, 48 deselected`。`operations/application/read_models/daemon_tables.py`
从 386 行收口到 168 行；service-set、service、process-instance、lease、
dependency-health、matching-service 和 runtime-label row projection 迁入
`daemon_table_rows.py`。

- [x] Operations Daemon chart / drain projection 拆分回归：

```bash
python -m ruff check src/crxzipple/modules/operations/application/read_models/daemon.py src/crxzipple/modules/operations/application/read_models/daemon_health.py src/crxzipple/modules/operations/application/read_models/daemon_charts.py src/crxzipple/modules/operations/application/read_models/daemon_drain.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/daemon.py src/crxzipple/modules/operations/application/read_models/daemon_health.py src/crxzipple/modules/operations/application/read_models/daemon_charts.py src/crxzipple/modules/operations/application/read_models/daemon_drain.py
PYTHONPATH=src pytest -q tests/unit/test_operations_daemon_read_model.py tests/unit/test_ui_operations_http.py -k daemon --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k daemon --tb=short
```

结果：ruff passed；compileall passed；Daemon read-model/UI scoped 回归
`5 passed, 22 deselected`；Operations observation Daemon scoped 回归
`1 passed, 48 deselected`。`operations/application/read_models/daemon_health.py`
从 380 行收口到 208 行；process/state/lease chart projection 迁入
`daemon_charts.py`，lease/drain key-value overview 迁入 `daemon_drain.py`。

## Conclusion

这轮重构方向总体正确：核心热路径已经明显去大块化，provider render / runtime request / tool policy 逐步形成正式层。剩余问题不在“有没有又写歪一套新架构”，而在几个旧聚合点还没有完全退场。下一步应继续按 owner truth、control slice、provider render、UI projection 的边界收口，避免 Workbench 和 orchestration 再承担事实补偿与调试拼装职责。
