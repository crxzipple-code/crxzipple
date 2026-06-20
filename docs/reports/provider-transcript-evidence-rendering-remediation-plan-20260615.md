# Provider Transcript Evidence Rendering Remediation Plan

Date: 2026-06-15

## 2026-06-15 决策修订：拆除 runtime 证据裁判层

最新决策：

- 通用 agent 不在 runtime 侧用 `EvidenceGate` / `EvidenceOutcomeClassifier` 替模型判题。
- LLM 自己判断执行情况、证据是否足够、下一步是否继续。
- CRXZipple 只负责把工具结果、stdout/stderr、失败摘要、artifact/read handle refs、owner 明示的 `key_facts/failure_signatures/gaps` 尽量清楚地渲染给模型。
- 若未来需要业务强验收，应由明确 workflow / skill evaluator 承担，而不是通用 agent loop 默认启用证据裁判。

因此，本文早期版本中关于新增 `EvidenceOutcomeClassifier`、`EvidenceGate`、terminal evidence gate 阻止 complete 的内容均取消；保留的施工方向只有：

1. 砍掉默认 `omitted_from_provider_transcript`。
2. 保留 provider-visible tool result 摘要、关键事实、失败签名、open gaps、refs。
3. 不自动推断业务证据状态；只渲染 owner/tool 明示字段。
4. 让 LLM 基于连续 transcript 自己判断是否继续探索。

## 2026-06-15 二次决策修订：移除不可穷举的 model-visible 运行时结论块

进一步检查后确认：除了已拆除的 `EvidenceGate` / `EvidenceOutcomeClassifier`，以下流程也会用不可穷举的启发式结论干扰 LLM 判断：

- `runtime_loop_correction`：用 tool-only streak、validation lag 等固定阈值判断“低效”并指导模型下一步。
- `runtime_evidence_frontier`：把工具结果分成 verified / partial / gap / failed 等类别，并提示模型如何处理。
- `loop_regression_baseline`：通过关键词和 step delta 推断 endpoint discovery、validation lag、final answer 是否有 verified facts。
- `context_workspace_delta`：把 tree node add/remove 当作 model-visible 上下文，容易让模型把树管理事实误认为任务进展。

最新施工原则：

1. 这些判断只保留在 Operations / Trace / Workbench debug，不默认进入 provider input。
2. Provider input 只给模型事实 transcript：用户任务、assistant 阶段消息、function_call、function_call_output、owner/tool 明示的摘要和 refs。
3. Runtime 可以记录观测事实，但不输出“应该验证 / 不要拓展 / open gap / suspected lag”这类行为指令。
4. 需要业务验收时，另建 workflow / skill evaluator；默认通用 agent loop 不做强验收。

## 2026-06-15 施工进展：事实渲染与展示口径收敛

本轮继续推进后，新增确认：

- Workbench / Trace 的 prompt route diagnostic 均同时统计 provider-visible `tool_result:` 和 compacted/omitted 工具结果，不再只识别旧的 `omitted_from_provider_transcript`。
- Context Workspace 的运行时文字从 “verified facts / unresolved gaps / do not repeat” 收敛为 “observed facts / uncertainty / materially different path”，避免把启发式观察变成模型指令。
- Browser investigation warning 的模型可见字段从 `action_required` 改为 `possible_next_step`，只提示可能路径，不宣告必须动作。
- Workbench / Operations 的最终证据文案从 “required / verified / unresolved gaps” 改为 “suggested / observed / uncertainty”，降低对模型判断的二次解释。
- `context_tree.update_plan` 的工具 schema 和工作计划内容从 `verified_facts` 迁移到 `observed_facts`，`update_reason=verified_fact` 迁移到 `observed_fact`。
- Context render / provider request metadata 的 evidence path 字段从 `final_response_requires_*`、`verified_*`、`unverified_*` 迁移到 `final_response_suggests_*`、`observed_*`、`uncertain_*`。
- Session evidence 默认 lifecycle 从 runtime 推断的 `verified` 降级为 `observed`；只有 owner 显式 `valid/validated/verified` 时才保留 verified 语义。
- Runtime evidence frontier 的 debug payload 从 `verified_count / partial_count / gap_count` 迁移为 `observed_count / uncertain_count / failed_count`；Operations runtime hints 同步展示 “Evidence observed / Evidence uncertain”。
- Tool result fact renderer 已补充通用 `result_excerpt`：当 owner 未显式给 `model_visible_payload` 时，从 `output_payload` / `details` 的 `content/data/result/body/rows/items` 等字段提取 bounded JSON/text 片段给 provider transcript；不做领域字段识别。
- Context Workspace 的树内大结果占位从 `result_body: omitted_from_prompt` 改为中性 `tool_result_ref` / `body_storage: externalized`，避免树回放时把“正文被省略”误当 provider 主输入事实。
- Provider request fallback 投影 `function_call_output` 时，text block 工具输出会转成纯文本 output，结构化 dict 才保留 JSON 字符串，减少模型阅读噪声。
- Auto LLM routing 的 `routing_input_content` 改为使用 `SessionReplayWindow.items`；修复 `filtered_session_items` 未定义导致 `requested_llm_id=auto` 分支直接 failed 的问题，并保证路由输入和 provider replay 来自同一窗口。
- `orchestration.llm_resolved` 事件新增 `routing_input_block_count` 和 `session_replay_window`，Operations LLM detail 的 Resolver section 同步展示 Routing Input Blocks / Session Replay Window，方便审计 auto 路由实际看见的上下文范围。
- Auto LLM routing 输入进一步收敛为 transcript-first：当 provider-facing transcript 已能渲染 blocks 时，不再追加同一窗口的 raw session item blocks；只有 transcript 为空时才 fallback 到 session item payload，避免路由模型被重复历史放大信号。
- Context Tree 默认根已移除 `evidence.frontier`，Session segment 不再自动生成 `Current Evidence Ledger` / `session_evidence` / browser investigation warning；事实仍保留在 session items、tool interactions、Tool owner 和 Operations debug 中，模型需要时通过正常 transcript 或显式树/工具读取。
- Context Workspace session adapter 已物理删除默认 evidence tree 的不可达入口和专用 helper：`_current_evidence_frontier_children`、`_current_evidence_children`、`_current_evidence_ledger_seed`、`_evidence_item_seed`、browser investigation warning seed/builders，以及只服务 ledger 的 read-hint/lifecycle-summary 渲染函数，避免后续误复活通用证据裁判层。
- Context Workspace orchestration metadata 已停止生成 `evidence_frontier_node`，snapshot metadata 不再写入 `evidence_frontier`，context delta 不再渲染 `evidence_delta`；运行时 `run.metadata["evidence_frontier"]` 即使存在，也只属于 orchestration/Operations debug 事实，不穿透到树化 prompt。
- LLM request metadata 不再携带 `context_delta` 原文；provider request 只保留 compact context projection、snapshot id、counts 和 refs，完整树/历史 diff 由 `context_tree.*` 显式工具读取。
- OpenAI Codex Responses adapter 已把 `context_workspace_projection` 识别为 incremental system input：runtime contract 保持在 `instructions`，compact projection 作为 input item 发送，避免树摘要变化污染 instructions fingerprint 并导致 provider-native continuation 退化。
- `ProviderTranscriptRenderer` 已作为 provider-native replay 渲染边界落地，并接入 `RunPromptInputCollector`；旧 `build_model_visible_session_item_prompt_window()` 仅作为薄委托保留，确保后续 provider replay 变更集中在 renderer。

