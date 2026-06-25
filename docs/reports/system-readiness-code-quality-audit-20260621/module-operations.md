# Module Audit: operations

## Verdict

Architecturally correct, implementation risk still meaningful but substantially improved for the core runtime pages. Operations is the right place for sidecar observation and read model materialization. Tool, LLM, Orchestration, Events, Daemon, Channels, Skills, Browser, Memory, and Access read-model facades have been split into focused projection helpers with regression coverage; the Operations DTO surface now has a thin export module and focused core/action/page response modules; the HTTP interface is now a thin route composition layer over runtime/SSE, projection read, and controlled-action route groups. Remaining risk is concentrated in large helper/table surfaces, production fallback policy, and full-page query-budget/freshness guarantees.

## Evidence

- 499 Python files, about 53091 lines after read-model, HTTP interface,
  observation model/event-projection, Events overview/page split, Events
  observer section retirement, Access table aggregate retirement, Channels
  overview/page split, Skills overview/page split, Daemon detail aggregate
  retirement, Events overview section, Tool lifecycle
  event source/row projection, Tool Run table fact/row projection, Tool
  overview aggregate retirement, Channels common helper split, observer runtime
  split, Orchestration execution-chain section split, Orchestration summary
  projection split, Orchestration overview/page split, Orchestration status
  projection split, Tool tab projection split, persistence store splits, and observation repository mapper/recording
  split, Operations action-flow split, Operations projection materializer split,
  Skills table aggregate retirement, Memory event-table split, Daemon
  process-table split, Tool readiness risk split, Tool worker projection split,
  Tool overview/page/fact split, Tool Run detail summary/projection split, Tool Run artifact ref split, Tool Run table
  label split, Tool scheduling blocker/section split, Channels table row split,
  Channels chart/runtime-record projection split, LLM overview/page/fact split, LLM provider
  request label split, LLM provider readiness split, LLM invocation detail item
  split, Daemon process output detail split, Daemon table row split, Daemon
  chart/drain/common-semantic split, LLM lifecycle event split, Events dead-letter table split,
  Orchestration ingress state/row split, Orchestration event-log row split,
  Browser common/profile-row helper split, Events page fact split, and projection
  read-payload/table-filter split, Orchestration page fact split, and Channels
  page filter split, Skills requirement table split, Context Workspace page
  fact split, Skills page fact split, Tool runtime metric split, Events
  contract matching split, LLM detail table aggregate retirement, Tool Source
  catalog row split, Tool page section wiring split, read-model port contract
  split, Channels event-record projection split, Context Workspace metric
  projection split, Orchestration event-log projection split, Daemon service
  row split, Orchestration worker projection split, LLM lifecycle bus split,
  Channels runtime/record/interaction detail split, Tool readiness payload
  split, Tool worker detail section split, Tool worker detail summary/runtime
  section split, Skills event source split, LLM
  invocation table row split, LLM invocation request-context item split,
  LLM invocation request-context runtime/provider split, LLM provider render
  label split,
  diagnostics loop-health split, Daemon page builder/fact split, Daemon event source
  split, Daemon browser instance summary split, LLM page tab split, Events event detail split, Memory source table
  split, Operations factory context split, Events overview navigation/
  contract compatibility split, Tool Run label/source/execution split,
  Tool Run query/time split, Tool lifecycle
  event projection split, Orchestration ingress projection split, Tool Run
  detail projection split, Events page projection split, LLM overview
  action split, Tool scheduling run/blocker projection split, Tool provider
  limit snapshot/local-capacity split, Access module overview inventory/row
  projection split, Tool HTTP detail DTO split, Operations action-audit
  summary split, Tool page fact derivation split, Tool page run selection split,
  LLM page section assembly
  split, Context Workspace node-status row split, Orchestration event-log
  label split, Tool worker provider-limit section split, observer runtime
  processing split, Events topic row split, Tool page section group split,
  Operations HTTP stream payload split, Access page builder split, Operations
  channel action route split, Events health projection split, Daemon browser
  instance summary split, LLM error classification ownership split, Skills
  usage table split, Daemon module row split, Events module row split, and LLM
  provider warmup split, Daemon health/metric split, and Tool metric value
  split, LLM error fact item split, Events recent projection split, Skills
  detail section split, Memory page fact split, Channels page summary split,
  Browser page filter/source
  split, Memory health/page-summary/chart split, Orchestration page section
  assembly split, LLM/Daemon detail HTTP DTO split, Skills profile-usage table
  split, Orchestration ingress row-value split, Memory detail projection split,
  Tool Source provider backend row split, LLM overview row split, observation
  store bucket split, Channels topic/connection helper split, Browser table
  aggregate retirement, Channels table aggregate retirement, Orchestration
  repeated-failure row projection split, Access target projection split, LLM
  provider render label split, LLM page invocation set split, Tool scheduling
  queue row split, Skills action/chart split, LLM run-context execution split,
  Orchestration runtime config projection split, Orchestration worker row split,
  Channels payload formatting split, LLM resolver label split, Daemon event
  filter split, Tool Source provider backend label split, Memory file helper
  split, Tool Source CLI row split, Orchestration queue row-value split, LLM
  provider row split, and Orchestration observation metric split.
- Large files now concentrate in helper/table surfaces rather than public facades.
  `application/projections.py` is now a 179-line materializer/write-flow facade;
  module routing lives in `projection_modules.py`, page loading lives in
  `projection_materializer_pages.py`, table/detail extraction lives in
  `projection_materializer_details.py`, and JSON-safe normalization lives in
  `projection_materializer_json.py`.
- Operations modules now have executable focus guards in
  `tests/unit/test_module_architecture_guards.py`: every non-`__init__.py`
  Python file under `modules/operations` must stay at or below 250 lines unless
  it is split before merge. The current largest Operations file is 245 lines.
- Operations read-model files now total 397 Python files and about 43472 lines;
  the largest read-model file is 186 lines after the current Access,
  Orchestration, LLM request-context, LLM error fact, and provider render label
  follow-up splits, plus the Tool worker detail summary/runtime section split
  and Tool page run selection split, plus the LLM page invocation set split and
  Tool scheduling queue row split, plus the Skills action/chart, LLM
  run-context execution, Orchestration runtime config projection, Orchestration
  worker row, Channels payload formatting, LLM resolver label, Daemon event
  filter, Tool Source provider backend label, Memory file helper, Tool Source
  CLI row, Orchestration queue row-value, LLM provider row, and Orchestration
  observation metric splits.
- `interfaces/http_projection_routes.py` is now a 23-line projection route
  composition module after moving runtime module page routes, support module
  page routes, detail routes, and overview/generic routes into focused route
  groups. This keeps the public Operations projection router thin while
  preserving the existing `/operations/*` API shape.
- `interfaces/http_runtime.py` is now a 151-line runtime-status helper after
  moving Operations projection-refresh SSE payload normalization and event-frame
  formatting to `http_stream_payloads.py`.
- `interfaces/http_models_support_pages.py` is now a 23-line support-page DTO
  export module after moving Access, Memory, and Skills response models into
  owner-focused page DTO modules. The external `http_models.py` export surface
  remains the single HTTP model import point for route modules.
- `interfaces/http_models_core.py` is now a 49-line core DTO export module.
  Primitive action/metric/tab/role DTOs, diagnostics/runtime-status DTOs,
  chart/table/key-value section DTOs, and generic page/overview DTOs now live
  in focused core model modules.
- `interfaces/http_models_channels_pages.py` is now 120 lines after moving
  Channel runtime/record/interaction detail response DTOs to
  `http_models_channel_details.py`.
- `interfaces/http_models_tool_pages.py` is now 141 lines after moving Tool run
  and worker detail response DTOs to `http_models_tool_details.py`. Tool page
  responses remain page-shaped while drill-down DTOs have their own interface
  file.
- `application/read_models/llm_page_builder.py` is now 105 lines after moving
  LLM page section assembly to `llm_page_sections.py`. The builder now owns
  the page shell, metric/tab/action wiring, and projection diagnostics only.
- `application/read_models/context_workspace_rows.py` is now 162 lines after
  moving node status aggregation to `context_workspace_node_status_rows.py`.
- `application/read_models/orchestration_event_log_projection.py` is now 179
  lines after moving event-key display label mapping to
  `orchestration_event_log_labels.py`.
- Operations action routes are now grouped by concern: resource operations route
  through focused Skills, Access, Daemon/Memory, and Audit route modules,
  execution operations route through focused LLM, Orchestration, and Tool route
  modules, channel runtime/dead-letter operations live in
  `http_action_routes_channels.py`, and event/observer cursor operations live
  in `http_action_routes_events.py`. The route-group files remain thin
  composition modules.
- Operations action HTTP DTOs are split by concern: base action/audit request
  models, audit response projection, event/channel maintenance actions, and
  resource/runtime action responses now live in focused
  `http_models_action_*` modules. `http_models.py` remains the public DTO export
  surface for route modules.
- Operations action audit result/error summary normalization now lives in
  `http_action_audit_summary.py`; `http_action_audit.py` keeps request
  validation, risk confirmation, and audit-store lifecycle writes.
- The aggregate `application/read_models/ports.py` has been retired. Runtime
  observation/events/bootstrap ports live in `ports_runtime.py`; access/settings
  ports in `ports_access_settings.py`; Tool/artifact/remote-runtime ports in
  `ports_tooling.py`; LLM/agent ports in `ports_llm_agent.py`; memory/context/
  skill ports in `ports_context.py`; and Browser/Channel/Daemon/Process ports
  in `ports_runtime_sources.py`. Read-model callers now import the focused
  source group they consume instead of routing through a universal port bucket.
- `application/read_models/factory.py` is now 185 lines after moving the
  explicit source read-model context DTO to `factory_context.py`. The factory
  module now keeps provider construction only; the context module owns typed
  cross-module read dependencies and observer runtime attachment.
- `application/read_models/projection_payloads.py` is now a 156-line projection
  read-payload facade. Detail payload deferral lives in
  `projection_detail_payloads.py`, while table/related projection filtering
  lives in `projection_table_filters.py`.
- The retired aggregate `application/read_models/llm_detail_tables.py` has been
  deleted. LLM response item tables live in `llm_response_item_tables.py` (137
  lines), response/observed event tables in `llm_response_event_tables.py` (116
  lines), policy trace tables in `llm_policy_trace_tables.py` (52 lines), and
  bounded payload/table helpers in `llm_detail_payloads.py` (62 lines).
- `application/read_models/events_contract_sections.py` is now 221 lines after
  moving topic/route contract matching, contract labels/statuses, and payload
  extraction into `events_contract_matching.py` (129 lines).
- `application/observation.py` is now 82 lines after moving observation DTOs to
  the public `observation_models.py` export surface, event-record normalization
  to `observation_event_projection.py`, and payload parsing/sanitizing to
  `observation_payloads.py`. Concrete observed-event/module observation,
  heartbeat, projection, and snapshot DTOs now live in focused observation model
  modules.
- `application/read_models/events_overview_sections.py` is now 110 lines after
  moving chart projection to `events_overview_charts.py`, owner volume table
  projection to `events_owner_sections.py`, shared overview labels/formatting
  to `events_overview_helpers.py`, tab/action projection to
  `events_navigation_sections.py` (103 lines), and contract compatibility
  key-value projection to `events_contract_compatibility.py` (72 lines).
- `application/read_models/tool_lifecycle_events.py` is now 64 lines after
  moving event-source aggregation/dedupe to `tool_lifecycle_event_sources.py`,
  event topic selection/predicate/dedupe rules to
  `tool_lifecycle_event_topics.py` (108 lines), run/worker/detail row
  projection to `tool_lifecycle_event_rows.py` (135 lines), and lifecycle event
  priority/tone/details/source/trace helpers to
  `tool_lifecycle_event_projection.py` (159 lines). The event source module now
  composes observation-backed and bus-backed Tool lifecycle events only.
- `application/read_models/tool_readiness_sections.py` is now 172 lines after
  moving access/runtime readiness risk payload normalization to
  `tool_readiness_risk.py`. The section file keeps only risk table row/section
  projection.
- `application/read_models/tool_readiness_risk.py` is now 139 lines after
  moving combined readiness payload normalization, access readiness payload
  normalization, readiness item coercion, requirement labels, and action route
  projection to `tool_readiness_payloads.py`.
- `application/read_models/tool_worker_sections.py` is now 160 lines after
  moving worker registration status, runtime/provider/capability summaries,
  worker pool chart projection, worker run fallback labels, success-rate, and
  average-duration projection out of the section file. Registration/runtime/
  capability rules live in `tool_worker_projection.py` (162 lines), worker pool
  chart projection lives in `tool_worker_pool_sections.py` (86 lines), and
  ToolRun-derived status, success-rate, load, lease, and average-duration
  labels live in `tool_worker_run_projection.py` (85 lines).
- `application/read_models/tool_worker_details.py` is now 110 lines after
  moving worker detail summary, capability section, runtime registry table,
  age/duration labels, and detail table column helpers to
  `tool_worker_detail_sections.py`.
- `application/read_models/tool_run_tables.py` is now 95 lines after moving
  Tool Run fact projection to `tool_run_table_facts.py`,
  source/trace/assignment/lease/progress/search labels to
  `tool_run_table_labels.py`, and row/status/action/column projection to
  `tool_run_table_rows.py`.
- `application/read_models/tool_run_filters.py` is now 144 lines after moving
  Tool Operations query DTO, normalization, pagination, and empty-state
  projection to `tool_run_query.py` (118 lines), and run time/duration semantics
  to `tool_run_time.py` (35 lines). The remaining file owns only filtering
  predicates, search matching, status matching, and run dedupe.
- `application/read_models/modules_access.py` is now a 91-line Access module
  fallback overview entry after moving Settings/inventory/readiness adaptation
  to `modules_access_inventory.py` and target-row/setup projection to
  `modules_access_projection.py`.
- The aggregate `application/read_models/tool_overview_sections.py` has been
  retired. Tool overview actions, risk rules, queue/risk/worker rows, type
  chart projection, and execution mix sections now live in focused
  `tool_overview_*` modules.
- `application/read_models/daemon.py` is now 59 lines after moving page assembly
  to `daemon_page_builder.py`. Daemon owner reads, runtime fact grouping,
  filtering/pagination, and health projection now live in
  `daemon_page_facts.py`; the public provider delegates to focused Daemon helper
  modules instead of owning page construction inline.
- `application/read_models/events_state.py` has been retired; recent event
  summaries, subscription/topic state, observer runtime state, and shared event
  state formatting/cursor helpers now live in focused `events_*_state.py`
  modules.
- `application/read_models/events_page_facts.py` is now 155 lines after moving
  registry/source reads to `events_page_sources.py`, topic/cursor/subscription/
  observer runtime state collection to `events_page_runtime_facts.py`, and
  recent-event source selection/filtering/pagination to
  `events_page_recent_facts.py`. The facts module now keeps page fact assembly,
  event buckets, topic rows, and health projection wiring.
- `application/read_models/channels_common.py` is now 181 lines after moving
  display/time/status/payload formatting helpers to `channels_formatting.py`,
  safe owner/event calls to `channels_safe_access.py`, channel topic parsing to
  `channels_topic_helpers.py`, connection topic/runtime matching to
  `channels_connection_helpers.py`, event routing/search helpers to
  `channels_event_helpers.py`, and table/key-value/capability section builders
  to `channels_sections.py`.
