# Model / Agent Policy LLM Request Options Plan 2026-06-11

本文记录 LLM request side 的配置来源：哪些能力开关来自 Model Profile，哪些来自 Agent Policy，哪些来自 Settings Runtime Defaults，哪些可由 Turn 覆盖。

关联文档：

- [provider-neutral-llm-response-stream-contract-plan-20260611.md](provider-neutral-llm-response-stream-contract-plan-20260611.md)
- [orchestration-llm-contract-driven-runtime-plan-20260611.md](orchestration-llm-contract-driven-runtime-plan-20260611.md)
- [llm-provider-adapter-response-item-implementation-plan-20260611.md](llm-provider-adapter-response-item-implementation-plan-20260611.md)

## Cutover Assumption

开发前会清除并重建数据库。本计划不保留旧 model profile/default params 兼容语义。旧字段如果不能表达新的 request options，应破坏式调整。

## 配置分层

### Model Profile owns

provider/model 固有能力和默认值：

```text
provider_family
model
api_family
supports_response_items
supports_reasoning_summary
supports_message_phase
supports_parallel_tool_calls
supports_structured_output
default_reasoning_effort
default_max_output_tokens
default_service_tier
default_provider_options
```

### Agent Policy owns

agent 行为偏好：

```text
reasoning_summary_policy
raw_reasoning_policy
tool_use_policy
parallel_tool_calls_policy
final_answer_policy
commentary_visibility_policy
provider_external_item_policy
```

第一版默认值按 Codex parity：

```text
reasoning_summary_policy = visible_and_replay_when_provider_supports
raw_reasoning_policy = hidden_by_default
provider_external_item_policy = history_and_trace_no_toolrun
commentary_visibility_policy = user_progress
final_answer_policy = phase_or_codex_unknown_fallback
```

### Settings Runtime Defaults owns

部署级默认值：

```text
global_max_output_tokens
default_service_tier
prompt_cache_enabled
default_parallel_tool_calls
trace_raw_provider_payload
reasoning_summary_default_visibility
```

### Turn / Run Override owns

单次请求的显式覆盖：

```text
response_format
output_schema
tool_choice
max_output_tokens
reasoning_effort
metadata overrides
```

覆盖必须有来源记录，进入 `LlmRequestEnvelope.metadata.resolution_trace`。

## Effective Request Policy

Orchestration request builder 需要拿到一个已解析结果：

```text
EffectiveLlmRequestPolicy
  reasoning_config
  output_contract
  provider_options
  tool_policy
  visibility_policy
  resolution_trace
```

解析顺序：

```text
runtime defaults
  -> model profile defaults/capabilities
  -> agent policy
  -> turn/run explicit override
```

后层不能开启 provider 不支持的能力，只能降级并写 diagnostic。

## Policy 输出到 Request

```text
reasoning_config:
  effort
  summary
  raw_policy

output_contract:
  response_format
  output_schema
  strict
  final_answer_expectation

provider_options:
  max_output_tokens
  service_tier
  prompt_cache_key
  include

tool_policy:
  tool_choice
  parallel_tool_calls
```

## Operations 可见性

Operations/Trace 应展示：

- effective policy。
- capability downgrade diagnostic。
- override source。
- provider option raw payload。
- prompt cache / service tier 选择。

## 退场项

- Orchestration 内部散落 provider options。
- adapter 靠 `extra_body` 隐式吞所有配置。
- prompt 文案模拟 reasoning/phase 能力。
- request option 无 resolution trace。
- 旧 default params 限制新 capability。

## Checklist

- [ ] 定义 ModelProfile capability fields。
- [ ] 定义 Agent LLM policy fields。
- [ ] 定义 EffectiveLlmRequestPolicy。
- [ ] Settings runtime defaults 增加 request option 默认值。
- [ ] Orchestration request builder 使用 effective policy。
- [ ] Adapter 拒绝或降级 provider 不支持的 option。
- [ ] Operations 展示 policy resolution trace。
- [ ] 清库重建后 model/agent/settings/llm 测试通过。
