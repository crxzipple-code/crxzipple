# Runtime UI Read Model 契约设计

本文档把当前设计稿拆成前后端共享的 read model 契约。它不是视觉规范，而是后续 `/ui/*`、`/operations/*` API、`frontend` 页面类型和 fixture 的共同基准。

关联文档：

- `docs/ui/current-ui-design-functional-spec.md`
- `docs/operations-data-truth-audit.md`
- `docs/agents/hosted-agent-operating-contract.md`

## 设计原则

1. 页面消费 read model，不消费 raw domain entity。
2. owner module 提供通用 application/query service 和业务事实，不提供 Operations 专用页面 provider。
3. `/ui/*` 和 `/operations/*` 只做页面级组合、权限过滤、降级隔离、projection 读取和 HTTP response mapping。
4. 前端不推断安全关键状态：权限、动作可用性、危险动作、配置 effective value、trace causality 都由后端给 truth。
5. Operations 不使用一个万能 overview 契约；每个模块有自己的页面契约。
6. Settings 不只是 CRUD；必须包含 effective preview、validation、impact、audit 和 dangerous actions。

## 共享基础类型

这些类型应同时映射到后端 Pydantic/dataclass 和前端 TypeScript。

### TraceContext

用于跨页面跳转和追踪。

字段：

- `trace_id`
- `correlation_id`
- `source_event_id`
- `source_owner`
- `source_surface_id`
- `source_event_name`
- `observed_event_id`
- `observed_event_name`
- `session_key`
- `session_id`
- `turn_id`
- `run_id`
- `step_id`
- `tool_run_id`
- `llm_invocation_id`
- `artifact_id`
- `approval_request_id`

### LinkedEntity

用于 inspector、关联资产、行级跳转。

字段：

- `type`
- `id`
- `label`
- `owner`
- `route`
- `copy_value`
- `trace`

### RuntimeAction

用于按钮和行级动作，后端决定动作是否允许。

字段：

- `id`
- `label`
- `owner`
- `target`
- `method`
- `risk`
- `allowed`
- `disabled_reason`
- `requires_confirmation`
- `reason_required`
- `audit_event`
- `trace`

`risk` 必须保持 `normal`、`controlled`、`dangerous` 三值语义；后端不能把
`controlled` 压扁成 `normal`。所有 audited mutation action 必须提供稳定的
`audit_event`，并且与 `/operations/actions/audits` 返回的 `action_type` /
`audit_event` 一致。

### TableSection

用于 Operations 和 Settings 中的大量表格，但列和行仍由服务端显式给出。

字段：

- `id`
- `title`
- `description`
- `columns`
- `rows`
- `total`
- `view_all_route`
- `empty_state`
- `actions`

### MetricCard

字段：

- `id`
- `label`
- `value`
- `delta`
- `tone`
- `trend`
- `trace`

## Workbench

### WorkbenchHomeReadModel

用途：左侧 Threads 和当前工作台入口。

owner module：

- orchestration：run/thread 状态。
- session：会话信息和消息统计。
- authorization：动作可用性。

字段：

- `connection`
- `filters`
- `threads`
- `active_thread_id`
- `active_run_id`
- `actions`

### WorkbenchRunReadModel

用途：当前 run / turn / step / inspector。

owner module：

- orchestration：run、turn、step read model、run control。
- tool：tool run linked entity。
- llm：llm invocation linked entity。
- artifacts：artifact preview。
- events：trace link。

字段：

- `run`
- `turns`
- `current_turn_id`
- `steps`
- `status_strip`
- `inspector`
- `composer`
- `linked_entities`
- `actions`

### WorkbenchContextTreeReadModel

用途：Workbench 右侧 inspector 的“上下文”页签，让人和 agent 看到当前 session 绑定的真实 Context Tree。

owner module：

- context_workspace：workspace、nodes、estimate、render snapshot。
- orchestration：当前 run id、`context_snapshot_id` 引用。
- tool / skills / memory / artifacts：只通过 Context Workspace owner adapter 暴露节点或 provider mirror，不由 Workbench 直接拼 owner 数据。

当前前端接口：

- `GET /context-workspaces/by-session/{session_key}/tree`
- `GET /context-workspaces/runs/{run_id}/render-snapshot`
- `POST /context-workspaces/by-session/{session_key}/nodes/{node_id}/actions/{action}`

字段：

- `workspace`
- `nodes`
- `estimate`
- `render_snapshot`
- `actions`

`nodes` 只展示节点元数据、状态、summary、estimate 和可执行 action。节点正文是否进入 prompt 由 `collapsed` / `prompt_visible` / `schema_enabled` 等状态控制；Workbench 不读取 owner module 内部文件或 secret。

## Trace

### TraceTimelineReadModel

owner module：

- events：事件读模型、payload、cursor。
- orchestration/tool/llm/channels：提供 linked entity resolver。

字段：

- `trace`
- `filters`
- `summary`
- `events`
- `selected_event`
- `inspector`
- `actions`

