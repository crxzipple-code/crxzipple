# Codex WebSocket Continuation Transport Plan

Date: 2026-06-14

## 背景

本轮重新审查 `/Users/crxzy/Documents/codex` 源码后，确认此前对 Codex continuation 的理解需要修正：

- Codex 确实使用 `previous_response_id`。
- 但它不是普通 HTTP `/responses` request 的字段。
- 它属于 Codex Responses WebSocket transport 的 `response.create` 消息字段。
- CRXZipple 当前 `openai_codex_responses` adapter 使用的是 HTTP endpoint：`https://chatgpt.com/backend-api/codex/responses`。
- 该 HTTP endpoint 实测拒绝顶层 `previous_response_id`，错误为 `Unsupported parameter: previous_response_id`。

因此，CRXZipple 不能把 Codex HTTP adapter 简单按 OpenAI Responses HTTP continuation 来实现。真正对齐 Codex 的路径是：新增 Codex WebSocket transport，并在 WebSocket `response.create` 消息中实现 incremental continuation。

## Codex 源码证据

### HTTP request 不含 `previous_response_id`

Codex HTTP request 类型定义：

`/Users/crxzy/Documents/codex/codex-rs/codex-api/src/common.rs`

- `ResponsesApiRequest` 定义在 180 行附近。
- 字段包括 `model`、`instructions`、`input`、`tools`、`tool_choice`、`parallel_tool_calls`、`reasoning`、`store`、`stream`、`include`、`service_tier`、`prompt_cache_key`、`text`、`client_metadata`。
- 该 struct 没有 `previous_response_id`。

### WebSocket `response.create` 含 `previous_response_id`

同文件：

- `ResponseCreateWsRequest` 定义在 226 行附近。
- 字段包含 `previous_response_id: Option<String>`。

`From<&ResponsesApiRequest> for ResponseCreateWsRequest` 初始转换时把它设为 `None`，随后 WebSocket incremental path 再按条件填充。

### WebSocket incremental path 写入 `previous_response_id`

`/Users/crxzy/Documents/codex/codex-rs/core/src/client.rs`

- `prepare_websocket_request` 定义在 1059 行附近。
- 它读取 `last_response.response_id`。
- 通过 `get_incremental_items` 判断当前 request input 是否可以基于上一轮压缩为 delta。
- 成功时构造：

```rust
ResponsesWsRequest::ResponseCreate(ResponseCreateWsRequest {
    previous_response_id: Some(last_response.response_id),
    input: incremental_items,
    ..payload
})
```

### HTTP path 不做 incremental continuation

同文件：

- `stream_responses_api` 定义在 1238 行附近。
- 它调用 `build_responses_request(...)` 得到 `ResponsesApiRequest`。
- 随后 `client.stream_request(request, options).await`。
- 该 path 没有给 HTTP request 添加 `previous_response_id` 的逻辑。

### WebSocket test 明确断言

`/Users/crxzy/Documents/codex/codex-rs/core/tests/suite/client_websockets.rs`

测试断言第二个 WebSocket request：

```rust
assert_eq!(second["type"].as_str(), Some("response.create"));
assert_eq!(second["previous_response_id"].as_str(), Some("resp-1"));
assert_eq!(second["input"], prompt_two.input[2..])
```

结论：Codex continuation 的准确形态是 `WebSocket response.create + previous_response_id + delta input`，不是 HTTP `/responses + previous_response_id`。

## 当前 CRXZipple 错位点

### 已发生的问题

CRXZipple 当前 Codex adapter 构造 HTTP payload：

```json
{
  "model": "gpt-5.5",
  "instructions": "...",
  "input": [{"type": "function_call_output", "...": "..."}],
  "previous_response_id": "resp_xxx",
  "stream": true
}
```

该 payload 发送到：

```text
https://chatgpt.com/backend-api/codex/responses
```

实测失败：

```text
Unsupported parameter: previous_response_id
```

### 已做止血

当前已临时收窄：

- `openai_responses` 继续允许 provider-native continuation。
- `openai_codex_responses` 不再通过 HTTP 发送 `previous_response_id`。
- Codex HTTP adapter 即便收到 continuation，也防御性忽略。

这是正确止血，但不是最终 Codex-like 对齐。

## 目标

