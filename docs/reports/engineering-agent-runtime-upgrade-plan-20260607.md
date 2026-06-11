# Engineering Agent Runtime Upgrade Plan 2026-06-07

本文是“让 CRXZipple agent 成为类似 Codex / Claude Code 的工程 agent”的当前施工入口。
它承接：

- [reference/codex-prompt-engineering-reference.md](../reference/codex-prompt-engineering-reference.md)
- [reference/claude-code-prompt-engineering-reference.md](../reference/claude-code-prompt-engineering-reference.md)
- [prompt-engineering-runtime-contract-upgrade-plan-20260605.md](prompt-engineering-runtime-contract-upgrade-plan-20260605.md)
- [context-workspace-prompt-tree-design.md](../context-workspace-prompt-tree-design.md)
- [session-semantics-design.md](../session-semantics-design.md)

## 目标

CRXZipple agent 在工程类任务中应表现为工程执行者，而不是普通问答助手：

- 会先定位事实：读代码、查测试、看日志、看 traces、看 browser/network/runtime state。
- 会直接施工：需求清楚时实现改动，而不是停在建议。
- 会持续推进：工具结果、后台结果、审批恢复、错误恢复进入同一条后续执行链。
- 会验证收口：用最小有效测试、build、browser check、trace 或命令输出验证。
- 会解释边界：区分已验证事实、推断、未完成项和阻塞点。

## 非目标

- 不把 CRXZipple 改成纯编程 agent。工程模式只在代码、系统设计、调试、浏览器/API
  调查、仓库施工、runtime repair 等任务中显性生效。
- 不新增 keyword router 或人工联想规则。
- 不在每个 turn 前强制跑一次独立规划 LLM。
- 不把 Context Workspace 降级回 orchestration prompt 拼装器。
- 不复活旧 orchestration facade 或前端绕路拼 prompt/tool truth。

## 已落地

- [x] Runtime contract 新增 `Engineering Work` 章节。
- [x] Runtime contract 强化 tool-result continuation、owner facts、runtime issue evidence path。
- [x] `tools/workspace` 新增 source inspection / source changes prompt groups。
- [x] `tools/command` 新增 run-and-verify / background-processes prompt groups。
- [x] `tools/context_tree` source summary 强化工程任务中先展开相关上下文和能力的规则。
- [x] `/turns/{run_id}/prompt-preview` 后端返回 `context_render_snapshot_id`、
  `context_render`、`context_render_metadata` 和 `provider_attachments`，不再只暴露
  provider messages / tool schemas。
- [x] Tool Context Tree 的自动 source group 已压平：没有显式 prompt groups 的 source
  被视为能力入口，展开 source 后直接暴露 tool functions；显式 groups 仍需按 group
  展开。
- [x] approval resume 覆盖 Context Tree 动态展开后的工具执行：模型先展开 source、
  再请求 effect-gated tool 时，会进入等待审批并在审批后继续同一执行链。
- [x] 后台 tool terminal completion 覆盖成功与失败结果：terminal tool run 会写入
  session tool result message，并以 recovery resume 进入后续 LLM 输入。
- [x] 后台 tool terminal abort/cancel/timed-out 不丢失 tool-result pair：无 result/error
  正文的 cancelled/timed-out run 会生成模型可见 terminal status 文本，并进入 recovery
  resume。用户取消 orchestration run 仍是外层停止语义，不自动恢复模型。
- [x] Provider-message ordering contract 已由 prompt transcript / orchestration tool loop
  覆盖：未完成的 assistant function call 不进入 provider transcript；已完成 tool result
  会保留对应 assistant tool call，并按 tool_call_id 成对进入后续 LLM 输入。
- [x] Browser source 已有工程调查式 prompt metadata 和分组：
  Observation / Action Trace / Forms & Overlays / DOM / Network / Code Insight /
  Storage / Diagnostics；context tree 测试覆盖 schema mirror。
