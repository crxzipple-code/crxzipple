# LLM Provider Capability Matrix

本文记录不同厂家、不同 API family、不同模型能力在 CRXZipple 中的调用形态和能力边界。它不是提示词文档，也不是厂商营销能力清单；它用于判断：

- provider 实际能返回哪些结构化结果。
- CRXZipple 当前 adapter 消化了哪些能力。
- 哪些能力需要进入新的 agent loop / session / operations contract。

## 维护原则

1. 以“API family + model capability”为单位记录，不以品牌粗粒度下结论。
2. 区分 provider 原生能力、CRXZipple adapter 已支持能力、CRXZipple orchestration 已消费能力。
3. 所有“已确认”能力必须有代码、实测 trace 或官方文档来源；不能只凭模型名推断。
4. hosted/provider builtin capability 不自动等同于 CRXZipple Tool Source。CRXZipple 的可执行能力仍优先由 Tool module/source 管理。
5. 能力矩阵是活文档。厂商 API 和模型能力变化快，落实现时需要同步更新验证日期。

## 当前 CRXZipple API Family

代码入口：`src/crxzipple/modules/llm/domain/value_objects.py`

| API family | Provider kind | Adapter | 当前 CRXZipple 输出形态 |
| --- | --- | --- | --- |
| `openai_responses` | `openai` / compatible | `openai_responses.py` | `LlmResult(text, tool_calls, usage, finish_reason, metadata)` |
| `openai_codex_responses` | `openai_codex` | `openai_codex_responses.py` | `LlmResult(text, tool_calls, usage, finish_reason, metadata)` |
| `openai_chat_compatible` | `openai_compatible` / `ollama` 等 | `openai_chat_compatible.py` | `LlmResult(text, tool_calls, usage, finish_reason, metadata)` |
| `anthropic_messages` | `anthropic` | `anthropic_messages.py` | `LlmResult(text, tool_calls, usage, finish_reason, metadata)` |
| `gemini_generate_content` | `google` | `gemini_generate_content.py` | `LlmResult(text, tool_calls, usage, finish_reason, metadata)` |
| `ollama_native` | `ollama` | 待确认 | 待确认 |

当前公共结果对象仍是压扁形态：

```text
LlmResult
  text
  tool_calls
  structured_output
  usage
  finish_reason
  metadata
```

这意味着 response item lifecycle、reasoning summary、message phase、provider `end_turn`、tool argument delta 等能力目前没有一等化。

## Capability Dimensions

后续评估每个 provider/model 时，按下列维度记录。

| 能力维度 | 含义 | CRXZipple 当前状态 |
| --- | --- | --- |
| Text output | 普通 assistant 文本 | 已支持 |
| Tool calling | 模型输出可执行 tool call | 已支持，压成 `ToolCallIntent` |
| Parallel tool calls | 一次 response 内多个 tool calls | 部分支持，依赖 adapter/provider |
| Tool argument streaming | tool 参数边生成边流式可见 | 未一等化 |
| Structured output | schema/json 输出 | 部分支持，压成 `structured_output` 或 text |
| Vision input | 输入图片/多模态内容 | 部分支持，依赖 adapter |
| Reasoning effort | 控制 reasoning effort | 部分支持，仅 `reasoning_effort` |
| Reasoning summary | provider 返回 reasoning 摘要 | 未一等化 |
| Raw/encrypted reasoning | provider 返回 raw/encrypted reasoning content | 未一等化 |
| Message phase | `commentary` / `final_answer` 等阶段 | 未一等化 |
| Response item lifecycle | item added/delta/done/completed | 未一等化 |
| Continuation signal | `end_turn=false` / needs follow-up | 未一等化 |
| Provider-native continuation transport | provider 是否支持用原生 response state 承接下一轮 | OpenAI Responses HTTP 已支持；Codex HTTP 不支持；Codex WebSocket 同步/async 桥接路径已支持 |
| Incremental input | provider-native continuation 下是否只发送新增 input delta | Codex WebSocket input-item prefix、instructions、tool schema fingerprint 已支持 |
| Hosted builtin tools | provider 自带 web/image/search 等 | 不作为 CRXZipple Tool Source 默认路线 |
| Prompt cache / service tier | provider 请求优化参数 | 部分通过 `extra_body` 或 adapter 支持 |

## OpenAI Responses / Codex Responses

### Continuation Transport Matrix

验证日期：2026-06-14。