实现 Codex WebSocket continuation transport，使 CRXZipple 能按 Codex 源码一致的协议工作：

```text
首轮:
WebSocket response.create(full request)

后续可增量轮次:
WebSocket response.create(previous_response_id + delta input)

无法增量轮次:
WebSocket response.create(full request, no previous_response_id)
```

同时保持 provider-neutral LLM module 设计：

- LLM module 暴露 provider transport capability，不把 WebSocket 细节泄漏给 orchestration。
- Orchestration 只表达 normalized request、tool result、context delta 和 continuation intent。
- Adapter 根据 profile capability 选择 HTTP full request 或 WebSocket incremental request。
- Operations 记录 normalized request 和 provider actual request preview，明确 transport。

## 非目标

- 不把 Codex 专有 WebSocket 协议硬塞给所有 provider。
- 不在 HTTP Codex adapter 上继续试探 `previous_response_id`。
- 不恢复完整 transcript 每轮无限增长作为长期方案。
- 不照抄 Codex hosted `web_search` / `image_generation` 特权工具。
- 不做历史数据兼容。开发前允许清库重建。

## 设计原则

1. Transport-aware continuation。
   `previous_response_id` 是否可用取决于 provider family + transport，不只取决于 API family。

2. HTTP 和 WebSocket request schema 分离。
   HTTP `ResponsesApiRequest` 不应包含 Codex WebSocket 字段。

3. Incremental input 必须可验证。
   只有当前 input 可证明以前一轮 input fingerprints 为前缀，且 instructions/tool schema fingerprints 均匹配时，才发送 `previous_response_id + suffix input`；无法验证时回退 full request，不发送 `previous_response_id`。

4. 失败后回退完整 request。
   WebSocket 连接失败、上一轮 response id 缺失、provider 返回协议错误、fingerprints 缺失或不匹配时，回退 full request，不发 `previous_response_id`。

5. 实际 provider payload 必须可观察。
   Workbench/Operations 必须能看到 transport、payload keys、input delta count、previous response id 是否使用。

## 模块改造

## 1. LLM Module

### 1.1 Profile capability

新增或明确以下 capability：

```python
LlmCapability.PROVIDER_NATIVE_CONTINUATION
LlmCapability.PROVIDER_WEBSOCKET_TRANSPORT
LlmCapability.PROVIDER_INCREMENTAL_INPUT
```

建议含义：

- `PROVIDER_NATIVE_CONTINUATION`：provider 支持承接上一轮 response state。
- `PROVIDER_WEBSOCKET_TRANSPORT`：adapter 可使用 WebSocket transport。
- `PROVIDER_INCREMENTAL_INPUT`：adapter 可在 provider-native continuation 下发送 delta input。

`openai_responses`：

- HTTP 可继续支持 `previous_response_id`，如实测可用。

`openai_codex_responses`：

- HTTP 不支持 `previous_response_id`。
- WebSocket 支持 `previous_response_id + delta input`。

### 1.2 Adapter request

扩展 `LlmAdapterRequest` 或 provider options：

```python
provider_transport: "http" | "websocket" | "auto"
continuation: LlmProviderContinuation | None
```

`LlmProviderContinuation` 增加 transport 语义：

```python
LlmProviderContinuation(
    mode: "provider_native",
    previous_response_id: str | None,
    previous_invocation_id: str | None,
    provider_family: str | None,
    transport: "http" | "websocket" | None,
)
```

### 1.3 Provider request preview

`provider_request_payload_preview` 必须增加：

```python
{
  "transport": "http" | "websocket",
  "message_type": "response.create" | null,
  "payload_keys": [...],
  "has_previous_response_id": true | false,
  "previous_response_id": "...",
  "input_item_count": 1,
  "input_item_types": [...],
  "input_delta_mode": true | false,
  "input_baseline_count": 12,
  "input_delta_count": 1
}
```

### 1.4 Codex WebSocket adapter

当前实现方式：在 `OpenAICodexResponsesAdapter` 内部增加 WebSocket path，由 `provider_transport` 选择 HTTP 或 WebSocket。

不拆新 adapter 的原因：HTTP 和 WebSocket 共享 Codex payload normalization、tool schema alias、response event normalization、reasoning parsing 和 OAuth credential resolution。现阶段拆 adapter 会复制协议逻辑；后续如果 WebSocket connection pool / warmup 需要独立生命周期，再抽 transport class。