- [x] Sessions source 已拆为 prompt groups：Session State & History、
  Delegation & Follow-up、Session Tree Control、Run Control。
- [x] 新增系统 skill `browser-investigation`：把 browser 任务的 evidence path
  固化为可复用技能，要求先观察/trace，再按 form/overlay/DOM/network/script/storage/
  diagnostics 深挖。
- [x] Skill context node 展开保持 handle-first：只暴露 `skill_read` 入口和文件 handle，
  不把完整 `SKILL.md` 正文直接灌入 prompt tree。
- [x] accepted-before-session 的 run cancellation 可幂等执行：session 尚未 materialize
  时取消 run 本身并跳过 session-tree 级联。

## 设计判断

Codex / Claude Code 的工程行为不是只靠一句提示词。它们共同依赖：

- 稳定总叙述：模型知道自己是执行型 agent。
- 具体工具 affordance：模型看见可调用的读、写、执行、检查、计划、委派工具。
- 工具结果回灌：tool call 和 tool result 成对回到下一轮模型输入。
- 历史归一和压缩：长链条不会因为分页、截断或压缩丢掉关键事实。
- 错误恢复：prompt-too-long、abort、tool failure、background completion 都有继续路径。
- 可观察最终请求：人能看到模型到底收到了哪些 system/input/tool/schema/attachment。

CRXZipple 的落点是 Context Workspace + Session + Execution Chain：

- Context Workspace 是 prompt 主体和能力控制面。
- Session 保存事实和历史语义。
- Orchestration / dispatch 保证执行链条、工具结果和恢复时序。
- LLM provider adapter 只做 provider-specific mirror。

## 后续任务清单

### P1. Final Request Inspectability

- [x] 后端 prompt preview / render snapshot 已暴露最终请求基础事实：
  `context_render_snapshot_id`、context tree XML、context render metadata、
  provider attachments、mirrored tool schemas、prompt report。
- [x] Workbench / Trace 已接入 Context Workspace render snapshot，并以 XML source
  viewer 显示真实 prompt tree。
- [x] Workbench / Trace 已接入 `/turns/{run_id}/prompt-preview`，Actual Request
  区域可查看 runtime contract / context tree XML、provider-native messages、
  mirrored tool schemas、provider attachments，以及 snapshot id、contract hash、
  schema count 等诊断。
- [x] UI 展示已把 XML prompt、provider messages、tool schemas、provider attachments
  分成同一个“Actual Request”区域下的 tabs，避免继续把所有诊断塞进单张卡片。
- [x] response format / output schema / request overrides / request metadata 已在
  prompt preview 的 `provider_request_options` 中明确暴露，并进入 Actual Request
  `Options` tab。
- [x] 已执行 run 的 prompt preview 优先读取已记录的 Context Workspace render snapshot，
  `provider_request_options.request_metadata.context_render_snapshot_id` 指向真实
  `ctxsnap_*`，不再误指向重新计算的 `ctxpreview_*`。
- [x] Actual Request 预览按已记录快照 metadata 中的
  `direct_transcript_message_count` 还原当次 provider transcript，避免把本轮已完成的
  assistant/tool 结果回灌进“请求”视图。
- [x] `context_render_snapshots` 不再以 `run_id` 唯一化；同一 run 可记录多次真实
  prompt render snapshot，`get_by_run` 仅作为 run-level 最新 snapshot 查询入口。
- [x] Context Workspace HTTP 增加按 `snapshot_id` 读取 render snapshot 的接口；
  Workbench / Trace 在选中 LLM invocation 时优先读取 invocation 自身保存的 provider
  messages、tool schemas、request metadata，再按 `context_render_snapshot_id` 读取对应
  XML snapshot；没有 invocation 时才退回 run-level latest preview。
- [x] LLM invocation `request_metadata` 明确携带 `prompt_mode`，Actual Request 能区分
  normal turn、memory flush、compaction、heartbeat 等请求类型，不再由前端猜默认值。