已验证：

```bash
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_workbench_read_model.py tests/unit/test_operations_llm_read_model.py tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_operations_llm_page_uses_runtime_state_and_events
cd frontend && npm run typecheck
ruff check src/crxzipple/app/integration/context_workspace_session.py src/crxzipple/app/integration/context_workspace_orchestration/run_workspace_metadata.py src/crxzipple/modules/context_workspace/application/root_nodes.py tests/unit/test_context_workspace_tree_service.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_snapshot_metadata.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_context_tree_tool.py tests/unit/test_context_workspace_tool_adapter.py
PYTHONPATH=src pytest -q tests/unit/test_evidence_frontier_prompt.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_ui_http.py
ruff check src/crxzipple/modules/orchestration/application/evidence_frontier_prompt.py src/crxzipple/interfaces/http/ui.py src/crxzipple/modules/operations/application/read_models/llm.py tests/unit/test_evidence_frontier_prompt.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_ui_http.py
PYTHONPATH=src pytest -q tests/unit/test_tool_result_model_text.py tests/unit/test_prompt_transcript.py
ruff check src/crxzipple/modules/orchestration/application/tool_result_model_text.py tests/unit/test_tool_result_model_text.py tests/unit/test_prompt_transcript.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_tool_result_model_text.py tests/unit/test_prompt_transcript.py
ruff check src/crxzipple/app/integration/context_workspace_session.py src/crxzipple/modules/orchestration/application/tool_result_model_text.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_tool_result_model_text.py tests/unit/test_prompt_transcript.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_prompt_transcript.py tests/unit/test_tool_result_model_text.py
ruff check src/crxzipple/modules/orchestration/application/runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py
PYTHONPATH=src pytest -q tests/unit/test_prompt_input_collector.py
ruff check src/crxzipple/modules/orchestration/application/prompt_input.py tests/unit/test_prompt_input_collector.py
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_operations_llm_page_uses_runtime_state_and_events tests/unit/test_prompt_input_collector.py
ruff check src/crxzipple/modules/orchestration/application/prompt_input.py src/crxzipple/modules/operations/application/read_models/llm.py tests/unit/test_prompt_input_collector.py tests/unit/test_ui_http.py
PYTHONPATH=src pytest -q tests/unit/test_prompt_input_collector.py
ruff check src/crxzipple/modules/orchestration/application/prompt_input.py tests/unit/test_prompt_input_collector.py
PYTHONPATH=src pytest -q tests/unit/test_prompt_input_collector.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_prompt_transcript.py tests/unit/test_tool_result_model_text.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_evidence_frontier_prompt.py tests/unit/test_ui_http.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_workspace_tool_adapter.py tests/unit/test_context_workspace_session_adapter.py
ruff check src/crxzipple/modules/context_workspace/application/rendering/xml_renderer.py src/crxzipple/modules/orchestration/application/prompt_input.py tests/unit/test_prompt_input_collector.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_root_nodes.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_context_snapshot_metadata.py
ruff check src/crxzipple/modules/context_workspace/application/root_nodes.py src/crxzipple/app/integration/context_workspace_session.py tests/unit/test_context_workspace_root_nodes.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_orchestration_context_workspace_snapshot.py
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_workspace_root_nodes.py tests/unit/test_context_snapshot_metadata.py tests/unit/test_orchestration_context_workspace_snapshot.py
PYTHONPATH=src pytest -q tests/unit/test_prompt_input_collector.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_prompt_transcript.py tests/unit/test_tool_result_model_text.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_workspace_root_nodes.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_ui_http.py
ruff check src/crxzipple/app/integration/context_workspace_session.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_workspace_root_nodes.py tests/unit/test_context_snapshot_metadata.py tests/unit/test_orchestration_context_workspace_snapshot.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_context_snapshot_metadata.py
PYTHONPATH=src pytest -q tests/unit/test_prompt_input_collector.py tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_prompt_transcript.py tests/unit/test_tool_result_model_text.py tests/unit/test_context_workspace_session_adapter.py tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_workspace_root_nodes.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_context_snapshot_metadata.py tests/unit/test_ui_http.py
ruff check src/crxzipple/app/integration/context_workspace_orchestration/run_workspace_metadata.py src/crxzipple/app/integration/context_workspace_orchestration/adapter.py src/crxzipple/modules/context_workspace/application/rendering/pipeline.py tests/unit/test_orchestration_context_workspace_snapshot.py
PYTHONPATH=src pytest -q tests/unit/test_orchestration_runtime_llm_request_builder.py tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_context_snapshot_metadata.py
ruff check src/crxzipple/modules/orchestration/application/runtime_llm_request.py tests/unit/test_orchestration_runtime_llm_request_builder.py
PYTHONPATH=src pytest -q tests/unit/test_llm_adapters.py -k "codex"
ruff check src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses.py tests/unit/test_llm_adapters.py
```