职责：

- 建立 WebSocket 连接。
- 发送 `response.create`。
- 解析 SSE-like / WS event stream。
- 保持与 HTTP adapter 一致的 `LlmAdapterResponse`、`LlmResponseItem`、`LlmContinuationSignal`。
- 保存 `last_request_input` 与 `last_response_id`，用于下一轮增量判断。

注意：adapter 内部不能持有跨 run 的全局 mutable state。连接状态应由 invocation/request scope 或 orchestration continuation state 显式传递。

## 2. Orchestration Module

### 2.1 Continuation state

扩展 run metadata 中的 provider continuation state：

```python
{
  "mode": "provider_native",
  "provider_family": "openai_codex_responses",
  "transport": "websocket",
  "previous_response_id": "resp_xxx",
  "previous_invocation_id": "inv_xxx",
  "last_request_input_fingerprint": "...",
  "last_request_input_count": 12,
  "last_context_snapshot_id": "ctxsnap_xxx",
  "last_context_revision": 8,
  "last_tool_surface_snapshot_id": "tool_surface_xxx"
}
```

### 2.2 Request builder

Orchestration 继续构造 normalized full request envelope：

- system/runtime instructions
- context tree snapshot or delta
- visible transcript window
- tool result messages
- tool schemas

不要在 orchestration 内直接裁剪成 provider delta。delta 判断交给 LLM adapter 或一个 LLM request shaping service。

### 2.3 Continuation gate

当前 gate 不能只看 `api_family`。

目标判断：

```text
if provider supports HTTP native continuation:
    continuation transport = http
elif provider supports WebSocket native continuation and profile transport allows websocket:
    continuation transport = websocket
else:
    transcript replay
```

Codex profile：

- HTTP transport：不发 `previous_response_id`。
- WebSocket transport：允许 `previous_response_id`。

### 2.4 Error recovery

如果 Codex WebSocket continuation 失败：

- 记录 provider error。
- 清空 `previous_response_id` continuation state。
- 下一轮回退 full request。
- 不把 run 直接 fail，除非 full request 也失败或达到 retry limit。

## 3. Context Workspace Module

### 3.1 Tree replay tool

保留当前计划：把 Context Tree replay/read 做成 agent-facing tool。

必要工具：

- `context_tree.list`
- `context_tree.expand`
- `context_tree.diff_since`
- `context_tree.render_current`
- `context_tree.read_snapshot`

用途：

- 首轮可给完整树。
- 后续不自动完整重发。
- 模型需要重新看树时显式调用工具。

### 3.2 Snapshot 与 delta

Context Workspace 仍负责：

- render snapshot
- render snapshot id
- tree revision
- provider tool schema mirror
- snapshot diff

Orchestration 只引用 snapshot，不拥有树真相。

## 4. Tool Module

### 4.1 Tool result protocol

工具结果必须保留 provider call id：

```python
ToolRunResultEnvelope(
    tool_call_id="call_xxx",
    provider_call_id="call_xxx",
    output_text="...",
    output_json={...},
)
```

### 4.2 Provider output item

Responses/Codex WebSocket 下，工具结果映射为：

```json
{
  "type": "function_call_output",
  "call_id": "call_xxx",
  "output": "..."
}
```

不能把 tool result 只作为普通 assistant/user message 回放。

## 5. Operations / Workbench

### 5.1 Invocation detail

展示新增字段：

- provider transport
- message type
- previous response id used
- input full/delta
- input item count
- tool schema count
- provider actual request preview
- normalized request count

### 5.2 Timeline

对于 Codex-like WebSocket continuation，应展示：

```text
LLM request
transport=websocket
message=response.create
continuation=previous_response_id
input=delta(1/13)
```

对于 fallback full request：

```text
LLM request
transport=websocket
message=response.create
continuation=full_request
reason=prefix_mismatch
```

### 5.3 错误提示

如果发生 `Unsupported parameter: previous_response_id`：

用户可见提示应是：

```text
当前 provider transport 不支持 previous_response_id，已切换为完整请求重试。
```

如果完整请求也失败，再显示 provider 原始错误。

## 施工阶段

## Phase 0: 文档和能力纠偏