- [x] Prompt preview API 不只显示 XML；必须能解释 provider 实际看见什么。
- [x] LLM invocation read model 保留足够字段供 UI 展示最终请求。

### P2. Tool Result Continuation Contract

- [x] 明确 ExecutionStep / StepItem 的 provider-message ordering contract：
  assistant tool call intent -> owner terminal result -> follow-up attachments。
- [x] approval resume 进入 continuation path，审批后工具结果回灌到后续 LLM 输入。
- [x] 后台 tool completion 进入 continuation path；成功和失败工具结果都会成为模型可见
  tool-result pair。
- [x] tool-wait recovery resume 可在 wait mapping 丢失后根据 recovery contract 继续。
- [x] 对 tool terminal abort/cancel/timed-out 生成模型可见的结果项，而不是丢失
  tool-result pair。
- [x] 单测覆盖后台成功、失败、取消恢复边界和 provider-message ordering contract。

Ordering contract:

- `ExecutionStep(kind=llm)` 记录本次 provider request 和 `llm_invocation` item。
- LLM 产生 tool call 时，orchestration 在同一 execution chain 中记录
  `tool_call` item，`owner_id` 使用 provider `tool_call_id`。
- Tool owner 只拥有 tool run 生命周期；orchestration 以
  `tool_call_id -> tool_run_id` 绑定 `tool_run` item，不让 tool/llm 自己推进外层 run。
- Tool terminal result、失败、取消或超时进入 `tool_result` item，并回写 session
  tool-result message；下一次 provider transcript 必须保留匹配 assistant tool call，
  再按 `tool_call_id` 附上 tool result。
- 未完成或没有 terminal result 的 assistant function call 不能进入 provider
  transcript；late/orphan tool result 只能记为 operational fact，不反向推动已完成
  chain。
- Follow-up attachments、context render snapshot 和 provider attachments 必须作为同一
  step/后续 step 的可观察事实进入 Context Workspace / prompt preview，不能藏在 run
  metadata 里作为唯一真相。

### P3. Session History And Compaction

- [x] normal turn 历史由 Context Workspace 渲染，而不是 provider transcript 隐式分页。
- [x] session segment / folded history 作为显式树节点出现。
- [x] 压缩保留工具调用和工具结果成对关系：折叠 segment 展开到 range 后以
  `tool_interaction` 节点恢复 call/result。
- [x] 压缩 summary 的插入位置有明确规则，不能挤掉 runtime contract 或最新用户意图。
- [x] 单测覆盖压缩后仍能看到最新 active segment、folded history handle 和展开后的
  tool results；runtime contract 独立由 prompt snapshot 测试覆盖。

Compaction placement contract:

- Runtime contract / context instructions 属于最高优先级 root，永远不能被 session
  summary 替代或挤到后面。
- 当前 active session segment 代表最新用户意图和当前执行事实，必须在同一 render 中保留。
- 旧 segment summary 作为 folded history handle 挂在 `session.current` 下，位置在当前
  active segment 之后；展开 folded range 才恢复旧消息和旧 tool interaction。
- Summary 只概括跨 segment 历史，不承载新的 runtime rule、agent identity 或当前用户输入。

### P4. Engineering Planning Affordance

- [x] 不强制每 turn 规划，但工程任务要有显式 plan/task affordance。
- [x] Context Tree 默认提供 `work.plan` 公开工作计划节点；agent-facing
  `context_tree.update_plan` 可更新轻量计划面：
  - 当前目标。
  - 正在执行的步骤。
  - 已验证事实。
  - 待验证假设。
  - 阻塞点。
- [x] 计划状态进入 Context Tree render snapshot，可在前端 Actual Request / Context Tree
  中观察；内容限定为公开工作状态，不使用隐藏 chain-of-thought。