## 背景

本轮对照了 CRXZipple 最新东航航班长链 run 和 Codex 同任务执行链。最新结论不是“Context Tree 节点完全缺失”，而是：

- Session / Context Workspace / Tool Interaction 节点大体存在。
- Provider input 中也存在 `function_call` / `function_call_output` 协议项。
- 关键问题在 provider-facing 渲染层：工具结果正文被大量折叠为 `result_body: omitted_from_provider_transcript`，失败证据被压成摘要或 read handle。
- Runtime evidence frontier 把很多“执行成功但任务证据失败”的步骤计成 verified/success，导致模型误判探索已足够。
- 模型看到的是内部树 delta、节点 id、成功计数和 read handle，而不是 Codex 那种连续、具体、可推理的 ResponseItem timeline。

因此本方案的核心目标是：**树仍然保留为 runtime 管理对象，但模型主要输入改为 provider-native transcript；工具结果必须可见、可追溯，但是否完成由 LLM 自己判断。**

## 观察证据

### CRXZipple 最新 run

样本 run：

- orchestration run: `780d417cfdf14d73bb30d35c02206899`
- session: `2fe5d137-b19c-4c03-9908-aae569c21181`
- final LLM invocation: `ab2d40896bde41399dbb6ba9bef8fcf5`

Provider input 中可见：

- `runtime_evidence_frontier`
- `runtime_loop_correction`
- `context_workspace_delta`
- `function_call`
- `function_call_output`

Context delta 中可见新增节点，例如：

- `session.item.2fe5d137-b19c-4c03-9908-aae569c21181.275`
- `session.tool_interaction.2fe5d137-b19c-4c03-9908-aae569c21181.call_CCcgNkpYn5RsNJkg9DkXDrH4`
- `session.item.2fe5d137-b19c-4c03-9908-aae569c21181.277`

这说明树不是完全缺节点。

但同一 invocation 中也可见：

```text
result_body: omitted_from_provider_transcript
read_full_result: use owner refs or evidence read_hints
```

并且 evidence frontier 出现：

```text
verified_count=56
gap_count=0
failed_count=1
```

而实际摘要中包含：

```text
ElementHandle.click: Element is not visible
TimeoutError clicked search
FINAL https://www.ceair.com/zh/cny/home
```

这类事实不能算“任务已验证”，只能算“工具执行过、路径失败或证据不足”。

### Codex 对照链

Codex 同任务链路具备以下特征：

- assistant 阶段消息持续进入后续上下文。
- function call / function output 连续作为 ResponseItem 回放。
- stdout/stderr、脚本结果、网络返回、页面状态直接塑造下一步行动。
- 模型能基于失败证据切换路径，例如从页面操作转向静态 JS、接口、Playwright、Edge。
- 最终即使失败，也能说明哪个接口、哪个 WAF、哪个响应导致无法验证。

CRXZipple 当前差距不是工具不存在，而是模型看不到足够具体的证据，或者被错误 evidence digest 告知“已经验证”。

## 总目标

1. 树继续作为 Context Workspace 管理对象，不删除。
2. 默认 provider request 不再把树 delta / 节点 id 当作主推理材料。
3. 模型主要看到 Codex-like ResponseItem timeline：
   - user message
   - assistant progress / reasoning summary
   - function_call
   - function_call_output
   - owner/tool 明示的结果摘要和 refs
   - final assistant answer
