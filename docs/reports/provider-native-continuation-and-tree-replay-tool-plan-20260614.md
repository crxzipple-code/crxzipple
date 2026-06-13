# Provider Native Continuation And Tree Replay Tool Plan

Date: 2026-06-14

## 背景

本轮对照了 Codex CLI 完成东航航班查询任务时的真实 Responses API 请求链，以及 CRXZipple 最新 `openai_codex.gpt-5.5` invocation 记录。

Codex CLI 的关键请求特征：

- 首轮发送完整起步上下文、工具面和用户任务。
- 后续轮次使用 `previous_response_id` 承接 provider response state。
- 后续只追加新的 `function_call_output` / provider external item output。
- 请求固定携带 `parallel_tool_calls=true`、`prompt_cache_key`、`text.verbosity=low`、`include=["reasoning.encrypted_content"]` 等 provider options。
- 工具结果、reasoning、hosted tool item、message phase 都保留为 response item lifecycle。

CRXZipple 最新 invocation 的实际形态：

- 每轮重建并发送越来越长的 `messages`，最新样本已有 50+ 条。
- `tool_schemas` 当前为 13 个，主要是 `context_tree.*`、`exec`、`process`、`web.fetch_json`、`web.fetch_text`。
- `request_overrides` 只有 `reasoning`。
- 没有 `previous_response_id`、`parallel_tool_calls`、`prompt_cache_key`、`text.verbosity`、`include`。
- Operations 当前展示的是 CRXZipple invocation payload，不是实际 provider HTTP payload。

结论：当前问题不是单纯 prompt 失效，也不是同一模型能力变弱，而是 CRXZipple 仍以 transcript replay loop 使用 Codex Responses API，没有充分释放 provider-native continuation、response item、tool output protocol 和 request policy 能力。

## 目标

将 CRXZipple agent loop 从“每轮重放完整历史和树”升级为：

```text
首轮:
Context Tree render snapshot + user task + initial tool surface -> provider

后续:
previous_response_id + new tool output/context delta/user delta + updated tool surface -> provider
```

同时保留 CRXZipple 的核心设计：

- Context Workspace 仍是 Context Tree、render snapshot、provider mirror 的 owner。
- Orchestration 仍是综合 runtime flow owner。
- LLM module 仍保持 provider-neutral contract。
- Tool module 仍拥有工具生命周期事实。
- Workbench/Operations 仍通过 read model 观察，不绕过 owner module。

## 非目标

- 不照抄 Codex CLI 的 provider-hosted `web_search` / `image_generation` 特权能力。
- 不把 CRXZipple 绑定到单一模型或单一 provider。
- 不保留历史数据兼容。施工前允许清库重建。
- 不恢复旧 orchestration facade。
- 不把 Context Tree 拼装逻辑塞回 orchestration 内部。

## 设计原则

1. Provider-native continuation 优先。
   支持 Responses-style continuation 的 provider 使用 `previous_response_id`；不支持的 provider 才退化为 transcript replay。

2. Context Tree 首轮完整渲染，后续显式回放。
   树不再每轮自动完整进入 prompt。模型需要查看当前树状态时，必须调用 Context Tree replay/read 工具。

3. 工具结果使用 provider 原生协议。
   Codex/OpenAI Responses 下，tool result 应映射为 `function_call_output`，并绑定上一轮 provider `call_id`。

4. 调度层负责 loop state，adapter 负责 provider shape。
   Orchestration 维护 continuation state、delta source、request envelope；adapter 只做 provider-specific payload mapping。

5. 实际请求必须可观察。
   Operations/Trace 需要能区分 CRXZipple normalized request 和 provider actual request preview。

## 目标请求形态

### 首轮请求

```json
{
  "model": "gpt-5.5",
  "instructions": "...runtime + system instructions...",
  "input": [
    {"type": "message", "role": "user", "content": "..."},
    {"type": "message", "role": "system", "content": "...context tree render..."}
  ],
  "tools": ["...provider-visible tools..."],
  "tool_choice": "auto",
  "parallel_tool_calls": true,
  "reasoning": {"effort": "medium"},
  "text": {"verbosity": "low"},
  "include": ["reasoning.encrypted_content"],
  "prompt_cache_key": "session-or-run-stable-key",
  "store": false,
  "stream": true
}
```