- [x] 完成规则：测试失败、实现部分完成、错误未解决时不能标记完成。
- [x] 单测覆盖默认 `work.plan` 节点、workspace refresh 保留计划、工具更新计划、
  tool catalog 注册。

### P5. Engineering Tool Surface

- [x] Workspace / Command / Context Tree 工具具备清晰工程能力入口和 prompt groups。
- [x] 自动 source group 不再额外消耗一层展开；source-first 能力入口可直接暴露未显式分组函数。
- [x] Browser / Sessions 工具补齐工程能力入口和 prompt groups；Debug 仍是窄用途
  runtime verification source，不作为工程能力主入口。
- [x] Browser 工程调查面继续强调：
  - snapshot 只是入口。
  - 可使用 form/overlay/network/script/storage/diagnostics。
  - 必要时分析前端请求和脚本，而不是困在 DOM 点击。
- [x] CLI source 在 Context Tree 中不镜像为 provider function；只作为
  `tool_cli_source` 指导节点暴露，并指向 command execution `exec`。Tool owner
  catalog 仍保留受管 CLI function records 用于治理和测试。
- [x] Tool group 仍按 source-first，不做关键词语义分类。

### P6. Skills And Memory For Engineering Work

- [x] Skill 节点默认只暴露介绍和 handle；需要深入时由 agent 主动读 SKILL.md 或相关文件。
- [x] 工程经验沉淀走 skill authoring / memory remember，而不是写进 runtime contract。
- [x] Memory 用于跨 session durable knowledge；当前 session execution facts 仍归 session/context tree。

Knowledge-capture contract:

- 当前任务事实、工具结果、错误恢复和执行状态归 `session` / Context Tree。
- 跨 session 稳定事实、用户明确要求记忆的信息、可长期复用的偏好归 `memory`，
  通过 `memory_write_daily` 或 memory flush maintenance 进入 durable store。
- 可复用流程、调查方法、工具使用经验和工程模式归 `skills`，通过
  `skill_draft_create -> validate -> diff -> approve/apply` 治理。
- Runtime contract 只写系统级规则，不作为普通经验库。
- 现有参考：
  [docs/memory-space-design.md](../memory-space-design.md)、
  [skill-authoring-meta-skill-checklist-20260521.md](skill-authoring-meta-skill-checklist-20260521.md)。

### P7. Browser/API Investigation Workflow

- [x] 给 browser source/group/function 增加工程调查式 prompt metadata。
- [x] 提供可复用 skill：从页面目标出发，按 snapshot -> form/overlay -> network/script -> storage/diagnostics
  路径找证据。
- [x] 工具结果回到 Context Tree/session history：session adapter 将成对的
  assistant function call + tool result 合并为 `tool_interaction` 节点，失败详情也进入
  XML render。

### P8. Verification

- [x] `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py`
- [x] `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tool_adapter.py`
- [x] `PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py`
- [x] `PYTHONPATH=src pytest -q tests/unit/test_prompt_transcript.py`
- [x] 补充验证：
  `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_prompt_transcript.py`
  和 CLI source guidance 聚焦测试。
- [x] P1/P4 补充验证：
  `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_tool_providers.py`
  和 prompt-preview provider options 聚焦测试。
- [x] P2/P3/P6 补充验证：
  `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py`
  相关 compaction/order 测试，以及 runtime contract loader/render 测试。
- [x] Runtime contract prompt asset packaging：
  `python -m pip wheel . --no-deps -w /tmp/crxzipple-wheel-check`，并确认 wheel
  包含 `crxzipple/modules/context_workspace/application/prompts/runtime_contract.md`。
- [x] 本轮最终聚焦回归：
  `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_tool_providers.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_context.py::OrchestrationContextTestCase::test_prompt_preview_routes_auto_to_vision_model_for_tool_attachments tests/unit/test_orchestration_memory.py::OrchestrationMemoryTestCase::test_request_memory_flush_records_durable_memory_without_transcript_reply tests/unit/test_turns_http.py::TurnsHttpTestCase::test_turns_endpoint_submits_async_turn_without_exposing_orchestration`
  -> 62 passed。
