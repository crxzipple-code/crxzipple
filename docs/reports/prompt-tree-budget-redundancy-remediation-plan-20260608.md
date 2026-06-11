# Prompt Tree Budget / Redundancy Remediation Plan 2026-06-08

本文是本轮 Prompt Tree 膨胀治理和长内容折叠压缩的施工入口。它承接
[context-workspace-session-segment-compaction-plan-20260601.md](context-workspace-session-segment-compaction-plan-20260601.md)、
[prompt-engineering-runtime-contract-upgrade-plan-20260605.md](prompt-engineering-runtime-contract-upgrade-plan-20260605.md) 和
[context-workspace-tree-schema-convergence-plan-20260607.md](context-workspace-tree-schema-convergence-plan-20260607.md)。

## 背景

CRXZipple 当前已经把历史对话、工具能力、skills、memory、artifacts、agent home 和 runtime
contract 收敛到 Context Workspace / Context Tree。orchestration 通过
`PromptInputCollector` 收集运行输入，再由 Context Workspace 生成 render snapshot，最后把
Context Tree prompt body 和 provider attachments 交给 LLM provider。

这个主方向正确，但最近的长 browser 执行链暴露出一个新问题：Context Tree 已经成为 prompt
主体后，provider-native transcript 仍然保留了完整当前 run 工具链；同时 Context Tree 又把同一批
tool call/result 投影成 `session.tool_interaction` 节点。于是链路越长，prompt 近似线性膨胀，
模型注意力被旧观察和重复工具结果吞掉。

本轮目标不是新增另一套 prompt 压缩系统，而是把现有 Context Tree 主链收干净：

- 保持 Context Tree 是 prompt 主体。
- 保持 provider-native messages 只承担当前 turn / tool protocol 必须承担的部分。
- 把已消费的长工具结果折叠成树上的语义摘要和 owner refs。
- 防止 tool schema mirror 一次性过宽。
- 让模型能够集中处理当下任务，同时不丢历史证据和可追溯引用。

## 本轮实测证据

最近一次真实 LLM invocation：

```text
invocation: d141f6ed5ae14a2cb0806d7ec00755d3
messages: 106
tool_schemas: 45
system(context_workspace): 176,032 chars
provider-native assistant/tool transcript: about 65,000 chars
```

对应最新 context render snapshot：

```text
snapshot: ctxsnap_4195c01231634af9b369e6f38d903fa2
prompt_body: 176,032 chars
session.current: about 125,749 chars
tools.available: about 34,497 chars
context.instructions: about 12,063 chars
included nodes: 151
session.tool_interaction nodes: 52
mirrored tool schemas: 45
```

最重的节点类型：

- `session.messages.current` 估算约 21,114 tokens。
- 多个 `session.tool_interaction.*` 节点单个可达 1,000-2,000 tokens。
- `runtime.contract` 约 1,793 tokens，虽然偏长，但不是最大问题。
- `browser.observe`、`browser.form.fill`、`browser.overlay.select` 等 browser 工具结果重复进入
  provider transcript 和 Context Tree。

## 当前代码定位

### Provider-native transcript 仍交付完整当前 run

[prompt_input.py](../../src/crxzipple/modules/orchestration/application/prompt_input.py)
在构建 prompt surface 时读取 active session messages：

```text
PromptInputCollector.build()
  -> session_service.get_session_with_messages(active_session_only=True)
  -> _current_run_transcript()
  -> build_current_run_prompt_window()
```

关键位置：

- `PromptInputCollector.build()` 读取 active session messages。
- `_current_run_transcript()` 从当前 inbound message 之后取全部当前 run messages。

这条链路对 provider tool protocol 必要，但不应该长期携带已经被模型消费过的长工具结果。

### Context Tree 又渲染同一批工具交互

[engine.py](../../src/crxzipple/modules/orchestration/application/engine.py) 会把 Context Workspace
render snapshot 插入 provider system message：

```text
_prompt_with_context_workspace_body()
  -> LlmMessage(role=SYSTEM, content=context_render_snapshot.prompt_body)
```

[context_workspace_session.py](../../src/crxzipple/app/integration/context_workspace_session.py) 又把
session message 中的 function call + tool result 配对为 `session.tool_interaction`：

```text
_message_node_seeds()
  -> _tool_interaction_node_seed()
```

当前 `_tool_interaction_node_seed()` 默认：

- `collapsed=False`
- `loaded=True`
- `content` 包含 arguments、result、error

这导致 tool result 同时通过 provider-native tool message 和 tree node 两条路径进入 LLM。

### Tool schema mirror 面过宽

[context_workspace_tool.py](../../src/crxzipple/app/integration/context_workspace_tool.py) 中 tool
function node 默认：

```text
ContextNodeState(schema_enabled=True, loaded=True)
```

只要展开 browser source/group，许多 function schema 会被
[services.py](../../src/crxzipple/modules/context_workspace/application/services.py) 的
`_render_provider_attachments()` 镜像到 provider tool schemas。

这不是多路径实现，但会让模型一次看到过宽的工具面，削弱按能力逐步展开的设计收益。

### Estimate 可能重复计量父子节点