- `application/read_models/browser_rows.py` is now 169 lines after moving
  Browser profile and page observation row projection to
  `browser_profile_rows.py`. The remaining row module owns daemon runtime,
  profile pool, and allocation rows only.
- `application/read_models/browser.py` is now 139 lines after moving Browser
  page fact assembly to `browser_page_data.py`. The provider now owns overview/
  page assembly only.
- `application/read_models/browser_page_data.py` is now 146 lines after moving
  Browser query normalization, row filtering, and pagination to
  `browser_page_filters.py`, and owner-safe profile/list reads to
  `browser_page_sources.py`. The page-data module now keeps daemon payload
  conversion, row projection composition, observed-event projection calls, and
  health classification wiring only.
- The aggregate `application/read_models/browser_tables.py` has been retired.
  Profile/pool/allocation/page observation tables now live in
  `browser_profile_tables.py`; Browser daemon runtime table projection lives in
  `browser_runtime_tables.py`; and network/diagnostic activity table projection
  lives in `browser_activity_tables.py`.
- `application/read_models/context_workspace_page_facts.py` is now 146 lines
  after moving Context Workspace owner-read safeguards, tree view reads,
  observation snapshot reads, and operations-slice row reads to
  `context_workspace_page_sources.py`. The facts module now keeps page fact
  assembly and health classification only.
- `application/read_models/memory_health.py` is now 33 lines after moving
  Memory metric-card/tab/action projection to `memory_page_summary.py` and
  index/retrieval chart projection to `memory_charts.py`. Memory health now
  keeps overall health classification only.
- `application/read_models/channels_page_builder.py` is now 179 lines after
  moving page owner reads, observed/live event selection, query filtering,
  pagination, runtime record projection, and health calculation to
  `channels_page_data.py`. The builder now owns page/table/chart/detail
  assembly only.
- The aggregate `application/read_models/channels_tables.py` has been retired.
  Runtime tables live in `channels_runtime_tables.py`; message/dead-letter/
  event tables in `channels_message_tables.py`; account/connection/profile
  binding tables in `channels_binding_tables.py`; and interaction tables in
  `channels_interaction_tables.py`.
- `application/read_models/channels_table_rows.py` is now 169 lines after moving
  event contract/definition/surface registry row projection to
  `channels_contract_rows.py`; corresponding contract section assembly lives in
  `channels_contract_tables.py`. Channel message, binding, profile,
  interaction, and observed-event rows remain in the table-row module.
- The aggregate `application/runtime.py` has been retired. Observer event-name
  catalog rules live in `observer_event_names.py`, subscription DTO/callback
  contracts live in `observer_subscriptions.py`, scan/wakeup cadence state lives
  in `observer_runtime_scan_state.py`, scan/wait processing lives in
  `observer_runtime_processing.py`, and the durable event pump lives in
  `observer_runtime_service.py`.
- `application/read_models/orchestration_execution_chain_sections.py` is now
  80 lines after moving candidate run/query safety helpers to
  `orchestration_execution_chain_queries.py`, continuation/tool-only diagnostics
  to `orchestration_execution_chain_diagnostics.py`, and table row projection to
  `orchestration_execution_chain_rows.py`.
- `application/read_models/orchestration_queue_sections.py` is now 58 lines
  after moving run queue row/status/trace/age projection to
  `orchestration_queue_rows.py`, then moving queue priority/wait/lease/tone/
  trace/age value rules to `orchestration_queue_row_values.py`. The section
  module now only sorts queued runs, declares table columns, and assembles the
  run queue table.
- `application/read_models/orchestration_status_sections.py` is now 162 lines
  after moving scheduler/policy status runtime-value parsing, duration/age/
  percentile/percentage labels, dispatch-task breakdown, and observer-state
  labels to `orchestration_status_projection.py`, then moving Policy & Limits
  section assembly to `orchestration_policy_sections.py` (108 lines).
- LLM and Tool page projection diagnostics now consume `owner_call_count` from
  their facts DTOs, matching the Orchestration page pattern. Page builders only
  assemble page sections; owner read-count semantics live with fact collection
  where owner reads are performed.
- `application/read_models/diagnostics.py` is now 181 lines after moving shared
  payload/value helpers, LLM response/request metrics, loop-health projection,
  run-signal diagnostics, and final-answer/missing-metric quality projection to
  focused modules. `diagnostics_run_signals.py` now keeps only runtime signal
  extraction, while `diagnostics_run_quality.py` owns quality/missingness rules.
- `application/read_models/llm_invocation_details.py` is now 131 lines after
  moving runtime observation labels, provider/tool replay labels, result payload
  sanitizing, tool-result replay summaries, and invocation summary/request
  context items to focused detail helper modules.
- `application/read_models/llm_rate_limiter_sections.py` is now 146 lines after
  moving limiter queue table projection to `llm_limiter_queue_sections.py`.
  The rate-limiter module now owns key-value summary and execution-blocking risk
  sections only.
- The aggregate `application/read_models/tool_scheduling_sections.py` has been
  retired. Queue summary/run/waiting-IO sections now live in
  `tool_scheduling_queue_sections.py`, capability-limit sections live in
  `tool_scheduling_capability_sections.py`, and blocker diagnostics sections
  live in `tool_scheduling_blocker_sections.py`; shared capacity helpers,
  blocker reason/row/tone projection, waiting/limit rows, and labels remain in
  their focused scheduling modules.
- `application/read_models/tool_scheduling_queue_sections.py` is now 141 lines
  after moving queue summary row projection and Waiting IO row selection to
  `tool_scheduling_queue_rows.py`. The section module now owns only table
  shell/columns/routes for queue-related sections.
- Tool provider identity rules now live in `tool_provider_identity.py`, so
  provider key/label projection is shared by provider sections, scheduling rows,
  run tables, run details, and page filtering instead of being duplicated.
- `application/read_models/tool_provider_sections.py` is now 126 lines after
  moving provider history bucket/row/state projection to
  `tool_provider_history_rows.py`.
- `application/read_models/tool_provider_limits.py` is now 145 lines after
  moving limiter metric/registry/local-capacity fact extraction to
  `tool_provider_limit_facts.py`, provider limit row/value formatting to
  `tool_provider_limit_rows.py`, and worker-detail provider limit section
  assembly to `tool_worker_provider_limits.py`.
- The aggregate `application/read_models/tool_source_sections.py` has been
  retired. Tool source common display/record helpers, owner-safe source query
  reads, source/function catalog sections, and provider backend health sections
  now live in focused `tool_source_*` modules.
- `application/read_models/tool_run_details.py` is now 157 lines after moving
  assignment history section projection, detail payload sanitizing, invocation
  context display, Browser profile/run display, Tool Run summary assembly, and
  assignment/source/trace/lease/status/tool label projection into focused
  `tool_run_*` helper modules.
- `application/read_models/llm_lifecycle_events.py` is now 66 lines after
  moving LLM lifecycle event source collection/dedupe to
  `llm_lifecycle_event_sources.py` and row label/payload/tone projection to
  `llm_lifecycle_event_rows.py`.
- `application/read_models/llm_lifecycle_event_sources.py` is now 128 lines
  after moving Events-bus topic seed selection, safe reads, topic predicates,
  record conversion, and bus-side dedupe to `llm_lifecycle_event_bus.py`. The
  sources module now composes observation-backed and bus-backed events and
  applies final cross-source ordering/dedupe.
- LLM error taxonomy now lives with the LLM owner module in
  `modules/llm/application/error_classification.py`; Operations
  `llm_error_sections.py` consumes that classification for error summary and
  invocation detail projection instead of duplicating provider failure semantics.
- `application/read_models/llm_provider_request_diagnostics.py` is now 175
  lines after moving provider continuation/transport/renderer/render-report/tool
  mapping/input-delta/options labels to `llm_provider_request_labels.py` and
  Provider Context Mapping table projection to
  `llm_provider_context_mapping.py` (82 lines). The diagnostics module now keeps
  request payload preview, runtime request summary, and provider wire preview.
- `application/read_models/llm_invocation_tables.py` is now 160 lines after
  moving streaming/recent/failed invocation row projection to focused
  `llm_invocation_*_rows.py` modules with shared stream-status projection.
  The tables module now keeps table section identity, columns, totals, and
  empty-state projection.
- `application/read_models/llm_invocation_filters.py` is now 156 lines after
  moving streaming invocation id/profile capability detection to
  `llm_invocation_streaming.py`. The filters module now keeps query
  normalization, invocation filtering, pagination, empty-state text, search
  text, and de-duplication.
- `application/read_models/llm_invocation_details.py` is now 137 lines after
  moving invocation summary and request-context item projection to
  `llm_invocation_detail_items.py`.
- `application/read_models/llm_invocation_detail_items.py` is now 98 lines
  after moving request-context/replay/tool-result/provider-request key-value
  projection to `llm_invocation_request_context_items.py`. The detail items
  module now keeps invocation summary items only.
- `application/read_models/context_workspace_rows.py` is now 224 lines after
  moving generic table/metadata/time/token helpers to
  `context_workspace_row_helpers.py`, snapshot/budget rows to
  `context_workspace_snapshot_rows.py`, and metric card projection to
  `context_workspace_metrics.py`.
- Operations persistence stores are no longer bundled in one
  `repositories.py`; projection, observation, and action-audit stores now live
  in `projection_repository.py`, `observation_repository.py`, and
  `action_audit_repository.py`.
- `application/projections.py` no longer mixes observer materialization with
  module route tables, page payload loading, table/detail projection extraction,
  and JSON serialization. Those responsibilities live in
  `projection_modules.py`, `projection_materializer_pages.py`,
  `projection_materializer_details.py`, `projection_memory_details.py`, and
  `projection_materializer_json.py`; the materializer keeps write ordering,
  projection freshness stamping, clearing, and invalidation publishing.
- `interfaces/http.py` is now 129 lines after moving runtime status/SSE helpers
  to `http_runtime.py`, projection read routes to `http_projection_routes.py`,
  projection exception/payload shaping to `http_projection_helpers.py`, action
  validation/audit helpers to `http_action_audit.py`, action payload helpers to
  `http_action_payloads.py`, action service construction to
  `http_action_service.py`, and controlled-action routes to focused execution/
  resource/event route modules.
- `interfaces/http_models.py` is now 165 lines after moving shared response
  primitives to `http_models_core.py`, action request/result DTOs to
  `http_models_actions.py`, support page responses to
  `http_models_support_pages.py`, Browser page response to
  `http_models_runtime_pages.py`, Channels page responses to
  `http_models_channels_pages.py`, Daemon page responses to
  `http_models_daemon_pages.py`, Events page responses to
  `http_models_events_pages.py`, Tool page responses to
  `http_models_tool_pages.py`, LLM page responses to `http_models_llm_pages.py`,
  Orchestration page responses to `http_models_orchestration_pages.py`, and
  LLM/Daemon detail responses to focused detail DTO modules.
- `application/read_models/tool.py` is now 61 lines after moving page
  DTO/payload helpers to `tool_models.py`, provider-local section/query wrappers
  to `tool_page_helpers.py`, page tab projection to `tool_page_tabs.py`,
  overview assembly to `tool_overview_builder.py`, page assembly to
  `tool_page_builder.py`, and page fact collection to `tool_page_facts.py`.
- `application/read_models/llm.py` is now 56 lines after moving view models,
  run-context projection, invocation detail projection, overview assembly, page
  assembly, and page fact collection into focused modules.
- `application/read_models/llm_overview_builder.py` is 129 lines and owns LLM
  Operations overview fact reads plus overview DTO assembly.
  `llm_overview_sections.py` is now 110 lines and keeps health plus page metric
  cards; queue, profile limit, profile load, invocation reason, and max-context
  row projection live in `llm_overview_rows.py`. Static LLM Operations actions live
  in `llm_overview_actions.py`.
  `llm_page_builder.py` is now 237 lines and owns page DTO assembly,
  `llm_page_tabs.py` owns tab/count projection, and `llm_page_facts.py` owns
  owner-fact reads. Invocation active/failed/streaming/detail/filter sets now
  live in `llm_page_invocation_sets.py`, and execution-owner run context
  projection now lives in `llm_run_context_execution.py`, so the public provider
  facade remains dependency wiring plus delegation only.
- `application/read_models/llm_resolver_sections.py` is now 150 lines after
  moving fallback/no-match resolver problem table projection to
  `llm_resolver_problem_sections.py` and replay-window/int/text label helpers
  to `llm_resolver_labels.py`. Resolver sections now keep run mapping, bucket
  semantics, model resolver chart projection, and invocation resolver facts.
- `application/read_models/orchestration.py` is now 63 lines after moving
  projection diagnostics, overview rows, worker/queue/ingress/event
  log/backpressure/execution-chain/status/failure/metric sections, action
  definitions, runtime fact helpers, page DTOs, Orchestration-specific ports,
  summary metric/tab projection, overview assembly, and page assembly into
  focused modules.
- `application/read_models/orchestration_overview_builder.py` is 131 lines and
  owns Orchestration overview fact reads plus metric/queue/lane/executor
  assembly. `orchestration_page_builder.py` is now 108 lines and owns the
  Orchestration page shell, action wiring, and projection diagnostics;
  `orchestration_page_sections.py` owns page section aggregation; and
  `orchestration_page_facts.py` owns page owner fact reads and derived
  run/lease/dispatch/observer sets.
- `application/read_models/orchestration_backpressure_sections.py` is now 94
  lines after moving Stuck Runs table projection and age/route helpers to
  `orchestration_stuck_run_sections.py` (156 lines). The backpressure module
  now owns only active-lane detection and the donut bucket projection.
- `application/read_models/orchestration_ingress_sections.py` is now 66 lines
  after moving pending ingress selection to `orchestration_ingress_state.py`
  (35 lines), row assembly to `orchestration_ingress_rows.py` (102 lines),
  source/target/priority projection to `orchestration_ingress_projection.py`
  (52 lines), and display/dispatch/tone/trace/age row values to
  `orchestration_ingress_row_values.py` (158 lines). The section file keeps
  only ingress queue table assembly.
- `application/read_models/orchestration_event_log_sections.py` is now 40 lines
  after moving event time/row projection to `orchestration_event_log_rows.py`
  (96 lines) and event source/summary/detail/tone/trace label rules to
  `orchestration_event_log_projection.py` (224 lines). The section file keeps
  only ops event log table assembly.
- `application/read_models/events.py` is now 56 lines after moving query/view
  models, filters, metrics, actions, charts, owners, contract summary, recent
  event table, event detail projection, observer/subscription sections,
  topic-contract-route projection, event state collection, dead-letter table
  projection, overview assembly, and page assembly into focused modules.
