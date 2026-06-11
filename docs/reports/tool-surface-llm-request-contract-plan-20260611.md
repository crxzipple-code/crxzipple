# Tool Surface LLM Request Contract Plan 2026-06-11

本文记录 LLM request contract 升级后 Tool module 的目标形态：从“提供可用 tool schema 列表”升级为提供稳定、可追溯、可授权、可执行的 `ToolSurface`。Orchestration 使用 ToolSurface 构造 `LlmRequestEnvelope`，Context Workspace 使用它生成 agent-facing tool schema mirror。

关联文档：

- [provider-neutral-llm-response-stream-contract-plan-20260611.md](provider-neutral-llm-response-stream-contract-plan-20260611.md)
- [orchestration-llm-contract-driven-runtime-plan-20260611.md](orchestration-llm-contract-driven-runtime-plan-20260611.md)
- [context-workspace-llm-request-surface-plan-20260611.md](context-workspace-llm-request-surface-plan-20260611.md)
- [model-agent-policy-llm-request-options-plan-20260611.md](model-agent-policy-llm-request-options-plan-20260611.md)
- [agent-runtime-contract-upgrade-testing-strategy-20260611.md](agent-runtime-contract-upgrade-testing-strategy-20260611.md)
- [browser-tool-source-contract-convergence-plan-20260610.md](browser-tool-source-contract-convergence-plan-20260610.md)
- [../context-workspace-prompt-tree-design.md](../context-workspace-prompt-tree-design.md)
- [../../src/crxzipple/modules/tool/README.md](../../src/crxzipple/modules/tool/README.md)

## Cutover Assumption

开发前会清除并重建数据库。本计划不考虑旧 tool schema projection、旧 keyword route、旧 configured.browser 特例路径、旧 process-local debug registry 主路径或旧 Operations projection 的兼容。

如果旧 Tool catalog/schema 表达阻碍 agent 最佳效果，应直接迁到新结构。migration 只服务新库初始化，不设计历史升级路径。

## 定位

Tool module 拥有：

- Tool Source。
- Tool Function Catalog。
- ToolRun 生命周期。
- runtime requirements。
- readiness / authorization 查询事实。
- result envelope。

LLM request 升级后，Tool module 额外提供：

```text
ToolSurface
  surface_id
  source groups
  visible functions
  schemas
  runtime requirements
  readiness
  authorization policy
  provider mapping hints
  prompt grouping metadata
```

ToolSurface 是 request-time view，不是新的 tool owner。

## 当前问题

### 1. Tool schema list 过薄

旧 request 只需要 `tool_schemas[]` 时，很多关键信息丢失：

- source/group 结构。
- runtime requirements。
- readiness/credential/authorization 状态。
- execution mode。
- background/inline 能力。
- shared-state concurrency。
- provider schema mapping hint。

### 2. Tool 可见性不应靠联想 router

已经决定砍掉关键词联想 route。模型能看到哪些工具，应由 ToolSurface + Context Tree 可见性 + policy 决定，不由本地语义 trigger map 决定。

### 3. Provider external item 不能混入 ToolRun

OpenAI hosted web/image 等 provider external item 不是 CRXZipple Tool Source。ToolSurface 只描述 CRXZipple local/runtime tools。

### 4. Result envelope 需要支持 Session replay

ToolRun result 不只是 UI output；它还要稳定写入 `SessionItem(kind=tool_result)`，供下一轮 provider replay。必须保留 call_id、tool_name、status、output/error、artifact refs。

## 目标

### 必须达成

1. Tool module 提供 `ToolSurface` query/service。
2. ToolSurface 按 source-first / group-first 组织。
3. ToolSurface 明确 always-visible、context-selected、enabled schema。
4. ToolSurface 携带 runtime requirements、readiness、authorization policy。
5. Orchestration 从 ToolSurface 验证并执行 `LlmResponseItem(kind=tool_call)`。
6. Context Workspace 从 ToolSurface 生成 tool schema mirror。
7. ToolRun result envelope 能直接投影为 Session `tool_result` item。
8. provider external item 不进入 ToolSurface，不创建 ToolRun。
9. 支持数据库完全重建，不做旧 tool schema 兼容。

### 非目标

- 不让 Tool module 决定 agent loop。
- 不让 Tool module 解析 LLM provider payload。
- 不让 Tool module 读取 Context Tree 状态。
- 不让 Tool module 做关键词语义 route。
- 不把 provider-hosted tools 注册为 local ToolRun。

## ToolSurface 草案

```text
ToolSurface
  id
  session_id
  run_id
  agent_id
  policy_version
  sources
  functions
  default_tool_choice
  parallel_tool_calls
  estimate
  diagnostics
  created_at
```

### ToolSurfaceSource

```text
ToolSurfaceSource
  source_id
  source_key
  source_kind
  title
  summary
  groups
  readiness
  authorization
  runtime_requirements
  prompt_metadata
```

### ToolSurfaceGroup

```text
ToolSurfaceGroup
  group_key
  title
  summary
  function_refs
  default_expanded
  schema_enabled
  estimate
```

### ToolSurfaceFunction