4. 工具结果默认保留模型判断所需的明示信息；只有超限时才压缩。
5. `runtime_evidence_frontier`、`runtime_loop_correction` 这类结论性运行时提示不默认进入 provider input。
6. Orchestration 不用通用 EvidenceGate 阻止 terminal；完成与否由 LLM 基于 transcript 判断。
7. Workbench 展示用户可读执行链，隐藏内部 debug 字段，但保留可审计事实。

## 非目标

- 不移除 Context Tree。
- 不恢复旧 orchestration facade。
- 不让 orchestration 拥有 Tool / LLM / Session / Context Workspace 原始真相。
- 不把 browser/CDP 写死为特化路径。
- 不追求历史数据兼容；允许清库重建。
- 不复制 Codex hosted web search / image generation 特权能力。

## 核心判断

当前问题分四层：

| 层级 | 判断 | 处理 |
| --- | --- | --- |
| Owner data truth | 大概率未丢 | 保持 Tool / Session / Context Workspace owner truth |
| Context Tree projection | 节点和 refs 大体存在 | 改成管理面和显式 replay 面 |
| Provider render | 关键证据被 omit / ref 化 | 本轮重点整改 |
| Runtime conclusion blocks | evidence frontier / loop correction 等启发式结论会干扰模型 | 从 provider input 移除，保留为观测 |

结论：**优先修 provider transcript rendering，砍掉 model-visible runtime 结论块，不优先补树节点，也不新增证据裁判层。**

## 要砍掉的设计

### 1. 砍掉默认 `omitted_from_provider_transcript`

当前位置：

- `src/crxzipple/modules/orchestration/application/prompt_transcript.py`
  - `_compact_tool_result_payload`
  - `_compact_tool_result_envelope_text`

当前问题：

- 只要存在 artifact refs、body removed、truncated，就倾向输出：

```text
result_body: omitted_from_provider_transcript
read_full_result: use owner refs or evidence read_hints
```

模型拿不到 stderr、stdout、网络响应、页面状态，无法做下一步判断。

目标：

- 默认输出“任务可判定摘要 + 关键原文片段”。
- 只有超过预算时才输出 omitted。
- omitted 时也必须保留 failure signature 和 evidence digest。

### 2. 砍掉 tool exit code 等价 success

当前位置：

- ToolRun outcome / result envelope
- Orchestration evidence frontier 写入逻辑
- `src/crxzipple/modules/orchestration/application/evidence_frontier_prompt.py`

当前问题：

- command exit code 0 只是工具执行成功，不是任务证据成功。
- 浏览器点击失败、页面停留首页、接口空响应等仍可能被包进 success。

目标：

- `tool_run_status` 只能表示工具生命周期事实，不转写成任务完成判断。
- 如 owner/tool 显式给出 `task_evidence_status`，只作为普通明示字段渲染；runtime 不自行推断或升级为 `verified`。

### 3. 砍掉树 delta 作为模型主上下文

当前位置：

- Context Workspace render snapshot metadata
- `context_workspace_delta` prompt block
- prompt preview / provider request assembly

当前问题：

- 模型看到 `added_rendered_nodes`、`removed_rendered_nodes`、`session.item.*`，但这些不是行动证据。
- 树结构占据上下文，反而掩盖 active task。

目标：

- 树 delta 进入 diagnostics / operations / debug。
- 模型默认只看到 compact context projection。
- 完整树通过 `context_tree.*` 工具显式读取。

### 4. 砍掉“read handle 自助补证据”的默认假设

当前问题：

- 模型并不一定会主动调用 read handle。
- 当前轮需要的关键证据如果只在 read handle 里，模型会断片。

目标：

- read handle 是补充机制，不是核心证据交付机制。
- 最近关键工具结果必须直接 provider-visible。

### 5. 砍掉过强 evidence frontier 结论

当前问题：

```text
gap_count=0
Use this frontier to avoid repeating evidence paths
```

在证据判断不可靠时，这会抑制探索。

目标：

- `runtime_evidence_frontier` 不再作为 model-visible prompt block 注入。
- 相关计数和分类只进入 metadata / Operations / Trace。
- 如需给模型上下文，只给 recent tool result 事实，不给 verified/gap/failed 结论。

### 6. 砍掉 runtime loop correction 作为模型指令

当前位置：

- `src/crxzipple/modules/orchestration/application/loop_correction.py`
- `src/crxzipple/modules/orchestration/application/loop_regression_baseline.py`

当前问题：

- `tool_only_streak` 只能说明最近几轮缺少可见文字，不等价于低效。
- `validation_lag` 依赖 endpoint discovery / validation 的启发式判定，不可穷举。
- 这些判断进入 system message 后，会压低模型正常探索意愿。

目标：

- `runtime_loop_correction` 不再作为 model-visible prompt block 注入。
- loop health / baseline 只进入 Operations / Trace / Workbench debug。
- 运行时只记录观测事实，不给“先验证再拓展”“不要重复”等行为指令。

## 要新增的组件

## 1. ProviderTranscriptRenderer

### 归属

建议放在：

```text
src/crxzipple/modules/orchestration/application/provider_transcript_renderer.py
```

Orchestration 负责 request assembly，但不拥有原始事实。Renderer 输入来自 owner query/ports，输出 provider-neutral `LlmInputItem[]`。

### 输入

- stable instructions ref
- SessionItem replay window
- ToolRun result envelope projection
- Context compact projection
- recent tool result refs / owner-visible result summaries
- active task state
- current turn delta