- `application/read_models/events_overview_builder.py` is 51 lines and owns
  Events overview projection. `events_page_builder.py` is now 173 lines and
  owns Events page DTO assembly; `events_page_facts.py` is now 155 lines and
  owns page fact assembly. Source reads live in `events_page_sources.py`, runtime
  topic/cursor/subscription/observer state lives in
  `events_page_runtime_facts.py`, and recent-event source selection/filtering/
  pagination lives in `events_page_recent_facts.py`. Source-topic selection,
  recent-event read limits, uncovered-event filtering, state flag counts,
  health-count aggregation, and health projection live in
  `events_page_projection.py` (162 lines). Live topic
  listing, topic prioritization, and
  safe topic snapshot reads now live in `events_topic_state.py` (65 lines).
- `application/read_models/events_contract_sections.py` is now 162 lines after
  moving topic row aggregation and uncovered-topic coverage projection to
  `events_topic_rows.py`. Contract and route table sections remain in the
  contract section module.
- `application/read_models/events_event_details.py` is now 87 lines after
  moving single-event detail, contract, subscription, and shared event display/
  tone helpers to `events_event_detail_sections.py` and `events_event_common.py`.
  The remaining file keeps only Recent Events table assembly and row projection.
- Events observer/subscription page sections no longer share a 368-line
  aggregate file. Common display/sort helpers live in
  `events_observer_common.py` (76 lines), consumer/subscription tables in
  `events_subscription_sections.py` (108 lines), observer runtime/lag tables in
  `events_observer_runtime_sections.py` (168 lines), and observer coverage in
  `events_observer_coverage_sections.py` (58 lines).
- The retired aggregate `application/read_models/events_state.py` has been
  deleted. Recent event source selection and dead-letter filtering live in
  `events_recent_state.py` (97 lines), record/observed-event summary projection
  lives in `events_recent_projection.py` (129 lines), subscription cursor state
  lives in `events_subscription_state.py`, topic scan and snapshot state lives
  in `events_topic_state.py`, observer heartbeat/runtime projection lives in
  `events_observer_runtime_state.py`, and shared cursor/display/json helpers
  live in `events_state_common.py`.
- `application/read_models/daemon.py`, `channels.py`, `skills.py`,
  `browser.py`, `memory.py`, and `access.py` now delegate page models,
  display/status helpers, event projection, table sections, detail projection,
  and health/action/chart sections to focused helper modules.
- `application/read_models/memory.py` is now 167 lines after moving query
  normalization, owner-safe profile/memory/watch/event reads, selected agent
  resolution, file filtering, search-hit collection, and health calculation to
  `memory_page_facts.py` (127 lines). The provider now keeps overview/page DTO
  assembly and delegates owner fact selection to the page-facts helper.
- The retired aggregate `application/read_models/browser_common.py` has been
  deleted. Runtime/proxy/daemon-instance fact projection lives in
  `browser_runtime_facts.py` (163 lines), status/health tone rules live in
  `browser_tones.py` (73 lines), and value/time/byte/filter/label helpers live
  in `browser_values.py` (127 lines). `browser.py` is now 139 lines and wires
  focused Browser projections through `browser_page_data.py`.
- The retired aggregate `application/read_models/access_tables.py` has been
  deleted. Target/missing/provider/authentication tables live in
  `access_target_tables.py` (173 lines), credential requirement rows in
  `access_requirement_tables.py` (97 lines), and usage/setup/expiry tables in
  `access_usage_tables.py` (136 lines). Access page assembly now lives in
  `access_page_builder.py`; `access.py` is a 65-line provider facade that owns
  dependencies and query entrypoints only. Access chart projection and access
  auth event count rules live in `access_charts.py`; `access_health.py` is now
  153 lines and owns health, metric cards, tabs, actions, and setup counts.
  Pure Access scalar/list/dict/text normalization now lives in
  `access_values.py` (65 lines), leaving `access_common.py` at 201 lines for
  Access-specific overview, health, and target semantics.
- `application/read_models/channels.py` is now 55 lines after moving owner fact
  reads, page DTO assembly, charts, tables, and detail projection wiring into
  `channels_page_builder.py` (171 lines), page data collection into
  `channels_page_data.py`, query normalization/filter projection into
  `channels_page_filters.py`, and overview projection into
  `channels_overview_builder.py` (50 lines).
- `application/read_models/skills.py` is now 55 lines after moving page DTO
  assembly, charts, tables, and detail projection wiring into
  `skills_page_builder.py` (149 lines), query normalization, safe owner reads,
  event buckets, and health into `skills_page_facts.py` (139 lines),
  SkillRecord readiness projection and filtering into `skills_page_records.py`,
  and overview projection into
  `skills_overview_builder.py` (53 lines).
- `application/read_models/skills_details.py` is now 50 lines after moving
  detail requirement/resource/event table projection and raw skill payload
  projection to `skills_detail_sections.py` (185 lines). The details module now
  only assembles `SkillDetailModel` records from visible skill facts.
- `application/read_models/skills_events.py` is now 160 lines after moving
  observation/bus event source reads, skill-event filtering, source dedupe, and
  latest-readiness mapping into `skills_event_sources.py`. The events module now
  keeps authoring/read/error detail labels and tone projection.
- `application/read_models/tool_metrics.py` is now 164 lines after moving
  runtime bootstrap policy metric card projection and config parsing helpers
  into `tool_runtime_metrics.py` (133 lines), and duration/window/percentile/
  throughput value helpers into `tool_metric_values.py` (57 lines).
- The retired aggregate `application/read_models/daemon_details.py` has been
  deleted. Daemon instance details live in `daemon_instance_details.py` (148
  lines), Browser Host instance summary projection lives in
  `daemon_browser_instance_summary.py` (98 lines), lease details in
  `daemon_lease_details.py` (68 lines), process details in
  `daemon_process_details.py` (76 lines), and shared metadata/event matching
  helpers in `daemon_detail_common.py` (53 lines).
- `application/read_models/daemon_runtime_facts.py` is now 107 lines after
  moving process-session reads, process row projection, missing-process rows,
  and instance-by-process indexing to `daemon_process_facts.py`.
- The retired aggregate `application/read_models/skills_tables.py` has been
  deleted. Installed/source/conflict/profile catalog tables live in
  `skills_catalog_tables.py`, missing capability tables live in
  `skills_missing_tables.py`, access/capability requirement tables live in
  `skills_requirement_tables.py`, and resolver detail tables live in
  `skills_resolver_tables.py`.
- `application/read_models/memory_tables.py` is now 151 lines after moving
  index sync activity, write/flush, and retrieval log event tables to
  `memory_event_tables.py`, context resolution event/current-record fallback
  projection to `memory_context_tables.py`, and source file, search trace, and
  source scan tables to `memory_source_tables.py`. The remaining file keeps
  Memory store, index job, and usage tables. Pure Memory scalar/time/status/text
  value helpers now live in `memory_values.py` (69 lines), while Memory file id,
  indexed coverage, size, search blob, and latest-update helpers live in
  `memory_file_helpers.py`. `memory_common.py` is now 141 lines and keeps
  Memory-specific overview, record/index status, watcher, backend, and health
  semantics.
- `application/read_models/modules.py` is now 156 lines after moving shared
  overview/table helpers to `modules_helpers.py` and fallback overview
  projections to `modules_access.py`, `modules_memory.py`, `modules_skills.py`,
  `modules_channels.py`, `modules_events.py`, and `modules_daemon.py`.
  Operations module overview section/table assembly now lives in
  `modules_overview_sections.py` (154 lines), leaving `modules_helpers.py` at
  103 lines for generic table item and value helpers.

## Findings

- The module is correctly not a business owner. It should consume events/query services and materialize read models.
- Tool, LLM, and Orchestration page read-models now keep public provider facades and delegate most projection rules to focused helper modules.
- Tool, LLM, and Orchestration Operations endpoints now have endpoint-level table
  query-budget coverage. Tool and LLM apply the existing table filters to
  `tool_runs` and `recent_invocations`; Orchestration now exposes the same
  `limit`/`offset` boundary for the primary `run_queue` table.
- Every primary Operations page response now exposes `projection_freshness`
  derived from the projection store record (`module`, `kind`, `query_key`,
  `updated_at`). This keeps freshness observable at the HTTP projection
  boundary without pushing UI-specific fields into owner read models.
- The remaining read-model facade risk is low; the larger risk is now helper/table surface size and production-readiness behavior under larger datasets.
- The Operations HTTP router no longer mixes projection reads and controlled action route bodies. The root router owns only runtime status, projection-refresh SSE, and sub-router composition.
- Projection freshness, stale data, and fallback behavior must be explicit.

## Launch Risks

- Operations pages may become slow as data grows.
- Projection bugs can mislead operators during incidents.
- Owner-specific logic can creep into Operations and weaken module boundaries.

## Recommendations

- Continue splitting large non-core read models into collector, materializer, DTO/projector, and diagnostics.
- Add query-budget and projection freshness metrics per page.
- Keep owner modules as generic query surfaces, not Operations-specific providers.
- Add load tests for `/operations/tool`, `/operations/llm`, `/operations/orchestration`, and Workbench linked entity detail.

## Detailed Pass 1

### Files Reviewed

- `application/read_models/tool.py`
- `application/read_models/llm.py`
- `application/read_models/orchestration.py`
- `application/read_models/events.py`
- `application/read_models/daemon.py`
- `interfaces/http.py`
- `interfaces/http_models.py`
- `application/observer_runtime_service.py`
- `application/observer_event_names.py`
- `application/observer_subscriptions.py`
- `application/projections.py`
- `infrastructure/persistence/projection_repository.py`
- `infrastructure/persistence/observation_repository.py`
- `infrastructure/persistence/action_audit_repository.py`

### File-Level Assessment

`application/read_models/tool.py` was the largest module-level hotspot at 6472 lines
and is now 61 lines after extracting focused helpers for run filtering/tables/details,
metrics, workers, scheduling, providers, readiness, lifecycle events, artifacts,
projection diagnostics, orchestration context lookup, page fact collection, and
page assembly. It remains the public Tool Operations provider facade, while
`tool_overview_builder.py` owns Tool overview fact reads plus metric/queue/risk/
worker assembly, `tool_page_builder.py` owns the Tool page shell, metadata,
metrics/tabs/actions, and diagnostics, `tool_page_sections.py` is now a 63-line
Tool page section composition entrypoint, and `tool_page_facts.py` owns Tool
page fact assembly. Source/provider owner reads live in
`tool_page_source_facts.py`, derived run buckets/filtering/detail contexts live
in `tool_page_run_facts.py`, execution/queue/scheduling sections live in
`tool_page_execution_sections.py`, catalog/source/readiness sections in
`tool_page_catalog_sections.py`, and worker/run detail section wiring in
`tool_page_detail_sections.py`.

`application/read_models/tool_readiness_sections.py` no longer mixes table
projection with risk payload normalization. Access/runtime readiness payload
source selection and access fallback live in `tool_readiness_risk.py`; combined
readiness payload normalization, access readiness payload normalization,
readiness item coercion, requirement labels, and action route projection live in
`tool_readiness_payloads.py`; the section file keeps Operations table
row/section assembly.

`application/read_models/tool_worker_sections.py` no longer owns shared worker
registration/runtime/capability/run metric projection. Registration,
runtime-provider, and capability summary rules live in `tool_worker_projection.py`
and are imported by both worker list sections and worker detail projection.
ToolRun-derived bucket/status/tone/lease/success-rate/average-duration labels live
in `tool_worker_run_projection.py`, so worker registration state and run history
metrics can change independently.

The retired `application/read_models/tool_source_sections.py` no longer bundles
owner-safe reads, Source/Function catalog tables, Provider Backend health
projection, and shared record helpers. Those responsibilities now live in
`tool_source_queries.py`, `tool_source_catalog_sections.py`,
`tool_source_provider_sections.py`, and `tool_source_common.py`; Tool Operations
imports those focused modules directly.
`tool_source_catalog_sections.py` is now 117 lines and only assembles source,
function, discovery failure, and CLI process health table sections; source row
projection, discovery failure rows, and function catalog risk rows live in
`tool_source_catalog_rows.py` (146 lines), CLI process health row projection
lives in `tool_source_cli_rows.py`, while source tab tone, health tone, endpoint,
tools-list, and runtime dependency labels live in `tool_source_catalog_labels.py`.
Provider Backend row projection and 24h run-count aggregation now live in
`tool_source_provider_backend_rows.py`; credential, readiness, runtime, and row
tone label rules live in `tool_source_provider_backend_labels.py`;
`tool_source_provider_sections.py` is a 47-line table section shell with
column/empty-state ownership only.

`application/read_models/tool_run_details.py` no longer exposes browser display,
assignment history table, or JSON-safe payload helpers as accidental public
helpers. Detail payload shaping lives in `tool_run_detail_payloads.py`,
assignment history projection lives in `tool_run_assignment_details.py`, and
Browser-specific run/profile projection lives in `tool_run_browser_details.py`.
Tool Run summary item assembly now lives in `tool_run_detail_summary.py`, while
assignment/source/trace/lease/status/tool label projection lives in
`tool_run_detail_projection.py`; `tool_run_details.py` remains detail model
assembly.

`application/read_models/tool_run_artifacts.py` is now 141 lines after moving
result payload normalization, result summaries, artifact-ref extraction,
artifact-service enrichment, byte/dimension labels, and optional value coercion
to `tool_run_artifact_refs.py`. The artifacts module now only assembles recent
and per-run artifact table sections.

`application/read_models/tool_run_artifact_refs.py` is now 43 lines after moving
payload block extraction, metadata artifact parsing, artifact-service
enrichment, byte/dimension labels, and optional value coercion to
`tool_run_artifact_ref_projection.py` (173 lines). The refs module now keeps
only ToolRun payload access, artifact ref de-duplication, and public entry-point
shape.

`application/read_models/tool_run_table_labels.py` is now 42 lines after moving
source/trace/context helpers to `tool_run_source_labels.py` and assignment/
lease/duration/progress labels to `tool_run_execution_labels.py`.
`tool_run_table_facts.py` now builds `ToolRunTableFacts` records from owner
facts and focused helper projections instead of importing a mixed label bucket.

`application/read_models/tool.py` no longer constructs its page tabs inline.
Tool tab projection now lives in `tool_page_tabs.py`, overview assembly lives in
`tool_overview_builder.py`, page fact collection lives in `tool_page_facts.py`,
and page section group wiring lives in `tool_page_sections.py`.

`application/read_models/tool.py` no longer owns Tool overview/page construction.
`ToolOperationsReadModelProvider` now delegates to `tool_overview_builder.py`
and `tool_page_builder.py`; the facade holds dependencies and query entrypoints
only. `tool_page_facts.py` keeps final page fact assembly out of the page
builder, while `tool_page_source_facts.py` owns source/provider owner reads and
`tool_page_run_facts.py` owns active/waiting/failed/detail/filter derivation.
`tool_page_builder.py` is now 128 lines after moving active run, queue,
source/catalog, provider, readiness, worker, risk, artifact, lifecycle, and
detail section wiring into `tool_page_sections.py`. That composition module now
delegates execution, catalog, and detail section groups to focused helper
modules instead of owning every section inline.