### 后续工具轮次

```json
{
  "type": "response.create",
  "model": "gpt-5.5",
  "previous_response_id": "resp_xxx",
  "input": [
    {
      "type": "function_call_output",
      "call_id": "call_xxx",
      "output": "...tool result..."
    }
  ],
  "tools": ["...updated provider-visible tools..."],
  "tool_choice": "auto",
  "parallel_tool_calls": true,
  "reasoning": {"effort": "medium"},
  "text": {"verbosity": "low"},
  "include": ["reasoning.encrypted_content"],
  "prompt_cache_key": "session-or-run-stable-key",
  "store": false,
  "stream": true
}
```

### 后续树变化轮次

```json
{
  "type": "response.create",
  "previous_response_id": "resp_xxx",
  "input": [
    {
      "type": "message",
      "role": "system",
      "content": "Context tree delta: enabled tool schemas: ..."
    },
    {
      "type": "function_call_output",
      "call_id": "call_xxx",
      "output": "...tool result..."
    }
  ],
  "tools": ["...updated tool schemas..."]
}
```

## 模块改造

## 1. LLM Module

### 数据模型

新增 provider-neutral continuation/request trace 字段：

- `LlmAdapterRequest.continuation`
- `LlmAdapterRequest.provider_input_mode`
- `LlmAdapterRequest.provider_request_options`
- `LlmAdapterRequest.provider_request_trace_id`
- `LlmInvocation.provider_request_payload_preview`
- `LlmInvocation.provider_response_payload_ref`

建议 value object：

```python
LlmProviderContinuation(
    mode: "provider_native" | "transcript_replay",
    previous_response_id: str | None,
    previous_invocation_id: str | None,
    provider_family: str | None,
)
```

```python
LlmProviderRequestPreview(
    provider: str,
    endpoint: str | None,
    payload_keys: tuple[str, ...],
    input_item_types: tuple[str, ...],
    tool_types: tuple[str, ...],
    tool_count: int,
    has_previous_response_id: bool,
    previous_response_id: str | None,
    option_summary: dict[str, object],
)
```

### Adapter 行为

OpenAI/Codex Responses adapter：

- `continuation.previous_response_id` 存在时，payload 增加：
  - `type="response.create"`
  - `previous_response_id`
- tool result input 使用 `function_call_output`。
- provider options 继续从 request overrides 透传：
  - `parallel_tool_calls`
  - `service_tier`
  - `prompt_cache_key`
  - `text`
  - `include`
  - `reasoning`
- streaming completed event 继续持久化 `response_items` 和 `continuation`。

非 Responses provider：

- 不接收 `previous_response_id`。
- 使用 transcript replay。
- 仍归一化 response items，能力缺失处显式记录 capability missing。

### Checklist

- [x] 扩展 `LlmAdapterRequest` continuation 字段。
- [x] 扩展 `LlmInvocation` provider request preview/ref 字段。
- [x] OpenAI Responses adapter 支持 `previous_response_id`。
- [x] Codex Responses adapter 支持 `previous_response_id`。
- [ ] Tool result 映射为 `function_call_output`。
- [x] Provider actual request preview 持久化。
- [x] 单测覆盖首轮 request。
- [x] 单测覆盖 continuation request。
- [ ] 单测覆盖 provider 不支持 continuation 时退化 transcript replay。

## 2. Orchestration Module

### Loop State

Orchestration run 需要维护最新 provider continuation state：

- latest provider response id。
- latest LLM invocation id。
- current provider family capability。
- pending tool call id 到 provider call id 的映射。
- context render snapshot id。
- tool surface snapshot id。
- last context tree revision sent to provider。

建议结构：