### 输出

Provider-neutral timeline：

```text
LlmInputItem(message:user)
LlmInputItem(message:assistant_progress)
LlmInputItem(reasoning_summary)
LlmInputItem(function_call)
LlmInputItem(function_call_output)
LlmInputItem(evidence_note)
LlmInputItem(message:assistant_final)
```

### 渲染原则

- `tools` 仍然作为 provider tool schema 单独传，不混进 transcript。
- `context_tree.*` 只有实际被模型调用时才进入 timeline。
- tree node id 默认不进入 provider-visible text。
- tool output 使用“关键证据优先”的结构化文本。

### 示例

目标输出：

```text
tool: exec
command: node /tmp/check-ceair.js
exit_code: 0
summary: Playwright reached ceair home page but search button click failed.
current_url: https://www.ceair.com/zh/cny/home
failure_signature:
- ElementHandle.click: Element is not visible
- TimeoutError after opening date picker
open_gaps:
- no flight list
- no price
- need alternative route: mobile endpoint, network capture, or script extraction
```

而不是：

```text
result_body: omitted_from_provider_transcript
read_full_result: use owner refs or evidence read_hints
```

## 2. EvidenceOutcomeClassifier（已取消）

最新决策：取消通用 runtime 侧 EvidenceOutcomeClassifier。工具结果渲染只展示 owner/tool 明示字段，不根据 stderr/URL/HTTP 状态自动判定 `verified/blocked/needs_followup`。

禁止恢复 `src/crxzipple/modules/orchestration/application/evidence_outcome.py` 作为默认 agent loop 组件。未来若某类任务需要业务验收，只能作为 workflow / skill evaluator 明确接入。

## 3. ToolResultFactRenderer

### 归属

建议放在 Tool application 或 Orchestration application 的 adapter 层：

- Tool owner 负责原始 result envelope。
- Orchestration 可拥有“tool result fact rendering”投影，只做字段选择和摘录，不做任务验收判断。

建议先落在：

```text
src/crxzipple/modules/orchestration/application/tool_result_model_text.py
```

当前 helper 文件名可先沿用，后续稳定后重命名为 fact/result rendering 语义并拆 port。

### 提取内容

- command
- exit code
- stdout head/tail
- stderr head/tail
- exception names
- URL / endpoint / method
- HTTP status
- bounded JSON/text result excerpt
- browser current URL / title / visible text excerpt
- artifact refs
- read handles
- owner/tool 明示的 key facts

### 预算策略

默认 provider-visible：

- 最近 3 个 tool result：关键摘要 + stderr/stdout 片段。
- owner/tool 明示 `failure_signatures` 时保留 failure signature。
- owner/tool 明示 `key_facts` / `verified_facts` 时保留这些事实。
- 大 JSON：保留 bounded excerpt、artifact refs、read handles，不全量塞。

## 4. EvidenceLedger（已取消）

最新决策：不新增通用 EvidenceLedger。现有 Tool / Session / Context Workspace / Operations 继续持有各自事实；Orchestration 不再维护一套跨任务“证据裁判账本”。

## 5. EvidenceGate（已取消）

最新决策：取消通用 runtime 侧 EvidenceGate。Orchestration 不在默认 agent loop 中用 required terms 或 evidence frontier 阻止 terminal；模型自行判断是否完成。业务强验收以后由 workflow / skill evaluator 提供。

禁止恢复 `src/crxzipple/modules/orchestration/application/evidence_gate.py` 作为默认 agent loop 组件。

## 要修改的模块

## 1. Orchestration

### 文件

- `src/crxzipple/modules/orchestration/application/prompt_transcript.py`
- `src/crxzipple/modules/orchestration/application/prompt_input.py`
- `src/crxzipple/modules/orchestration/application/runtime_llm_request.py`
- `src/crxzipple/modules/orchestration/application/engine.py`
- `src/crxzipple/modules/orchestration/application/engine_llm_invoker.py`
- `src/crxzipple/modules/orchestration/application/engine_session_recorder.py`
- `src/crxzipple/modules/orchestration/application/evidence_frontier_prompt.py`

### 改动

- 引入 `ProviderTranscriptRenderer`。
- 将 `_compact_tool_result_payload` 从默认 omit 改为 tool-result-aware render。
- `runtime_evidence_frontier` 不再参与 provider prompt；若保留则降级为 runtime observation/debug projection。
- `prompt_input.py` 中 `render_mode=ref` 不得吞掉 protocol-required tool result 的关键证据。
- 不在 `engine.py` 默认 terminal path 调用 EvidenceGate；是否完成由 LLM 自行判断。
- execution item summary 增加：
  - `provider_visible_excerpt_chars`
  - `omitted_body_reason`
  - `model_visible_result_refs`

## 2. Tool

### 文件

- `src/crxzipple/modules/tool/application/result_envelope.py`
- `src/crxzipple/modules/tool/application/worker_service.py`
- `src/crxzipple/modules/tool/domain/entities.py`
- `tools/command/tool.yaml`
- `tools/command/README.md`

### 改动

- Tool result envelope 明确区分：
  - raw body ref
  - provider-visible excerpt
  - user-visible summary
  - trace-visible full refs
- command tool 输出保留：
  - stdout excerpt
  - stderr excerpt
  - exit code
  - timeout
  - working directory
  - command string