- [x] 确认 Codex 源码中 `previous_response_id` 所在协议位置。
- [x] 确认 HTTP Codex endpoint 实测拒绝 `previous_response_id`。
- [x] 暂时禁止 Codex HTTP adapter 发送 `previous_response_id`。
- [x] 更新旧文档中“Codex HTTP 支持 previous_response_id”的错误描述。
- [x] 在能力参考文档中记录 HTTP/WebSocket continuation 差异。

## Phase 1: Provider capability model

- [x] 增加 transport-aware continuation capability。
- [x] Profile sync 不再按 api_family 粗暴附加 continuation。
- [x] LLM settings/read model 展示 transport capability。
- [x] 单测覆盖 Codex HTTP 不支持 continuation。
- [x] 单测覆盖 Codex WebSocket 支持 continuation。

2026-06-14 进展：

- `LlmCapability` 已增加 `provider_websocket_transport`、`provider_incremental_input`。
- `LlmProviderContinuation` 已增加 `transport` 字段，并支持 payload roundtrip。
- `LlmAdapterRequest` 已增加 `provider_transport` 字段。
- provider actual request preview 已增加 `transport`、`message_type`、`input_delta_mode`、`input_baseline_count`、`input_delta_count`。
- Codex HTTP adapter preview 明确为 `transport=http`，且不包含 `previous_response_id`。
- OpenAI Responses native continuation state 已记录 `transport=http`。
- Workbench continuation timeline 已展示 provider transport。
- Operations LLM invocation request context 已展示 provider transport 和 input delta preview。

## Phase 2: Codex WebSocket transport

- [x] WebSocket transport request guard：要求 WebSocket 时不再静默走 HTTP。
- [x] WebSocket transport preview 标记 `transport=websocket`、`message_type=response.create`。
- [x] 实现同步 WebSocket connection 建立。
- [x] 实现同步 `response.create` request 发送。
- [x] 实现同步 event stream 解析。
- [x] 映射 assistant message、tool call、completed event。
- [x] 补齐 WebSocket reasoning summary 专项回归。
- [x] 记录 response id。
- [x] 记录 provider actual request preview。
- [x] 实现 async WebSocket transport。
- [x] async WebSocket bridge 支持事件级转发。
- [x] WebSocket transient error 在未输出前自动重试。
- [x] 实现 WebSocket connection reuse。
- [x] 实现 WebSocket warmup。

2026-06-14 进展：

- Codex adapter 已过滤内部 `provider_transport` override，避免泄漏到 provider payload。
- Codex adapter 在 `provider_transport=websocket` 时会生成 WebSocket preview：`wss://.../responses`、`type=response.create`。
- 同步 `invoke()` 已可通过 WebSocket 发送 `response.create` 并读取 text frame event 到 `response.completed`。
- WebSocket `response.output_item.done` 已复用现有 output item cache，可在 completed 不带 output 时还原 tool call。
- WebSocket reasoning summary/raw reasoning delta 已有专项回归，走与 SSE 一致的 `reasoning_summary_delta` / `reasoning_raw_delta` normalized event。
- WebSocket request 携带 `OpenAI-Beta: responses_websockets=2026-02-06`。
- WebSocket continuation 在 provider 拒绝 delta 且尚未输出任何内容时，会自动清空 continuation 并用 full request 重试一次。
- WebSocket connection/transport/server transient error 在尚未输出任何事件前，会按现有 stream retry policy 重试，不产生额外 orchestration trace item。
- async WebSocket transport 当前是线程桥接版，已避免 daemon async 路径直接 `NotImplementedError`；bridge 会按事件转发 `text_delta` / item / completed，不再等 completed 后一次性回放。原生 async WebSocket client 仍待实现；主动 warmup 已通过 service/HTTP/CLI 暴露。
- Adapter 已增加实例级 WebSocket connection pool：正常 `response.completed` 后连接回池，下一次同 endpoint/header/timeout 的 Codex WebSocket request 复用连接；异常、fallback 失败或显式 `close_websocket_pool()` 时关闭连接。
- WebSocket connection reuse 是 adapter 内部能力，不发布 orchestration trace item，也不改变 LLM invocation request/response contract。
- Adapter 已提供 `warmup_websocket(profile, resolved_credential=...)`，只建立并缓存 WebSocket 连接，不发送 `response.create`。
- LLM application service 已提供 `warmup_profile` 入口：解析 profile credential 后调用 adapter warmup；该入口不创建 LLM invocation，不发布 orchestration run trace。
- LLM HTTP/CLI 已暴露 profile warmup 入口：`POST /llms/{llm_id}/warmup` 与 `llm warmup <llm_id>`；两者走 `llm.warmup` 授权动作，返回 transport/endpoint/reuse 等预检结果，不创建 invocation。
- Operations 已暴露受控 warmup action：`POST /operations/llm/profiles/{llm_id}/warmup`。该入口先写 Operations action audit，再授权并委托 LLM owner service；成功/失败结果进入 action audit，profile warmup 事实仍由 LLM owner event 承载。
- LLM owner event 已覆盖 warmup 结果：`llm.profile_warmup_succeeded` / `llm.profile_warmup_skipped` / `llm.profile_warmup_failed`。这些事件描述 profile transport readiness，不创建 invocation，也不改变 orchestration run。
- Operations `Provider Access & Health` / `Provider Auth / Access Blocked` 已展示最近 warmup 状态和下一步处理建议，用户无需展开 JSON 即可看到 `Warmed`、`Skipped`、`Failed`、`Run warmup`、`Check WebSocket transport` 等状态；LLM Operations 页面已提供 profile warmup 操作条，从 Operations action 入口触发，不绕过 `/operations` 数据/操作面。
- Settings / LLM Profiles 已提供 Warmup 操作按钮：针对已保存 profile 调用 `POST /llms/{llm_id}/warmup`，在同一侧栏展示 status、transport、endpoint 和 connection reuse 摘要；Direct Test 仍保留为当前表单 payload 的 `/llms/test` 冒烟测试。