| API family / transport | `previous_response_id` 支持 | input 形态 | CRXZipple 状态 | 依据 |
| --- | --- | --- | --- | --- |
| `openai_responses` HTTP | 支持 | HTTP Responses payload 顶层 `previous_response_id` + provider input | 已支持，transport 标记为 `http` | 本仓 adapter 与单测 |
| `openai_codex_responses` HTTP | 不支持 | HTTP `/backend-api/codex/responses` full request | 已禁止发送 `previous_response_id`，防止 `Unsupported parameter` | Codex 源码 `ResponsesApiRequest` 无字段；本地实测错误 |
| `openai_codex_responses` WebSocket | 支持 | WebSocket `response.create(previous_response_id + delta input)` | 同步 adapter 与事件级 async bridge 已实现；input-item prefix、instructions、tool schema fingerprint fallback 已实现；warmup/reuse 待补 | `/Users/crxzy/Documents/codex` 中 `ResponseCreateWsRequest` 与 WebSocket continuation test；本仓 adapter 单测 |

结论：不能只按 `api_family` 判断 provider-native continuation。是否能发送
`previous_response_id` 必须同时看 provider family、transport 和 request schema。
Codex-like continuation 要走 WebSocket transport；Codex HTTP profile 在 WebSocket
完成前只能使用完整 request / tool-result replay。

### Provider Input Shape

Codex CLI 观察到的 OpenAI Responses 请求能力面：

```text
Prompt
  input: Vec<ResponseItem>
  tools: Vec<ToolSpec>
  parallel_tool_calls
  base_instructions
  personality
  output_schema
  output_schema_strict
```

Responses 请求可包含：

```text
model
instructions
input
tools
tool_choice = auto
parallel_tool_calls
reasoning
store
stream = true
include
service_tier
prompt_cache_key
text/output_schema
client_metadata
```

### Provider Output Shape

Codex CLI 可消费的 response stream 包括：

```text
Created
OutputItemAdded(ResponseItem)
OutputTextDelta
ToolCallInputDelta
ReasoningSummaryDelta
ReasoningSummaryPartAdded
ReasoningContentDelta
OutputItemDone(ResponseItem)
Completed { token_usage, end_turn, ... }
```

常见 `ResponseItem`：

```text
Message { role, content, phase }
Reasoning { summary, content, encrypted_content }
FunctionCall
FunctionCallOutput
CustomToolCall
CustomToolCallOutput
ToolSearchCall
ToolSearchOutput
LocalShellCall
WebSearchCall
ImageGenerationCall
Compaction
ContextCompaction
Other
```

### CRXZipple 当前消化情况

| 上游能力 | 当前 adapter 消化 | 当前 orchestration 消费 |
| --- | --- | --- |
| `output_text` | `text_delta` / `LlmResult.text` | 作为 assistant text |
| `function_call` | `LlmResult.tool_calls` | 执行 Tool module |
| usage tokens | `LlmUsage` | Operations/diagnostics |
| reasoning tokens | `openai_codex_responses` 部分记录 | Operations/diagnostics |
| reasoning summary | 未消化 | 不可见 |
| message phase | 未消化 | 不可见 |
| `end_turn` | 未消化 | 不参与 loop |
| output item lifecycle | 只收集 completed output item 辅助最终 build | 不作为 turn item |
| tool argument delta | 未消化 | 不可见 |
| hosted web/image | 不作为标准 Tool Source | 不应照抄为默认路线 |

### 适配结论

OpenAI Responses 类模型的能力已经超过 `text + tool_calls`。CRXZipple 后续应增加 provider-neutral response item contract，而不是把 OpenAI hosted tool 模式照搬为系统标准。

建议抽象：

```text
LlmResponseEvent
  invocation_started
  item_started
  text_delta
  reasoning_summary_delta
  tool_argument_delta
  item_completed
  completed(end_turn, usage)
  failed

LlmResponseItem
  assistant_message(phase)
  reasoning_summary
  tool_call
  tool_result
  structured_output
  provider_external_item
  compaction
```

## OpenAI Chat Compatible

### 常见输入输出

典型接口是 chat messages + tools/function calling：

```text
messages[]
tools[]
tool_choice
stream
response_format
temperature/top_p/max_tokens
```

典型输出：

```text
assistant message content
tool_calls[]
finish_reason
usage
stream delta
```

### CRXZipple 当前消化情况

| 能力 | 当前状态 |
| --- | --- |
| Text output | 已支持 |
| Tool calling | 已支持 |
| XML-ish fallback tool call parsing | 已支持 |
| Streaming text delta | 已支持 |
| Streaming tool-call argument delta | adapter 内合并，未一等化暴露 |
| Structured output | 部分支持 |
| Reasoning summary / message phase / end_turn | 通常无原生等价，未一等化 |