`_aggregate_estimate()` 当前直接累加所有 visible nodes 的 estimate。`session.messages.current`
会估算整段 active messages，子级 `session.message` / `session.tool_interaction` 又各自估算内容。

这会影响预算判断和 Operations 指标。真实 prompt 本身也确实很大，但 estimate 也需要从
“节点总和”升级为“rendered content budget”。

## 设计原则

### 1. 不新增冗余 prompt 路径

禁止方向：

```text
新增 browser 专属 prompt 总结通道。
新增 orchestration 内部 prompt 压缩器再拼一次历史。
新增 provider adapter fallback 来绕过 Context Tree。
把 tool result 同时完整保存在 direct transcript、Context Tree、单独 evidence prompt 三处。
```

推荐方向：

```text
Context Tree 仍是 prompt 主体。
Provider-native messages 只保留协议尾巴。
长结果的原文留在 owner module 事实中。
Context Tree 只保留摘要、关键字段、引用和可展开 handle。
模型需要回看原文时，调用 owner query/tool 读取。
```

### 2. Current run 和历史 segment 分开治理

历史 segment 已经有 compaction/rotation 方向；本轮重点是 active run 内部的长链治理。

语义分层：

```text
session.current
  current_goal
  frontier
    latest unconsumed tool call/result protocol tail
  evidence_ledger
    verified facts and decisions
  tool_phases
    collapsed groups for consumed tool interactions
  raw_refs
    session_message_id / tool_run_id / artifact_id references
```

`frontier` 是当前模型下一步必须直接处理的内容。`evidence_ledger` 和 `tool_phases` 是可追溯上下文，
默认不把完整长结果展开。

### 3. 折叠不是分页

不要恢复机械分页：

```text
messages 1-8
messages 9-16
messages 17-24
```

这种分页容易让模型丢失上下文，也不能表达“哪个内容还重要”。本轮应采用语义折叠：

- 一个 browser investigation 阶段。
- 一个 failed approach 阶段。
- 一个 verified API endpoint 阶段。
- 一个 result extraction 阶段。
- 一个 unresolved evidence gap 阶段。

每个折叠节点必须包含：

- 摘要。
- 关键事实。
- 状态：verified / failed / superseded / unresolved。
- owner refs：`session_message_id`、`tool_call_id`、`tool_run_id`、`artifact_id`、`target_id` 等。
- 可展开动作或 owner 查询建议。

### 4. 长内容留 owner，树上留证据索引

Context Tree 不复制大结果。它应该像 DOM / IDE outline 一样显示结构和可操作 handle。

长内容包括：

- browser snapshot / observe 结果。
- network response body。
- script source。
- evaluate 大 JSON。
- 文件内容。
- 大型 tool stdout/stderr。
- 图片和二进制附件。

处理规则：

- 小而关键的结果可直接进 `frontier`。
- 中等结果提取关键字段和摘要。
- 大结果必须落 artifact 或 owner fact，并在树上保引用。

### 5. Tool schema 按能力渐进启用

默认可见的是 capability group / bundle，而不是所有 function schema。

推荐层级：

```text
tools.available
  browser
    navigation
    observation
    runtime_investigation
    network_capture_replay
    script_source_insight
    storage_session_state
    diagnostics_trace
```

展开 group 只显示能力说明和候选 function。只有 agent 显式选择或 runtime 根据任务策略启用时，才
mirror function schema。

`context_tree.*` 基础控制工具可以保持默认可用，因为它是模型操作 Context Tree 的入口。

## 目标状态

一次长 browser task 的 prompt 应该收敛为：

```text
SYSTEM:
  <context_tree>
    <context_instructions>...</context_instructions>
    <execution.current>...</execution.current>
    <session.current>
      <frontier>
        latest relevant unconsumed tool result
      </frontier>
      <evidence_ledger>
        confirmed endpoint / payload / result shape
      </evidence_ledger>
      <tool_phases>
        collapsed browser interaction phase
        collapsed runtime investigation phase
      </tool_phases>
    </session.current>
    <tools.available>
      visible groups and selected function schemas only
    </tools.available>
  </context_tree>

USER:
  latest user instruction

ASSISTANT / TOOL:
  only protocol-required current tail

PROVIDER TOOLS:
  context_tree controls
  task-relevant enabled function schemas
```

模型不丢历史，因为 tree 上仍然有阶段摘要和 refs；模型不被历史淹没，因为完整原文不默认进入
prompt。

## 施工计划

### Phase 1：Prompt Budget Audit 固化

- [x] 为 LLM invocation / render snapshot 增加稳定 budget breakdown query。
- [x] 在 Operations / Workbench prompt preview 中展示：
  - `system(context_workspace)` chars/tokens。
  - provider-native transcript chars/tokens。
  - mirrored schema count/tokens。
  - duplicate delivery warning。
- [x] top context nodes by rendered chars/tokens 已接入 `estimate_breakdown.top_rendered_nodes`；
  口径为单节点局部 XML 渲染估算，不把子节点重复计入父节点。
- [x] 增加单元测试覆盖 render snapshot metadata 中的：
  - direct transcript count。
  - tree tool interaction count。
  - mirrored tool schema count。
  - rendered content estimate。

验收：