后端必须支持的 query：

- keyword / id search
- time range
- status
- family
- owner
- key event only
- limit / cursor

### TraceGraphReadModel

owner module：

- events：graph read model。
- orchestration：run/step read model。

字段：

- `trace`
- `summary`
- `lanes`
- `nodes`
- `edges`
- `viewport`
- `selected_node`
- `inspector`
- `legend`

## Operations

当前实现决策：Operations 运维面的页面 read model 位于 `modules/operations/application/read_models`，由 `operations-observer` 物化到 Postgres `operations_projections`，前端从 `/operations/{module}` 获取。下面章节中的 `owner module` 指业务真相归属，不表示该业务模块要实现 Operations 专用 provider。

所有 Operations read model 共享：

- `module`
- `title`
- `subtitle`
- `health`
- `updated_at`
- `auto_refresh`
- `role`
- `metrics`
- `tabs`
- `actions`
- `trace`
- `sections`

但每个模块必须有自己的 section 字段。

### OperationsOrchestrationReadModel

业务真相 owner：orchestration。Operations read model owner：operations。

当前后端接口：

- `GET /operations/orchestration`：返回页面级 read model projection。
- `GET /operations/orchestration/overview`：模块摘要 projection，不作为新版页面主契约。

section：

- `scheduler_status`
- `backpressure`
- `stuck_runs`
- `policy_limits`
- `run_queue`
- `lane_locks`
- `executor_overview`
- `ingress_queue`
- `recent_failures`
- `ops_event_log`

动作：

- open run
- open trace
- cancel run
- requeue
- force release lane

### OperationsToolReadModel

业务真相 owner：tool。Operations read model owner：operations。

section：

- `tool_runs`
- `tool_types`
- `auth_missing`
- `worker_pool`
- `tool_queue`
- `long_running_runs`
- `inline_risk`
- `failed_tools`
- `recent_artifacts`
- `strategies`
- `source_health`
- `discovery_failures`
- `function_catalog`
- `provider_backend_health`
- `cli_process_health`

`provider_backend_health` 的 readiness 来自 Tool application service 对 Access
credential readiness 与 runtime requirements 的聚合；Operations 只增加 24h
calls/failures 等运维统计，不在页面侧重新解释 credential requirement。

动作：

- open tool run
- open trace
- open access
- cancel tool run
- disable tool

### OperationsLlmReadModel

业务真相 owner：llm。Operations read model owner：operations。

section：

- `provider_access_health`
- `provider_auth_blocked`
- `model_resolver`
- `rate_limiter`
- `streaming_requests`
- `recent_invocations`
- `latency`
- `token_usage`
- `invocation_rate`
- `stream_health`
- `execution_blocking_risk`
- `fallback_problems`
- `context_pressure`
- `model_availability`
- `error_summary`

动作：

- open invocation
- open trace
- open access
- view limits
- configure pricing
- disable profile

### OperationsAccessReadModel

业务真相 owner：access。Operations read model owner：operations。

section：

- `missing_access`
- `credential_health`
- `provider_auth_blocked`
- `credentials_by_kind`
- `expiring_soon`
- `auth_success_rate`
- `authentication_status`
- `access_usage`
- `recent_access_events`
- `fallback_problems`
- `setup_flows`

动作：

- setup
- open access
- retry runs
- rotate
- view limits

### OperationsChannelsReadModel

业务真相 owner：channels。Operations read model owner：operations。

section：

- `channel_status`
- `message_flow`
- `delivery_trend`
- `top_channels`
- `dead_letter_queue`
- `recent_messages`
- `failures_by_category`
- `channel_bindings`

动作：

- inspect message
- retry delivery
- open run
- open trace
- open channel profile

### OperationsMemoryReadModel

业务真相 owner：memory。Operations read model owner：operations。

section：

- `memory_stores`
- `index_health`
- `index_jobs`
- `retrieval_performance`
- `retrieval_trace`
- `write_flush`
- `memory_usage`
- `recent_retrieval_logs`
- `source_scan_status`
- `source_files`

动作：

- view trace
- rebuild index
- rescan source
- view document

### OperationsContextWorkspaceReadModel

业务真相 owner：context_workspace。Operations read model owner：operations。

当前后端接口：

- `GET /operations/context_workspace`：返回 Context Workspace 运维页 projection。
- `GET /operations/context_workspace/overview`：模块摘要 projection。

section：

- `workspaces`
- `visible_nodes`
- `render_snapshots`
- `diagnostics`

指标：

- health
- workspaces
- visible nodes
- pinned nodes
- render snapshots
- snapshot tokens

动作：

- open context tree

Operations 只能展示 Context Workspace 运维状态和节点元信息；不得把节点正文、artifact bytes、secret 或 owner module 内部资源直接铺到运维页。需要查看正文时走 Workbench/Context Tree 的受控节点操作或 owner module 专门 read API。