```python
ProviderContinuationState(
    mode: "provider_native" | "transcript_replay",
    provider_family: str,
    previous_response_id: str | None,
    previous_invocation_id: str | None,
    last_context_snapshot_id: str | None,
    last_context_revision: int | None,
    last_tool_surface_id: str | None,
)
```

### Request Envelope

`LlmRequestEnvelope` 增加：

- `continuation_state`
- `input_delta_items`
- `context_delta`
- `tool_result_protocol_items`
- `provider_request_mode`

首轮：

- 构造完整 context render snapshot。
- 构造完整 tool surface。
- 无 `previous_response_id`。

后续：

- 如果 provider 支持 native continuation：
  - 不调用完整 transcript replay。
  - 只收集本轮新增 tool result / approval result / user delta / context delta。
  - 携带 `previous_response_id`。
- 如果 provider 不支持：
  - 使用现有 transcript replay。

### Completion Criteria

Loop 结束判断继续使用：

- provider continuation signal。
- response items 中是否有 tool call。
- final answer item。
- pending tool/approval state。

但要避免将 “无 tool call” 简化为终止条件。无 tool call 但 provider `end_turn=false` 或 commentary/reasoning-only 时，应继续或生成诊断。

### Checklist

- [ ] Run loop 保存 latest provider response id。
- [ ] Tool call session item 记录 provider call id。
- [ ] Tool result replay item 绑定 provider call id。
- [ ] `LlmRequestEnvelope` 支持 delta input。
- [ ] 首轮完整 Context Tree render。
- [ ] 后续 provider-native continuation 不再重放完整 tree/transcript。
- [ ] context tree revision 变化时生成 context delta。
- [ ] tool surface 变化时更新 provider tools。
- [ ] execution chain summary 展示 continuation state。
- [ ] 单测覆盖首轮 -> tool call -> tool result continuation。
- [ ] 单测覆盖 `context_tree.enable_tool_schema` 后工具面更新。
- [ ] 单测覆盖 final answer 完成 run。

## 3. Context Workspace Module

### Tree Replay Tool

新增或增强 Context Tree 工具，让模型显式查看当前树状态，而不是依赖 orchestration 自动回放整棵树。

建议工具：

- `context_tree.render_current`
- `context_tree.diff_since`
- `context_tree.read_snapshot`

`context_tree.render_current`：

- 输入：`session_key`、`scope`、`max_tokens`。
- 输出：当前可见树的 compact render。
- 用途：模型迷路、需要重新看当前上下文时主动调用。

`context_tree.diff_since`：

- 输入：`snapshot_id` 或 `revision`。
- 输出：新增/变更/删除节点、schema_enabled 变化、pin/collapse 状态变化。
- 用途：provider-native continuation 下向模型注入 delta。

`context_tree.read_snapshot`：

- 输入：`snapshot_id`。
- 输出：历史 render snapshot 摘要和 refs。
- 用途：trace/debug 或模型需要追溯首轮树。

### Tree-to-Provider Renderer

保留内部 renderer：

- 首轮完整 render。
- 后续只生成 delta render。
- provider mirror 继续产生 tool schemas。
- Context Workspace 仍拥有节点状态和 render snapshot 真相。

### Checklist

- [ ] 新增 `context_tree.render_current`。
- [ ] 新增 `context_tree.diff_since`。
- [ ] 新增 `context_tree.read_snapshot`。
- [ ] Render service 支持 delta render。
- [ ] Provider mirror 支持 tool schema delta summary。
- [ ] Context snapshot 记录 revision 和 parent snapshot。
- [ ] 单测覆盖显式 tree replay。
- [ ] 单测覆盖 schema_enabled delta。

## 4. Tool Module

### Tool Result Protocol

ToolRun result 需要携带 provider protocol refs：

- provider tool call id。
- LLM response item id。
- session tool call item id。
- tool execution plan id。
- result payload visibility。

对 Responses provider：

- Tool result envelope 能转成 `function_call_output`。
- `call_id` 必须来自 provider response item。
- output 保持结构化摘要和完整 payload ref。