- 能在不手写数据库脚本的情况下解释一次 prompt 为什么变大。
- 最近 invocation 的 prompt 结构能被 UI 或 API 直接查看。

2026-06-08 进度：

- [x] Context render snapshot metadata 已记录 direct transcript chars/tokens、
  rendered prompt chars/tokens、mirrored schema estimated tokens、
  estimated provider prompt tokens 和 duplicate delivery warning。
- [x] 单元测试已覆盖 render snapshot budget metadata 的核心字段。
- [x] Context Workspace Operations read model 已新增 `prompt_budget` section，暴露
  provider/tree/direct/schema token 估算和 duplicate delivery risk。
- [x] LLM invocation `request_metadata` 已接入 rendered prompt、direct transcript、schema mirror、
  estimated provider prompt、schema budget status 和 duplicate delivery risk 等预算字段。
- [x] Workbench prompt preview / invocation-derived preview 已合并 snapshot metadata 和
  provider request metadata 作为预算显示来源，真实调用详情不再只能在 options JSON 中查看预算字段。
- [x] `/context-workspaces/by-session/{session_key}/render` 已作为稳定 render breakdown query，
  返回 `estimate_breakdown`、`provider_attachment_report`、`provider_attachments`、
  `mirrored_node_ids`、`runtime_contract` 和 tree schema/root metadata。
- [x] Workbench / Trace prompt preview 的最终 provider request 明细已补强：
  XML、provider-native messages、mirrored tool schemas、provider options 和 provider
  attachments 使用同一份 prompt preview / snapshot fallback 口径展示。

### Phase 2：Provider-native Transcript 收成协议尾巴

- [x] 明确 normal turn provider-native transcript 规则：
  - 当前 user message 必须保留。
  - 尚未被下一次 LLM 消费的 assistant tool call / tool result 必须保留。
  - 已消费的旧 tool call/result 不再完整进入 provider-native transcript。
- [x] 为 execution chain 增加可判断的 consumed frontier 信息，不从裸 session 历史猜测。
- [x] 修改 `build_current_run_prompt_window()` 及其调用方，使其只返回 current protocol tail。
- [x] 保留 provider API 必需的 tool call/result pairing，避免破坏 OpenAI/Anthropic tool protocol。
- [x] 为 tool call 批次添加回归测试：
  - 同一次 LLM 返回多个 tool call。
  - 多个 tool result 全部到齐后再进入下一次 LLM。
  - 已消费结果不再重复出现在后续 provider-native transcript。

验收：

- 长 browser run 中 provider-native `assistant/tool` chars 不再随全量历史线性增长。
- tool protocol 不报 orphan function call / missing tool result。

2026-06-08 进度：

- [x] Normal turn provider-native transcript 规则已落地：
  - 当前 inbound user message 通过 `preserve_message_ids` 强制保留。
  - 上一次 LLM 已消费到的 active-session sequence 由 execution chain
    `summary_payload.llm_transcript_consumption.direct_transcript_sequence_range` 计算。
  - `build_current_run_prompt_window()` 只保留 consumed frontier 之后的 tool protocol tail。
  - function call 只有在对应 tool result 仍在当前窗口内时才会进入 provider transcript，避免
    orphan function call / missing tool result。
- [x] LLM invocation `request_metadata` 已记录本次 direct transcript 实际消费的
  `direct_transcript_message_refs`、`direct_transcript_sequence_range`、
  `direct_tool_protocol_refs`、`direct_tool_protocol_call_ids` 和 `current_inbound_ref`。
  这些字段是后续安全生成 consumed frontier / protocol tail 的 owner fact。
- [x] 回归测试已覆盖 helper metadata 和真实 orchestration inline tool loop 中的持久化 invocation
  metadata。
- [x] `RunExecutionService` 已把 LLM request metadata 中的 transcript consumption 子集写入
  execution payload；`RunProgressCoordinator` / `RunWaitCoordinator` 已将其物化到
  LLM invocation execution item 的 `summary_payload.llm_transcript_consumption`。
- [x] Inline tool loop 回归已验证：最终 LLM 请求只直送当前 inbound 和最新
  `call-echo-1` assistant/tool pair，旧 `context_tree.expand` /
  `context_tree.enable_tool_schema` protocol pair 不再重复进入 provider transcript。
- [x] Operations / LLM invocation 读模型已暴露 `estimated_provider_prompt_tokens`、
  `direct_transcript_session_message_count`、`direct_transcript_estimated_tokens`、
  `direct_tool_protocol_call_ids` 数量、sequence range 和 context render snapshot id；recent
  invocation 表与 detail drawer 均可查看这些预算/消费事实。
- [x] 后续真实 browser 长链的观测验收已归入本文“回归场景”统一追踪，避免在进度区重复维护。

### Phase 3：Context Tree Tool Interaction 语义折叠

- [x] 将当前 provider protocol 已消费/已配对的 `session.tool_interaction` 默认渲染为
  collapsed summary + refs，不重复放 arguments/result/error 全文。
- [x] 只让 frontier 中未消费 / 刚返回的 tool result 默认展开。
- [x] 为 tool interaction node 增加状态字段：
  - [x] `frontier`
  - [x] `consumed`
  - [x] `superseded`
  - [x] `failed`
  - [x] `verified`
