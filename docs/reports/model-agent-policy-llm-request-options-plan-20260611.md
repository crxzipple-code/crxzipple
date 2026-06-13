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

- [x] 定义 ModelProfile capability/default fields。
- [x] 定义 Agent LLM policy fields。
- [x] 定义 EffectiveLlmRequestPolicy。
- [x] Settings runtime defaults 增加 request option 默认值。
- [x] Orchestration request builder 使用 effective policy。
- [x] Adapter 前置 policy resolver 降级 provider 不支持的 reasoning option。
- [x] Operations 展示 policy resolution trace。
- [x] model/agent/settings/llm 目标回归通过。
- [x] 清库重建后 model/agent/settings/llm smoke 通过。

## 施工状态 2026-06-12

- `src/crxzipple/modules/orchestration/application/llm_request_policy.py`
  已新增 `EffectiveLlmRequestPolicy` 和 resolver。
- `RunPromptInput` 已携带 `llm_defaults`，由 `RunPromptInputCollector`
  从 `LlmProfile.default_params.to_payload()` 填充。
- Agent Profile 已新增 `llm_policy`，agent home config、settings import、
  HTTP request/response、CLI settings sync 和 DTO 均可读写该策略。
- `RunPromptInput` 已携带 `llm_policy`，由 `RunPromptInputCollector`
  从 `AgentProfile.llm_policy.to_payload()` 填充。
- Engine preview/真实 invoke 已使用 effective policy 合成
  `provider_options`、`reasoning_config`、`output_contract`。
- Agent LLM policy 已进入 effective policy resolver：reasoning summary policy
  会在 provider 支持 reasoning 时默认请求 `summary=auto`，不支持时写入
  downgrade trace；final answer/tool use policy 会进入 `output_contract`，
  parallel tool calls policy 会在明确 enabled/disabled 时进入
  `provider_options`。
- Settings 已新增 `llm_request_defaults`，由 `APP_LLM_REQUEST_DEFAULTS`
  JSON object 加载；assembly 会将其注入 `RunPromptInputCollector`，
  `RunPromptInput.runtime_llm_defaults` 再交给 effective policy resolver。
- runtime defaults 已支持 `max_output_tokens`、`reasoning_effort`、
  `service_tier`、`prompt_cache_enabled`、`parallel_tool_calls`、
  `trace_raw_provider_payload`、`reasoning_summary_default_visibility` 和
  `extra_body`，解析顺序为 runtime defaults -> model defaults ->
  agent policy -> run override。
- 2026-06-14 已补充 Codex/OpenAI Responses 风格 provider options：
  runtime/model defaults 可配置 `response_verbosity`、`text`、`include`、
  `include_reasoning_encrypted_content`；当 `prompt_cache_enabled=true`
  且未显式提供 `prompt_cache_key` 时，resolver 会从 run 的 session/agent
  上下文生成稳定 `prompt_cache_key`。
- 2026-06-14 已补充 provider capability filter：当 `RunPromptInput`
  携带的 `llm_api_family` 不是 OpenAI Responses / Codex Responses 时，
  resolver 会移除 `include`、`parallel_tool_calls`、`prompt_cache_key`、
  `prompt_cache_enabled`、`text` 等 Responses-only provider options，并在
  resolution trace 中记录 downgraded 原因。
- request metadata 已写入 `llm_request_policy` payload，包含 resolution trace。
- LLM Operations invocation detail 已新增 `policy_trace` 表格，展示
  `field`、`source`、`status`、`value`、`reason`，前端 LLM Operations 抽屉
  已展示该表格。
- reasoning option 会在模型缺少 `LlmCapability.REASONING` 时降级并记录
  `llm_capability_not_supported`。
- 2026-06-12 已补跑 `test_llm_settings_integration.py`、`test_agent_http.py`、`test_app_assembly_module_local.py`，共 40 个测试通过。
- Docker reset 后已补跑 model/agent/LLM 组合回归：`test_llm_settings_integration.py`、`test_agent_http.py`、`test_app_assembly_module_local.py`、`test_llm.py`、`test_llm_adapters.py` 共 99 个测试通过；`llm list` 可读取 6 个 imported profiles。