`application/read_models/llm.py` was 4480 lines and is now 56 lines after extracting
focused helpers for invocation filters/facts/tables, lifecycle and response events,
runtime metrics, resolver/provider/rate-limiter/usage/error/stream sections, provider
request diagnostics, detail tables, view models, run-context projection, overview
assembly, page assembly, and page fact collection. `llm_overview_builder.py` owns
overview fact reads plus overview DTO assembly, `llm_overview_sections.py` keeps
health/page metric cards, `llm_overview_rows.py` owns queue/profile/context row
projection, `llm_overview_actions.py` owns static actions,
`llm_page_builder.py` owns page DTO assembly, `llm_page_tabs.py` owns tab/count projection, and
`llm_page_facts.py` owns owner-fact reads plus derived invocation/profile/event
sets. `llm.py` remains the public LLM Operations provider facade.

`application/read_models/llm_lifecycle_events.py` no longer owns event source
collection or row label/payload formatting. Event collection composition from
Operations observation and the Events bus lives in
`llm_lifecycle_event_sources.py`; bus topic selection, safe reads, record
conversion, and bus-side dedupe live in `llm_lifecycle_event_bus.py`; row
transport/continuation/input-delta/details/tone projection lives in
`llm_lifecycle_event_rows.py`; the lifecycle file keeps only section assembly.

`application/read_models/llm_invocation_details.py` is no longer a mixed detail
payload/protocol/replay hotspot. It now assembles `LlmInvocationDetailModel`;
runtime observation labels live in
`llm_invocation_detail_runtime.py`, replay/tool-result labels live in
`llm_invocation_detail_replay.py`, result payload preview/sanitizing lives in
`llm_invocation_detail_payloads.py`, and small shared label helpers live in
`llm_invocation_detail_common.py`.
Invocation summary and request-context item lists now live in
`llm_invocation_detail_items.py` and
`llm_invocation_request_context_items.py`, while provider request labels live in
`llm_provider_request_labels.py` and Provider Context Mapping table projection
lives in `llm_provider_context_mapping.py`. `llm_invocation_details.py` now
keeps detail model assembly only.

`application/read_models/llm_invocation_tables.py` now keeps table section
assembly only. The retired `llm_invocation_table_rows.py` aggregate has been
split into streaming rows, recent rows, failed rows, and shared stream-status
projection modules. Provider/model, run context, token counters, continuation
labels, stream state, and action routes now live with those focused row
families.

`application/read_models/llm_provider_sections.py` is now 109 lines. Access
readiness, availability, credential/context/capability labels, and
latest-invocation lookup live in `llm_provider_readiness.py` (118 lines).
Warmup event selection, warmup labels/actions, and warmup next-action
projection live in `llm_provider_warmup.py` (107 lines). Provider access,
auth-blocker, and model-availability row projection lives in
`llm_provider_rows.py`; provider sections now only assemble table shells,
columns, and empty states.

`application/read_models/orchestration.py` was 3058 lines and is now 63 lines after
extracting projection diagnostics, overview rows, worker/queue/ingress/event log,
backpressure, execution chain, scheduler status, policy limits, repeated-probe, and
recent-failure sections, plus health/metric projection, action definitions, runtime
fact helpers, page DTOs, Orchestration-specific ports, and summary metric/tab
projection. `orchestration_overview_builder.py` now owns overview fact reads plus
metric/queue/lane/executor assembly; `orchestration_page_builder.py` owns page DTO
assembly; `orchestration_page_facts.py` owns page owner fact reads and derived
run/lease/dispatch/observer sets.

`application/read_models/orchestration_backpressure_sections.py` no longer mixes
Backpressure bucket/chart projection with Stuck Runs table projection. Stuck Run
buckets, oldest-age labels, approval labels, and Workbench routes now live in
`orchestration_stuck_run_sections.py`; the backpressure file keeps active lane
detection and wait-reason bucket rules.
run/lease/dispatch/observer sets. `orchestration.py` remains the public
Orchestration Operations provider facade.

`application/read_models/orchestration_execution_chain_sections.py` is no longer
the execution-chain helper hotspot. It now only assembles the Operations table
section; candidate run selection and safe query calls live in
`orchestration_execution_chain_queries.py`, continuation/tool-only labels live in
`orchestration_execution_chain_diagnostics.py`, and row/cell/status/route
projection lives in `orchestration_execution_chain_rows.py`.
Execution-chain label/tone/route/age/breakdown display rules now live in
`orchestration_execution_chain_row_values.py`, leaving row assembly focused on
joining run, chain, dispatch, step, and item facts.

`application/read_models/orchestration_summary_sections.py` now owns
Orchestration overview/page metric-card construction only; page tab projection
lives in `orchestration_page_tabs.py`. This keeps the public provider facade
focused on owner fact reads, section assembly, and projection diagnostics
instead of inline DTO construction.

`application/read_models/orchestration_status_sections.py` no longer mixes
status section assembly with low-level runtime config parsing, dispatch task
breakdown, observer cursor labels, and duration/percentile helpers. Those rules
now live in `orchestration_status_projection.py`, while runtime bootstrap config
value parsing and policy labels live in `orchestration_runtime_config_projection.py`.
It also no longer owns Policy & Limits section assembly; that section lives in
`orchestration_policy_sections.py`, so scheduler status and runtime policy display
can evolve independently.

`application/read_models/orchestration_worker_sections.py` is now 95 lines
after moving run type/progress labels, lane-lock TTL/expiry/renewal labels,
executor status tone, trace/workbench route projection, age labels, duration
labels, and numeric display helpers to `orchestration_worker_projection.py`,
then moving lane-lock/executor row assembly to `orchestration_worker_rows.py`.
The worker section file now keeps executor/lane table shells only.

`application/read_models/daemon.py` is now a 59-line provider facade after
extracting Daemon page assembly to `daemon_page_builder.py`. Page view models,
shared display/status helpers, event collection/table projection,
service/instance/lease/dependency table sections, process-session table
projection, instance/lease/process detail projections, health/metric/chart
sections, owner-safe runtime fact reads, process row synthesis/currentness
helpers, query filtering, page action/link helpers, and page construction now
live in focused Daemon helper modules instead of the public provider facade.

`application/read_models/daemon_events.py` is now 100 lines after moving
Operations observation/Event-bus source collection to `daemon_event_sources.py`
and daemon/process topic matching, owner/module filtering, and dedupe rules to
`daemon_event_filters.py`. The events module now owns only table row/cell/detail
projection.

`application/read_models/daemon_common.py` is now 124 lines after moving Daemon
status/availability/tone rules to `daemon_status_helpers.py`, process binding/
currentness/output marker rules to `daemon_process_helpers.py`, and browser host
manifest labels to `daemon_browser_helpers.py`. The common module now keeps only
scalar/time/filter normalization helpers used across Daemon projections.

`application/read_models/daemon_tables.py` is now 168 lines after moving Process
Sessions table projection to `daemon_process_tables.py`, service-set/service/
dependency-health row projection to `daemon_service_rows.py`, and instance/
lease/runtime-label row projection to `daemon_table_rows.py`. Daemon table
modules now separate table section assembly from row synthesis.

`application/read_models/daemon_health.py` is now 67 lines after moving process
health, state summary, and lease health chart projection to `daemon_charts.py`,
lease/drain key-value overview projection to `daemon_drain.py`, and metric-card/
tab projection to `daemon_metrics.py` (158 lines). The health module now keeps
overall health classification and shared desired-service rules only.

The retired aggregate `application/read_models/daemon_details.py` has now been
deleted. Process stdout/stderr output reads, output payload shaping, and output
table projection remain in `daemon_process_output_details.py`; instance, Browser
Host instance summary, lease, and process detail assembly live in focused
`daemon_instance_details.py`, `daemon_browser_instance_summary.py`,
`daemon_lease_details.py`, and `daemon_process_details.py`.

`application/read_models/channels_common.py` is no longer the shared dumping ground
for generic display helpers. Channel-specific query/event safety helpers remain
there, while pure formatting, date/age labels, and status/tone labels live in
`channels_formatting.py`; JSON excerpting and payload display helpers live in
`channels_payload_formatting.py`. Channels page, health, event, detail, and table
modules now import those helpers directly instead of routing through
`channels_common.py`.

`application/read_models/channels_events.py` is now 172 lines after moving
Channel event record projection from observed events and event-topic records to
`channels_event_records.py` (154 lines). The events module now keeps channel
type discovery, dead-letter/recent topic selection, event reads, dedupe, and
connection binding enrichment.

`application/read_models/channels_details.py` is now 123 lines after moving
record detail projection to `channels_record_details.py` and interaction detail
projection to `channels_interaction_details.py`. The details module now keeps
runtime detail assembly only, while record and interaction views own their
domain-specific payload and route labels.

The retired aggregate `application/read_models/channels_tables.py` no longer owns
runtime, message, interaction, binding, profile, or observed-event table section
projection. Those table section definitions now live in focused
`channels_*_tables.py` modules, while row projection remains in
`channels_table_rows.py`.

`application/read_models/channels_health.py` is now 42 lines after moving
message-flow, delivery-trend, top-channel, failure-category, and shared chart
segment projection to `channels_charts.py`, runtime row fact projection to
`channels_runtime_records.py`, and metric-card/tab/action projection to
`channels_page_summary.py`. Channels page summary uses the shared Operations
presenters for health labels/tone/delta, and Channels health now keeps overall
health classification only.

`application/read_models/tool_provider_limit_facts.py` is now a 54-line limiter
metric/config parser after moving runtime metric/registry snapshot reads to
`tool_provider_limit_snapshots.py` and worker/local capacity projection to
`tool_provider_local_capacity.py`. `tool_provider_limits.py` remains a
145-line global provider-limit section assembler. Worker-detail provider limit
section assembly lives in `tool_worker_provider_limits.py`, while provider
limit rows, numeric coercion, duration labels, and table-column helpers live in
`tool_provider_limit_rows.py`.

`interfaces/http.py` is now a 129-line route composition surface, and
`interfaces/http_models.py` is a 165-line DTO export surface. Projection routes,
projection payload/error mapping, controlled action routes, action service
construction, runtime status helpers, stream payload formatting, and response
DTO families now live in focused interface modules. The remaining interface risk
is no longer route-file size; it is keeping projection/action subrouters thin as
new Operations controls are added.

`application/read_models/modules.py` is no longer a fallback overview hotspot. It now acts as a thin module-page provider, while shared overview helpers and module-specific fallback projections live in focused `modules_*` files. Future work should retire fallback projections when owner-specific Operations pages fully cover a module, not re-grow `modules.py`.

`application/read_models/diagnostics.py` is no longer a mixed baseline and
metrics hotspot. It now only builds the loop regression baseline; common
payload/value helpers live in `diagnostics_common.py`, LLM response/request
metrics live in `diagnostics_response_metrics.py`, tool-only streak and
loop-health projection lives in `diagnostics_loop_health.py`, and run
signal/final answer/missing-metric projection lives in `diagnostics_run_signals.py`.

The aggregate `application/read_models/tool_scheduling_sections.py` has been
retired instead of kept as a compatibility facade. Queue summary/run/waiting-IO
section assembly lives in `tool_scheduling_queue_sections.py`, capability-limit
section assembly lives in `tool_scheduling_capability_sections.py`, and blocker
diagnostic section assembly lives in `tool_scheduling_blocker_sections.py`.
Capacity and worker availability logic live in `tool_scheduling_capacity.py`,
waiting run and capability-limit row projection live in
`tool_scheduling_rows.py`, blocker row assembly lives in
`tool_scheduling_blockers.py`, blocker reason/blocked-by/next-step/tone
projection lives in `tool_scheduling_blocker_projection.py`, Tool Run
assignment/source/trace/lease/tool label projection lives in
`tool_scheduling_run_projection.py`, and generic capability/queue/priority/
age/table labels live in `tool_scheduling_labels.py`.

`application/read_models/context_workspace.py` is no longer a mixed
provider/projection hotspot. It now keeps the Context Workspace Operations query,
provider facade, overview, and page assembly. Safe owner reads, slice collection,
page health, and derived page facts live in `context_workspace_page_facts.py`;
workspace/node/diagnostic rows live in `context_workspace_rows.py`; metric
card projection lives in `context_workspace_metrics.py`;
generic table/metadata/time/token helpers live in `context_workspace_row_helpers.py`;
snapshot and context-budget rows live in `context_workspace_snapshot_rows.py`.

Operations persistence is no longer a single mixed store file. Projection,
observation, and controlled action audit persistence now have separate
repository modules, and app assembly imports those concrete stores directly.
The persistence package export remains a package-level convenience surface, but
there is no retired `repositories.py` compatibility shim.

`infrastructure/persistence/observation_repository.py` is now 197 lines after
moving SQLAlchemy row/domain mapping to `observation_repository_mappers.py` and
module summary/event bucket recording helpers to
`observation_repository_recording.py`, then moving observer heartbeat upsert
mechanics to `observation_repository_heartbeats.py`. The repository now keeps
store methods, transaction boundaries, and query statements while mapper/update
mechanics live in focused infrastructure helpers.

`application/actions.py` now delegates through an explicit
`OperationsActionDependencies` bundle. Runtime controls, resource controls,
orchestration controls, dependency validation, action result DTOs, event
subscription cursor advancement, and stale Channel runtime pruning live in
focused action modules. The service remains the Operations action facade while
HTTP composition owns dependency assembly.

`infrastructure/observation_store.py` is now a 141-line file-backed lightweight
store facade. File lock and atomic-write mechanics live in
`observation_store_io.py`; event bucket aggregation lives in
`observation_store_buckets.py`; snapshot parsing, event recording, and heartbeat
recording live in `observation_store_records.py`.

### Boundary Cleanliness

Operations is allowed to depend on many owner query services because it is an observation projection layer. The issue is not the direction of dependency; it is the density and repeated interpretation logic inside read model files.

Current risk pattern:

- Owner facts are read through query ports and services.
- Operations then performs module-specific interpretation; this is safer now for Tool,
  LLM, and Orchestration because focused helpers and golden/unit tests pin projection
  rules.
- The resulting interpretation becomes a parallel operational model that can drift from owner semantics.

This is acceptable only if projection rules are small, tested, and versioned. That
guarantee is now much stronger for Tool, LLM, and Orchestration; it is still weaker for
the remaining large page providers.

### Lifecycle And Projection Risk

Operations observer/projection is the right pattern. The risk is page request work becoming too expensive:

- Some remaining read models still appear to combine projection store reads, owner query service reads, event topic reads, runtime metrics reads, and table/chart assembly.
- Without query budgets, a larger dataset can make `/operations/tool` or `/operations/llm` slow.
- Projection freshness is not obviously front-and-center in every page.

### Persistence And Efficiency

Persistence implementation exists under `infrastructure/persistence`, and Operations observed events/projections are intended to be in Postgres. That is correct.

Risk:

- If HTTP request path falls back to scanning events/owner repositories to compensate for projection gaps, performance becomes dataset-sensitive.
- File-backed observation storage is no longer exported from the Operations
  infrastructure package and is guarded from app/interface shared runtime paths.
  It remains only as an explicit lightweight/test implementation at
  `operations.infrastructure.observation_store`.

### Concurrency And Multi-User Readiness

Read model projection can scale if materialized projections are primary. It will not scale if every UI request reconstructs complex views by scanning owner stores/events.

Production requirement:

- Page read path should be bounded and mostly projection-store backed.
- Owner query calls should be explicit, few, and measurable.
- Projection lag should be visible.

### External Integration Readiness