- [x] 大结果不进 `content`，进入 owner refs / artifact refs。
- [x] 摘要结构至少包含：
  - tool name。
  - status。
  - arguments digest。
  - result digest。
  - key facts。
  - refs。
- [x] browser 工具结果增加第一版 evidence extraction：
  - URL / target_id。
  - matched selectors / refs。
  - endpoint / method / payload / status。
  - page runtime globals。
  - failure reason 继续通过 result status/error refs 暴露；更细失败分类留到后续语义状态增强。

验收：

- 最新 snapshot 中 `session.current` 不再因为 50 个 tool interactions 达到 100k+ chars。
- 展开旧阶段前，模型仍能看到“发生了什么、证据在哪里、下一步该看哪里”。

2026-06-08 进度：

- [x] 当前 run 已配对的 `session.tool_interaction` 在 direct transcript 仍承担 provider tool
  protocol 时，Context Tree 默认只渲染 summary 和 `<refs />`，不重复渲染 arguments/result/error
  全文。
- [x] `session.tool_interaction` 支持按需展开；展开后仍能看到完整 arguments/result/error。
- [x] `session.segment.current` 保持可展开，单条 `session.message` 保持只读估算/钉住语义。
- [x] 第一版 `session.evidence.current` 已接入 active segment；它从当前 run 的 tool result
  payload/details 中提取 compact evidence item，只保留关键事实和 refs，不复制原始大结果。
- [x] `context_tree.*` 控制工具结果不会进入 evidence ledger，避免把树操作噪音误当业务证据。
- [x] Context render snapshot metadata 已记录 `tree_evidence_item_count` 和 `evidence_node_refs`；
  Context Workspace Operations render snapshots 表已暴露 evidence count。
- [x] Browser 工具结果已输出标准 `browser_evidence` 小结构；证据账本可稳定吸收 profile、
  target、endpoint、method、status、selector/ref、payload shape、result shape、runtime
  globals 等事实，不依赖原始 snapshot/body 文本。
- [x] `session.tool_interaction` 节点已暴露 `lifecycle_status`、`frontier`、`consumed`、
  `failed`、`verified`，并把 consumed 映射到 `ContextNodeState.consumed`；render XML
  直接输出这些状态属性，模型无需打开节点 JSON 才能判断当前 protocol tail / 已消费历史 /
  失败尝试 / 已验证事实。
- [x] `session.tool_interaction` 默认可见性已收口为：当前 active run 的 frontier tool result
  默认展开 arguments/result/error，已消费历史默认折叠为 summary + refs；历史节点仍可通过
  `context_tree.expand` 按需展开完整内容。
- [x] `session.messages.current` 在真实 run render 中已收成可展开 handle，不再把 active
  segment 的全部普通消息作为 Context Tree 子节点默认交付给 LLM；provider-native transcript
  继续承担当前 user message 和协议尾巴。非 run/调试 render 仍可默认展开，便于 UI 和测试观察。
- [x] `session.messages.current` 使用版本化 revision 刷新节点默认状态：旧 workspace 会在升级后
  收成 handle，agent 后续显式展开不会被下一次 render 重置。
- [x] frontier 展开不再等于复制大结果正文；带 artifact refs / body omitted 标记的 browser/network
  结果会渲染为 endpoint、method、request_id、payload/result shape 和回查提示，原始 body
  继续留在 owner refs / artifacts / browser read hint 中。
- [x] `session.tool_interaction` 的 frontier/consumed 默认状态已接入 execution chain
  `llm_transcript_consumption.direct_transcript_sequence_range`：同一个 current run 内已经被上一轮
  LLM direct transcript 消费过的 tool pair 默认折叠，新返回且未消费的 tool pair 才作为
  frontier protocol tail 展开；没有 execution fact 的 target 仍按 session-local current inbound
  近似判断。
- [x] 新增长 browser synthetic 回归：55 个 browser/network tool interactions 中，前 54 个已消费
  tool pair 只以紧凑折叠 XML + refs 呈现，evidence item 默认折叠，最后 frontier 才展开；prompt
  不再因旧 raw body / evidence detail 重复进入 prompt 而超过预算阈值。
- [x] `superseded` 已作为显式 owner fact 接入：tool result/session metadata 明确给出
  `superseded` / `superseded_by_tool_call_id` 时，`session.tool_interaction` owner_ref、
  metadata 和 XML 都会暴露该状态；没有明确事实时稳定为 `false`，不做猜测。
- [x] Execution summary -> Context Workspace 的显式 `superseded` owner fact 通道已接通：
  `tool_lifecycle.superseded` / `superseded_by_tool_call_id` 会被 execution item summary
  保留，并驱动 `session.tool_interaction` 与 `session_evidence` 生命周期；仍不从相似调用或结果内容猜测替代关系。
- [x] 替代关系生产策略已收口：工具结果生产端或显式运行策略在确认“新结果替代旧结果”时声明
  `tool_lifecycle.supersedes_tool_call_id` / `supersedes_tool_run_id` /
  `supersedes_result_message_id`；orchestration 只保留这些 owner facts，Context Workspace
  只按显式 target ref 标旧 `session.tool_interaction` / `session_evidence` 为
  `superseded`。Context Workspace 和 prompt renderer 不做 endpoint/参数相似度猜测。