### 适配注意

OpenAI-compatible 不等于 OpenAI Responses。部分本地/代理模型只实现 chat-completions 子集。不能把 Responses item stream 能力假设到所有 compatible provider 上。

## Anthropic Messages

### 待确认维度

需要按官方文档和实测补齐：

| 能力 | 状态 |
| --- | --- |
| Text output | 当前 adapter 支持 |
| Tool use / tool result | 当前 adapter 支持 |
| Streaming text | 待确认当前 adapter 是否一等化 |
| Thinking / extended thinking | 待确认 |
| Thinking summary | 待确认 |
| Message phase | 待确认 |
| Continuation signal | 待确认 |
| Structured output | 待确认 |
| Vision input | 待确认 |

### 适配注意

不要把 Anthropic 的 content block/tool_use 直接塞进 OpenAI ResponseItem 语义。应先归一到 CRXZipple-native response item，再由 Anthropic adapter 负责 provider-specific 编解码。

## Google Gemini GenerateContent

### 待确认维度

| 能力 | 状态 |
| --- | --- |
| Text output | 当前 adapter 支持 |
| Function calling | 当前 adapter 支持 |
| Streaming | 待确认 |
| Thought/reasoning signal | 待确认 |
| Structured output/schema | 待确认 |
| Vision/multimodal input | 待确认 |
| Tool result protocol | 待确认 |

### 适配注意

Gemini 的 `content/parts/functionCall/functionResponse` 形态应映射到 CRXZipple-native response item，而不是硬套 chat-completions message。

## Ollama / Local Models

### 待确认维度

| 能力 | 状态 |
| --- | --- |
| Text output | 待确认 |
| Tool calling | 依赖模型和 OpenAI-compatible 层 |
| Streaming | 待确认 |
| Structured output | 依赖模型和 API |
| Reasoning summary | 通常不可假设 |
| Vision input | 依赖模型 |

### 适配注意

本地模型能力差异非常大。profile 必须能表达“能力可用性”，orchestration 不应仅按 provider kind 推断。

## CRXZipple 目标消化层

不是照抄某一家 provider，而是建立 provider-neutral 的消化层。

### Adapter Layer

Adapter 应从 provider-native response 映射为：

```text
LlmResponseEvent
LlmResponseItem
LlmContinuationSignal
```

并保留必要 raw payload：

```text
provider_payload
provider_item_id
provider_item_type
provider_sequence
```

### Orchestration Layer

Orchestration 继续作为综合 runtime 流程 owner：

```text
consume response item stream
decide needs_follow_up
call Tool module
write Session module
publish Execution events
update Context Workspace references
```

终止条件不应继续只依赖 `tool_calls`：

```text
no local tool pending
and provider end_turn is not false
and no pending input/hook/approval/waiting continuation
=> turn may complete
```

### Session Layer

Session 不必成为 UI 时间线镜像，但需要能保存可重放 agent history：

```text
session turn item
  kind
  role/phase
  content_payload
  provider_payload
  model_visible
  user_visible
  source_kind/source_id
  sequence_no
```

### Context Workspace Layer

Context Workspace 不拥有 provider response truth。它消费 Session/Orchestration facts，决定哪些 turn item 进入 agent-facing context tree render snapshot。

## Verification Checklist

为某个 provider/model 标记能力前，至少完成：

- [ ] 记录 provider、model、api_family、adapter。
- [ ] 保存一次原始请求 payload 样本。
- [ ] 保存一次原始 response / stream event 样本。
- [ ] 标注 text/tool/reasoning/phase/end_turn/usage 是否存在。
- [ ] 标注 adapter 当前是否保留该字段。
- [ ] 标注 orchestration 当前是否消费该字段。
- [ ] 标注 session/context/workbench 当前是否可见。
- [ ] 若能力不可用，区分 provider 不支持、model 不支持、profile 未开启、adapter 未消化。

## Open Questions

- 是否将 `reasoning_summary` 默认 user-visible、但按策略决定 model-visible？
- 是否为 `message phase` 定义 CRXZipple-native enum：`commentary` / `final_answer` / `unknown`？
- 是否让 `context_tree.update_plan` 继续作为 Tool module 能力，还是引入 first-class `plan_update` item？
- 是否允许 provider-hosted capabilities 作为 `provider_external_item` 进入 history，但不注册为 Tool Source？
- 是否为所有 streaming adapters 提供统一 item lifecycle event？
