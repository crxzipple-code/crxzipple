# Assistant Progress Session Context Convergence Plan 2026-06-11

本文记录 “LLM 在 `text + tool_calls` 回合产生的阶段性说明没有稳定进入 session / Context Tree” 的修复方案。

关联文档：

- [provider-neutral-llm-response-stream-contract-plan-20260611.md](provider-neutral-llm-response-stream-contract-plan-20260611.md)
- [codex-like-agent-loop-governance-development-plan-20260611.md](codex-like-agent-loop-governance-development-plan-20260611.md)
- [codex-like-agent-prompt-contract-convergence-plan-20260610.md](codex-like-agent-prompt-contract-convergence-plan-20260610.md)
- [../context-workspace-prompt-tree-design.md](../context-workspace-prompt-tree-design.md)
- [../context-workspace-prompt-tree-development.md](../context-workspace-prompt-tree-development.md)
- [../orchestration-design.md](../orchestration-design.md)

## 当前定位

本文保留为问题观察和历史证据：它解释了为什么 “assistant progress text 没有进入 session/context” 会削弱 agent 长链路推进。

最终施工入口不再是单独补 `text + tool_calls` 写 session，而是 [provider-neutral LLM response stream contract](provider-neutral-llm-response-stream-contract-plan-20260611.md)。在新方案中，assistant progress 是 `assistant_message(phase=commentary|unknown)` response item 的一个投影；Session / Workbench / Context Tree 都应从 LLM response item contract 消化它，而不是继续围绕旧 `LlmResult.text` 做补丁。

数据库允许完全重建，因此本方案中涉及旧 session message、旧 execution item、旧 projection 的兼容描述只作为背景，不约束后续实现。

## 背景

在执行 “访问东航/昆航官网查询航班” 等长链路任务时，CRXZipple agent 容易陷入低效探索：

- 重复走 `web_search` / `fetch_text` / `urllib` / 抓 JS。
- 已经发现候选接口或页面机制后，下一轮仍重新探索。
- Workbench timeline 只能看到 LLM / tool call / tool result，看不到模型在 tool call 前后形成的阶段性判断。

对照 Codex 执行形态后，发现 Codex 常见的中间内容：

```text
我看到已有 query service 能列 execution chains/steps/items，正好可以复用...
我会新增一个 application 层小型 baseline builder...
开始落代码...
```

这些内容不是 tool result，而是 LLM 在工具调用之间生成的普通 assistant text。它的价值是：

- 对用户可见：知道 agent 为什么这样推进。
- 对后续 LLM 可见：保留 “我已确认 X，下一步做 Y” 的阶段性状态。

CRXZipple 当前问题是这类内容没有稳定成为 session/context 事实。

## 证据

基于 2026-06-11 本地 Docker/Postgres 历史数据检查：

- `llm_invocations` 中存在 **70 次** `result.text + result.tool_calls` 同时返回。
- 示例文本：
  - `现在我不依赖普通快照，直接检查候选层，并尝试精确点击...`
  - `我先点出发城市并输入“昆明”。`
  - `字段基本到位，我现在提交查询。`
- `sessions = 155`。
- `assistant_llm_session_messages = 0`。
- `assistant_tool_call_text_session_messages = 0`。
- 已有 `assistant_progress` execution item 中有 **28 条** 指向 function_call session message，payload 只有 `type/name/call_id/arguments`，没有自然语言正文。

结论：

- 模型确实返回过阶段性自然语言。
- 这些自然语言没有稳定写入 session。
- Workbench 之前的 progress item 有 id 混用问题，把 function_call message 当成 progress message。
- 后续 LLM 不能依赖 session transcript / Context Tree 看到这些阶段性判断。

## 目标

### 必须达成

1. LLM 在 `text + tool_calls` 回合返回的自然语言必须写入 session。
2. function_call message 和 assistant progress text message 必须分离记录。
3. Workbench 能展示真实 assistant progress，不能展示兜底假文案。
4. 后续 provider request 必须能通过 session transcript / Context Tree 看到这些 assistant progress。
5. Trace / Workbench 必须能诊断每次 LLM invocation 是否产生了 text、tool calls、session message。

### 非目标

- 不新增独立 “planning layer”。
- 不把 progress 伪装成 tool result。
- 不让 orchestration 拥有 Context Tree 真相。
- 不恢复关键词联想 router。
- 不新增 “assistant summary” 特殊消息类型作为 prompt 概念。

核心原则：

```text
先把 LLM 已经说出口的阶段性判断变成 session/context 事实；
不要替模型发明另一套总结系统。
```

## 术语

### assistant progress