### Phase 4：Active Run Evidence Ledger

- [x] 新增 session owner projection，把当前 run 的关键事实投影成 `evidence_ledger`。
- [x] Evidence item 核心类型：
  - `observation`
  - `hypothesis`（保留识别入口，后续由显式 evidence 状态生产端补足）
  - `verified_fact`
  - `failed_attempt`
  - `api_endpoint`
  - `payload_shape`
  - `result_shape`
  - `user_visible_result`
- [x] Evidence lifecycle first pass 已独立建模在 `session_evidence` 节点上：
  `evidence_lifecycle_status` 与 `verified` / `failed` / `superseded` / `hypothesis` /
  `unresolved` 作为 evidence owner fact 暴露；`frontier` / `consumed` 继续只属于
  tool interaction protocol delivery 状态。
- [x] Evidence item 必须带 source refs，不允许成为不可追溯摘要。
- [x] Browser/network 类 tool result 的 `details` 已可提取 URL、target_id、endpoint、method、
  status 等核心字段。
- [x] Tool result session payload 已保留筛选后的 result metadata；browser profile、target、
  allocation、host service、artifact refs 等小事实可被 evidence ledger 提取，任意 custom
  metadata / execution_context 不进入 session payload。
- [x] Browser investigation 工具已通过 result metadata 的 `browser_evidence` 规范沉淀更多稳定
  key facts，例如 payload shape、result shape、verified selector/ref、runtime global 等；session
  payload 仍只保留筛选后的小 metadata，不复制原始 body/source。
- [x] `browser_evidence` 生产端已补第一批业务语义索引：action/form 类工具会暴露
  `action_kind`、`action_ok`、selector/ref/field label；network replay 会暴露 source request、
  changed fields、body source、response summary；script/network causality 会暴露 script frames
  和 API candidates。仍保持只输出小事实，不复制正文、源码或敏感 query。
- [x] 已消费、非 frontier 的 `tool_interaction` XML 首屏只保留工具名、node handle、状态、
  序列和必要错误标记；不再重复暴露 `call_id`、默认 `frontier=false` /
  `consumed=true` / `superseded=false`、hash 摘要和 collapsed refs。展开或 pin 后仍可读取
  refs / arguments / result。
- [x] Active session 的已消费工具历史已增加语义 range：`session.messages.current`
  默认只保留最近 8 条 consumed tool interaction 和所有 frontier tool interaction；更早的已消费工具链折成
  `session_tool_interaction_range`。展开该 range 会重新加载对应范围内的 tool interaction 子节点，
  因此历史可追溯但不默认逐条占用 prompt。
- [x] Collapsed `session_evidence` XML 首屏只保留 evidence 类型、生命周期、状态、工具名和
  true 状态标记；不再输出默认 false 布尔和 call id，避免 evidence ledger 与 tool interaction
  两边重复铺属性。
- [x] Evidence summary 已按证据用途重排关键事实优先级：API/browser 证据优先显示
  endpoint、method、http status、request id、target/ref，再显示 profile/url/kind 等辅助字段。
- [x] Evidence node id 已改为稳定短 hash；完整 session id、tool call id、tool run id
  继续保存在 owner_ref/metadata/read_hints 中，树内定位不再把长原始 id 重复塞进 prompt。

验收：

- 模型不必重新阅读 20 个 browser snapshot，也能知道当前已确认的 endpoint / payload / result shape。
- 旧事实可以通过 refs 回查。

### Phase 5：Tool Schema Mirror 预算治理

- [x] `context_tree.*` 保持默认 callable。
- [x] tool function node 默认不再全部 `schema_enabled=True`。
- [x] group 展开只披露候选 function，schema mirror 需要：
  - agent 显式 `enable_tool_schema`；
  - 或 runtime task policy 通过 render metadata 显式选择少量默认 schema。
- [x] 增加 schema budget：
  - max mirrored schema count。
  - max schema estimated tokens。
- [x] browser prompt groups 已声明 `default_tool_schema_ids` /
  `default_tool_schema_max_count` / `default_tool_schema_source`，作为后续显式 runtime
  task policy 选择 group 时的稳定 owner 数据源。
- [x] 当 schema 被预算挡住时，snapshot / Operations / Workbench / Trace 显示预算状态与
  skipped 数，不再静默不可见。

验收：

- browser task 默认不再镜像 45 个 browser schemas。
- 模型能通过 group 继续启用需要的工具，而不是误以为工具不存在。

2026-06-08 进度：

- [x] `context_tree.*` 控制工具保持默认 `schema_enabled=true`，保证 agent 总能操作
  Context Tree。
- [x] 非 `context_tree.*` tool function 默认 `schema_enabled=false`；展开 bundle/group 只披露
  handle、summary 和 provider schema availability，不再直接镜像为 provider callable schema。
- [x] `context_tree.enable_tool_schema` / `context_tree.disable_tool_schema` 已作为显式启停路径验证；
  orchestration 内联工具循环更新为 expand -> enable schema -> call tool。
