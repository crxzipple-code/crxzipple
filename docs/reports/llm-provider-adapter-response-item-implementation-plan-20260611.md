# LLM Provider Adapter Response Item Implementation Plan 2026-06-11

本文记录 provider adapter 如何实现 provider-neutral LLM request/response contract。重点是 OpenAI Responses / Codex Responses 先落地完整 item stream，其他 provider 映射到最小可用 contract。

关联文档：

- [provider-neutral-llm-response-stream-contract-plan-20260611.md](provider-neutral-llm-response-stream-contract-plan-20260611.md)
- [../reference/llm-provider-capability-matrix.md](../reference/llm-provider-capability-matrix.md)
- [orchestration-llm-contract-driven-runtime-plan-20260611.md](orchestration-llm-contract-driven-runtime-plan-20260611.md)
- [model-agent-policy-llm-request-options-plan-20260611.md](model-agent-policy-llm-request-options-plan-20260611.md)

## Cutover Assumption

开发前会清除并重建数据库。本计划不保留旧 adapter 只返回 `LlmResult(text, tool_calls)` 的主路径，不为旧 invocation payload 做兼容解析。

`LlmResult` 只能作为 adapter 从 response items 派生的 summary cache。

第一版 adapter 行为按 Codex parity 对齐：provider 返回的 message/reasoning/tool_call/tool_result/provider external item 都必须保留为 normalized response item；summary/raw delta 进入 response events；只有 completed response item 才作为 durable replay fact。

## Adapter 责任

LLM adapter 负责：

- 将 `LlmRequestEnvelope` 映射为 provider-native request。
- 将 provider stream events 映射为 `LlmResponseEvent`。
- 将 provider completed items 映射为 `LlmResponseItem`。
- 将 provider completion/end_turn/stop_reason 映射为 `LlmContinuationSignal`。
- 保存 raw provider payload 供追溯。
- 提供 derived `LlmResult` summary。

Adapter 不负责：

- 执行 ToolRun。
- 判断 Orchestration run 完成。
- 写 Session。
- 生成 Workbench timeline。

## OpenAI Responses / Codex Responses

### Request Mapping

```text
LlmRequestEnvelope.base_instructions -> instructions
input_items                          -> input
tool_surface                         -> tools/tool_choice/parallel_tool_calls
reasoning_config                     -> reasoning
output_contract                      -> text/response_format/output_schema
provider_options                     -> service_tier/prompt_cache_key/max_output_tokens/include
metadata                             -> metadata/client_metadata
```

### Stream Mapping

| Provider event | CRXZipple event/item |
| --- | --- |
| `response.created` | `invocation_started` |
| `response.output_item.added` | `item_started` |
| `response.output_text.delta` | `text_delta` |
| `response.reasoning_summary_text.delta` | `reasoning_summary_delta` |
| `response.reasoning_text.delta` | `reasoning_raw_delta` |
| `response.function_call_arguments.delta` | `tool_argument_delta` |
| `response.output_item.done: message` | `assistant_message` |
| `response.output_item.done: reasoning` | `reasoning` |
| `response.output_item.done: function_call/custom_tool_call` | `tool_call` |
| `response.output_item.done: function_call_output` | `tool_result` |
| `response.output_item.done: web_search_call/image_generation_call` | `provider_external_item` |
| `response.completed` | `completed` + continuation |
| error event | `failed` |

### Phase / Continuation

- message `phase` 能识别时填 `commentary/final_answer`。
- `completed.end_turn=false` 映射为 `needs_follow_up=true, reason=provider_end_turn_false`。
- tool call item 存在时 continuation reason 至少包含 `tool_call`。

## OpenAI Chat Compatible

最小 mapping：

```text
message.content        -> assistant_message(phase=unknown)
message.tool_calls[]   -> tool_call
delta.content          -> text_delta
delta.tool_calls[]     -> tool_argument_delta or adapter-local merge
finish_reason          -> completed metadata
```

默认：

```text
end_turn=None
needs_follow_up = tool_call items exist
phase=unknown
```

不要把 chat compatible provider 假设成 Responses item stream。

## Anthropic Messages

预期 mapping：

```text
text block        -> assistant_message
tool_use block    -> tool_call
tool_result block -> tool_result
thinking block    -> reasoning, if available
stop_reason       -> continuation metadata
```

thinking/raw reasoning policy 必须按 provider 安全语义处理，不默认写入 Session。

## Gemini GenerateContent

预期 mapping：

```text
text part             -> assistant_message
functionCall part     -> tool_call
functionResponse part -> tool_result
thought part          -> reasoning, if available
finishReason          -> continuation metadata
```

## Raw Payload Retention

每个 event/item 都应保留：

```text
provider_payload
provider_item_id
provider_item_type
provider_response_id
provider_request_id
```

未知 item 使用 `kind=unknown`，不可丢弃。

## Derived Summary

`LlmResult` 派生规则：

- `text` 合并 assistant_message text。
- `tool_calls` 从 local tool_call items 派生。
- `usage` 来自 completed usage。
- `finish_reason` 从 provider status / continuation 派生。
- `metadata` 放 item counts、provider ids、capability flags。

## Checklist

- [x] 定义 adapter 输出 item/event/continuation 的公共接口。
- [x] OpenAI Codex Responses request envelope mapping。
- [x] OpenAI Codex Responses stream item lifecycle mapping。
- [x] reasoning summary delta/item mapping。
- [x] tool argument delta mapping。
- [x] `end_turn=false` continuation mapping。
- [x] provider external item mapping。
- [x] Chat compatible 最小 item mapping。
- [x] Anthropic/Gemini 最小 item mapping。
- [x] unknown item raw payload retention。
- [x] derived `LlmResult` summary 单测。
