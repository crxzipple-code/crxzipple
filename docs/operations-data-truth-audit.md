# Operations 数据真相审计

本文档记录当前 Operations 运维面的数据来源、投影路径和仍未完全接通的点。结论先放前面：Operations 是独立观察/运维面，由 `modules/operations` 通过 port/query service、事件总线和 projection store 聚合数据；前端只消费 Operations read model，不在浏览器里拼运行真相。

## 数据流

1. 业务模块和运行进程写自己的状态：orchestration run、tool run/worker、LLM invocation、channel runtime、daemon instance、memory file/index 等。
2. 业务模块同时发布事件到 `EventsApplicationService` 的 topic store。
3. `OperationsObserverRuntimeService` 订阅持久事件名和运行事件名，把事件转成 `OperationsObservedEvent`，并触发相关 Operations projection 重建。
4. projection source provider 位于 `src/crxzipple/modules/operations/application/read_models/*.py`，通过通用 application/query service、event bus、runtime metrics 聚合页面级 read model。
5. `OperationsProjectionMaterializer` 将 `page` / `overview` 投影写入 Postgres `operations_projections`。
6. `/operations/*` HTTP read surface 通过显式 `AppKey.OPERATIONS_PROJECTION_STORE`
   读取物化投影；缺 projection 时返回可诊断错误，而不是在请求线程里大范围扫库/扫 topic。
7. `frontend` 只调用 `/operations/{module}`，不直接读模块内部 API，也不直接消费 raw event stream。

## Observer 进程

当前已经有独立 observer runtime：

- 入口：`src/crxzipple/modules/operations/interfaces/worker_cli.py`
- Runtime：`src/crxzipple/modules/operations/application/runtime.py`
- 观察状态持久化：`SqlAlchemyOperationsObservationStore` 写入 `operations_observed_events`、`operations_module_observations`、`operations_observer_heartbeats`、`operations_event_time_buckets`
- 页面投影落库：`src/crxzipple/modules/operations/infrastructure/persistence/repositories.py`
- 构建：`_build_operations_observer_runtime_event_service(...)`

它不是 orchestra 的 projector。它消费 event bus，落 Operations observation snapshot，并物化页面 projection。若这只进程没有运行，`/operations/*` 的页面投影会滞后或缺失；正确处理方式是启动/修复 `worker:operations-observer`，不是让前端或 HTTP 请求线程重新拼完整页面。

## 模块数据来源

| 模块 | Provider | 主真相来源 | 事件 / Observation 来源 | 仍需注意 |
| --- | --- | --- | --- | --- |
| Orchestration | `orchestration.py` | `orchestration_run_query_service`、`orchestration_executor_service`、ingress/scheduler query | event bus + `operations_observation_store` | `observed_facts` 依赖 observer；策略超时来自 settings；若 ingress query 缺失会退化用 accepted runs。 |
| Tool | `tool.py` | `tool_service.list_tools/runs/workers/assignments`、`artifact_service` | event bus + observation | provider limit/worker runtime metrics 依赖 worker 上报 `runtime_metrics`/`runtime_registry` snapshot；否则只能看到 API 进程和本地 policy。 |
| LLM | `llm.py` | `llm_service.list_profiles/list_invocations`、`runtime_metrics`、`access_service`、run query | LLM/resolver events from event bus + observation | rate limiter 是当前进程 metric snapshot；跨进程 LLM worker 要上报 metrics 才完整。stream delta 只做事件/调用摘要，不重建完整文本流。 |
| Access | `access.py` | `collect_access_inventory(...)` 聚合 access、LLM、tool、channel services | access credential/action events from event bus + observation + `operations_event_time_buckets` | 认证成功率和失败数优先读 24h bucket；明细表仍读 recent observation。 |
| Channels | `channels.py` | `channel_profile_service`、`channel_runtime_manager`、`channel_interaction_service` | channel events from observation + event bus fallback + `operations_event_time_buckets` | delivery/status 趋势优先读 24h bucket；单条消息明细仍来自 recent observation/event。 |
| Memory | `memory.py` | `agent_service`、`memory_context_resolver`、`file_memory_service`、index store、watch registry | memory events from event bus + observation | watch metrics 是进程内 registry snapshot；多进程下需要统一上报。source scan/index health 是文件和索引状态，不是事件聚合。 |
| Skills | `skills.py` | `skill_manager`、`tool_service`、`access_service`、`agent_service` | skill/resolution/read events from observation + event bus fallback + `operations_event_time_buckets` | resolution event 总量/失败数优先读 24h bucket；per-skill 使用排行仍依赖 recent event payload。 |
| Events | `events.py` | `events_service` topics/snapshots/cursors、event contract/definition registry | observer runtime subscriptions + observation snapshot + `operations_event_time_buckets` | 事件状态/owner 图表优先读 24h bucket；topic 表和 contract coverage 仍需要 event service 当前游标。 |
| Daemon | `daemon.py` | `daemon_service` specs/sets/leases、`daemon_manager` instances、`process_service` sessions/output | daemon/process events from event bus + observation | drain/dependency 是派生判断；process output 取决于 process service 保留范围。 |

## 当前缺口

1. 页面 projection 与 observer observation 已进入 Postgres；`FileBackedOperationsObservationStore` 只保留为轻量/测试实现，不再是运行真相。
2. 多个 provider 依赖 `Any` service 反射调用，应补正式 Operations query port/protocol，让数据契约稳定。
3. Access / Skills / Events / Channels 的首屏趋势已优先读取 `operations_event_time_buckets`；更细粒度的 topic/entity/per-skill 长窗口排行仍缺专门 bucket。
4. Tool/LLM/Memory 的跨进程运行指标依赖各 worker 主动上报 snapshot；没有上报就只能看到 API 进程视角。
5. Events 页能看 observer cursor lag，但 observer worker heartbeat/lease 还需要和 daemon/operations 更清晰地联动。
6. Skills 的 per-skill 使用量、Access/Channel/Event 的明细表仍展示 recent observation 范围；长期明细需要扩展 bucket 维度或新增聚合表。

## 下一步落点

1. 扩展 `operations_event_time_buckets` 维度或新增聚合表，覆盖 topic/entity/per-skill 等长窗口排行。
2. 为 Operations source provider 补正式 query port/protocol，减少 `Any` 反射调用。
3. 为 Tool/LLM worker runtime metrics 定义统一上报事件或 registry snapshot 契约。
4. 给 Events 建最小聚合 read store：topic/time bucket、owner/time bucket、dead-letter/time bucket。
5. 为 `operations_event_time_buckets` 补正式 read-model query API，避免页面 helper 直接探测 store 方法。