- [x] Context Render 已接入 schema mirror count/token 上限，默认最多 32 个 provider schema /
  24k 估算 schema tokens；超限会记录 `tool_schema_mirror_budget`。
- [x] Workbench / Trace / Operations prompt budget 已显示 schema mirror budget 状态和 skipped
  数。
- [x] Context Render 已接入显式运行时默认 schema 通道：
  `RenderContextPromptInput.metadata.default_tool_schema_ids` / `default_tool_schema_source`。
  该通道只影响本次 render，不反写 `ContextNodeState.schema_enabled`，且仍经过同一份
  schema count/token budget。
- [x] Orchestration snapshot adapter 会转交 `prompt_flow_hint.default_tool_schema_ids`，但不会
  自行根据关键词或工具全集推断默认工具。
- [x] Browser source 的 prompt group metadata 已透出有序 schema bootstrap 候选和 group
  max count；Context Tree group 节点可以看到这些 owner 声明。
- [x] `/turns` 已允许上游显式传入 run `metadata`；`prompt_bootstrap_policy` 和
  `runtime_task_policy.prompt_bootstrap` 会在 intake 阶段归一进 `prompt_flow_hint`。
- [x] Orchestration snapshot adapter 已支持
  `prompt_flow_hint.default_tool_schema_group_refs`：它会通过 Context Tree 显式展开
  `tools.available -> bundle -> group`，从 group owner metadata 收集
  `default_tool_schema_ids` / `default_tool_schema_max_count` /
  `default_tool_schema_source`，再进入同一份 render schema budget。
- [x] runtime task policy 入口只接受显式 tool schema ids 或显式 source/group refs；当前仍不做
  用户文本关键词联想。
- [x] SQL Context Node repository 的 `save_many` 已对同批 `(workspace_id,node_id)` 去重，
  行为对齐 in-memory repository，避免长执行链多次 render 同一 evidence 节点时触发唯一键冲突。
- [x] Collapsed `tool_function` XML 已改为 compact handle：
  `name` / `node_id` / `schema_enabled` / 必要 access。已 mirror provider
  schema 的函数不再在 XML handle 重复摘要；未 mirror schema 的函数保留短摘要，展开函数节点才显示完整
  effect / capability / runtime 信息。
- [x] Collapsed `tool_function` compact handle 进一步去掉和树层级重复的 `state` / `source_id`；
  source、runtime、effect、capability 只在函数节点展开后出现。
- [x] 已 mirror 为 provider schema 的 collapsed `tool_function` 不再输出 XML handle，避免同一
  callable tool 同时出现在 provider tools 和 Context Tree XML 中；未 mirror 的 tool function
  仍以短 handle 作为可启用候选。

### Phase 6：Rendered Estimate 改为所见即所得

- [x] Render prompt 主 estimate 不再简单使用所有 visible node estimate 累加；visible node
  aggregate 只作为 breakdown 观察口径保留。
- [x] 增加 rendered-content estimate：
  - 按实际 XML 输出文本计算。
  - 单独统计 provider attachment schema tokens。
  - 单独统计 artifact/file/image attachment budget。
- [x] 父节点 summary estimate 与子节点 content estimate 不再作为主预算判断口径重复计量。
- [x] Snapshot metadata 同时保留：
  - `node_estimate_breakdown` 用于 owner 观察。
  - `rendered_prompt_estimate` 用于预算判断。

验收：

- Operations 显示的 prompt budget 接近真实 provider request。
- compaction / folding 触发依据不被父子节点重复估算扭曲。

2026-06-08 进度：

- [x] `ContextRenderService.render_prompt_body()` 的主 `estimate` 已改为按实际 `<context_tree>`
  XML prompt body 计算。
- [x] 原 visible node aggregate 保留在 `estimate_breakdown.node_visible`；实际渲染口径保留在
  `estimate_breakdown.rendered_prompt`。
- [x] render snapshot metadata 已记录 `rendered_prompt_estimate`、`node_visible_estimate` 和
  `node_estimate_breakdown`，避免预算判断和 owner 观察口径混在一起。
- [x] Context Workspace Operations 页已能通过 `prompt_budget` tab 查看 rendered/provider
  口径、direct transcript 和 schema mirror 预算。
- [x] Workbench / Trace prompt snapshot 摘要已改为展示 rendered prompt、provider prompt、direct
  transcript、schema mirror 四种预算口径，不再用一个笼统 `Tokens` 混合解释。
- [x] Context snapshot metadata 已增加 `artifact_content_budget`、
  `artifact_content_estimated_tokens`、candidate/block/image/file/omitted counts；这些字段会进入
  LLM invocation request metadata，并参与 `estimated_provider_prompt_tokens` 合计。

### Phase 7：Long Content Owner Reads

- [x] 明确 owner read 工具/API：
  - session message raw read：`/sessions/{session_key}/messages` 可按 sequence window 读取。
  - tool run raw result read：`/tools/runs/{tool_run_id}` / `python -m crxzipple.main tool get-run`。
  - artifact read：`/artifacts/{artifact_id}`、`/artifacts/{artifact_id}/download`。
  - browser trace / network body read：`browser.network.get_response_body` /
    `browser.network.get_request_body`，大 body 默认落 artifact。