- exec description 强化“本地探索运行时”语义，但不特化到某个网站。

## 3. Context Workspace

### 文件

- `src/crxzipple/modules/context_workspace/application/rendering/xml_renderer.py`
- `tools/context_tree/tool.yaml`
- `src/crxzipple/modules/context_workspace/application/root_nodes.py`

### 改动

- XML renderer 的 tree/debug 读句柄提示改为 `<full_result_refs>`，不再使用命令式 `<read_full_result>`；它仍不作为默认 provider transcript 主体。
- 新增或强化 tree replay/read 工具：
  - `context_tree.render_current`
  - `context_tree.read_evidence`
  - `context_tree.diff_since`
- 默认 request 只注入 compact context projection：
  - active task
  - known slots
  - available capabilities summary
  - explicit open gaps
- 不把 `added_rendered_nodes` / `removed_rendered_nodes` 暴露为普通 model-visible system text。

## 4. LLM

### 文件

- `src/crxzipple/modules/llm/application/adapters.py`
- `src/crxzipple/modules/llm/domain/value_objects.py`
- `src/crxzipple/modules/llm/infrastructure/adapters/openai_responses.py`
- `src/crxzipple/modules/llm/infrastructure/adapters/openai_codex_responses.py`
- `src/crxzipple/modules/llm/interfaces/dto.py`

### 改动

- `LlmInputItem` 支持 evidence note / assistant progress / reasoning summary 的无损保存和回放。
- Adapter 保持 provider-native shape，不把 ResponseItem 降级成普通 chat messages。
- Provider request preview 增加：
  - provider-visible raw excerpt count
  - omitted result count
  - evidence item count
  - replay item types
- HTTP / WebSocket continuation 差异保持明确，不再向不支持的 HTTP endpoint 发送 unsupported field。

## 5. Session

### 文件

- `src/crxzipple/modules/session/application/services.py`
- `src/crxzipple/modules/session/domain/*`

### 改动

- SessionItem 保存 response item 原型：
  - role / kind
  - provider item type
  - call_id
  - output item id
  - user_visible
  - model_visible
  - trace_visible
- assistant progress 不折成普通最终 answer。
- tool result item 保存 provider-visible excerpt 和 raw refs。

## 6. Operations / Workbench

### 文件

- `src/crxzipple/modules/operations/application/read_models/llm.py`
- `src/crxzipple/modules/operations/application/read_models/orchestration.py`
- `src/crxzipple/modules/orchestration/application/read_models/workbench.py`
- `frontend/src/pages/workbench/WorkbenchPage.vue`
- `frontend/src/pages/trace/TracePage.vue`
- `frontend/src/pages/operations/modules/LlmOperationsPage.vue`

### 改动

- Workbench timeline 展示：
  - 用户任务
  - 模型阶段总结
  - 工具调用
  - 工具结果证据
  - 失败路径
  - 下一步
  - 最终回答
- 不展示：
  - `none; end_turn=-; follow_up=false`
  - `session.item.xxx`
  - `added_rendered_nodes`
  - provider-only debug 字段
- LLM invocation detail 可展开：
  - normalized transcript
  - provider actual request preview
  - tool result refs / runtime debug observations
  - omitted/raw excerpt diagnostics

## Provider Transcript 目标格式

### Tool result owner 明示关键事实

```text
tool_result:
  tool: exec
  status: ok
  command: node ceair-price.js
  key_facts:
    - origin: KMG
    - destination: Shanghai
    - date: 2026-06-21
    - flight: MU5801
    - ticket_price: 700
    - tax_fee: 200
    - total_price: 900
    - currency: CNY
  source:
    - official endpoint: /m-base/sale/shoppingv2/querySummaryPrice
    - transaction_id: ...
  stdout_excerpt:
    ...
```

### Tool result owner 明示失败摘要

```text
tool_result:
  tool: exec
  status: ok
  command: node desktop-search.js
  summary: Desktop site loaded but no flight list or price was obtained.
  current_url: https://www.ceair.com/zh/cny/home
  failure_signatures:
    - ElementHandle.click: Element is not visible
    - TimeoutError while opening date picker
  open_gaps:
    - no flight list
    - no price
  recommended_next_actions:
    - inspect mobile site resources
    - replay official endpoint
    - use browser network capture if available
```

### Tool result owner 明示阻断事实

```text
tool_result:
  tool: exec
  status: ok
  summary: Official endpoint was identified, but WAF challenge blocked replay.
  failure_signatures:
    - HTTP 412
    - aliyun WAF challenge
  key_facts:
    - endpoint path exists in official JS bundle
  open_gaps:
    - response body does not contain flight prices
```

## Runtime Observation Debug 格式

替换旧的 model-visible 结论格式：

```text
Counts: verified=56, gaps=0, failed=1
```

目标格式仅用于 Trace / Operations / Workbench inspector，不默认进入 provider input：

```text
Runtime observation:

Observed tool facts:
- Official desktop home page loaded: https://www.ceair.com/zh/cny/home

Owner-explicit gaps:
- No flight list observed.
- No ticket price observed.
- Date picker click failed.

Observed failed paths:
- Desktop DOM interaction failed: ElementHandle.click: Element is not visible.

Debug note:
- This block is for human inspection only; do not inject as model instructions.
```

## 分阶段施工计划

## Phase 0. 基线冻结