Operations is a useful external observability integration point, but current APIs are product-page-shaped rather than stable integration contracts. External consumers will need smaller, versioned resources for module health, active runs, queues, failed items, and projection freshness.

### Remediation Checklist

- [x] Split `read_models/tool.py` into focused Tool Operations projection helpers while preserving `ToolOperationsReadModelProvider`.
- [x] Move Tool Operations overview assembly out of `tool.py` into
  `tool_overview_builder.py`.
- [x] Move Tool Operations page assembly out of `tool.py` into
  `tool_page_builder.py`.
- [x] Move Tool page owner-fact collection and derived run sets out of
  `tool_page_builder.py` into `tool_page_facts.py`.
- [x] Split Tool page pure fact derivations out of `tool_page_facts.py`.
- [x] Split Tool page run selection/query/filter/pagination helpers out of
  `tool_page_helpers.py`.
- [x] Split Tool page source/provider owner reads and run-derived facts out of
  `tool_page_facts.py`.
- [x] Split Tool page section wiring out of `tool_page_builder.py` into
  `tool_page_sections.py`.
- [x] Split Tool page section groups into execution, catalog, and detail
  section modules.
- [x] Split `read_models/llm.py` into focused LLM Operations projection helpers while preserving `LlmOperationsReadModelProvider`.
- [x] Move LLM Operations overview assembly out of `llm.py` into
  `llm_overview_builder.py`.
- [x] Move LLM Operations page assembly out of `llm.py` into
  `llm_page_builder.py`.
- [x] Move LLM page owner-fact collection and derived invocation/profile/event
  sets out of `llm_page_builder.py` into `llm_page_facts.py`.
- [x] Split LLM page invocation active/failed/filter/visible/streaming/detail
  set derivation out of `llm_page_facts.py`.
- [x] Split LLM page tab/count projection out of `llm_page_builder.py` into
  `llm_page_tabs.py`.
- [x] Split LLM page section assembly out of `llm_page_builder.py`.
- [x] Split Orchestration page tab/count projection out of
  `orchestration_summary_sections.py`.
- [x] Split static LLM Operations action definitions out of
  `llm_overview_sections.py`.
- [x] Split LLM resolver fallback/no-match problem table projection out of
  `llm_resolver_sections.py`.
- [x] Split `read_models/orchestration.py` into focused Orchestration Operations projection helpers while preserving the public provider facade.
- [x] Move Orchestration Operations overview assembly out of `orchestration.py`
  into `orchestration_overview_builder.py`.
- [x] Move Orchestration Operations page assembly out of `orchestration.py`
  into `orchestration_page_builder.py`.
- [x] Move Orchestration Operations page owner-fact collection and derived
  run/lease/dispatch/observer sets out of `orchestration_page_builder.py` into
  `orchestration_page_facts.py`.
- [x] Split Orchestration Operations page section aggregation out of
  `orchestration_page_builder.py` into `orchestration_page_sections.py`.
- [x] Split Orchestration ingress display/dispatch/tone/trace/age row values
  out of `orchestration_ingress_projection.py`.
- [x] Move HTTP DTO assembly out of `interfaces/http.py` where it is not strictly route logic.
- [x] Split LLM and Daemon detail HTTP DTOs out of page response modules.
- [x] Split Operations projection-refresh stream payload formatting out of
  `interfaces/http_runtime.py`.
- [x] Split channel runtime/dead-letter action routes out of
  `http_action_routes_events.py`.
- [x] Add focused projection cost counters and diagnostics coverage for Tool, LLM, and Orchestration page helpers.
- [x] Add freshness fields to every Operations page response.
- [x] Add full endpoint query-budget tests for `/operations/tool`, `/operations/llm`, `/operations/orchestration`.
- [x] Disable file observation fallback in shared production runtime.
- [x] Split Operations persistence stores into projection, observation, and
  action-audit repositories without keeping a retired repository shim.
- [x] Split observer heartbeat upsert mechanics out of the Operations
  observation repository.
- [x] Split Operations projection materializer routing and payload extraction
  out of `application/projections.py`.
- [x] Split Operations projection read-payload detail deferral and table filter
  rules out of `read_models/projection_payloads.py`.
- [x] Split loop-regression diagnostics into baseline assembly, common helpers,
  LLM response/request metrics, loop-health projection, and run-signal
  projection.
- [x] Split loop-regression final-answer quality and missing-metric rules out
  of run-signal extraction.
- [x] Split LLM invocation detail projection into model assembly, runtime
  observation labels, replay/tool-result labels, and result payload preview.
- [x] Retire aggregate `llm_detail_tables.py` and split response item,
  response event, policy trace, and bounded payload helper projections.
- [x] Split Channels read-model formatting helpers out of
  `channels_common.py` into `channels_formatting.py` without introducing a
  compatibility facade.
- [x] Split Daemon runtime fact collection, query filtering, and page helper
  projection out of `daemon.py` into focused helper modules.
- [x] Split Daemon page assembly out of `daemon.py` into
  `daemon_page_builder.py`.
- [x] Split Daemon page owner reads, runtime fact grouping, filtering,
  pagination, and health projection out of `daemon_page_builder.py`.
- [x] Split Daemon event source collection and dedupe out of
  `daemon_events.py` into `daemon_event_sources.py`.
- [x] Split Daemon event topic matching, owner/module filtering, and dedupe out
  of `daemon_event_sources.py` into `daemon_event_filters.py`.
- [x] Split Daemon Process Sessions table projection out of `daemon_tables.py`.
- [x] Split Daemon service, instance, lease, and dependency row projection out
  of `daemon_tables.py`.
- [x] Split Daemon service-set/service/dependency row projection out of
  `daemon_table_rows.py` into `daemon_service_rows.py`.
- [x] Split Daemon chart and lease/drain overview projection out of
  `daemon_health.py`.
- [x] Split Daemon Process output detail projection out of
  `daemon_details.py`.
- [x] Split Daemon common helper semantics into scalar/time normalization,
  status projection, process semantics, and browser host label helpers.
- [x] Split Channel runtime/record/interaction detail HTTP response DTOs out of
  `http_models_channels_pages.py`.
- [x] Split Tool run/worker detail HTTP response DTOs out of
  `http_models_tool_pages.py`.
- [x] Retire aggregate read-model `ports.py` and split Operations owner/source
  read contracts by runtime, access/settings, tooling, LLM/agent, context, and
  runtime-source groups.
- [x] Split Operations observer scan/wakeup cadence state out of the durable
  observer runtime service.
- [x] Split Operations observer available-event scan and wait processing out of
  the durable observer runtime service.
- [x] Split Channels event record projection from channel event topic discovery
  and reads.
- [x] Split LLM lifecycle event collection and row/payload projection out of
  `llm_lifecycle_events.py`.
- [x] Split LLM lifecycle Events-bus topic/read/record projection out of
  `llm_lifecycle_event_sources.py`.
- [x] Split Events dead-letter table projection out of `events.py`.
- [x] Move Events Operations overview assembly out of `events.py` into
  `events_overview_builder.py`.
- [x] Move Events Operations page assembly out of `events.py` into
  `events_page_builder.py`.
- [x] Retire aggregate `events_observer_sections.py` and split Events
  consumer/subscription, observer runtime/lag, and observer coverage sections.
- [x] Retire aggregate `access_tables.py` and split Access target,
  credential-requirement, and usage/setup table projections.
- [x] Split Access page assembly out of `access.py`.
- [x] Split Access module fallback overview inventory/readiness adaptation and
  target-row projection out of `modules_access.py`.
- [x] Move Channels Operations overview/page assembly out of `channels.py`
  into focused builder modules.
- [x] Move Skills Operations overview/page assembly out of `skills.py` into
  focused builder modules.
- [x] Split Skills Operations page facts and SkillRecord projection out of
  `skills_page_builder.py`.
- [x] Split Skills runtime actions and chart projection out of
  `skills_health.py`.
- [x] Split Tool runtime policy metric cards out of `tool_metrics.py`.
- [x] Split Events topic/route contract matching out of
  `events_contract_sections.py`.
- [x] Split Events topic row aggregation and uncovered-topic projection out of
  `events_contract_sections.py`.
- [x] Split Events single-event detail projection out of
  `events_event_details.py`.
- [x] Retire aggregate `daemon_details.py` and split Daemon instance, lease,
  process, and shared detail helpers.
- [x] Retire aggregate `events_state.py` and split recent event summary,
  subscription/topic state, observer runtime state, and common cursor/display
  helpers into focused Events state modules.
- [x] Retire aggregate `tool_source_sections.py` and split Tool Source owner
  reads, catalog tables, provider backend health projection, and shared record
  helpers into focused modules.
- [x] Split Tool Source catalog row/tone/endpoint/runtime projection out of
  `tool_source_catalog_sections.py`.
- [x] Split Tool Source catalog label/endpoint/runtime dependency projection
  out of `tool_source_catalog_rows.py`.
- [x] Split Tool Run detail assignment history, payload sanitizing, invocation
  context display, and Browser run/profile display helpers out of
  `tool_run_details.py`.
- [x] Split Tool Run detail summary/source/trace/lease/status projection out of
  `tool_run_details.py`.
- [x] Split Tool Run detail assignment/source/trace/lease/status/tool label
  projection out of `tool_run_detail_summary.py`.
- [x] Split Tool Run artifact reference extraction and result summary helpers
  out of `tool_run_artifacts.py`.
- [x] Split Tool Run artifact payload/metadata/enrichment projection out of
  `tool_run_artifact_refs.py`.
- [x] Split Tool Run table source/trace/lease/progress/search label helpers out
  of `tool_run_table_facts.py`.
- [x] Split Tool Run source/trace/context and assignment/lease/progress label
  helpers out of `tool_run_table_labels.py`.
- [x] Split Tool Run query normalization/pagination/empty-state projection and
  run time/duration semantics out of `tool_run_filters.py`.
- [x] Split Tool lifecycle event priority/tone/details/source/trace projection
  out of `tool_lifecycle_event_rows.py`.
- [x] Split Tool lifecycle event topic selection, predicates, and dedupe rules
  out of `tool_lifecycle_event_sources.py`.
- [x] Split Operations observation model DTOs into observed event/module,
  heartbeat, projection, and snapshot model modules.
- [x] Split Operations projection materializer page loading, detail/table
  extraction, and JSON normalization into focused modules.
- [x] Replace Operations projection materializer reserved logging fields with
  safe structured fields and cover materialization/publish failure paths.
- [x] Split file-backed Operations observation store IO and snapshot/update
  mechanics out of `observation_store.py`.
- [x] Retire mixed `http_action_helpers.py` and split action audit validation
  from action response payload shaping.
- [x] Split Operations action audit result/error summary normalization out of
  `http_action_audit.py`.
- [x] Move Operations action dependency assembly into an explicit
  `OperationsActionDependencies` bundle owned by HTTP composition.
- [x] Split Orchestration ingress source/status/dispatch/trace/action/age
  projection out of `orchestration_ingress_rows.py`.
- [x] Split Orchestration run queue priority/wait/lease/tone/trace/age value
  projection out of `orchestration_queue_rows.py`.
- [x] Split Orchestration observed-facts metric projection out of
  `orchestration_metrics.py`.
- [x] Split LLM provider request label projection out of
  `llm_provider_request_diagnostics.py`.
- [x] Split LLM provider renderer/render-report/tool-mapping label projection
  out of `llm_provider_request_labels.py`.
- [x] Split LLM Provider Context Mapping table projection out of
  `llm_provider_request_diagnostics.py`.
- [x] Split LLM provider access readiness and profile labels out of
  `llm_provider_sections.py`.
- [x] Split LLM provider warmup event projection out of
  `llm_provider_sections.py`.
- [x] Split LLM provider access/auth-blocked/model-availability row projection
  out of `llm_provider_sections.py`.
- [x] Split LLM invocation summary/request-context item projection out of
  `llm_invocation_details.py`.
- [x] Split LLM invocation table row projection out of
  `llm_invocation_tables.py`.
- [x] Retire `llm_invocation_table_rows.py` and split streaming, recent,
  failed, and shared stream-status row projection.
- [x] Split LLM invocation streaming id/profile capability detection out of
  `llm_invocation_filters.py`.
- [x] Split LLM invocation request-context key-value projection out of
  `llm_invocation_detail_items.py`.
- [x] Split LLM invocation request-context runtime/replay/tool-result/artifact
  items and provider wire/renderer items out of
  `llm_invocation_request_context_items.py`.
- [x] Split LLM error fact item projection out of `llm_error_sections.py`.
- [x] Split Tool scheduling source/trace/lease/queue/priority/column label
  helpers out of `tool_scheduling_rows.py`.
- [x] Split Tool scheduling blocker row/reason/tone projection out of
  `tool_scheduling_rows.py`.
- [x] Split Tool scheduling assignment/source/trace/lease/tool label projection
  out of `tool_scheduling_labels.py`.
- [x] Split Tool scheduling blocker reason/blocked-by/next-step/tone projection
  out of `tool_scheduling_blockers.py`.
- [x] Retire aggregate `tool_scheduling_sections.py` and split queue,
  capability-limit, and blocker diagnostic section assembly into focused
  modules.
- [x] Split Tool scheduling queue summary row projection and Waiting IO row
  selection out of `tool_scheduling_queue_sections.py`.
- [x] Split Orchestration event-log label/status/tone/detail projection out of
  `orchestration_event_log_rows.py`.
- [x] Split Orchestration event-log display label mapping out of
  `orchestration_event_log_projection.py`.
- [x] Split Orchestration execution-chain label/tone/route/age/breakdown
  projection out of `orchestration_execution_chain_rows.py`.
- [x] Split Events page source-topic/recent-limit/health projection out of
  `events_page_facts.py`.
- [x] Split Events page runtime topic/cursor/subscription state and
  recent-event fact projection out of `events_page_facts.py`.
- [x] Split Events live topic listing/prioritization/snapshot helpers out of
  `events_subscription_state.py`.
- [x] Split Orchestration worker runtime/route/status label projection out of
  `orchestration_worker_sections.py`.
- [x] Split Orchestration lane-lock/executor row projection out of
  `orchestration_worker_sections.py`.
- [x] Split Tool provider limiter fact extraction and row/value formatting out
  of `tool_provider_limits.py`.
- [x] Split Tool provider history bucket/row/state projection out of
  `tool_provider_sections.py`.
- [x] Split Tool provider runtime/registry snapshot reads and local capacity
  projection out of `tool_provider_limit_facts.py`.
- [x] Split Tool worker provider-limit section assembly out of
  `tool_provider_limits.py`.
- [x] Split Tool readiness risk payload normalization out of
  `tool_readiness_sections.py`.
- [x] Split Tool readiness payload normalization out of
  `tool_readiness_risk.py`.
- [x] Split Tool worker registration/runtime/capability projection out of
  `tool_worker_sections.py`.
- [x] Split Tool worker pool chart projection out of
  `tool_worker_sections.py`.
- [x] Split Tool worker ToolRun-derived status/success/duration projection out
  of `tool_worker_projection.py`.
- [x] Split Tool worker detail summary/capability/runtime sections out of
  `tool_worker_details.py`.
- [x] Split Tool worker detail summary and runtime registry sections out of
  `tool_worker_detail_sections.py`.