LLM 在同一次 invocation 中同时返回：

- `result.text` 非空。
- `result.tool_calls` 非空。

其中 `result.text` 是 assistant progress。

### function_call message

为 provider transcript 维护的 assistant function call 记录，payload 形如：

```json
{
  "type": "function_call",
  "call_id": "...",
  "name": "browser.click",
  "arguments": {}
}
```

它不是 assistant progress，不应在 Workbench 以自然语言进展展示。

### assistant_progress_message_ids

只允许包含 `result.text` 写成的 assistant session message id。

### tool_call_message_ids

只允许包含 function_call session message id。

## 目标数据流

### 1. LLM 返回

```text
LlmInvocation.result.text = "我先检查页面状态。"
LlmInvocation.result.tool_calls = [browser.snapshot, browser.click]
```

### 2. Engine 记录 session

写入三类事实：

1. assistant progress text message：

```json
{
  "role": "assistant",
  "source_kind": "llm_invocation",
  "source_id": "<invocation_id>",
  "content_payload": {
    "blocks": [{"type": "text", "text": "我先检查页面状态。"}],
    "text": "我先检查页面状态。",
    "finish_reason": "tool_calls"
  }
}
```

2. assistant function_call message：

```json
{
  "role": "assistant",
  "source_kind": "llm_invocation",
  "source_id": "<invocation_id>",
  "content_payload": {
    "type": "function_call",
    "call_id": "...",
    "name": "browser.snapshot",
    "arguments": {}
  }
}
```

3. tool result message。

### 3. EngineAdvanceOutcome

```json
{
  "assistant_message_ids": [
    "<progress_message_id>",
    "<function_call_message_id>"
  ],
  "assistant_progress_message_ids": [
    "<progress_message_id>"
  ],
  "tool_result_message_ids": []
}
```

### 4. Execution chain

LLM step summary：

```json
{
  "llm_invocation_id": "<invocation_id>",
  "assistant_progress_message_ids": ["<progress_message_id>"],
  "assistant_progress_text": "我先检查页面状态。",
  "tool_call_names": ["browser.snapshot", "browser.click"]
}
```

LLM step item：

- `LLM_INVOCATION` item 指向 invocation。
- `SESSION_MESSAGE` item 只为 progress message 建立，`message_kind=assistant_progress`。
- function_call session message 不作为 `assistant_progress` item。

### 5. Workbench

Workbench timeline 展示：

```text
Agent 进展
Assistant
我先检查页面状态。
```

如果 summary 缺正文：

- 按 `session_message_id` 回查 session message。
- 查不到或无正文则不展示该行。
- 不显示兜底文案。

### 6. 后续 prompt

后续 provider request 的 session transcript / Context Tree 应包含该 assistant text。

模型看到：

```text
assistant: 我先检查页面状态。
assistant function_call: browser.snapshot(...)
tool: ...
```

这样下一轮能延续阶段性判断，而不是从相似入口重新探索。

## 已完成改动

- [x] `EngineAdvanceOutcome` 增加 `assistant_progress_message_ids`。
- [x] engine 中分离 assistant progress message ids 与 function_call message ids。
- [x] execution payload 只从 `assistant_progress_message_ids` 生成 progress item。
- [x] Workbench provider 注入 `SESSION_SERVICE`，用于按 message id 回查正文。
- [x] Workbench read model 不再显示 `Assistant progress message recorded.` 兜底文案。
- [x] Workbench read model 在 summary 缺正文时回查 session message。
- [x] 单测覆盖 execution payload 不把 function_call message 混入 progress ids。
- [x] 单测覆盖 Workbench 从 session message 回读 progress 正文。

已跑验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py \
  tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_workbench_reads_llm_trace_from_execution_chain_without_run_metadata \
  tests/unit/test_orchestration_tool_resource_policy.py
```

结果：

```text
30 passed
```

追加验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py \
  tests/unit/test_orchestration_tools.py::OrchestrationToolsTestCase::test_text_with_tool_calls_records_assistant_progress_for_next_prompt \
  tests/unit/test_prompt_transcript.py \
  tests/unit/test_context_workspace_session_adapter.py \
  tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_workbench_reads_llm_trace_from_execution_chain_without_run_metadata \
  tests/unit/test_operations_llm_read_model.py \
  tests/unit/test_llm.py

PYTHONPATH=src pytest -q tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_trace_summary_and_events_use_event_read_model

PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py::test_execution_payload_keeps_tool_call_messages_out_of_assistant_progress \
  tests/unit/test_orchestration_tools.py::OrchestrationToolsTestCase::test_text_with_tool_calls_records_assistant_progress_for_next_prompt \
  tests/unit/test_events.py \
  tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_trace_summary_and_events_use_event_read_model

PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py \
  tests/unit/test_orchestration_tools.py::OrchestrationToolsTestCase::test_text_with_tool_calls_records_assistant_progress_for_next_prompt \
  tests/unit/test_prompt_transcript.py \
  tests/unit/test_context_workspace_session_adapter.py \
  tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_workbench_reads_llm_trace_from_execution_chain_without_run_metadata \
  tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_trace_summary_and_events_use_event_read_model \
  tests/unit/test_operations_llm_read_model.py \
  tests/unit/test_llm.py \
  tests/unit/test_events.py

cd frontend && npm run typecheck
```