### Exec/Process 能力释放

Codex trace 里，模型能脱困的重要原因是 shell 结果足够真实：

- 能看到命令失败。
- 能探测 npm/node/python/playwright。
- 能安装临时依赖。
- 能捕获 stderr/stdout/exit code。

CRXZipple 的 `exec/process` 结果应明确返回：

- cwd。
- command。
- exit code。
- timed out。
- stdout/stderr 摘要和完整 ref。
- runtime capability facts。
- network/install permission state。
- sandbox/approval state。

### Checklist

- [ ] ToolRun 记录 provider call id。
- [ ] ToolRun result envelope 支持 provider-native output mapping。
- [ ] Exec result 返回环境事实。
- [ ] Process result 返回可恢复 session/ref。
- [ ] stderr/stdout 裁剪保留完整 payload ref。
- [ ] 单测覆盖 function_call_output mapping。
- [ ] 单测覆盖 exec failure 结果可用于下一步推理。

## 5. Model / Agent Policy

### Codex/OpenAI Responses 默认策略

在 `EffectiveLlmRequestPolicy` 中按 provider capability 合成：

```json
{
  "parallel_tool_calls": true,
  "prompt_cache_key": "{session_or_run_stable_key}",
  "text": {"verbosity": "low"},
  "include": ["reasoning.encrypted_content"],
  "reasoning": {"effort": "medium"},
  "service_tier": "priority"
}
```

其中：

- `service_tier` 必须可配置，不适合所有环境硬编码。
- `prompt_cache_key` 应稳定绑定 session/run，而不是每轮随机。
- `include` 只在 provider 支持时启用。
- 非 Responses provider 不应收到不支持字段。

### Checklist

- [ ] Model profile capability 声明 provider-native continuation。
- [ ] Agent profile policy 可配置 text verbosity。
- [ ] Runtime settings 可配置 service tier。
- [ ] Policy resolver 生成 prompt cache key。
- [ ] Policy trace 展示每个字段来源。
- [ ] 单测覆盖 Codex/OpenAI Responses policy。
- [ ] 单测覆盖非 Responses provider 字段过滤。

## 6. Operations / Workbench

### Request Trace

Operations 需要区分三类请求视图：

- CRXZipple normalized invocation payload。
- Provider request preview。
- Raw provider payload ref。

Workbench timeline 需要展示：

- 首轮完整 context snapshot ref。
- 后续 continuation request。
- previous response id。
- input delta item 类型。
- tool result -> provider call id。
- context delta。
- updated tool schema count。

### 可见性

继续区分：

- user-visible。
- model-visible。
- trace-visible。
- hidden/internal。

Reasoning raw 默认不展示；reasoning summary 按 policy 展示；provider external item 不伪装成本地 tool run。

### Checklist

- [ ] Operations LLM detail 展示 provider request preview。
- [ ] Trace 展示 previous_response_id。
- [ ] Workbench timeline 展示 continuation badge。
- [ ] Workbench timeline 展示 context delta item。
- [ ] Workbench timeline 展示 provider call id。
- [ ] UI 不把 normalized request 当 actual provider request。
- [ ] 前端 typecheck/build。

## 7. Evidence Frontier

长链探索要自动沉淀关键事实，避免模型重复踩坑。

示例：

- 官网页面需要 JS。
- 直接 curl API 被 anti-bot 拦截。
- Nuxt bundle 暴露 endpoint。
- Playwright 捕获到 S200 `briefInfo`。
- 某个解析假设失败，已校正字段路径。

来源：

- tool result。
- failed command。
- browser/network trace。
- provider response item。
- user correction。

### Checklist

- [ ] 定义 evidence frontier item schema。
- [ ] Tool result 自动提取 failure/success evidence。
- [ ] Orchestration 每轮生成 evidence delta。
- [ ] Context Tree 展示 evidence frontier。
- [ ] 后续 continuation 可注入 evidence delta。
- [ ] Workbench 展示 verified facts 和 remaining gaps。

## 迁移策略

不做历史兼容。

施工前：