- [x] Split Skills event source reads, filtering, dedupe, and readiness mapping
  out of `skills_events.py`.
- [x] Split Skills record readiness/access projection and record filtering out
  of `skills_page_facts.py`.
- [x] Split LLM execution-owner run context projection out of
  `llm_run_contexts.py`.
- [x] Split Context Workspace generic row helpers and snapshot/budget row
  projection out of `context_workspace_rows.py`.
- [x] Split Context Workspace page facts and safe owner reads out of
  `context_workspace.py`.
- [x] Split Context Workspace metric card projection out of
  `context_workspace_rows.py`.
- [x] Split Context Workspace node status aggregation out of
  `context_workspace_rows.py`.
- [x] Split Channels table row projection out of `channels_tables.py`.
- [x] Retire aggregate `channels_tables.py` and split Channels runtime,
  message/event, binding/profile, and interaction table section projection.
- [x] Split Channels chart projection out of `channels_health.py`.
- [x] Split Channels runtime record projection out of `channels_health.py`.
- [x] Split Channels page query normalization and filter projection out of
  `channels_page_builder.py`.
- [x] Split Channels page owner reads, observed/live event selection, filtered
  page data, pagination, and health calculation out of
  `channels_page_builder.py`.
- [x] Split Channels runtime, record, and interaction detail projection into
  focused detail modules.
- [x] Split Channels metric-card, tab, and action projection out of
  `channels_health.py`.
- [x] Split Browser profile and page observation row projection out of
  `browser_rows.py`.
- [x] Split Browser owner reads, daemon payload conversion, row filtering,
  pagination, and health calculation out of `browser.py`.
- [x] Split Browser page query normalization, row filtering, pagination, and
  owner-safe page source reads out of `browser_page_data.py`.
- [x] Retire aggregate `browser_tables.py` and split Browser profile, runtime,
  and activity table section projection.
- [x] Split Daemon process-session reads, process row projection, missing
  process rows, and instance-by-process indexing out of
  `daemon_runtime_facts.py`.
- [x] Split Access chart projection and auth event count rules out of
  `access_health.py`.
- [x] Split Access scalar/list/dict/text normalization helpers out of
  `access_common.py`.
- [x] Split Access target status/check/metadata/usage/setup/event projection
  helpers out of `access_common.py`.
- [x] Split Orchestration repeated failure and repeated probe row projection
  out of `orchestration_failure_sections.py`.
- [x] Split Orchestration Operations page DTO and Orchestration-specific query
  ports out of `orchestration.py`; reuse common Operations observation port.
- [x] Split Orchestration scheduler/policy status projection helpers out of
  `orchestration_status_sections.py`.
- [x] Split Orchestration Policy & Limits section assembly out of
  `orchestration_status_sections.py`.
- [x] Split Orchestration runtime bootstrap config value projection out of
  `orchestration_status_projection.py`.
- [x] Split Orchestration Stuck Runs table projection out of
  `orchestration_backpressure_sections.py`.
- [x] Retire aggregate `skills_tables.py` and split Skills catalog tables from
  requirement/resolver tables.
- [x] Split Memory event-backed tables out of `memory_tables.py`.
- [x] Split Memory context resolution event/current-record fallback projection
  out of `memory_event_tables.py`.
- [x] Split Memory source file, retrieval trace, and source scan tables out of
  `memory_tables.py`.
- [x] Split Memory page owner-fact collection, query normalization, filtering,
  search-hit collection, and health calculation out of `memory.py`.
- [x] Split Memory scalar/time/size/status/text value helpers out of
  `memory_common.py`.
- [x] Split Memory metric-card, tab, action, index-health chart, and retrieval
  chart projection out of `memory_health.py`.
- [x] Split Operations source read-model context DTO out of `factory.py`.
- [x] Split Skills missing capability and resolver detail tables out of
  `skills_requirement_tables.py`.
- [x] Split Tool Run result payload/summary projection out of
  `tool_run_artifact_refs.py`.
- [x] Split Operations module overview section/table assembly out of
  `modules_helpers.py`.

### Remediation Verification

Commands passed after the current Operations split wave:

```bash
python -m ruff check tests/unit/test_module_architecture_guards.py src/crxzipple/modules/operations/interfaces src/crxzipple/modules/operations/application src/crxzipple/modules/operations/infrastructure tests/unit/test_operations_observation.py
PYTHONPATH=src pytest -q tests/unit/test_module_architecture_guards.py tests/unit/test_operations_observation.py tests/unit/test_ui_operations_actions_http.py tests/unit/test_ui_operations_http.py tests/unit/test_ui_operations_orchestration_http.py tests/unit/test_operations_presenters.py --tb=short --maxfail=1
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_read_model.py tests/unit/test_operations_tool_metrics.py tests/unit/test_operations_tool_run_filters.py tests/unit/test_operations_tool_run_tables.py tests/unit/test_operations_tool_run_details.py tests/unit/test_operations_tool_run_error_diagnostics.py tests/unit/test_operations_tool_run_artifacts.py tests/unit/test_operations_tool_source_sections.py tests/unit/test_operations_tool_worker_sections.py tests/unit/test_operations_tool_worker_details.py tests/unit/test_operations_tool_scheduling_sections.py tests/unit/test_operations_tool_provider_sections.py tests/unit/test_operations_tool_readiness_sections.py tests/unit/test_operations_tool_lifecycle_events.py tests/unit/test_operations_tool_overview_sections.py tests/unit/test_operations_tool_projection_diagnostics.py tests/unit/test_operations_tool_run_contexts.py tests/unit/test_operations_llm_read_model.py tests/unit/test_operations_llm_invocation_filters.py tests/unit/test_operations_llm_projection_diagnostics.py tests/unit/test_operations_llm_lifecycle_events.py tests/unit/test_operations_llm_runtime_metrics.py tests/unit/test_operations_llm_response_events.py tests/unit/test_operations_llm_resolver_sections.py tests/unit/test_operations_llm_invocation_facts.py tests/unit/test_operations_llm_overview_sections.py tests/unit/test_operations_llm_provider_sections.py tests/unit/test_operations_llm_rate_limiter_sections.py tests/unit/test_operations_llm_usage_sections.py tests/unit/test_operations_llm_error_sections.py tests/unit/test_operations_llm_stream_sections.py tests/unit/test_operations_llm_invocation_tables.py tests/unit/test_operations_llm_provider_request_diagnostics.py tests/unit/test_operations_llm_detail_tables.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_orchestration_execution_chain_sections.py tests/unit/test_operations_orchestration_backpressure_sections.py tests/unit/test_operations_orchestration_event_log_sections.py tests/unit/test_operations_orchestration_ingress_sections.py tests/unit/test_operations_orchestration_queue_sections.py tests/unit/test_operations_orchestration_worker_sections.py tests/unit/test_operations_orchestration_overview_rows.py tests/unit/test_operations_orchestration_projection_diagnostics.py tests/unit/test_ui_operations_orchestration_http.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k orchestration --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py::UiHttpTestCase::test_operations_endpoints_apply_projection_table_query_budgets tests/unit/test_ui_operations_orchestration_http.py::UiOperationsOrchestrationHttpTestCase::test_page_uses_owner_runtime_state --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py::UiHttpTestCase::test_operations_page_responses_expose_projection_freshness tests/unit/test_ui_http.py::UiHttpTestCase::test_operations_endpoints_apply_projection_table_query_budgets --tb=short
python -m ruff check src/crxzipple/modules/operations/interfaces/http.py tests/unit/test_ui_http.py --ignore F401
python -m ruff check src/crxzipple/modules/operations/interfaces/http.py src/crxzipple/modules/operations/interfaces/http_models.py tests/unit/test_ui_http.py --ignore F401
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py tests/unit/test_operations_tool_read_model.py tests/unit/test_operations_llm_read_model.py --tb=short
python -m ruff check src/crxzipple/modules/operations/interfaces/http.py src/crxzipple/modules/operations/application/read_models/projection_payloads.py tests/unit/test_ui_operations_http.py --ignore F401,I001,E501
python -m ruff check src/crxzipple/modules/operations/application/projections.py src/crxzipple/modules/operations/application/projection_modules.py src/crxzipple/modules/operations/application/projection_materializer_pages.py src/crxzipple/modules/operations/application/projection_materializer_details.py src/crxzipple/modules/operations/application/projection_materializer_json.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/projections.py src/crxzipple/modules/operations/application/projection_modules.py src/crxzipple/modules/operations/application/projection_materializer_pages.py src/crxzipple/modules/operations/application/projection_materializer_details.py src/crxzipple/modules/operations/application/projection_materializer_json.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py tests/unit/test_ui_operations_http.py -k operations --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_context_workspace_read_model.py tests/unit/test_operations_browser_read_model.py --tb=short
python -m ruff check src/crxzipple/modules/operations/application/read_models/skills.py src/crxzipple/modules/operations/application/read_models/skills_catalog_tables.py src/crxzipple/modules/operations/application/read_models/skills_requirement_tables.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/skills.py src/crxzipple/modules/operations/application/read_models/skills_catalog_tables.py src/crxzipple/modules/operations/application/read_models/skills_requirement_tables.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k skills --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k skills --tb=short
python -m ruff check src/crxzipple/modules/operations/application/read_models/memory.py src/crxzipple/modules/operations/application/read_models/memory_tables.py src/crxzipple/modules/operations/application/read_models/memory_event_tables.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/memory.py src/crxzipple/modules/operations/application/read_models/memory_tables.py src/crxzipple/modules/operations/application/read_models/memory_event_tables.py
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k memory --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k memory --tb=short
python -m ruff check src/crxzipple/modules/operations/application/read_models/daemon.py src/crxzipple/modules/operations/application/read_models/daemon_tables.py src/crxzipple/modules/operations/application/read_models/daemon_process_tables.py src/crxzipple/modules/operations/application/read_models/daemon_detail_common.py src/crxzipple/modules/operations/application/read_models/daemon_instance_details.py src/crxzipple/modules/operations/application/read_models/daemon_lease_details.py src/crxzipple/modules/operations/application/read_models/daemon_process_details.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/daemon.py src/crxzipple/modules/operations/application/read_models/daemon_tables.py src/crxzipple/modules/operations/application/read_models/daemon_process_tables.py src/crxzipple/modules/operations/application/read_models/daemon_detail_common.py src/crxzipple/modules/operations/application/read_models/daemon_instance_details.py src/crxzipple/modules/operations/application/read_models/daemon_lease_details.py src/crxzipple/modules/operations/application/read_models/daemon_process_details.py
PYTHONPATH=src pytest -q tests/unit/test_operations_daemon_read_model.py tests/unit/test_ui_operations_http.py -k daemon --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k daemon --tb=short
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool_readiness_sections.py src/crxzipple/modules/operations/application/read_models/tool_readiness_risk.py src/crxzipple/modules/operations/application/read_models/tool.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool_readiness_sections.py src/crxzipple/modules/operations/application/read_models/tool_readiness_risk.py src/crxzipple/modules/operations/application/read_models/tool.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_readiness_sections.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_metrics.py tests/unit/test_operations_tool_scheduling_sections.py tests/unit/test_operations_tool_provider_sections.py --tb=short
python -m ruff check src/crxzipple/modules/operations/application/read_models/tool_worker_sections.py src/crxzipple/modules/operations/application/read_models/tool_worker_projection.py src/crxzipple/modules/operations/application/read_models/tool_worker_details.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/tool_worker_sections.py src/crxzipple/modules/operations/application/read_models/tool_worker_projection.py src/crxzipple/modules/operations/application/read_models/tool_worker_details.py
PYTHONPATH=src pytest -q tests/unit/test_operations_tool_worker_sections.py tests/unit/test_operations_tool_worker_details.py tests/unit/test_operations_tool_read_model.py tests/unit/test_ui_operations_http.py -k tool --tb=short
python -m ruff check src/crxzipple/modules/operations/application/read_models/daemon_detail_common.py src/crxzipple/modules/operations/application/read_models/daemon_instance_details.py src/crxzipple/modules/operations/application/read_models/daemon_lease_details.py src/crxzipple/modules/operations/application/read_models/daemon_process_details.py src/crxzipple/modules/operations/application/read_models/daemon_process_output_details.py src/crxzipple/modules/operations/application/read_models/daemon.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/daemon_detail_common.py src/crxzipple/modules/operations/application/read_models/daemon_instance_details.py src/crxzipple/modules/operations/application/read_models/daemon_lease_details.py src/crxzipple/modules/operations/application/read_models/daemon_process_details.py src/crxzipple/modules/operations/application/read_models/daemon_process_output_details.py src/crxzipple/modules/operations/application/read_models/daemon.py
PYTHONPATH=src pytest -q tests/unit/test_operations_daemon_read_model.py tests/unit/test_ui_operations_http.py -k daemon --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k daemon --tb=short
python -m ruff check src/crxzipple/modules/operations/application/read_models/llm.py src/crxzipple/modules/operations/application/read_models/llm_lifecycle_events.py src/crxzipple/modules/operations/application/read_models/llm_lifecycle_event_sources.py src/crxzipple/modules/operations/application/read_models/llm_lifecycle_event_rows.py src/crxzipple/modules/operations/application/read_models/llm_response_item_tables.py src/crxzipple/modules/operations/application/read_models/llm_response_event_tables.py src/crxzipple/modules/operations/application/read_models/llm_policy_trace_tables.py src/crxzipple/modules/operations/application/read_models/llm_detail_payloads.py tests/unit/test_operations_llm_lifecycle_events.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/llm.py src/crxzipple/modules/operations/application/read_models/llm_lifecycle_events.py src/crxzipple/modules/operations/application/read_models/llm_lifecycle_event_sources.py src/crxzipple/modules/operations/application/read_models/llm_lifecycle_event_rows.py src/crxzipple/modules/operations/application/read_models/llm_response_item_tables.py src/crxzipple/modules/operations/application/read_models/llm_response_event_tables.py src/crxzipple/modules/operations/application/read_models/llm_policy_trace_tables.py src/crxzipple/modules/operations/application/read_models/llm_detail_payloads.py
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_lifecycle_events.py tests/unit/test_operations_llm_read_model.py tests/unit/test_ui_operations_http.py -k llm --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_llm_detail_tables.py tests/unit/test_operations_llm_invocation_tables.py tests/unit/test_operations_llm_response_events.py --tb=short
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k llm --tb=short
python -m ruff check src/crxzipple/modules/operations/application/read_models/events.py src/crxzipple/modules/operations/application/read_models/events_dead_letters.py --ignore I001,E501
python -m compileall -q src/crxzipple/modules/operations/application/read_models/events.py src/crxzipple/modules/operations/application/read_models/events_dead_letters.py
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py -k events --tb=short
PYTHONPATH=src pytest -q tests/unit/test_ui_operations_http.py -k events --tb=short
PYTHONPATH=src pytest -q tests/unit/test_events.py::EventsModuleTestCase::test_event_definition_registry_covers_tool_and_llm_lifecycle_events tests/unit/test_events.py::EventsModuleTestCase::test_event_definition_registry_covers_operations_observer_subscriptions --tb=short
```

Results:

- Tool + LLM focused Operations tests: 86 passed
- Orchestration focused Operations tests: 18 passed
- Orchestration observation scoped tests: 6 passed, 43 deselected
- Operations endpoint query-budget suite: 2 passed
- Operations page freshness suite: 2 passed
- Operations HTTP projection helper suite: 31 passed
- Operations projection materializer split checks: ruff passed; compileall
  passed; Operations observation/UI projection regression `75 passed`;
  Context Workspace + Browser Operations projection regression `12 passed`
- Operations projection read-payload/table-filter split checks: ruff passed;
  compileall passed; UI/projection HTTP regression `27 passed`; Operations
  observation scoped regression `49 passed`
- Operations Orchestration page facts split checks: ruff passed; compileall
  passed; Orchestration UI/observation scoped regression
  `9 passed, 43 deselected`; execution-chain/diagnostics/freshness regression
  `3 passed`
- Operations Skills table aggregate retirement checks: ruff passed; compileall
  passed; UI Skills scoped regression `1 passed, 25 deselected`; Operations
  observation Skills scoped regression `5 passed, 44 deselected`
- Operations Skills requirement table split checks: ruff passed; compileall
  passed; UI Skills scoped regression `1 passed, 25 deselected`; Operations
  observation Skills scoped regression `5 passed, 44 deselected`
- Operations Skills page facts split checks: ruff passed; compileall passed;
  UI Skills scoped regression `1 passed, 25 deselected`; Operations
  observation Skills scoped regression `5 passed, 44 deselected`
- Operations Skills record projection split checks: ruff passed; compileall
  passed; UI Skills scoped regression `1 passed, 25 deselected`; Operations
  observation Skills scoped regression `5 passed, 44 deselected`
- Operations Skills event source split checks: ruff passed; compileall passed;
  Skills UI/observation scoped regression `75 passed`
- Operations Tool runtime metric split checks: ruff passed; compileall passed;
  Tool metrics/read-model/UI scoped regression `10 passed, 22 deselected`
- Operations Events contract matching split checks: ruff passed; compileall
  passed; UI Events scoped regression `6 passed, 20 deselected`; Operations
  observation Events scoped regression `19 passed, 30 deselected`; Events
  owner/http regression `42 passed`
- Operations Events event detail split checks: ruff passed; compileall passed;
  UI Events scoped regression `6 passed, 20 deselected`; Operations observation
  Events scoped regression `19 passed, 30 deselected`; Events owner contract
  coverage regression `2 passed`
- Operations Context Workspace page facts split checks: ruff passed; compileall
  passed; Context Workspace read-model regression `2 passed`;
  Context Workspace observation scoped regression `2 passed, 47 deselected`;
  UI Operations + Context Workspace regression `28 passed`
- Operations Context Workspace metric split checks: ruff passed; compileall
  passed; Context Workspace Operations/UI scoped regression `28 passed`; diff
  whitespace check passed
- Operations Memory event-table split checks: ruff passed; compileall passed;
  UI Memory scoped regression `1 passed, 25 deselected`; Operations observation
  Memory scoped regression `3 passed, 46 deselected`
- Operations Memory context table split checks: ruff passed; compileall passed;
  Memory UI/observation scoped regression `4 passed, 71 deselected`
- Operations Memory source table split checks: ruff passed; compileall passed;
  UI Memory scoped regression `1 passed, 25 deselected`; Operations observation
  Memory scoped regression `3 passed, 46 deselected`
- Operations Memory health/page-summary/chart split checks: ruff passed;
  compileall passed; Operations observation Memory scoped regression
  `3 passed, 48 deselected`; UI Memory scoped regression
  `1 passed, 25 deselected`
- Operations Daemon process-table split checks: ruff passed; compileall passed;
  Daemon read-model/UI scoped regression `5 passed, 22 deselected`; Operations
  observation Daemon scoped regression `1 passed, 48 deselected`
- Operations Daemon page builder split checks: ruff passed; compileall passed;
  Daemon read-model/UI scoped regression `5 passed, 22 deselected`; Operations
  observation Daemon scoped regression `1 passed, 48 deselected`
- Operations Daemon page fact split checks: ruff passed; compileall passed;
  Daemon UI scoped regression `4 passed, 22 deselected`; Operations observation
  Daemon scoped regression `1 passed, 48 deselected`
- Operations Daemon event source split checks: ruff passed; compileall passed;
  Daemon read-model/UI scoped regression `5 passed, 22 deselected`; Operations
  observation Daemon scoped regression `1 passed, 48 deselected`
- Operations Daemon event filter split checks: ruff passed; compileall passed;
  Daemon read-model/observation/UI scoped regression `6 passed, 72 deselected`
- Operations Tool readiness risk split checks: ruff passed; compileall passed;
  Tool readiness/read-model/UI scoped regression `11 passed, 22 deselected`;
  Tool metrics/scheduling/provider regression `7 passed`
- Operations Tool readiness payload split checks: ruff passed; compileall
  passed; Tool readiness/read-model/UI scoped regression
  `11 passed, 22 deselected`
- Operations Tool scheduling blocker split checks: ruff passed; compileall
  passed; Tool scheduling/read-model/UI scoped regression
  `10 passed, 22 deselected`; Tool metrics/provider regression `5 passed`
- Operations Tool scheduling run/blocker projection split checks: ruff passed;
  compileall passed; Tool scheduling focused regression `2 passed`; Tool
  scheduling/read-model/UI scoped regression `10 passed, 22 deselected`
- Operations Tool provider limit snapshot/local-capacity split checks: ruff
  passed; compileall passed; Tool provider/read-model/UI scoped regression
  `11 passed, 22 deselected`; Tool scheduling regression `2 passed`
- Operations Tool provider history row split checks: ruff passed; compileall
  passed; Tool provider/read-model/UI scoped regression
  `11 passed, 22 deselected`
- Operations Access module overview inventory/row projection split checks:
  ruff passed; compileall passed; Operations boundary/UI scoped regression
  `29 passed`
- Operations Tool scheduling section aggregate retirement checks: ruff passed;
  compileall passed; Tool scheduling/read-model/UI scoped regression
  `10 passed, 22 deselected`; Tool metrics/provider regression `5 passed`
- Operations Tool page builder split checks: ruff passed; compileall passed;
  Tool read-model/UI scoped regression `8 passed, 22 deselected`;
  scheduling/metrics/provider regression `7 passed`
- Operations Tool page facts split checks: ruff passed; compileall passed;
  Tool read-model/UI scoped regression `8 passed, 22 deselected`;
  scheduling/metrics/provider regression `7 passed`
- Operations Tool page section wiring split checks: ruff passed; compileall
  passed; Tool read-model/UI scoped regression `8 passed, 22 deselected`;
  Tool source/metrics/provider/scheduling regression `9 passed`
- Operations Tool page section group split checks: ruff passed; compileall
  passed; Tool read-model/UI scoped regression `30 passed`; Tool provider/
  worker/run/scheduling regression `10 passed`
- Operations Tool worker projection split checks: ruff passed; compileall
  passed; Tool worker/list/detail/read-model/UI scoped regression
  `11 passed, 22 deselected`
- Operations Tool worker pool section split checks: ruff passed; compileall
  passed; Tool worker/read-model/UI scoped regression
  `10 passed, 22 deselected`
- Operations Tool worker run projection split checks: ruff passed; compileall
  passed; Tool worker/list/detail/read-model/UI scoped regression
  `11 passed, 22 deselected`; Operations observation Tool scoped regression
  `3 passed, 46 deselected`
- Operations Tool worker detail section split checks: ruff passed; compileall
  passed; Tool worker/detail/read-model/UI scoped regression
  `11 passed, 22 deselected`
- Operations Channels table row split checks: ruff passed; compileall passed;
  UI Channels scoped regression `2 passed, 24 deselected`; Channels SSE
  live-event regression `1 passed`; Operations observation Channels scoped
  command had no matching tests (`49 deselected`)
- Operations Channels table aggregate retirement checks: ruff passed;
  compileall passed; UI Channels scoped regression `2 passed, 24 deselected`;
  full Operations observation regression `51 passed`
- Operations Channels chart split checks: ruff passed; compileall passed; UI
  Channels scoped regression `2 passed, 24 deselected`; Channels SSE live-event
  regression `1 passed`
- Operations Channels runtime record split checks: ruff passed; compileall
  passed; UI Channels scoped regression `2 passed, 24 deselected`; Channels
  live-event regression `1 passed`
- Operations Channel HTTP detail DTO split checks: ruff passed; compileall
  passed; Channel Operations UI/observation scoped regression
  `2 passed, 73 deselected`
- Operations Channels page filter split checks: ruff passed; compileall passed;
  UI Channels scoped regression `2 passed, 24 deselected`; Channels SSE
  live-event regression `1 passed`
- Operations Channels page data split checks: ruff passed; compileall passed;
  UI Channels scoped regression `2 passed, 24 deselected`; Channels SSE
  live-event regression `1 passed`; Operations observation Channels scoped
  command had no matching tests (`49 deselected`)
- Operations Channels page summary split checks: ruff passed; compileall
  passed; UI Channels scoped regression `2 passed, 24 deselected`
- Operations Channels topic/connection helper split checks: ruff passed;
  compileall passed; UI Channels scoped regression `2 passed, 24 deselected`;
  Operations observation Channels scoped command had no matching tests
  (`51 deselected`); owner Channels smoke stopped at sandbox socket bind after
  `11 passed`
- Operations Browser profile/page row split checks: ruff passed; compileall
  passed; Browser read-model regression `10 passed`; UI Browser scoped command
  had no matching tests (`26 deselected`)
- Operations Browser page data split checks: ruff passed; compileall passed;
  Browser read-model regression `10 passed`; UI Browser scoped command had no
  matching tests (`26 deselected`)
- Operations Browser page filter/source split checks: ruff passed; compileall
  passed; Browser scoped regression `10 passed, 26 deselected`
- Operations Browser table aggregate retirement checks: ruff passed; compileall
  passed; Browser scoped regression `10 passed, 26 deselected`
- Operations Orchestration status projection split checks: ruff passed;
  compileall passed; Orchestration UI/observation scoped regression
  `9 passed, 43 deselected`; Orchestration overview/execution-chain regression
  `5 passed`
- Operations Orchestration policy section split checks: ruff passed; compileall
  passed; Orchestration UI/page scoped regression `7 passed`; Operations
  observation Orchestration scoped regression `6 passed, 43 deselected`
- Operations Orchestration stuck-run section split checks: ruff passed;
  compileall passed; Backpressure/UI page scoped regression `5 passed`;
  Operations observation Orchestration scoped regression
  `6 passed, 43 deselected`
- Operations LLM provider request label split checks: ruff passed; compileall
  passed; LLM provider request/error/read-model/UI scoped regression
  `9 passed, 23 deselected`
- Operations LLM provider context mapping split checks: ruff passed; compileall
  passed; LLM provider request/read-model/UI scoped regression
  `6 passed, 23 deselected`; Operations observation LLM scoped regression
  `1 passed, 48 deselected`
- Operations LLM provider readiness split checks: ruff passed; compileall
  passed; LLM provider/read-model/UI scoped regression
  `7 passed, 23 deselected`; LLM provider request/error/detail scoped
  regression `7 passed`
- Operations LLM provider row split checks: ruff passed; compileall passed;
  LLM provider/read-model/UI scoped regression `7 passed, 23 deselected`
- Operations LLM resolver problem table split checks: ruff passed; compileall
  passed; LLM resolver/read-model/UI scoped regression
  `8 passed, 23 deselected`; Operations observation LLM scoped regression
  `1 passed, 48 deselected`
- Operations LLM page tab split checks: ruff passed; compileall passed;
  LLM read-model/UI scoped regression `4 passed, 23 deselected`; Operations
  observation LLM scoped regression `1 passed, 48 deselected`
- Operations Orchestration page tab split checks: ruff passed; compileall
  passed; Orchestration UI/overview scoped regression `9 passed, 24 deselected`
- Operations Orchestration execution-chain row value split checks: ruff passed;
  compileall passed; execution-chain/UI/observation scoped regression
  `10 passed, 43 deselected`
- Operations LLM overview action split checks: ruff passed; compileall passed;
  LLM overview/read-model/UI scoped regression `7 passed, 23 deselected`
- Operations LLM overview row split checks: ruff passed; compileall passed;
  LLM overview/read-model scoped regression `4 passed`
- Operations Tool Run detail summary split checks: ruff passed; compileall
  passed; Tool Run detail/read-model/UI scoped regression
  `12 passed, 22 deselected`
- Operations Tool Run detail projection split checks: ruff passed; compileall
  passed; Tool Run detail/table/read-model/UI scoped regression
  `15 passed, 22 deselected`
- Operations Tool Run artifact ref split checks: ruff passed; compileall
  passed; Tool artifact/detail/read-model/UI scoped regression
  `14 passed, 22 deselected`; Tool run table/context regression `5 passed`
- Operations Tool Run artifact ref projection split checks: ruff passed;
  compileall passed; Tool Run artifact focused regression `2 passed`; Tool
  read-model/UI scoped regression `11 passed, 22 deselected`
- Operations Tool Run table label split checks: ruff passed; compileall
  passed; Tool table/read-model/UI scoped regression `13 passed, 22 deselected`;
  Tool artifact/detail regression `6 passed`
- Operations Tool Run source/execution label split checks: ruff passed;
  compileall passed; Tool Run table/read-model/UI scoped regression
  `9 passed, 24 deselected`; Tool Run detail/artifact regression `6 passed`
- Operations Tool Run query/time split checks: ruff passed; compileall passed;
  Tool Run filter/table/detail scoped regression `10 passed`; Tool
  read-model/UI scoped regression `8 passed, 22 deselected`; Tool
  metrics/provider/worker/scheduling regression `9 passed`
- Operations Tool lifecycle event projection split checks: ruff passed;
  compileall passed; Tool lifecycle/run-detail/worker-detail regression
  `7 passed`; Tool read-model/UI scoped regression `8 passed, 22 deselected`;
  Operations observation Tool scoped regression `3 passed, 46 deselected`
- Operations Tool lifecycle event topic split checks: ruff passed; compileall
  passed; Tool lifecycle/read-model scoped regression `6 passed`
- Operations Orchestration ingress projection split checks: ruff passed;
  compileall passed; ingress/queue/UI scoped regression `6 passed`;
  Orchestration observation scoped regression `6 passed, 43 deselected`;
  Orchestration overview/event-log/execution-chain/worker regression `9 passed`
- Operations LLM invocation detail item split checks: ruff passed; compileall
  passed; LLM provider request/error/detail-table/read-model/UI scoped
  regression `11 passed, 23 deselected`
- Operations LLM invocation table row split checks: ruff passed; compileall
  passed; LLM invocation/read-model/UI scoped regression `7 passed, 23 deselected`
- Operations LLM invocation row aggregate retirement checks: ruff passed;
  compileall passed; LLM invocation/read-model/UI scoped regression
  `7 passed, 23 deselected`
- Operations LLM invocation streaming helper split checks: ruff passed;
  compileall passed; LLM invocation filter/stream/table regression `7 passed`;
  LLM read-model/UI scoped regression `4 passed, 23 deselected`