结果：

```text
83 passed
1 passed
36 passed
117 passed
typecheck passed
```

## 待施工阶段

## Phase 1: Session Fact Integrity

目标：确认并修复 `text + tool_calls` 回合的 assistant progress 必然写入 session。

任务：

- [x] 增加 engine 级单测：LLM 返回 `text + tool_calls` 时，session 中出现一条 assistant text message。
- [x] 同一测试中确认 function_call message 仍会写入 session。
- [x] 确认 assistant progress message 的 `source_kind=llm_invocation`、`source_id=<invocation_id>`。
- [x] 确认 assistant progress message 的 `content_payload.finish_reason=tool_calls`。
- [x] 确认 `assistant_progress_message_ids` 只包含 assistant text message id。
- [x] 确认 function_call session message 不会被 materialize 为 `assistant_progress` execution item。
- [ ] 确认 `assistant_message_ids` 可包含 text + function_call 总集合。
- [ ] 检查 `record_assistant_messages=False` 的 prompt mode，只允许 memory flush 等明确不记录场景跳过。

建议测试：

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_execution_chain.py
```

验收：

- 新运行的 session history 中能查到 `role=assistant, source_kind=llm_invocation, finish_reason=tool_calls, text!=empty`。

## Phase 2: Prompt Transcript Visibility

目标：后续 LLM invocation 能看到 assistant progress。

任务：

- [x] 增加端到端单测：assistant progress text message 进入下一轮 provider request。
- [x] 增加 `prompt_transcript.py` 单测：assistant progress text message 保留为普通 assistant message。
- [x] 确认 `_filter_transcript_messages` 不把 assistant progress 当作 orphan function_call 移除。
- [ ] 确认 `consumed_through_sequence_no` 不错误吞掉最近 progress。
- [ ] 确认 budget truncation 优先保留最近 assistant progress。
- [ ] 增加 orchestration prompt preview 测试：上一轮 progress text 能出现在下一轮 prompt / Context Tree render 中。

建议测试：

```bash
PYTHONPATH=src pytest -q tests/unit/test_prompt_transcript.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py
```

验收：

- 下一轮 provider request 中能看到上一轮 assistant progress text。
- Context Tree render snapshot metadata 能追踪 history delivery 口径。

## Phase 3: Context Tree Rendering

目标：Context Workspace 作为 agent-visible 面稳定呈现 session progress。

任务：

- [x] 检查 `session.current` / session history 节点是否包含 assistant progress。
- [x] 确认 assistant progress 不被折叠成空节点。
- [ ] 如果历史较长，progress 可以被预算压缩，但压缩文本必须保留阶段性判断要点。
- [x] 添加 Context Workspace 单测覆盖 progress message render。
- [ ] 保持 Context Workspace owner 边界：orchestration 只提交/引用 session fact，不直接拼树。

建议测试：

```bash
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tool_adapter.py
```

验收：

- `context_tree` 中能看到最新 assistant progress。
- provider mirror / tool schema 不受 progress message 影响。

## Phase 4: Workbench And Trace Diagnostics

目标：以后不用猜 “模型没说话 / 没写 session / 没进 prompt”。

任务：

- [x] LLM timeline item 增加诊断摘要：
  - `text_present`
  - `text_chars`
  - `tool_calls_count`
  - `finish_reason`
  - `assistant_progress_message_count`
  - `tool_call_message_count`
- [x] LLM timeline item 增加 `tool_call_message_count`。
- [x] Trace 事件 payload 展示 LLM text/tool diagnostic：
  - `text_present`
  - `text_chars`
  - `tool_call_count`
  - `tool_call_names`
- [x] Trace detail 通过 `orchestration.execution.llm_step_completed` 事件展示 orchestration execution summary 中的 `assistant_progress_message_ids` 与 `tool_call_message_ids`。
- [x] Workbench 对没有 text 的 tool-call 回合展示 “tool call only” 状态，而不是 progress 行。
- [x] Operations LLM detail read model 加 text/tool/progress 诊断字段。
- [x] 前端 i18n 补齐新增固定文案。

建议测试：

```bash
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_read_model.py
cd frontend && npm run typecheck
```

验收：

- 前端能一眼区分：
  - LLM returned text + tool calls。
  - LLM returned tool calls only。
  - progress text recorded to session。
  - progress text missing from session。

## Phase 5: Regression Baseline

目标：用真实长任务确认低效探索是否缓解。

已建立历史对照样本：

```bash
source scripts/dev/infra-env.sh
PYTHONPATH=src python -m crxzipple.main orchestration baseline \
  e62ecf184e1b4f7eb62945f9fd853df4 \
  --task-label "东航官网周五昆明到北京"