## Phase 3: Incremental input

- [x] 保存上一轮 normalized provider input fingerprint。
- [x] 判断当前 input 是否以前一轮为前缀。
- [x] WebSocket continuation 时发送 tool-result delta input。
- [x] prefix mismatch 时发送 full input，且不发送 `previous_response_id`。
- [x] 缺少 previous response id 时发送 full input。
- [x] 缺少上一轮 input fingerprints 时发送 full input，且不发送 `previous_response_id`。
- [x] instructions/system prompt fingerprint mismatch 时发送 full input，且不发送 `previous_response_id`。
- [x] tool schema fingerprint mismatch 时发送 full input，且不发送 `previous_response_id`。
- [x] WebSocket request transient retry 不污染 run trace。
- [x] Context Tree 状态不再作为隐式 provider-native continuation delta 自动重发；模型需要树状态时显式调用 `context_tree.*`。
- [x] Context Tree continuation 场景下，树/指令 fingerprint 变化不再污染 provider-native continuation；fingerprint 不匹配时走 full input，模型需要树状态时显式调用 `context_tree.*`。
- [x] WebSocket connection reuse 不污染 run trace。
- [x] WebSocket warmup 不污染 run trace。

2026-06-14 进展：

- Codex WebSocket continuation 已改为 fingerprint 驱动，而不是只按 `previous_response_id` 粗暴裁剪。
- provider request preview 已记录 `input_item_fingerprints`、`input_baseline_fingerprints`、`instructions_fingerprint`、`tool_fingerprints`、`input_delta_mode`、`input_baseline_count`、`input_delta_count`。
- Orchestration 会把上一轮 `input_baseline_fingerprints`、`instructions_fingerprint`、`tool_fingerprints` 保存到 `provider_continuation_state`，下一轮通过 `LlmProviderContinuation` 回传给 adapter。
- 当 profile 默认参数或本轮 request option 解析出 `provider_transport=websocket`、存在 `previous_response_id`、存在上一轮 fingerprints，且当前 full input 以前一轮 fingerprints 为前缀时，发送 suffix input 并带上 `previous_response_id`。
- 如果缺少 fingerprints、instructions mismatch、tool schema mismatch、prefix mismatch 或缺少 `previous_response_id`，则发送 full input 且不带 `previous_response_id`。

## Phase 4: Orchestration integration