- [ ] 记录最新失败 run id、session id、LLM invocation id。
- [ ] 保存 provider normalized request preview。
- [ ] 保存 Workbench timeline 截图或 JSON。
- [ ] 记录 Codex 对照链关键步骤。
- [ ] 把基线写入 `agent-runtime-contract-upgrade-progress-dashboard-20260611.md` 或专项审计记录。

验收：

```bash
source scripts/dev/infra-env.sh
PYTHONPATH=src python -m crxzipple.main orchestration prompt-preview <run_id>
PYTHONPATH=src python -m crxzipple.main llm get-invocation <invocation_id>
```

## Phase 1. Tool result fact rendering

- [x] 新增 `tool_result_model_text.render_tool_result_model_text` 基础版，语义限定为事实渲染 helper。
- [x] 覆盖 command stdout/stderr/exit code。
- [x] 覆盖 browser evidence / endpoint / method / artifact refs 的渲染入口。
- [x] 覆盖结构化 `output_payload` / `details` 的 bounded `result_excerpt`，避免 API/页面状态结果只剩 read handle。
- [x] 覆盖 large output excerpt policy / artifact refs / read handles 的 provider-visible 提示。
- [x] 单测 command success / command failure / browser timeout / artifact-only result / structured result excerpt 的 owner envelope 生成。
- [x] 单测 tool-result-aware render helper 和 prompt transcript 接入。
- [x] 移除代码路径里的旧 `result_body: omitted_from_prompt` / `omitted_from_provider_transcript` marker；历史问题样例只保留在本文档观察证据中。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_prompt_transcript.py tests/unit/test_tool_execution.py
```

## Phase 2. Evidence outcome classifier（取消）

- [x] 已拆除 `EvidenceOutcomeClassifier` 基础版。
- [x] 不再由 runtime 根据 stderr/URL/HTTP 状态自动推断 `task_evidence_status`。
- [x] 工具结果只渲染 owner/tool 明示的 status、key_facts、failure_signatures、gaps。
- [ ] 若未来需要业务验收，交给 workflow / skill evaluator，不进入通用 agent loop。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_evidence_frontier_prompt.py tests/unit/test_orchestration_loop_regression_baseline.py
```

## Phase 3. Provider transcript renderer

- [x] 新增 `ProviderTranscriptRenderer`。
- [x] `RunPromptInputCollector` 通过 `ProviderTranscriptRenderer.render_session_items()` 构造 provider transcript；旧函数仅委托 renderer。
- [x] 替换 `_compact_tool_result_payload` 默认 omit 策略。
- [x] provider input 中输出 tool-result-aware `function_call_output` 基础文本。
- [x] 保留 read handles，但不作为唯一证据。
- [x] prompt transcript stats 保留 omitted/artifact/read handle counters，并通过 tool result fact renderer 输出 excerpt。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_prompt_transcript.py tests/unit/test_orchestration_runtime_llm_request_builder.py
```

## Phase 4. Runtime conclusion block 降级

- [x] 停止把 `runtime_evidence_frontier` 注入 provider messages。
- [x] 停止把 `runtime_loop_correction` 注入 provider messages。
- [x] `evidence_frontier` / `loop_health` 继续写入 request metadata、Operations、Trace、Workbench debug。
- [x] `evidence_frontier_prompt.py` 和 `loop_correction.py` 只保留 payload builder，不再暴露 prompt 插入函数。
- [ ] provider input 若需要提示，只给事实列表，例如 recent tool results，不给 verified/gap/failed 分类和行为建议。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_context_workspace_snapshot.py tests/unit/test_orchestration_runtime_llm_request_builder.py
```

## Phase 5. Terminal evidence gate（取消）

- [x] 已拆除 `EvidenceGate` 基础版。
- [x] 不接入 engine，不用 required terms 阻止 terminal。
- [x] 不生成 runtime terminal evidence corrective continuation。
- [ ] 未来若需要强验收，由 workflow / skill evaluator 提供独立验收，不作为默认 agent loop。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_orchestration_tools.py tests/unit/test_loop_correction.py
```

## Phase 6. Context Tree delivery 收口

- [x] 默认 provider input 不展示 tree node id delta。
- [x] tree delta 进入 request metadata / trace/debug，不作为 provider message。
- [x] `context_tree.render_current` / `context_tree.diff_since` 显式工具输出可进入 timeline。
- [x] compact context projection 去掉 `included_node_ids` / `mirrored_node_ids` / ref `node_id` / `source_ref` 等内部树标识。
- [ ] compact context projection 保留 active task / known slots；open gaps 仅在 owner/tool 明示时进入。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_context_workspace_tree_service.py tests/unit/test_context_tree_tool.py tests/unit/test_context_render_xml_renderer.py
```

## Phase 7. Workbench / Operations 可视化