- [x] Actual Request recorded snapshot 聚焦回归：
  `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_tool_providers.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_context.py::OrchestrationContextTestCase::test_prompt_preview_routes_auto_to_vision_model_for_tool_attachments tests/unit/test_orchestration_memory.py::OrchestrationMemoryTestCase::test_request_memory_flush_records_durable_memory_without_transcript_reply tests/unit/test_turns_http.py::TurnsHttpTestCase::test_turns_endpoint_submits_async_turn_without_exposing_orchestration`
  -> 81 passed。
- [x] Context render snapshot run history 迁移：
  `bash -lc 'source scripts/dev/infra-env.sh && PYTHONPATH=src python -m crxzipple.main db upgrade head'`
  已在本机 Postgres 执行 `0069 -> 0070`。
- [x] Fresh SQLite fallback 迁移验证：
  `APP_DATABASE_URL="sqlite:////tmp/crxzipple-migration-fresh-0070b-$RANDOM.db" PYTHONPATH=src python -m crxzipple.main db upgrade head`
  已通过；同时修复 0069 在 SQLite 上不支持 `ALTER COLUMN DROP DEFAULT` 的问题。
- [x] Actual Request + run snapshot history 聚焦回归：
  `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_tool_providers.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_context.py::OrchestrationContextTestCase::test_prompt_preview_routes_auto_to_vision_model_for_tool_attachments tests/unit/test_orchestration_memory.py::OrchestrationMemoryTestCase::test_request_memory_flush_records_durable_memory_without_transcript_reply tests/unit/test_turns_http.py::TurnsHttpTestCase::test_turns_endpoint_submits_async_turn_without_exposing_orchestration`
  -> 82 passed。
- [x] Invocation-level Actual Request 聚焦验证：
  `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_http.py::ContextWorkspaceHttpTestCase::test_context_workspace_tree_action_and_render_snapshot tests/unit/test_context_workspace_tree_service.py::test_render_snapshots_keep_run_history_and_latest_lookup tests/unit/test_turns_http.py::TurnsHttpTestCase::test_turns_endpoint_submits_async_turn_without_exposing_orchestration`
  -> 3 passed。
- [x] Invocation request metadata `prompt_mode` 聚焦验证：
  `PYTHONPATH=src pytest -q tests/unit/test_context_workspace_http.py::ContextWorkspaceHttpTestCase::test_context_workspace_tree_action_and_render_snapshot tests/unit/test_context_workspace_tree_service.py::test_render_snapshots_keep_run_history_and_latest_lookup tests/unit/test_turns_http.py::TurnsHttpTestCase::test_turns_endpoint_submits_async_turn_without_exposing_orchestration tests/unit/test_orchestration_context_workspace_snapshot.py::test_engine_carries_context_contract_metadata_for_llm_invocation tests/unit/test_orchestration_memory.py::OrchestrationMemoryTestCase::test_request_memory_flush_records_durable_memory_without_transcript_reply`
  -> 5 passed。
- [x] 前端验证：
  `cd frontend && npm run typecheck`、`cd frontend && npm run build` 均通过；build 仅保留既有
  `operations-access` chunk size warning。
- [x] 前端涉及 prompt preview / trace 时运行：

```bash
cd frontend
npm run typecheck
npm run build
```

## 通过标准

- 工程类任务中，模型能稳定看到“先定位、再实施、再验证”的总契约。
- 读代码、改代码、跑命令、看上下文树这些能力以清晰 source/group 节点出现。
- 工具结果和后台恢复不会丢失或要求用户反复手动说“继续”。
- 长会话压缩不会让最新执行事实、工具结果或 runtime contract 消失。
- 人能在 Workbench / Trace 中解释一次 LLM 调用的完整输入。