- [x] Context Tree 节点只提供 refs 和建议动作，不代理 owner resource。
- [x] 大型 text tool result 已在 `ToolWorkerService` 统一外化为 artifact，默认 tool
  result 只保留短摘要和 metadata refs，避免普通 stdout/JSON 全文进入 Context Tree。
- [x] Session evidence item 已增加 `read_hints`，把 tool/session/artifact/browser owner-read
  入口作为小结构暴露给模型和 UI；不新增 `context_tree.raw_read` 之类旁路。
- [x] Workbench Context Tree 的选中节点详情已展示 `owner_ref` 和 evidence
  `read_hints`，作为 raw owner-read 入口；仍不提供 Context Tree 自己的 raw proxy。

验收：

- 长内容不默认进 prompt，但模型和人都能按需回看。
- Context Tree 不变成第二套资源系统。

## 风险与约束

### Tool protocol 风险

Provider-native tool protocol 要求 assistant tool call 和 tool result 成对出现。裁剪 transcript 时不能把
需要继续协议的 tail 切断。

控制方式：

- 根据 execution chain item 状态判断 frontier。
- 对每个 LLM call 记录 direct transcript message ids。
- 增加 orphan tool call / orphan tool result 单元测试。

### 模型遗忘风险

如果只裁剪不摘要，模型会丢失为什么走到当前状态。

控制方式：

- 裁剪前先写 evidence ledger。
- 折叠节点保留 source refs。
- `frontier` 保留最新待处理结果。

### 多路径复发风险

如果为了修复 browser 再加 browser-specific prompt 或 hidden prompt，系统会回到旧中间态。

控制方式：

- 所有 prompt 内容必须能在 Context Render Snapshot 中看到。
- Provider adapter 不允许注入不可观察的大段额外 prompt。
- Browser 工具增强只产出 owner facts / tool results / artifacts，不直接改 prompt。

## 回归场景