- [x] continuation state 增加 transport。
- [x] continuation gate 改为 provider family + transport capability。
- [x] Codex WebSocket profile 使用 WebSocket continuation。
- [x] Codex HTTP profile 使用 full request。
- [x] continuation failure 自动 fallback full request。
- [x] run metadata 记录 fallback reason。
- [x] invoke 阶段复用 request envelope provider options 计算 continuation，避免二次计算丢失 `provider_transport=websocket`。
- [x] LLM profile 默认参数支持声明 `provider_transport`。
- [x] Orchestration request policy 从 profile default params 下发 `provider_options.provider_transport`。

2026-06-14 进展：

- OpenAI Responses HTTP profile 继续允许 provider-native continuation。
- Codex HTTP profile 不允许 provider-native continuation。
- Codex WebSocket profile 只有在 `provider_transport=websocket` 且 profile capability 同时包含 `provider_native_continuation`、`provider_websocket_transport`、`provider_incremental_input` 时才允许 continuation。
- Settings profile import 已支持 Codex WebSocket capability 自动补齐 `provider_native_continuation`。
- `provider_transport` 已从 LLM profile default params / request overrides 进入 `LlmAdapterRequest.provider_transport`，同时由 adapter 过滤避免泄漏到 provider payload。
- Codex WebSocket profile 可在 `default_params.provider_transport=websocket` 中声明默认 transport；orchestration 测试已移除 run metadata 临时 override，避免把 transport 选择做成单次任务私有配置。
- Orchestration invoke 阶段已复用 `request_envelope.provider_options` 重新计算 continuation；此前 `_build_advance_context` 能正确判定 WebSocket continuation，但实际 invoke 二次计算未传 provider options，会导致 Codex 第二轮丢失 `previous_response_id`。
- 当前 fallback 先在 Codex adapter 内完成：只处理“尚未输出前的 WebSocket continuation 拒绝/协议错误”，不会覆盖已经开始输出的 stream，也不会吞掉 server_error 可重试异常。fallback 成功时会写入 LLM result metadata：`provider_continuation_fallback=true`、`provider_continuation_fallback_reason=websocket_continuation_failed_before_output`。
- Orchestration 已从 LLM result metadata 提取 fallback 状态，并写入 `provider_continuation_state.fallback` / `provider_continuation_state.fallback_reason`，用于后续 continuation decision、Workbench 和 Operations 展示。

## Phase 5: Context Tree replay tool

- [x] `context_tree.expand` / `context_tree.list` 支持按节点句柄查看树内容。
- [x] `context_tree.render_current` 支持当前可见树重放。
- [x] `context_tree.diff_since` 支持 snapshot id/revision diff。
- [x] `context_tree.read_snapshot` 支持历史 render snapshot 读取。
- [x] prompt 中说明模型需要重读树时显式调用工具。
- [x] provider-native continuation 后续轮次不再每轮自动完整重发树。

2026-06-14 进展：

- Context Tree replay 已由 `tools/context_tree` 提供：`list` / `expand` / `render_current` / `read_snapshot` / `diff_since`。
- `context_tree.render_current` 默认输出上限为 `max_chars=16000`，避免 replay 工具本身引入额外 token estimator 依赖。
- Context Tree usage guide 已提示模型需要重读完整当前可见树时调用 `context_tree.render_current`。
- Orchestration provider-native continuation 场景已经通过 Context Workspace snapshot metadata 注入 delta，不再依赖每轮完整树回放。

## Phase 6: Observability

- [x] LLM invocation read model 暴露 transport preview。
- [x] Operations projection 存储 provider actual request preview。
- [x] LLM preview 写入后发布 `llm.invocation_provider_request_prepared` 事件。
- [x] LLM profile warmup 发布 owner event。
- [x] Operations profile access 表展示最近 warmup 状态和 next action。
- [x] Settings LLM profile 页面可直接触发 saved profile warmup。
- [x] Operations LLM 页面可直接触发 saved profile warmup，并写入 Operations action audit。
- [x] Workbench timeline 展示 continuation transport。
- [x] Workbench timeline 展示 continuation fallback reason。
- [x] Operations LLM detail 展示 provider continuation fallback。
- [x] failed run 展示 provider 原始错误和 fallback 行为。

2026-06-14 进展：