- Operations Orchestration page section split checks: ruff passed; compileall
  passed; Orchestration page observation scoped regression
  `3 passed, 48 deselected`; Orchestration diagnostics/UI scoped regression
  `3 passed, 24 deselected`
- Operations LLM/Daemon detail HTTP DTO split checks: ruff passed; compileall
  passed; LLM/Daemon UI scoped regression `7 passed, 19 deselected`
- Operations Skills profile-usage table split checks: ruff passed; compileall
  passed; Skills UI scoped regression `1 passed, 25 deselected`
- Operations Orchestration ingress row-value split checks: ruff passed;
  compileall passed; ingress/queue/execution-chain/UI scoped regression
  `7 passed`
- Operations Memory detail projection split checks: ruff passed; compileall
  passed; materializer memory/detail scoped regression
  `5 passed, 46 deselected`
- Operations LLM invocation request-context item split checks: ruff passed;
  compileall passed; LLM detail/render-report/read-model/UI scoped regression
  `7 passed, 23 deselected`
- Operations diagnostics loop-health split checks: ruff passed; compileall
  passed; loop-regression/observation scoped regression
  `6 passed, 48 deselected`
- Operations diagnostics run-quality split checks: ruff passed; compileall
  passed; loop-regression/diagnostics scoped regression
  `5 passed, 49 deselected`
- Operations observer scan-state split checks: ruff passed; compileall passed;
  observer/runtime port-boundary regression `49 passed, 1 deselected`
- Operations observer runtime processing split checks: ruff passed; compileall
  passed; Operations observation/port-boundary regression `50 passed`
- Operations observation repository heartbeat split checks: ruff passed;
  compileall passed; Operations observation/architecture guard regression
  `67 passed`
- Operations LLM detail table aggregate retirement checks: ruff passed;
  compileall passed; LLM detail table regression `2 passed`; LLM
  read-model/UI scoped regression `4 passed, 23 deselected`; LLM
  response-event/provider-request regression `9 passed`
- Operations Tool Source catalog row split checks: ruff passed; compileall
  passed; Tool Source focused regression `2 passed`; Tool read-model/UI scoped
  regression `8 passed, 22 deselected`; Tool metrics/provider/scheduling
  regression `7 passed`
- Operations Tool Source catalog label split checks: ruff passed; compileall
  passed; Tool Source focused regression `2 passed`; UI Tool Source scoped
  command had no matching tests (`26 deselected`)
- Operations Daemon process output detail split checks: ruff passed; compileall
  passed; Daemon read-model/UI scoped regression `5 passed, 22 deselected`;
  Operations observation Daemon scoped regression `1 passed, 48 deselected`
- Operations Daemon process facts split checks: ruff passed; compileall passed;
  Daemon UI scoped regression `4 passed, 22 deselected`; Operations
  observation Daemon scoped regression `1 passed, 48 deselected`
- Operations Daemon table row split checks: ruff passed; compileall passed;
  Daemon read-model/UI scoped regression `5 passed, 22 deselected`; Operations
  observation Daemon scoped regression `1 passed, 48 deselected`
- Operations Daemon chart/drain split checks: ruff passed; compileall passed;
  Daemon read-model/UI scoped regression `5 passed, 22 deselected`; Operations
  observation Daemon scoped regression `1 passed, 48 deselected`
- Operations Daemon common semantic split checks: ruff passed; compileall
  passed; Daemon read-model/UI scoped regression `7 passed, 25 deselected`;
  diff whitespace check passed
- Operations Access chart split checks: ruff passed; compileall passed; Access
  UI scoped regression `1 passed, 25 deselected`; Operations observation Access
  scoped regression `3 passed, 46 deselected`
- Operations Access page builder split checks: ruff passed; compileall passed;
  Access UI scoped regression `1 passed, 25 deselected`
- Operations read-model port contract split checks: ruff passed; compileall
  passed; boundary/Tool/LLM/Daemon/Orchestration/UI scoped regression
  `38 passed`; Context Workspace Operations regression `2 passed`; diff
  whitespace check passed
- Operations factory context split checks: ruff passed; compileall passed;
  read-model boundary/lifecycle architecture scoped regression `3 passed,
  21 deselected`; app assembly/Operations HTTP smoke regression `26 passed,
  34 deselected`
- Operations Channels event-record split checks: ruff passed; compileall
  passed; Channels Operations/observation scoped regression `75 passed`;
  Channels UI scoped regression `2 passed, 24 deselected`; diff whitespace
  check passed
- Operations Orchestration event-log projection split checks: ruff passed;
  compileall passed; Orchestration event-log/status/UI scoped regression
  `54 passed`; diff whitespace check passed
- Operations LLM lifecycle event split checks: ruff passed; compileall passed;
  LLM lifecycle/read-model/UI scoped regression `7 passed, 23 deselected`;
  LLM detail/invocation/response event regression `9 passed`; Operations
  observation LLM scoped regression `1 passed, 48 deselected`
- Operations Daemon service row split checks: ruff passed; compileall passed;
  Daemon read-model/UI scoped regression `27 passed`; diff whitespace check
  passed
- Operations Daemon browser instance summary split checks: ruff passed;
  compileall passed; Daemon observation scoped regression `1 passed, 50
  deselected`; Daemon page materialized-state regression `1 passed`
- Operations Orchestration worker projection split checks: ruff passed;
  compileall passed; Orchestration worker/UI/observation scoped regression
  `54 passed`; diff whitespace check passed
- Operations LLM lifecycle bus split checks: ruff passed; compileall passed;
  LLM lifecycle/read-model/UI scoped regression `30 passed`; diff whitespace
  check passed
- Operations Channels detail split checks: ruff passed; compileall passed;
  Channels UI/observation scoped regression `75 passed`; diff whitespace check
  passed
- Operations Events dead-letter table split checks: ruff passed; compileall
  passed; Events observation scoped regression `19 passed, 30 deselected`;
  UI Events scoped regression `6 passed, 20 deselected`; event registry checks
  `2 passed`
- Operations Events overview navigation/contract split checks: ruff passed;
  compileall passed; UI Events scoped regression `6 passed, 20 deselected`;
  Events observation scoped regression `19 passed, 30 deselected`
- Operations Events page projection split checks: ruff passed; compileall
  passed; Events observation scoped regression `19 passed, 30 deselected`;
  UI Events scoped regression `6 passed, 20 deselected`
- Operations Events topic state split checks: ruff passed; compileall passed;
  UI Events scoped regression `6 passed, 20 deselected`; Events observation
  scoped regression `19 passed, 30 deselected`; event registry checks `2 passed`
- Operations Events topic row split and projection materializer logging checks:
  ruff passed; compileall passed; Events/Operations/projection materializer
  scoped regression `77 passed`
- Targeted Operations HTTP/read-model ruff: passed
- Operations Access value helper split checks: ruff passed; compileall passed;
  Access UI scoped regression `1 passed, 25 deselected`; Operations
  observation Access scoped regression `3 passed, 46 deselected`
- Operations Memory value helper split checks: ruff passed; compileall passed;
  UI Memory scoped regression `1 passed, 25 deselected`; Operations
  observation Memory scoped regression `3 passed, 46 deselected`
- Operations Memory file helper split checks: ruff passed; compileall passed;
  Memory UI/observation scoped regression `4 passed, 73 deselected`
- Operations Tool Run result payload split checks: ruff passed; compileall
  passed; Tool Run artifact/detail/table regression `9 passed`
- Operations module overview section split checks: ruff passed; compileall
  passed; UI Operations scoped regression `26 passed`; diff whitespace check
  passed
- Operations LLM/Tool projection owner-call facts alignment checks: ruff
  passed; compileall passed; LLM/Tool read-model and projection diagnostics
  regression `7 passed`
- Operations action HTTP DTO split checks: ruff passed; compileall passed; UI
  HTTP/Operations observation/Tool/LLM read-model regression `85 passed`;
  architecture guard `18 passed`
- Operations HTTP stream payload split checks: focused interface ruff passed;
  compileall passed; Operations HTTP regression `26 passed`; runtime status
  regression `1 passed`
- Operations channel action route split checks: ruff passed; compileall
  passed; Operations action/channel/event HTTP regression `29 passed`
- Operations Channels contract row/table split checks: ruff passed; compileall
  passed; Channels UI/observation scoped regression `55 passed, 25 deselected`
- Operations Orchestration queue row split checks: ruff passed; compileall
  passed; Orchestration queue/UI/observation scoped regression `53 passed`
- Operations Orchestration queue row-value split checks: ruff passed;
  compileall passed; Orchestration queue/overview/UI scoped regression
  `7 passed, 24 deselected`
- Operations Orchestration observation metric split checks: ruff passed;
  compileall passed; Orchestration queue/projection/UI scoped regression
  `8 passed, 24 deselected`
- Operations Context Workspace source-read split checks: ruff passed;
  compileall passed; Context Workspace read-model/observation scoped regression
  `4 passed, 47 deselected`; UI Operations HTTP regression `26 passed`
- Operations LLM limiter queue split checks: ruff passed; compileall passed;
  LLM limiter/read-model/projection diagnostics regression `4 passed`
- Operations Events page source split checks: ruff passed; compileall passed;
  Events UI/observation scoped regression `20 passed, 60 deselected`
- Operations Events page runtime/recent fact split checks: ruff passed;
  compileall passed; Events UI scoped regression `6 passed, 20 deselected`;
  Events observation scoped regression `21 passed, 30 deselected`
- Operations Tool HTTP detail DTO split checks: ruff passed; compileall passed;
  Tool Operations HTTP scoped regression `4 passed, 22 deselected`
- Operations action audit summary split checks: ruff passed; compileall
  passed; action-audit scoped regression `4 passed, 45 deselected`
- Operations action dependency bundle checks: ruff passed; compileall passed;
  Operations UI HTTP regression `26 passed`; architecture/observation/UI
  regression `96 passed`
- Operations Tool page fact derivation split checks: ruff passed; compileall
  passed; Tool read-model/query regression `7 passed`
- Operations Tool page source/run facts split checks: ruff passed; compileall
  passed; Tool read-model/projection diagnostics regression `8 passed`; Tool UI
  scoped regression `4 passed, 22 deselected`
- Operations LLM page section split checks: ruff passed; compileall passed;
  LLM read-model/UI scoped regression `4 passed, 23 deselected`
- Operations Context Workspace node-status split checks: ruff passed;
  compileall passed; Context Workspace read-model/UI scoped regression
  `2 passed, 26 deselected`
- Operations Orchestration event-log label split checks: ruff passed;
  compileall passed; Orchestration event-log/UI scoped regression `5 passed`
- Operations Tool worker provider-limit section split checks: ruff passed;
  compileall passed; Tool provider/worker-detail scoped regression `4 passed`
- Operations Events health projection split checks: ruff passed; compileall
  passed; Events observation scoped regression `19 passed, 32 deselected`
- Operations/LLM error classification ownership checks: ruff passed; compileall
  passed; LLM error section regression `3 passed`
- Operations Skills usage table split checks: ruff passed; compileall passed;
  Operations observation Skills scoped regression `5 passed, 46 deselected`
- Operations Daemon module row split checks: ruff passed; compileall passed;
  Daemon UI scoped regression `4 passed, 22 deselected`
- Operations Daemon health/metric split checks: ruff passed; compileall
  passed; Daemon read-model/UI scoped regression `5 passed, 22 deselected`
- Operations Events module row split checks: ruff passed; compileall passed;
  Events UI scoped regression `6 passed, 20 deselected`
- Operations LLM provider warmup split checks: ruff passed; compileall passed;
  LLM provider/warmup scoped regression `3 passed, 1 deselected`
- Operations Tool metric value split checks: ruff passed; compileall passed;
  Tool metric/provider/readiness/scheduling/worker/run regression `22 passed`
- Operations Events recent projection split checks: ruff passed; compileall
  passed; Events UI scoped regression `6 passed, 20 deselected`; Events
  observation scoped regression `19 passed, 32 deselected`
- Operations Skills detail section split checks: ruff passed; compileall
  passed; Skills UI scoped regression `1 passed, 25 deselected`; Operations
  observation Skills scoped regression `5 passed, 46 deselected`
- Operations Tool Source provider backend row split checks: ruff passed;
  compileall passed; Tool Source/Tool read-model scoped regression `6 passed`
- Operations Tool Source provider backend label split checks: ruff passed;
  compileall passed; Tool Source/Tool/UI scoped regression
  `10 passed, 22 deselected`
- Operations Tool Source CLI row split checks: ruff passed; compileall passed;
  Tool Source/Tool/UI scoped regression `10 passed, 22 deselected`
- Operations observation store bucket split checks: ruff passed; compileall
  passed; Operations observation regression `51 passed`; Operations file-focus
  guard regression `2 passed`
- Operations Orchestration failure-row split checks: ruff passed; compileall
  passed; Orchestration observation scoped regression `6 passed, 45 deselected`;
  Orchestration UI/projection diagnostics scoped regression `4 passed`
- Operations Access target projection split checks: ruff passed; compileall
  passed; Access UI scoped regression `1 passed, 25 deselected`; Operations
  observation Access scoped regression `3 passed, 48 deselected`
- Operations current broad regression after Access/Orchestration follow-up:
  Operations observation/UI/action/presenter regression `85 passed`;
  architecture/port boundary regression `19 passed`; diff whitespace check passed
- Operations LLM invocation request-context runtime/provider split checks:
  ruff passed; compileall passed; LLM detail/provider-request/UI scoped
  regression `10 passed, 23 deselected`
- Operations LLM error fact item split checks: ruff passed; compileall
  passed; LLM error/detail/UI scoped regression `8 passed, 23 deselected`
- Operations LLM provider render label split checks: ruff passed; compileall
  passed; LLM provider-request/detail/UI scoped regression
  `7 passed, 23 deselected`
- Operations Tool worker detail summary/runtime section split checks: ruff
  passed; compileall passed; Tool worker/detail/UI scoped regression
  `7 passed, 22 deselected`
- Operations Tool page run selection split checks: ruff passed; compileall
  passed; Tool read-model/filter/UI scoped regression `11 passed, 22 deselected`
- Operations LLM page invocation set split checks: ruff passed; compileall
  passed; LLM read-model/filter/UI scoped regression `7 passed, 23 deselected`
- Operations Tool scheduling queue row split checks: ruff passed; compileall
  passed; Tool scheduling/read-model/UI scoped regression
  `10 passed, 22 deselected`
- Operations Skills action/chart split checks: ruff passed; compileall passed;
  Skills observation/UI scoped regression `6 passed, 71 deselected`
- Operations LLM run-context execution split checks: ruff passed; compileall
  passed; LLM read-model/table/UI scoped regression `7 passed, 23 deselected`
- Operations Orchestration runtime config projection split checks: ruff passed;
  compileall passed; Orchestration scoped regression `13 passed, 24 deselected`
- Operations Orchestration worker row split checks: ruff passed; compileall
  passed; Orchestration worker/UI scoped regression `8 passed, 24 deselected`
- Operations Channels payload formatting split checks: ruff passed; compileall
  passed; Channels observation/UI scoped regression `2 passed, 75 deselected`
- Operations LLM resolver label split checks: ruff passed; compileall passed;
  LLM resolver/read-model/UI scoped regression `8 passed, 23 deselected`