- [x] 长 browser investigation synthetic：50+ tool interactions 后 prompt 不超过预算目标。
- [x] 长 browser investigation real run：通过 Operations / LLM invocation 预算面确认真实现场
  provider-native assistant/tool chars 不再随全量历史线性增长。
  2026-06-09 首次尝试验收时本机 Docker/Colima 未运行，现场验收暂缓；随后已通过
  `colima start` / `make dev-up` 恢复本地 Postgres + Redis + API + daemon + frontend。
  使用旧真实 browser run `ee71599fd2504ab3950f118c671952d7` / session
  `agent:crxzipple:conversation:a5483cb719034993a35e1766848d594d` live render 验收：
  - 旧落库 snapshot `ctxsnap_4195c01231634af9b369e6f38d903fa2` 为 176,032 chars，
    45 mirrored schemas，且旧 attachment key 仍是 `prompt_surface`。
  - 修复 schema mirror 优先级后，`context_tree.*` 9 个控制 schema 不再被 browser schema
    count limit 挤掉；真实 render 保持 32 schemas / 13 skipped。
  - 修复缺失 execution consumption fact 的 fallback 后，旧现场从 54 个 frontier
    收成 1 个 frontier / 53 个 consumed。
  - 修复非 frontier tool interaction render guard 后，真实 render 从 205,132 chars
    下降到 95,504 chars / 23,876 estimated tokens；`arguments` / `result` 只剩当前 frontier
    各 1 个，53 个已消费 tool interaction 输出 `content_omitted="non_frontier_budget_guard"`。
  - Tool catalog compact handle 修复后，真实 render 从 95,504 chars 下降到
    84,970 chars；`tools.available` 从约 35,099 chars 降到 23,963 chars，45 个
    tool function 不再按通用 `<node><summary>` 输出。
  - 已消费 tool interaction / evidence 默认属性压缩后，真实 render 继续下降到
    67,068 chars / 16,767 estimated tokens。当前 breakdown：
    `session.current=32,094`、`tools.available=19,188`、
    `context.instructions=12,063`、`execution.current=2,354`。
    `tool_function` 属性字符约 7,780，`session.tool_interaction` 行约 15,139，
    `session_evidence` 行约 5,835。
  - 当时尚未完全达成 50k 级目标：剩余膨胀主要来自 active session 中 50+ 已消费工具历史仍作为独立
    handle 全量可见，以及 browser 多个 group 被旧 workspace 状态展开。因此随后继续做
    active session consumed tool history 的语义 range / phase handle，使旧工具历史可追溯但不默认逐条
    暴露；不要用隐藏 browser prompt、provider adapter 注入或直接吞节点的补丁绕过 Context Tree。
  - Active consumed tool history range 落地后，真实 render 下降到
    51,190 chars / 12,798 estimated tokens：`session.current=16,216`，默认只剩
    9 个 `tool_interaction` 和 1 个 `session_tool_interaction_range`。这证明当前 session 历史可以
    收成可展开 handle，而不丢失可追溯路径。
  - Collapsed tool function 去掉重复 `state/source_id` 后，真实 render 进一步下降到
    48,841 chars / 12,211 estimated tokens，达成本轮 50k 级真实 browser 长链目标。当前主要剩余：
    `tools.available=16,839`、`session.current=16,216`、`context.instructions=12,063`。
  - 2026-06-09 继续收口：
    - Runtime contract 从约 8.7k chars 压缩到 4.3k chars，并通过 root refresh 让旧 workspace
      拿到新版 contract hash `fc65850f0841c8141d2c24be0492caafef13b001f1abab91fc3380e8fe6a5264`。
    - `context.priority` / `context.tree_usage` 改为版本化静态 guide，默认折叠且保留用户 pin/展开操作；
      live render 中不再输出 `Context Tree usage:` / `Context authority order:` 正文。
    - 已 mirror 的 collapsed `tool_function` 从 XML 中省略，`tools.available` 从 16,839 降到
      11,363 chars，provider schemas 保持 32。
    - `session.messages.current` 在 run render 中收成 handle，`session.current` 从 16,216
      降到 8,473 chars，`tool_interaction` 默认可见计数降为 0。
    - Evidence node id 短化后，`session.current` 继续降到 7,433 chars。
    - 当前 live render：30,671 chars / 7,668 estimated tokens；
      breakdown 为 `context.instructions=8,152`、`session.current=7,433`、
      `tools.available=11,363`、`execution.current=2,354`，`tool_function=0`、
      `tool_interaction=0`、`evidence=16`、provider schemas=32。
    - Tool context nodes 增加版本化 owner seed，旧 workspace 中非 `context_tree.*` tool function
      残留的 `schema_enabled=true` 会在 owner refresh 时回到新默认值；只有通过
      `context_tree.enable_tool_schema` / `context_tree.disable_tool_schema` 产生的显式控制状态会被
      `schema_enabled_source=context_tree_action` 保留。
    - schema 状态归属修正后，旧真实 browser run live render 继续下降到
      24,926 chars / 6,232 estimated tokens；breakdown 为
      `context.instructions=8,152`、`session.current=7,433`、
      `tools.available=5,618`、`execution.current=2,354`，`tool_bundle=14`、
      `tool_group=0`、`tool_function=0`、`tool_interaction=0`、`evidence=16`。
      provider schemas 从 32 收到 9 个，仅保留 `context_tree.*` 控制工具；
      `tool_schema_mirror_budget.estimated_tokens=1,110`。browser/tool schema 需要通过
      显式 group refs 或 agent 的 context-tree action 进入同一份 schema budget。
    - 新版本真实 run `59fdfc722da446a9a0f17c36fdb3895c` 验收通过：用户要求“只检查浏览器相关能力，
      最多一步工具探索”。执行链为 LLM -> `context_tree.expand(tools.bundle.configured.browser)` -> LLM，
      没有访问外部网站，没有调用 browser 操作工具。
      - snapshot `ctxsnap_2704d1c014ad4a3988ba51edd1ff30b0`：
        `prompt_chars=18,192`、`rendered_prompt_estimated_tokens=4,548`、
        `direct_transcript_estimated_tokens=20`、`mirrored_tool_schema_estimated_tokens=997`、
        `estimated_provider_prompt_tokens=5,565`、provider schemas=9、duplicate risk=false。
      - snapshot `ctxsnap_467eee54484d4f9c9722f115fb11c6bc`：
        `prompt_chars=21,967`、`rendered_prompt_estimated_tokens=5,492`、
        `direct_transcript_estimated_tokens=474`、`mirrored_tool_schema_estimated_tokens=997`、
        `estimated_provider_prompt_tokens=6,963`、provider schemas=9、duplicate risk=false。
      - 对应 LLM invocations `118636a2aa08408d8e4434a973c38347` /
        `48003c2883a4414484e9e01f73e4ed09` 均落库了 rendered/direct/schema/provider
        预算字段；第二次 direct transcript range 为同一 active session 的 seq 1-3，说明 provider-native
        transcript 只承载当前协议尾巴，没有回到旧 100+ messages / 45 schemas 形态。
- [x] 同一次 LLM 返回多个 tool call：全部结果到齐后只触发一次下一步 LLM。
- [x] Tool result 大 JSON：下一轮可见摘要和 refs，不重复塞全文。
- [x] Browser network response body：默认不进 prompt，按需 raw read。
- [x] Tool group 展开：只显示 group/function 描述，不自动镜像全部 schemas。
- [x] 显式 enable schema：下一轮 provider tools 出现对应 function。
- [x] Historical segment：默认只显示 summary，展开受预算守卫。
- [x] Prompt preview：UI/API 显示 provider messages、tree XML、mirrored schemas 和 budget breakdown。

## 本轮非目标

- 不重写 turn/run/execution chain 状态机。
- 不新增固定 plan/execution/check 多模型流水线。
- 不把 memory 作为当前 session 压缩的替代品。
- 不把 skill、memory、artifact、browser raw content 变成 Context Tree 内部资源读取协议。
- 不为 browser 单独创建第二套 prompt 管线。

## 预期收益

- 长执行链 prompt 从“线性堆积全部工具结果”转为“frontier + evidence + refs”。
- 模型能集中处理当前问题，而不是反复消化旧 browser snapshot。
- 历史不会丢失，必要时可通过树节点和 owner refs 回看。
- Tool schema 暴露更贴近能力展开，减少注意力浪费。
- Operations 能解释 prompt 预算来源，便于后续托管 agent 接手治理。