```text
ToolSurfaceFunction
  function_id
  name
  title
  description
  input_schema
  output_contract
  source_id
  group_key
  runtime_kind
  execution_modes
  requires_confirmation
  mutates_state
  readiness
  authorization
  concurrency_key
  provider_schema_hints
```

## Source-First 可见性

ToolSurface 默认按：

```text
source -> group -> function
```

组织。原因：

- source 是稳定治理边界。
- group 是注意力治理边界。
- function 是 provider schema 映射边界。

常驻工具不是新概念；它是 Tool module policy 对 surface 的选择结果：

```text
always_visible=true
```

Context Workspace 可以展示/折叠它，但不决定其授权和 readiness。

## Request 映射

Orchestration 把 ToolSurface 放入 `LlmRequestEnvelope.tool_surface`。LLM adapter 根据 provider family 映射：

```text
OpenAI Responses    -> tools[] / tool_choice / parallel_tool_calls
Chat Compatible     -> tools[] / tool_choice
Anthropic Messages  -> tools[]
Gemini              -> functionDeclarations
```

Tool module 不生成 provider-native schema；它提供 provider-neutral schema 和 mapping hints。

## Tool Call 执行

Orchestration 从 LLM response item 构建：

```text
ToolExecutionPlan
  llm_response_item_id
  call_id
  tool_name
  arguments
  tool_surface_id
  function_id
```

Tool module 验证：

- function 是否属于该 surface。
- readiness 是否仍有效。
- authorization 是否满足。
- runtime requirements 是否满足。
- arguments 是否符合 input schema。

然后创建 ToolRun。

## Tool Result Envelope

ToolRun terminal result 应能投影为 Session item：

```text
ToolResultEnvelope
  tool_run_id
  call_id
  tool_name
  status
  output_payload
  error_payload
  artifact_refs
  truncated
  model_visible_payload
  user_visible_payload
  trace_payload
```

规则：

- `model_visible_payload` 用于 Session `tool_result` replay。
- `user_visible_payload` 用于 Workbench/Trace 展示。
- raw large output 通过 artifact/read handle 保留，不直接塞 prompt。

## Persistence

允许破坏式调整或新增：

```text
tool_surfaces
  id
  session_id
  run_id
  agent_id
  policy_version
  surface_payload
  estimate_payload
  diagnostics_payload
  created_at

tool_runs
  ...
  call_id
  tool_surface_id
  function_id
  result_envelope_payload
```

ToolSurface 可以是 request-time snapshot，保证后续能解释“本轮模型可见哪些工具”。

## 与 Context Workspace 配合

Context Workspace 只消费 ToolSurface：

```text
ToolSurface -> tool.surface Context Tree nodes -> tool_schema_mirror
```

它不直接读 Tool Source internal rows 来判断 readiness。

## 与 Orchestration 配合

Orchestration：

- 请求 ToolSurface。
- 把 ToolSurface 放入 LLM request envelope。
- 用 ToolSurface 验证 tool_call response item。
- 提交 ToolRun。
- 将 ToolResultEnvelope 写入 Session tool_result item。

Tool module：

- 不完成 orchestration run。
- 不决定是否继续 LLM。
- 不解析 LLM response item 原始 provider payload。

## 退场项

必须退场或降级：

- request-time 临时 `tool_schemas[]` 拼接主路径。
- keyword route / trigger synonym map。
- configured.browser 或 provider capability 绕开 Tool Source。
- process-local debug registry 作为生产 tool truth。
- provider external item 创建 ToolRun。
- tool result 只作为 UI 文本，不支持 model replay。
- 不得为旧 tool schema projection 保留兼容 shim。

## Checklist

### Domain / Application

- [ ] 定义 `ToolSurface`。
- [ ] 定义 `ToolSurfaceSource`。
- [ ] 定义 `ToolSurfaceGroup`。
- [ ] 定义 `ToolSurfaceFunction`。
- [ ] 定义 `ToolResultEnvelope`。
- [ ] 提供 ToolSurface query/service。

### Persistence

- [ ] 保存 request-time ToolSurface snapshot。
- [ ] ToolRun 记录 `tool_surface_id`。
- [ ] ToolRun 记录 `call_id`。
- [ ] ToolRun 保存 result envelope。

### Orchestration Integration

- [ ] request builder 获取 ToolSurface。
- [ ] tool_call response item 用 ToolSurface 验证。
- [ ] ToolRun result envelope 投影为 Session tool_result。
- [ ] provider external item 不进入 Tool module。

### Context Workspace Integration

- [ ] tool surface source/group/function 生成 Context Tree mirror。
- [ ] schema_enabled 状态只控制镜像展示，不改 readiness。
- [ ] tool schema mirror 引用 ToolSurface id。

### Verification

- [ ] 常驻工具通过 ToolSurface always-visible 暴露。
- [ ] context-selected tool 可进入 ToolSurface。
- [ ] 未授权/未 ready tool 不进入 enabled function。
- [ ] tool_call call_id 贯穿 response item、ToolRun、Session tool_result。
- [ ] provider external item 不创建 ToolRun。
- [ ] 清库重建后 tool/orchestration 相关测试通过。