1. 停止 daemon。
2. 清空或重建 Postgres/Redis。
3. 执行最新 Alembic。
4. 重建 LLM/tool/agent profiles。
5. 启动 daemon 和 operations observer。

不需要：

- 旧 invocation 数据迁移。
- 旧 session message 兼容。
- 旧 execution chain schema 兼容。

## 验证任务

### 单元测试

- LLM adapter request construction。
- provider-native continuation。
- tool result protocol mapping。
- context tree delta render。
- orchestration loop completion。
- Workbench read model projection。

### 集成测试

1. 首轮用户任务触发 LLM。
2. LLM 返回 tool call。
3. ToolRun 完成。
4. 下一轮 request 使用 `previous_response_id`。
5. 下一轮 input 只有 `function_call_output` 和必要 delta。
6. 模型继续 tool call 或 final answer。
7. Workbench timeline 能显示完整链路。

### 回归任务

使用禁用 browser 的东航查询任务：

```text
去东航官网给我查下昆明到上海周日的票
```

观察指标：

- 是否使用 `previous_response_id`。
- 每轮 input item 数是否稳定低位。
- 是否通过 `exec` 探测环境。
- 是否在失败后切换路径。
- 是否沉淀 evidence frontier。
- 是否最终拿到官网页面或官网接口证据。

## 推进顺序

### Phase 1: Provider Request Trace

- 落 provider request preview。
- 让 Operations/Trace 能看清实际 provider request shape。
- 不改变 loop 行为。

### Phase 2: Provider Native Continuation

- LLM adapter 支持 `previous_response_id`。
- Orchestration 保存 continuation state。
- Tool result 映射 `function_call_output`。

### Phase 3: Context Tree Replay Tool

- 新增 `render_current` / `diff_since` / `read_snapshot`。
- 后续轮次默认不完整回放树。
- 模型显式调用工具看树。

### Phase 4: Request Policy Defaults

- Codex/OpenAI Responses provider options 默认合成。
- prompt cache key、verbosity、parallel tool calls 生效。

### Phase 5: Exec/Process Evidence Quality

- 增强工具结果环境事实。
- evidence frontier 自动沉淀。

### Phase 6: Workbench/Operations 可视化

- continuation、context delta、provider call id、actual request preview 全部可见。

## 施工前决策

- [ ] `previous_response_id` 存储位置：Orchestration run metadata 还是独立 loop state 表。
- [ ] Raw provider payload 是否持久化全文，还是只保存 preview + artifact ref。
- [ ] `service_tier=priority` 是否默认启用，还是仅 agent/model profile 开关。
- [ ] `include=["reasoning.encrypted_content"]` 是否对 Codex family 默认开启。
- [ ] Context Tree delta 是否作为 system message 注入，还是 provider-specific input item。
- [ ] `context_tree.render_current` 最大 token 默认值。
- [ ] Exec 是否允许模型在临时目录安装 npm/pip 依赖，权限由 tool runtime 还是 authorization module 控制。

## 风险

- Provider-native continuation 会让完整上下文不再每轮显式可见，需要 request trace 和 replay 工具保证可审计。
- `previous_response_id` 失效时必须能 fallback 到 transcript replay。
- Tool schema 动态变化必须和 provider call id 映射保持一致。
- 过度暴露 raw provider payload 可能泄露敏感信息，需要 sanitize/ref 策略。
- Exec 能力增强可能扩大操作面，必须保留 authorization 和 sandbox 事实。

## 成功标准

- 最新 Codex/OpenAI Responses invocation 后续轮次出现 `previous_response_id`。
- 后续轮次 `messages` 不再线性增长到几十条。
- Tool result 以 provider-native output item 进入下一轮。
- Context Tree 只有首轮完整发送；后续通过 delta 或显式 tree replay tool 更新。
- Operations 能同时展示 normalized request 和 provider request preview。
- 禁 browser 的东航任务中，agent 能通过 `exec` 自主探测并切换路径，而不是停在静态 fetch 或泛泛拒答。