- LLM invocation owner record 已持久化 `provider_request_payload_preview`。
- `llm.invocation_succeeded` / `llm.invocation_failed` 终态事件继续携带 preview。
- 新增 `llm.invocation_provider_request_prepared` 事件，在 preview 生成并写库后发布，避免 started 事件先发导致 Operations 实时链路看不到 provider actual request。
- Operations observer 与 LLM Operations read model 已纳入该事件 topic。
- Operations LLM failed invocation detail 的 Error Facts 已展示 provider error message、provider preview error、transport、continuation、input delta 和 continuation fallback，避免用户只看到 `adapter_error`。

## Phase 7: Regression

- [x] 单测：Codex HTTP 不发送 `previous_response_id`。
- [x] 单测：Codex WebSocket 第二轮发送 `previous_response_id`。
- [x] 单测：Codex WebSocket orchestration run 第二轮带 `previous_response_id`，且工具结果作为 provider input delta。
- [x] 单测：缺少 input fingerprints 时发送 full input，不带 `previous_response_id`。
- [x] 单测：prefix mismatch 时发送 full input，不带 `previous_response_id`。
- [x] 单测：instructions mismatch 时发送 full input，不带 `previous_response_id`。
- [x] 单测：tool schema mismatch 时发送 full input，不带 `previous_response_id`。
- [x] 单测：async WebSocket bridge 流式产出 text delta / completed。
- [x] 单测：WebSocket reasoning summary/raw reasoning delta。
- [x] 单测：WebSocket transient connection error 在输出前重试。
- [x] 单测：WebSocket continuation 失败后 fallback full request。
- [x] 单测：WebSocket 正常完成后复用连接。
- [x] 单测：WebSocket warmup 建连后下一次 invoke 复用连接，且不发送 `response.create`。
- [x] 单测：LLM service warmup profile 不创建 invocation。
- [x] 单测：LLM HTTP warmup endpoint 解析 credential、调用 adapter warmup，且不创建 invocation。
- [x] 单测：LLM service warmup profile 发布 `llm.profile_warmup_succeeded`。
- [x] 单测：Operations LLM lifecycle events 能看到 profile warmup 结果。
- [x] 单测：Operations Provider Access 表能看到 warmup 状态和 next action。
- [x] 单测：Operations warmup action 调用 LLM owner service，不创建 invocation，记录 action audit，并投影 warmup owner event。
- [x] 单测：默认授权策略允许 `llm.warmup`。
- [x] 单测：tool result 作为 `function_call_output`。
- [x] 单测：LLM settings/profile default params 可声明 `provider_transport=websocket`。
- [x] 单测：Codex WebSocket orchestration run 通过 profile default transport 触发 continuation，不依赖 run metadata override。
- [ ] 集成测试：东航航班任务至少完成工具循环，不因 continuation 参数失败。
- [x] 集成测试：Operations timeline 能看到 delta request。

## 验收标准

1. 使用 Codex HTTP profile 时：
   - 请求不包含 `previous_response_id`。
   - 不再出现 `Unsupported parameter: previous_response_id`。
   - 工具循环可继续走显式回放。

2. 使用 Codex WebSocket profile 时：
   - 首轮 request 是完整 `response.create`。
   - 第二轮在 prefix match 时包含 `previous_response_id`。
   - 第二轮 input 只包含 delta items。
   - provider actual preview 标记 `transport=websocket`。

3. 使用 OpenAI Responses HTTP profile 时：
   - 保持现有 HTTP continuation 行为。
   - 不受 Codex WebSocket 改造影响。

4. Workbench/Operations：
   - 能区分 normalized full request 和 provider actual delta request。
   - 能展示 fallback reason。
   - 用户能看到明确错误处理建议。

## 风险

- Codex WebSocket 鉴权/header 与 HTTP endpoint 不完全一致，需要按 Codex 源码补齐。
- WebSocket event stream 的 provider item schema 可能与 HTTP SSE 有差异。
- delta input 判断如果放错层，会导致 orchestration 与 adapter 双重裁剪。
- prompt tree 后续不完整重发后，模型可能需要更主动调用 tree replay 工具。

## 当前决策

- 短期：保留已做的 Codex HTTP `previous_response_id` 禁用，避免新会话直接 failed。
- 中期：实现 Codex WebSocket transport，才恢复 Codex provider-native continuation。
- 长期：把 provider continuation 能力从 api_family 维度提升到 provider family + transport + request schema 维度。