- [x] Workbench timeline 使用 tool-result-aware item，并复用 provider-visible tool result renderer。
- [x] Workbench 主 timeline 不再追加 `evidence_frontier` internal debug placeholder。
- [x] LLM linked entity detail 显示 replay input 中的 tool result excerpt count / sample。
- [x] Workbench LLM linked entity replay 面板展示 tool result excerpt count / sample。
- [x] Operations LLM detail 显示 tool result item / compacted / omitted / artifact ref / read handle counters。
- [x] Operations runtime debug 区域从 `Runtime Hints` 降级命名为 `Runtime Observations`。
- [x] Operations LLM detail 显示 provider replay 中 tool result excerpt count。
- [x] Operations LLM detail 显示 provider-visible tool result excerpt sample。
- [x] i18n 补齐 runtime observation 用户可见文案。
- [x] Workbench prompt route diagnostic 同时统计 provider-visible `tool_result:` 与 compacted/omitted 结果。
- [x] Trace prompt route diagnostic 同时统计 provider-visible `tool_result:` 与 compacted/omitted 结果。
- [x] Workbench / Trace 最终证据诊断文案降级为 suggested / observed / uncertainty。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_read_model.py
cd frontend
npm run typecheck
npm run build
npm run audit:operations-layout
```

## Phase 8. 东航回归任务

用同一类任务回归：

```text
去东航官网给我查下昆明到上海周日的票。请自己探索可用本地能力，优先使用官网真实页面或官网实际接口；如果页面 JS/DOM 受限，继续用 shell/脚本/浏览器自动化/CDP/网络请求等方式查证。最后给出航班/价格/查询路径，说明证据来源。
```

验收标准：

- 模型能看到上轮工具失败原因。
- 模型不会把首页停留当完成。
- 模型能基于 stderr/stdout 换路径。
- Workbench 能看到阶段总结。
- final answer 要么给出航班/价格/来源，要么明确 blocked evidence，不编造。

## 数据库与兼容策略

用户已明确：

- 不考虑历史数据兼容。
- 开发前可以清库重建。
- 目标是 agent 最佳效果，不被旧 schema 包袱限制。

因此：

- 可新增 migration。
- 可修改 SessionItem / LLM invocation payload 结构。
- 可删除旧 fallback 字段。
- 不新增旧结构 shim。

## 风险与防回归

## 1. 输出太大导致 token 膨胀

控制方式：

- tool result fact renderer 做 head/tail/keyword excerpt。
- owner/tool 明示 key facts 结构化。
- 大 body 用 artifact refs + 关键片段。
- provider request preview 记录 excerpt chars。

## 2. Runtime 误做业务结论

控制方式：

- 默认 agent loop 不做 `verified/blocked/needs_followup` 推断。
- 只渲染 owner/tool 明示字段。
- 业务验收必须进入 workflow / skill evaluator，不进入通用 runtime prompt。

## 3. 树被弱化导致模型不知道上下文

控制方式：

- compact context projection 常驻。
- `context_tree.*` 工具可显式 replay。
- active task / known slots 进入默认 input；open gaps 只在 owner/tool 明示时进入。

## 4. UI 再次展示内部碎片

控制方式：

- Workbench read model 显式区分 user_visible/model_visible/trace_visible。
- internal debug 只进 inspector。
- i18n 文案覆盖所有状态。

## 5. Provider 差异被混淆

控制方式：

- HTTP / WebSocket continuation capability 分离。
- provider actual payload preview 可观察。
- unsupported provider option 禁止静默发送。

## Checklist 总表

### Must Cut

- [x] 默认 `result_body: omitted_from_provider_transcript`
- [x] `runtime_evidence_frontier` model-visible prompt block
- [x] `runtime_loop_correction` model-visible prompt block
- [x] tree node id delta 默认 model-visible
- [x] read handle 作为唯一证据
- [x] runtime 侧对任务完成/证据充分的不可穷举判断不再默认 model-visible

### Must Add

- [x] `ProviderTranscriptRenderer`
- [x] Tool result fact rendering 基础 helper
- [x] `context_tree.render_current` / `context_tree.diff_since` 等通用树回放工具

### Must Modify

- [x] `prompt_transcript.py`
- [x] `evidence_frontier_prompt.py`
- [x] `prompt_input.py`
- [x] `provider_request.py`
- [x] `engine.py`
- [ ] Tool result envelope
- [x] Session / Context Workspace evidence lifecycle 默认观测语义
- [ ] SessionItem response item storage
- [x] Operations LLM projection
- [x] Workbench timeline

### Must Verify

- [x] Unit tests pass for prompt transcript / tool result rendering / orchestration request.
- [x] Frontend typecheck pass.
- [x] Frontend build pass.
- [ ] Prompt preview 不再以 tree delta 为主。
- [ ] LLM invocation provider input 包含关键 stdout/stderr/tool result excerpt。
- [ ] 东航任务不再把失败路径当完成。

## 与既有文档关系

本文件是以下文档之后的 remediation 施工入口：

- [codex-capability-alignment-development-plan-20260614.md](codex-capability-alignment-development-plan-20260614.md)
- [provider-native-continuation-and-tree-replay-tool-plan-20260614.md](provider-native-continuation-and-tree-replay-tool-plan-20260614.md)
- [orchestration-codex-like-request-assembly-plan-20260614.md](orchestration-codex-like-request-assembly-plan-20260614.md)
- [context-workspace-tree-projection-plan-20260614.md](context-workspace-tree-projection-plan-20260614.md)
- [llm-session-response-item-replay-plan-20260614.md](llm-session-response-item-replay-plan-20260614.md)
- [workbench-operations-response-item-observability-plan-20260614.md](workbench-operations-response-item-observability-plan-20260614.md)

若旧文档仍描述“首轮完整树默认入 prompt”或“tool result 默认 omitted”，以后以本文为准。