### OperationsSkillsReadModel

业务真相 owner：skills。Operations read model owner：operations。

section：

- `recently_resolved_skills`
- `resolution_outcomes`
- `top_used_skills`
- `missing_capabilities`
- `access_requirements`
- `capability_requirements`
- `resolution_logs`
- `resolver_detail`
- `import_normalize`
- `skill_package_sources`
- `conflicts_overrides`
- `profile_usage`
- `skill_inspector`

动作：

- open trace
- view run
- import package
- upload package
- manage mappings

### OperationsEventsReadModel

业务真相 owner：events。Operations read model owner：operations。

section：

- `events_over_time`
- `events_by_surface`
- `owners_by_volume`
- `contract_compatibility`
- `recent_events`
- `consumer_health`
- `observer_mapping_failures`
- `topics`
- `subscriptions`
- `observers`
- `dead_letters`
- `event_inspector`

动作：

- replay original
- retry delivery
- retry observation
- view payload
- view trace

### OperationsDaemonReadModel

业务真相 owner：daemon。Operations read model owner：operations。

section：

- `service_sets`
- `drain_overview`
- `dependency_health`
- `processes`
- `process_health`
- `restart_summary`
- `quick_actions`
- `links_to_operations`

动作：

- start
- stop
- restart
- drain
- reload config

## Settings

Settings 共享契约分成两层。

### SettingsOverviewReadModel

字段：

- `contract_summary`
- `configuration_summary`
- `resource_counts`
- `configuration_health`
- `recent_changes`
- `configuration_distribution`
- `configuration_issues`
- `configuration_inheritance`
- `sources_versioning`
- `quick_actions`
- `useful_links`

### SettingsResourcePageReadModel

适用于：

- agent profiles
- llm profiles
- tool catalog
- skill catalog
- memory config
- access assets
- channel profiles
- event contracts
- runtime defaults
- environment
- audit logs
- backup restore

字段：

- `resource`
- `title`
- `description`
- `tabs`
- `list`
- `detail`
- `summary`
- `effective_configuration`
- `validation`
- `impact`
- `audit`
- `danger_zone`
- `actions`

不同资源的 detail section 由 owner module 定义。例如 Tool Catalog 必须有 input schema、output schema、runtime strategy、access/effects、artifact output、contract test；Runtime Defaults 必须有 precedence、dry run、impact preview、audit reason。

Tool Catalog Settings 当前按全屏应用结构组织为：

- Function table：source、runtime、status、enabled、credential readiness、policy。
- Source table：source kind（catalog source type）、status、revision、discovery history 和
  refresh/disable/delete；runtime function 使用 definition origin 表达定义来源。
- Backend table：backend capability、credential binding、Tool-owned readiness、runtime、status。
- Run table：tool run lifecycle、attempt、target、error/result。
- 右侧 detail drawer：根据所选视角展示 contract、requirements、policy、recent runs、
  source config、discovery history 或 backend readiness；不把 provider/backend/source
  假数据塞进通用卡片。

Settings 可以触发 Tool owner module 提供的 create/update/refresh/disable/delete/test
application action，但不直接调用 discovery adapter、runtime registry 或 Access secret
material。

## API 设计建议

第一阶段只做 read endpoints：

- `GET /ui/workbench`
- `GET /ui/workbench/runs/{run_id}`
- `GET /ui/trace/{trace_id}/timeline`
- `GET /ui/trace/{trace_id}/graph`
- `GET /operations/{module}`
- `GET /ui/settings`
- `GET /ui/settings/{resource}`
- `GET /ui/settings/{resource}/{id}`

第二阶段再补 action endpoints，动作按治理 owner 路由：

- `POST /ui/actions/{action_id}`

该 endpoint 只作为 console action dispatcher，payload 必须包含 owner、target、confirmation、reason 和 trace。实际写操作不在 `/ui` 内部完成，而是路由到治理 owner 的 application service：

- Settings-owned config resource 写入 Settings action service；access asset、credential binding 声明、consumer binding、provider/account/scope enablement、rotation/export/redaction policy 等外部访问配置属于 Settings-owned config resource 或 Access-governed config shell。
- Access runtime action 只处理 secret material capture、credential verification、setup session、OAuth account lifecycle、credential lease 等外部访问运行时事实，不持有内部 authorization policy 或 authorization grant。
- Operations/runtime action 写入 Operations 或对应 runtime control action service。
- 业务模块可以提供 validator、runtime summary 和 apply hook，但不能绕过 Settings / Access 成为配置或访问治理写入口。

## 近期落地顺序

1. 在 `frontend` 新增分页面 TypeScript contract。
2. 让 fixture 改成这些 contract，而不是继续复用 generic overview。
3. 后端先补 Operations Orchestration / Tool / LLM 三个完整 read model。
4. 再补 Trace graph。
5. Settings 从 Overview + Agent Profiles + LLM Profiles + Tool Catalog + Access Assets 开始。