```

结果摘要：

```json
{
  "run_id": "e62ecf184e1b4f7eb62945f9fd853df4",
  "status": "cancelled",
  "orchestration_steps": 14,
  "llm_calls": 5,
  "tool_calls": 8,
  "llm_text_tool_call_steps": 4,
  "llm_tool_only_steps": 1,
  "assistant_progress_message_count": 6,
  "tool_call_message_count": 0,
  "progress_without_tool_call_messages": true,
  "first_endpoint_discovery_step": 9,
  "first_candidate_validation_step": null,
  "metrics_missing": [
    "first_candidate_validation_step",
    "final_answer_has_verified_facts",
    "final_answer_has_gaps",
    "tool_call_message_ids"
  ]
}
```

这个样本体现了修复前问题：LLM 已经产生 assistant progress，
但 function_call session message id 没进入 execution summary / baseline。

任务：

- [x] 启动最新 API / daemon / Docker。
- [ ] 跑 “你去东航官网看下周五昆明到北京的航班”。
- [ ] 跑 “你去昆航官网看下周五昆明到北京的航班”。
- [ ] 记录每轮：
  - LLM text present。
  - tool_calls_count。
  - assistant progress 是否进入 session。
  - function_call message 是否进入 session。
  - 下一轮 prompt 是否包含上一轮 progress。
  - 是否重复相同 fetch/search/JS 探测路径。
- [ ] 对比修复前 baseline：
  - LLM calls。
  - tool calls。
  - `llm_text_tool_call_steps`。
  - `llm_tool_only_steps`。
  - `assistant_progress_message_count`。
  - `tool_call_message_count`。
  - 重复探测次数。
  - 首次候选 endpoint 发现步数。
  - 首次候选 endpoint 验证步数。

验收：

- 模型能延续上一轮阶段性判断。
- 重复探索明显下降。
- Workbench timeline 能展示关键阶段性判断。
- 最终回答能区分 verified facts 和 unresolved gaps。

## 代码改造点

### Orchestration Engine

文件：

- `src/crxzipple/modules/orchestration/application/engine.py`
- `src/crxzipple/modules/orchestration/application/engine_session_recorder.py`
- `src/crxzipple/modules/orchestration/application/execution.py`

要求：

- `append_assistant_response_message()` 负责写 assistant progress text。
- `append_tool_call_messages()` 负责写 function_call message。
- 两类 message ids 必须分流。
- `EngineAdvanceOutcome.assistant_progress_message_ids` 是 progress 唯一来源。

### Execution Chain

文件：

- `src/crxzipple/modules/orchestration/application/coordinators/progress.py`
- `src/crxzipple/modules/orchestration/application/execution_chain_lifecycle.py`

要求：

- LLM step summary 保留 `assistant_progress_text`。
- 只为 `assistant_progress_message_ids` 创建 `message_kind=assistant_progress` 的 `SESSION_MESSAGE` item。
- function_call message 不创建 progress item。

### Prompt Transcript

文件：

- `src/crxzipple/modules/orchestration/application/prompt_transcript.py`
- `src/crxzipple/modules/orchestration/application/prompt_input.py`

要求：

- assistant progress text 作为普通 assistant message。
- function_call 继续按 tool-call pairing 规则处理。
- 不把 progress text 当成 function_call 或 tool result。

### Context Workspace

文件：

- `src/crxzipple/modules/context_workspace/application/rendering/xml_renderer.py`
- `src/crxzipple/modules/context_workspace/application/services.py`
- `src/crxzipple/modules/context_workspace/application/root_nodes.py`

要求：

- session history / current session 节点能包含 assistant progress。
- 不新增 orchestration-owned prompt 拼接。
- 不绕过 Context Tree render snapshot。

### Workbench / Trace

文件：

- `src/crxzipple/modules/orchestration/application/read_models/workbench.py`
- `src/crxzipple/interfaces/http/ui.py`
- `frontend/src/pages/workbench/WorkbenchPage.vue`
- `frontend/src/shared/runtime/types.ts`
- `frontend/src/shared/i18n/messages/*.ts`

要求：

- `agent_progress` 只展示真实文本。
- trace detail 增加 LLM invocation text/tool/session diagnostic。
- 前端文案进入 i18n。

## 风险

### 风险 1: session 变长

assistant progress 会增加 session 历史长度。

控制：

- 不记录空 text。
- 只记录模型真实返回 text。
- 由现有 transcript budget / Context Tree budget 控制长度。
- 后续可在 Context Workspace 层做压缩，但不在本阶段新增总结概念。

### 风险 2: function_call 与 progress 顺序错误

如果 provider transcript 要求 function_call 紧跟 tool result，插入 text message 可能影响兼容性。

控制：

- 保持消息原始顺序：assistant text -> assistant function_call -> tool result。
- 适配器层按 provider 要求序列化。
- 增加 provider adapter 回归测试。

### 风险 3: progress 被误当最终回答

assistant progress 不是 final response。

控制：

- Workbench type 使用 `agent_progress`。
- Execution step 仍归属 LLM tool-call step。
- final response 仍来自 final response step / terminal outcome。

### 风险 4: 过度可见导致噪声

模型可能输出很多短进展。

控制：

- UI 可折叠，但不能从 session/context 事实中丢失。
- 后续 loop governance 可基于重复度做提示，不在本阶段硬编码路由。

## 完整验收清单

- [x] `text + tool_calls` 写入 assistant progress session message。
- [x] function_call message 不进入 `assistant_progress_message_ids`。
- [x] Workbench 展示真实 `agent_progress` 文本。
- [x] Workbench 不展示兜底假文案。
- [x] 下一轮 prompt transcript 包含上一轮 assistant progress。
- [x] Context Tree render snapshot 包含或可展开看到 assistant progress。
- [x] Workbench LLM step 能显示 text/tool/progress 诊断摘要。
- [x] Workbench LLM step 能显示连续 tool-only streak 诊断，帮助区分 “progress 丢失” 和 “模型没有输出 progress”。
- [x] Trace 能通过 `llm.invocation_succeeded` 事件显示 text/tool 诊断字段。
- [x] Trace 能显示 orchestration session message id 诊断字段。
- [ ] 东航/昆航真实任务回归中重复探索下降。
- [x] 东航真实任务回归证明 function_call session message 已经进入 baseline：run `41b59160c8c043bfbc0f9b1decf99874` 终态观测到 `tool_call_message_count=35`、`progress_without_tool_call_messages=false`。
- [x] 东航真实任务回归区分出新问题：同一 run 终态观测到 `assistant_progress_message_count=0`、`max_consecutive_llm_tool_only_steps=20`、`tool_only_loop_suspected=true`，说明前端无阶段性文字不是兜底丢失，而是模型连续 tool-only。
- [x] 所有新增固定前端文案进入 i18n。
- [x] 后端相关单测通过。
- [x] 前端 typecheck 通过，若失败需说明是否为既有 unrelated 问题。

## 真实回归结论

2026-06-11 重启 Docker app 后提交东航任务：

```text
你去东航官网看下周五昆明到北京的航班
```

Run ID：`41b59160c8c043bfbc0f9b1decf99874`。

运行中 baseline 关键值：

```json
{
  "llm_text_tool_call_steps": 0,
  "llm_tool_only_steps": 20,
  "max_consecutive_llm_tool_only_steps": 20,
  "assistant_progress_message_count": 0,
  "tool_call_message_count": 35,
  "progress_without_tool_call_messages": false,
  "tool_only_loop_suspected": true
}
```

结论：

- 本文修复的旧问题是：LLM 已经返回 `text + tool_calls`，但 progress text 没有稳定进入 session/context。
- 该问题已通过 `tool_call_message_count > 0` 与 `progress_without_tool_call_messages=false` 得到正向验证。
- 当前真实任务仍慢，是另一类问题：模型连续返回 tool-only，没有给出任何 assistant progress text。
- 下一步应进入 loop governance 的 tool-only streak 治理，而不是继续在 Workbench 兜底文案上打补丁。

## 推荐施工顺序

1. Phase 1：session fact integrity。
2. Phase 2：prompt transcript visibility。
3. Phase 3：Context Tree rendering。
4. Phase 4：Workbench / Trace diagnostics。
5. Phase 5：真实任务回归。

不要跳过 Phase 1。只有先保证 session 事实存在，后面的 Context Tree / UI 才不是在修投影幻觉。
