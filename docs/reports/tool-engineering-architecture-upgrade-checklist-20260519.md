# Tool Engineering Architecture Upgrade Checklist 2026-05-19

本文档是 Tool 模块从“启动时扫描工具”升级为“Tool Source / Tool
Function Catalog / Tool Runtime / Tool Run Lifecycle”完整工程架构的施工清单。

目标不是补一层兼容壳，也不是把 Settings 做成代理中心；目标是让 Tool
模块成为工具来源、能力目录、治理策略和运行生命周期的 owner。Settings
通过 Tool application 完成治理操作，Access 提供外部凭证，Authorization
提供内部 ABAC，Operations 侧向观察运行事实。

## 冻结口径

- `tools/*/tool.yaml` 是内置 `local_package` / bundled OpenAPI source 的声明文件，
  不是整个 Tool Catalog 的唯一真相。
- Tool 模块拥有 `ToolSource`、`ToolFunction`、provider backend、tool policy 和
  `ToolRun` 生命周期。
- Source 负责声明和发现能力；Catalog reconcile 负责把能力稳定映射成
  `ToolFunction`。
- Settings 只作为治理入口和业务视图，通过 Tool / Access / Authorization / Agent
  application port 完成操作，不直接持有 Tool 真相。
- Access 只负责外部凭证、OAuth account、credential binding、readiness、secret
  resolve 和 audit；Tool runtime 不直接读取 `env:`、`file:`、raw token 或其他本地
  secret source。
- Authorization 只负责内部 ABAC / effect / permission policy，不和 Access 的外部凭证
  治理混淆。
- Operations 不直接调用 `/tools`、`/llms` 等模块 API 拼页面真相；Tool 运行事实通过事件和
  Tool query service 进入 `/operations/tool` read model。
- CLI source 不开放任意 shell；只开放已注册 CLI source 的受控 argv envelope、cwd/root
  policy、timeout、输出上限和 approval/readiness。CLI help 只能作为 guided exec
  的观察输入，不能自动解析并发布为 `ToolFunction`；稳定 CLI function 必须来自显式
  promoted 配置或后续受治理的人工/agent promotion 流程。
- Provider backend 默认挂在稳定 Tool Function 后面，例如
  `image_generate -> openai_codex | fal | local_sd`，不默认把每个 backend 暴露成新工具。
- Runtime handler 不持有 container、resolver、`SimpleNamespace` 或 owner module concrete
  service；跨模块能力必须在 app assembly / activation 阶段显式注入。
- 不接受最小迁移后长期双轨。旧 manual/register/discover 临时路径必须在 cutover 阶段删除或改名为明确测试辅助。

## 当前基线

- 内置工具来源：
  - `tools/*/tool.yaml`，由 `src/crxzipple/modules/tool/infrastructure/tool_packages.py`
    扫描。
  - `kind: local_package` 声明 local handlers、remote runtimes、sandbox runtimes。
  - `kind: openapi` 声明 OpenAPI spec、credentials 和 remote runtime。
- 运行态装配：
  - `src/crxzipple/app/assembly/tool.py` 构造 `LocalToolRuntimeRegistry`、
    `ToolDiscoveryRegistry`、`ToolRuntimeRegistry` 和 runtime gateway。
  - MCP source 来自 Settings materialized provider config，再通过 `tools/list` 动态发现。
  - 配置型 OpenAPI provider 来自 Settings materialized provider config。
  - 配置型 CLI source 已进入 Tool-owned source/function catalog，运行时通过受控
    guided functions 调用 Process application service。
  - 递归 `tool.json` filesystem discovery、process-local 注册和旧 provider discover
    入口已退场；local 工具只能作为 `local_package` source 进入 catalog。
- 治理现状：
  - Tool Function enablement 已由 Tool owner catalog 持有，Settings 不再 materialize
    Tool enablement。
  - Access credential requirement 已能从 OpenAPI security scheme 和 native/local
    manifest 投影。
- 已收口：
  - `ToolSource` / `ToolFunction` catalog 已持久化并成为 `/tools` list/run 真相。
  - `list_tools()`、runtime pool 和 tool submission 不再从 runtime registry 或 legacy
    discovery 临时拼接。
  - Source CRUD、discovery run、schema hash、stale/deprecated、enablement/trust/policy
    已回到 Tool owner application。
  - CLI source 已支持 guided function、credential injection、stdout/stderr 事件、
    promoted function 和 Settings 实时 test console。
  - Provider backend 已作为稳定 Tool Function 后端治理并可进入运行 metadata。

## 2026-05-19 首轮施工记录

- 已组织 agent 完成三条并行切片：
  - P1 Tool catalog 持久化：新增 `ToolSource`、`ToolFunction`、
    `ToolProviderBackend` domain model、repository port、SQLAlchemy model/repository、
    Alembic `0051_tool_source_function_catalog`。
  - P3/P4 application contract：新增 `ToolFunctionCandidate`、
    `ToolProviderBackendCandidate`、`ToolSourceDiscoveryResult`、
    `ToolFunctionCatalogRecord` 和 `ToolCatalogReconcileService`。
  - Settings/API/Operations 接入审查：确认前端与 Operations 暂缓大改，避免在
    P1-P4 完整落库前制造第二套真相。
- 主线程已补齐 P1/P4 对接：新增 SQLAlchemy-backed
  `ToolFunctionCatalogRepository` adapter，使 reconcile 结果可完整写入
  `tool_functions`，并保留治理字段、runtime/access requirement、stale/deprecated
  时间戳。
- 历史状态：当时 runtime pool、`/tools`、Settings Tool 页面和 Operations Tool
  projection 仍走旧查询/发现路径；该缺口已被后续 P2/P5/P11/P12/P13 关闭。
- 已验证：
  - `PYTHONPATH=src pytest -q tests/unit/test_tool_source_catalog_persistence.py tests/unit/test_tool_catalog_reconcile.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_tool_catalog.py tests/unit/test_tool_execution.py tests/unit/test_tool_background.py tests/unit/test_tool_settings_integration.py`
  - `PYTHONPATH=src python -m ruff check ...`
  - 空 SQLite 库 `python -m crxzipple.main db upgrade head`

## 2026-05-19 第二轮施工记录

- 已新增 Tool-owned source service：
  - `ToolSourceCommandService`：upsert、disable、restore、delete、sync source。
  - `ToolSourceQueryService`：list/get source。
  - sync 流程：source upsert -> discovery adapter -> candidate reconcile -> `tool_functions`
    落库。
- 已新增 bundled package catalog adapter：
  - `tools/*/tool.yaml` 会被解释为 `bundled.local_package.<namespace>` 或
    `bundled.openapi.<namespace>` source。
  - local package 只产出 `ToolFunctionCandidate`，不修改 runtime registry。
  - bundled OpenAPI source 通过现有 OpenAPI parser 产出 candidates。
- 已在 API / CLI_ADMIN app activation 中增加幂等 backfill：
  - app 启动时内置 source 先写入 `tool_sources`。
  - discovery/reconcile 后写入 `tool_functions`。
  - 旧 runtime pool 暂未切换，仍由 `LocalToolRuntimeRegistry`/runtime registry 执行。
- 已验证：
  - `PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py tests/unit/test_tool_source_catalog_persistence.py tests/unit/test_tool_catalog_reconcile.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_tool_catalog.py tests/unit/test_tool_execution.py tests/unit/test_tool_background.py tests/unit/test_tool_settings_integration.py`
  - `PYTHONPATH=src python -m ruff check ...`
  - API target 启动 smoke：13 个 bundled source、48 个 function 落库。

## 2026-05-19 第三轮施工记录

- Tool run 提交路径已开始读取持久化 `ToolFunction`：
  - `_prepare_run_request` 会按 `tool_id -> tool_functions.function_id` 解析 catalog target。
  - source/function 不存在、source disabled/error/deleted、function stale/deprecated/disabled
    时拒绝提交。
  - 新 `ToolRun` 会记录 `function_id`、`function_revision`、`source_id`、
    `source_revision`、`schema_hash`。
- Worker 执行前会再次读取 catalog target：
  - 排队后如果 source/function 状态发生变化，worker 不再直接调用旧 runtime handler。
  - 失败会走既有 run failure/dispatch failure 路径。
- Tool run lifecycle 事件补充了 function/source/revision/schema hash 字段，Operations 后续可直接
  解释 run 对应的 catalog 版本。
- activation backfill 扩展到 API / CLI_ADMIN / ORCHESTRATION_EXECUTOR / TOOL_WORKER /
  TEST，保证各执行目标都有本地 bundled catalog 基线。
- 提交路径已取消全量 `resolved_tool_map()` 预构建；catalog-backed tool run 直接按
  `tool_functions.function_id` 读取持久化 function，并由 `ToolFunction.handler_ref`
  反建执行态 `Tool`。
- Worker / background scheduler 对 catalog-backed run 使用 `ToolFunction` 反建的 runtime
  ref 做并发分组和执行准备，不再为这类 run 触发旧 discovery/resolve 路径。
- 反建执行态 `Tool` 时补齐 input schema、credential requirements、runtime requirements、
  required effects、execution policy/support、definition origin 和 runtime key，避免持久化
  catalog 丢失 background/thread/process 等执行能力。
- 已验证：
  - `PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py tests/unit/test_tool_source_catalog_persistence.py tests/unit/test_tool_catalog_reconcile.py tests/unit/test_tool_catalog.py tests/unit/test_tool_execution.py tests/unit/test_tool_background.py tests/unit/test_tool_settings_integration.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_tool_http.py tests/unit/test_tool_cli.py`
  - `PYTHONPATH=src python -m ruff check ...`（source files）

## 2026-05-19 第四轮施工记录

- Tool runtime 查询面开始读取持久化 catalog：
  - `list_tools()` / `list_enabled_tools()` 从 active `ToolSource` + active
    `ToolFunction` 构建运行可见工具列表。
  - `get_tool()`、`list_tools()` 和 tool submission 的最终形态是 catalog-only；
    不存在 catalog record 的工具不可见、不可执行。
  - `list_tools()` 不触发 provider discovery，避免页面/接口查询制造运行时扫描和目录真相漂移。
- 递归 `tool.json` 热发现最终已退场；本地扩展必须迁入 `local_package` source。
- 已验证：
  - `PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py tests/unit/test_tool_source_catalog_persistence.py tests/unit/test_tool_catalog_reconcile.py tests/unit/test_tool_catalog.py tests/unit/test_tool_execution.py tests/unit/test_tool_background.py tests/unit/test_tool_settings_integration.py tests/unit/test_tool_http.py tests/unit/test_tool_cli.py tests/unit/test_tool_providers.py tests/unit/test_openai_image_tool.py tests/unit/test_tool_workspace.py`
  - `PYTHONPATH=src python -m ruff check ...`（source files）

## 2026-05-19 第五轮施工记录

- 配置型 MCP/OpenAPI provider 已物化为 Tool-owned source catalog：
  - Settings/bootstrap 中的 OpenAPI provider 形成
    `configured.openapi.<provider>` `ToolSource(kind=openapi)`。
  - Settings/bootstrap 中的 MCP provider 形成
    `configured.mcp.<provider>` `ToolSource(kind=mcp)`。
  - 新增 `ToolConfiguredProviderDiscoveryAdapter`，OpenAPI 从 spec 产出
    `ToolFunctionCandidate`，MCP 从 `tools/list` 产出 `ToolFunctionCandidate`。
- 运行列表和执行现在能通过持久化 `ToolFunction` 解释配置型 provider 工具：
  - OpenAPI/MCP `ToolFunction.handler_ref` 保存原 runtime key。
  - worker 执行时使用该 runtime key 命中现有 remote runtime registry。
  - OpenAPI security scheme 的 credential requirements 继续由 OpenAPI parser 自动投影到
    function catalog。
- 配置型 MCP/OpenAPI runtime handler 激活已从直接读取 bootstrap config 改为读取 active
  `ToolSource`：
  - `tool.activate_configured_provider_runtimes` activation task 从
    `ToolSourceQueryService` 读取 `kind=openapi|mcp` source。
  - `ToolFunction.metadata` 持久化 OpenAPI operation / MCP definition payload。
  - `activate_configured_provider_runtimes()` 根据 active source + active function metadata
    注册 remote runtime handler，不再在 activation 阶段重读 OpenAPI spec 或执行 MCP
    `tools/list`。
  - 配置型 provider 工具通过 `ToolSource/ToolFunction` 出现在 `/tools` 和 `tool list`。
- Source discovery 已有 Tool-owned history：
  - 新增 `tool_source_discovery_runs`，每次实际 discovery 都记录 source revision、config hash、
    status、function/backend 数量、错误和 metadata。
  - `ToolSourceQueryService.list_discovery_runs()` 提供查询面。
  - `/tools/sources`、`/tools/sources/{source_id}/refresh|disable|restore`、
    `/tools/sources/{source_id}/discovery-runs` 暴露 source 治理入口。
  - CLI 增加 `tool sources`、`tool source-history`、`tool source-refresh`、
    `tool source-disable|source-restore|source-delete`。
- 当轮剩余尾巴已关闭：
  - Settings Tool UI 已接入 source list/detail、refresh、disable/restore、delete、
    discovery history、source create/update 抽屉和测试运行入口。
  - 启动 sync 仍会 refresh configured source；这属于 source policy 后续优化，不是
    catalog cutover 阻塞项。
- 已验证：
  - `PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py tests/unit/test_tool_source_catalog_persistence.py tests/unit/test_tool_catalog_reconcile.py tests/unit/test_tool_catalog.py tests/unit/test_tool_execution.py tests/unit/test_tool_background.py tests/unit/test_tool_settings_integration.py tests/unit/test_tool_http.py tests/unit/test_tool_cli.py tests/unit/test_tool_providers.py tests/unit/test_openapi_access.py tests/unit/test_openai_image_tool.py tests/unit/test_tool_workspace.py`
  - `PYTHONPATH=src python -m ruff check ...`（source files）
  - `cd frontend && npm run typecheck`
  - `cd frontend && npm run build`

## 2026-05-19 第六轮施工记录

- Tool owner API 补齐 Source create/update：
  - `ToolSourceCommandService.create_source()` / `update_source()` 只接受 configured
    OpenAPI/MCP source。
  - create/update 只写 source 治理配置，不触发 discovery，不写
    `tool_source_discovery_runs`。
  - bundled package source 明确拒绝 UI/CLI 创建或修改，避免覆盖内置 package loader 真相。
- Tool owner API 补齐 Function enable/disable：
  - 新增 `ToolFunctionCommandService.set_function_enabled()`。
  - Function enabled 是用户治理字段；source refresh/reconcile 不覆盖该字段。
  - `/tools/functions`、`/tools/functions/{id}`、
    `/tools/functions/{id}/enable|disable` 已接入。
  - CLI 增加 `tool functions`、`tool function-enable|function-disable`。
- Settings Tool 页面已调用真实 Tool owner API：
  - 页面加载 `/tools/functions` 识别 source-managed functions。
  - 选中 source-managed tool 时可启停对应 `ToolFunction`。
  - process-local/manual/system runtime tools 保持只读，不走 Settings proxy。
- 已验证：
  - `PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py tests/unit/test_tool_http.py tests/unit/test_tool_cli.py`
  - `PYTHONPATH=src python -m ruff check src/crxzipple/modules/tool/application/source_service.py src/crxzipple/modules/tool/application/__init__.py src/crxzipple/app/keys.py src/crxzipple/app/assembly/tool.py src/crxzipple/modules/tool/interfaces/http.py src/crxzipple/modules/tool/interfaces/cli.py tests/unit/test_tool_source_service.py tests/unit/test_tool_cli.py`
  - `cd frontend && npm run typecheck`
  - `cd frontend && npm run build`

## 2026-05-19 第七轮施工记录

- Settings Tool 页面补齐 Source create/update UI：
  - 新增 `New Source` 入口和 Source detail `Edit` 操作。
  - 表单收进右侧抽屉，不常驻首屏；只支持当前 Tool owner API 已验证的 configured
    OpenAPI/MCP source。
  - 保存调用 `POST /tools/sources` / `PUT /tools/sources/{source_id}`，只写 Source 配置，
    不自动 discovery；用户仍需显式 Refresh Source。
  - 内置 bundled source、unsupported source 仍保持只读，避免覆盖 Tool package loader 真相。
- Settings Tool 页面补齐 Test Run 面板：
  - 参数表单来自 Tool owner 返回的 `parameters`，按 string/number/boolean/object/array
    渲染输入。
  - 执行目标来自 Tool owner 返回的 `execution_support`，提交调用
    `POST /tools/{tool_id}/runs`。
  - 运行结果在当前面板展示 run id、target、attempt、result/error，并刷新 Recent Runs。
- Owner Mutations 区过期的 “Source edit form is a follow-up” 文案已移除，改为真实
  source create/edit 操作入口；Manual Run 占位按钮改为跳转 Test Run 面板。

## 2026-05-19 第八轮施工记录

- Tool owner API 补齐 Function policy 治理：
  - 新增 `ToolFunctionCommandService.update_function_policy()`。
  - `PUT /tools/functions/{function_id}/policy` 可更新 `trust_policy`、
    `approval_policy`、`credential_binding_overrides` 和
    `required_effect_overrides`。
  - `ToolFunctionResponse` 现在返回上述治理字段，Settings 不再需要猜测或绕路读底层。
  - CLI 增加 `tool function-policy`，用于脚本化设置 Function policy。
- Settings Tool 页面接入 Function Governance：
  - UI 暴露 Trust Level、Approval Mode、Requires Approval、Effect Overrides、
    Credential Overrides 常用字段，不要求用户直接编辑 JSON。
  - 保存调用 Tool owner endpoint，source refresh/reconcile 后 policy 字段仍会保留。
- 已验证：
  - `PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py tests/unit/test_tool_http.py tests/unit/test_tool_cli.py`
  - `PYTHONPATH=src python -m ruff check src/crxzipple/modules/tool/application/source_service.py src/crxzipple/modules/tool/interfaces/http.py src/crxzipple/modules/tool/interfaces/cli.py tests/unit/test_tool_source_service.py tests/unit/test_tool_cli.py`
  - `cd frontend && npm run typecheck`
  - `cd frontend && npm run build`
  - Playwright smoke：Settings Tool 页面保存 `echo` Function Governance 成功。

## 2026-05-19 第九轮施工记录

- Access credential requirement catalog 改为读取 Tool owner 的 function catalog：
  - 修复 `ToolSourceQueryService` 返回 `ToolFunctionCatalogRecord` 时丢失
    `credential_requirements` 的问题。
  - `/ui/access` 现在通过 Tool source query service 读取 active ToolFunction 的
    credential requirements，并投成 Access consumer binding read model。
  - Settings 写入的 credential binding 与 Tool owner requirement 按
    `consumer_module + consumer_id` 合并，绑定后不再出现一条 Tool requirement 和一条
    Settings requirement 的重复视图。
  - Tool function 的 `credential_binding_overrides` 会参与 Access requirement binding
    解析，保持 Tool policy 对凭证槽位的治理权。
- Settings Tool 页面 credential binding selector 改为只展示兼容项：
  - 过滤 status 非 active/ready/valid 的 binding。
  - 过滤 credential kind 不匹配的 binding。
  - 当 binding metadata 声明 provider 时，按 requirement provider 做硬匹配。
- 已验证：
  - `PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py tests/unit/test_ui_access_http.py tests/unit/test_access_read_models.py tests/unit/test_access_actions.py`
  - `PYTHONPATH=src pytest -q tests/unit/test_access_policies.py tests/unit/test_access_architecture_docs.py`
  - `PYTHONPATH=src python -m ruff check src/crxzipple/modules/tool/application/source_service.py src/crxzipple/modules/access/application/query.py src/crxzipple/modules/access/interfaces/ui_http.py tests/unit/test_tool_source_service.py tests/unit/test_ui_access_http.py`
  - `cd frontend && npm run typecheck`
  - `cd frontend && npm run build`

## 2026-05-19 第十轮施工记录

- Settings Tool enablement 旧真相路径已切断：
  - 删除 `ToolEnablementService`、`ToolEnablementDiscoveryGateway`、
    `ToolEnablementRuntimeGateway` 和 `ToolEnablementTarget`。
  - 删除 `AppKey.TOOL_ENABLEMENT_SERVICE`，Tool runtime/discovery gateway 不再被 Settings
    enablement 包裹。
  - 删除 `SettingsEffectiveConfigMaterializer.tool_enablements()` 和共享
    `ToolEnablementConfig`。
  - Tool Function 的 enable/disable 只通过 Tool owner command service 写入
    `tool_functions.enabled`。
- 已补架构防回潮测试：
  - Settings materializer 不再暴露 `tool_enablements`。
  - app/tool/settings/shared 生产代码不能重新出现 `ToolEnablementService`、
    `ToolEnablementConfig`、`TOOL_ENABLEMENT_SERVICE`。
- 已验证：
  - `PYTHONPATH=src pytest -q tests/unit/test_tool_settings_integration.py tests/unit/test_settings_materialization.py tests/unit/test_settings_contracts.py tests/unit/test_app_assembly_architecture.py`
  - `PYTHONPATH=src python -m ruff check src/crxzipple/modules/tool/application/settings_integration.py src/crxzipple/app/assembly/tool.py src/crxzipple/app/keys.py src/crxzipple/modules/settings/application/materialization.py src/crxzipple/shared/settings.py tests/unit/test_tool_settings_integration.py tests/unit/test_settings_materialization.py tests/unit/test_settings_contracts.py tests/unit/test_app_assembly_architecture.py`

## 2026-05-19 第十一轮施工记录

- Agent Profile 的 Tool 弱绑定已退场：
  - `AgentRuntimePreferences` 现在会丢弃 `tool_ids` / `tools` / `skill_ids` /
    `skills`，Agent home config、HTTP update、Settings bootstrap 都不能再把 Tool catalog
    selection 写成 Agent truth。
  - Agent resolution 不再从 Agent attrs 读取 tool selection；它从 Authorization owner
    policies 解析 agent 的 tool/effect grant，再通过 Tool query service 投影“已预授权工具”。
  - Settings Agent Profile 页面移除 Tool `Use` 选择框，不再随 Agent profile 保存
    `tool_ids`；Tool Access 面板只做 Authorization grant/revoke 操作。
- 已补验证：
  - Agent settings integration 测试覆盖 runtime attrs 清理。
  - Agent HTTP resolution 测试覆盖 tool access/readiness 来自 Authorization grant +
    Tool owner catalog，而不是 Agent attrs。
- 已验证：
  - `PYTHONPATH=src pytest -q tests/unit/test_agent_settings_integration.py tests/unit/test_agent_http.py`
  - `cd frontend && npm run typecheck`
  - `cd frontend && npm run build`
  - `PYTHONPATH=src python -m ruff check src/crxzipple/modules/agent tests/unit/test_agent_settings_integration.py`

## 2026-05-20 第十二轮施工记录

- Tool execution gate 的 credential/runtime readiness 失败改为结构化返回：
  - `ToolExecutionNotAllowedError` 保留人可读 message，同时携带稳定 `code`、
    `category`、`tool_id` 和 `readiness` payload。
  - `/tools/{tool_id}/runs` 遇到缺失 Access credential、OAuth account 或 runtime daemon
    时返回 `409`，`detail` 直接包含 Access/runtime readiness 结构，不再只给字符串。
  - HTTP 测试覆盖缺失 env credential、缺失 OAuth account、缺失 runtime daemon 三条拦截路径，
    且确认被拦截时不会创建 ToolRun。
- 已验证：
  - `PYTHONPATH=src pytest -q tests/unit/test_tool_http.py tests/unit/test_openai_image_tool.py tests/unit/test_access.py tests/unit/test_access_actions.py`
  - `ruff check src/crxzipple/modules/tool/domain/exceptions.py src/crxzipple/modules/tool/application/submission_service.py src/crxzipple/modules/tool/interfaces/http.py`

## 2026-05-20 第十三轮施工记录

- Tool catalog execution gate 的状态拦截改为结构化返回：
  - catalog function disabled 返回 `tool_function_disabled`，并携带 `category`、
    `function_id`、`source_id`、`function_status` 和 `enabled`。
  - stale/deprecated function 返回 `tool_function_not_executable`，前端可直接根据
    `function_status` 展示原因。
  - source missing / disabled / deleted 返回 source 维度结构化 payload。
  - HTTP authorization guard 在 active query 找不到工具时不再抢先抛未处理异常，交给
    execution gate 返回 404 或 catalog 状态错误。
- 已验证：
  - `PYTHONPATH=src pytest -q tests/unit/test_tool_http.py tests/unit/test_openai_image_tool.py tests/unit/test_auth_http.py`
  - `ruff check src/crxzipple/modules/tool/application/submission_service.py src/crxzipple/modules/tool/domain/exceptions.py src/crxzipple/modules/tool/interfaces/http.py src/crxzipple/interfaces/authorization.py`

## 2026-05-20 第十四轮施工记录

- credential/env fallback 清理项复核并闭合：
  - handler 侧扫描未发现 API key/token/secret 直读 env fallback；`openai_image`
    只通过注入的 `credential_provider` 向 Access 解析 `openai-api-key` binding。
  - OpenAPI runtime 只接受 credential binding id，由 Access provider 解引用后注入
    header/query/cookie。
  - Tool manifest 与 Settings provider config 已拒绝 `env:`、`file:`、
    `codex_auth_json` 和 `auth_ref` 等直连凭证来源。
- 已验证：
  - `PYTHONPATH=src pytest -q tests/unit/test_tool_access_architecture.py tests/unit/test_tool_settings_integration.py tests/unit/test_openapi_access.py tests/unit/test_openai_image_tool.py`
  - `ruff check tests/unit/test_tool_access_architecture.py src/crxzipple/modules/tool/infrastructure/runtimes/openapi_remote.py tools/openai_image/local.py src/crxzipple/modules/tool/infrastructure/tool_packages.py src/crxzipple/modules/tool/application/settings_integration.py`

## 2026-05-20 第十五轮基线扫描记录

- runtime/discovery 即时拼接路径：
  - 当时仍存在 `ToolCatalogService.discover_tools()`、旧 local discovery alias、
    `discover_resolution_specs()` 和 `refresh_local_extension_discovery()`；后续第十八轮已删除
    runtime resolution 中的隐式 discovery fallback。
  - `LocalToolRuntimeRegistry` 仍承担 runtime handler registry，同时仍有 legacy/debug
    discovery provider 可显式输出 `ToolSpec`。
  - app activation 侧已走 `ToolPackageApplyContext` / `activate_tool_packages(...)`，内置
    package 装载路径已进入 source/function catalog。
- Settings `tool-catalog` 当前实际控制字段：
  - Source：create/update、refresh、disable/restore/delete、discovery history。
  - Function：list/detail、enable/disable、trust policy、approval policy、
    credential binding overrides、required effect overrides。
  - Test Run：构造 input schema 表单并调用 Tool run endpoint；credential binding 通过
    Access action 绑定。
  - 旧 discover/provider 调试入口已删除；治理入口只保留 source/function/run/readiness。
- Tool HTTP/CLI API 分类：
  - owner API：`/tools/sources*`、`/tools/functions*`、function policy、source refresh 与
    source lifecycle。
  - execution/query API：`/tools/{tool_id}/runs`、run list/get/cancel/retry、
    readiness、workers prune。
  - 已删除入口：旧 local discovery alias、旧 HTTP/CLI provider discover 命令。
- `tools/*/tool.yaml` 使用情况：
  - 当前内置 13 个 manifest：9 个 `local_package`，4 个 `openapi`。
  - OpenAPI manifest 使用 binding id：`brave-search-api-key`、`itick-api-token`；
    open-meteo 两个 source 无 credential。
  - local package 中 browser 声明 `daemon-group:browser` runtime requirement；
    openai_image 声明 `credential_provider` 依赖与 Access credential requirements。
- Filesystem extension 使用情况：
  - 递归 manifest discovery 不再是 Tool runtime 入口；相关测试夹具只保留为退役行为验证。

## 2026-05-20 第十六轮施工记录

- Local Tool handler factory 退掉小号 service locator：
  - `ToolPackageApplyContext` 仍由 framework/assembly 层解析 manifest dependency bindings；
    但传给 handler factory 的参数改为 typed deps dataclass，不再把
    `ToolHandlerFactoryDeps.service/require_service/setting` 暴露给 `tools/*/local.py`。
  - `ToolHandlerFactoryDeps` 只保留 dependency data；`tool_packages` 根据 handler factory
    入参类型自动从 declared dependencies 构造 typed deps。
  - 已迁移 memory、workspace、command、mobile、sessions、skills、openai_image、browser
    local handlers，删除 `require_service(...)` fallback。
  - 架构测试加严：Tool handler/runtime 路径禁止 `AppContainer`、`SimpleNamespace`、
    `PortResolver`、`ToolHandlerFactoryDeps`、`require_service`、`container.*`。
- 已验证：
  - `PYTHONPATH=src pytest -q tests/unit/test_module_lifecycle_architecture.py tests/unit/test_tool_providers.py tests/unit/test_openai_image_tool.py tests/unit/test_tool_http.py`
  - `ruff check src/crxzipple/modules/tool/application/activation.py src/crxzipple/modules/tool/infrastructure/tool_packages.py tests/unit/test_module_lifecycle_architecture.py tools/memory/local.py tools/workspace/local.py tools/command/local.py tools/mobile/local.py tools/sessions/local.py tools/skills/local.py tools/openai_image/local.py tools/browser/local.py`

## 2026-05-20 第十七轮守卫记录

- P0 架构守卫补齐：
  - 新增测试确认 Tool module 生产代码不直接使用 Settings materializer；app assembly 中
    仅允许 `tool_providers()` / `tool_roots()` 生成 bootstrap source seed，不允许
    Settings materializer 决定 runtime catalog truth。
  - 新增测试确认 Tool submission path 读取 `uow.tool_functions.get(data.tool_id)` 并从
    `ToolFunction` 构建 execution target，不允许 runtime registry fallback。
- 已验证：
  - `PYTHONPATH=src pytest -q tests/unit/test_app_assembly_architecture.py tests/unit/test_tool_access_architecture.py`
  - `ruff check tests/unit/test_app_assembly_architecture.py tests/unit/test_tool_access_architecture.py`

## 2026-05-20 第十八轮施工记录

- Local runtime registry / source truth 收口：
  - `LocalToolCatalog` 正式改名为 `LocalToolRuntimeRegistry`，
    `AppKey.TOOL_LOCAL_CATALOG` 改为 `TOOL_LOCAL_RUNTIME_REGISTRY`，避免继续把 handler
    registry 误读成工具 catalog 真相。
  - App startup 不主动扫描 filesystem manifest；后续 cutover 已删除该显式 debug 路径。
  - `ToolCatalogService.resolve_tool()` 不再调用 `discover_resolution_specs()`，并删除
    `refresh_local_extension_discovery()`；最终执行路径只走 source/function catalog。
  - `tool.activate_packages` 读取 active `ToolFunction.handler_ref` 后再注册 local handlers；
    disabled/stale/deleted function 不再进入 local runtime registry。
  - 旧 local discovery alias 已从 HTTP/CLI/application surface 删除；跨命令执行不再依赖
    上一次 discovery 的进程内 handler side effect。
  - Filesystem discovery provider 后续已删除，不再提供 definition/candidate 视图。
  - `LocalToolRuntimeRegistry.replace_provider_tools()` 删除，runtime registry 只保留显式
    activation/test 注册与 handler lookup。
  - `ToolApplicationService.register()` / `ToolCatalogService.register()` 删除；后续 cutover
    已继续删除 process-local 临时注册 API，避免把测试/benchmark overlay 误当生产
    catalog 治理入口。
  - 新增 `ToolRuntimePoolService`，生产 runtime pool 从 active `ToolSource` + active
    `ToolFunction` 构建；`ToolOrchestrationPortAdapter.list_enabled_tools()` 改为读取
    runtime pool。后续 cutover 已删除 TEST overlay 参数。
  - Runtime pool 接收 caller/agent/session/workspace context，并在池内过滤
    function/source enabled/status、Access readiness 和 daemon/runtime readiness。
    Authorization effect policy 与 approval policy 继续由 Orchestration `ToolResolver`
    在池之后根据 run subject/context 判断，不反向塞入 Tool module。
  - Skills local tool 只依赖 `skill_manager`，不再把 local runtime registry 暴露给
    handler factory。
  - 新增架构守卫：禁止 runtime resolution 重新引入 discovery fallback 或 startup
    filesystem discovery。
  - 已验证：
    `PYTHONPATH=src pytest -q tests/unit/test_tool_access_architecture.py tests/unit/test_tool_catalog.py tests/unit/test_tool_execution.py tests/unit/test_tool_background.py tests/unit/test_tool_http.py tests/unit/test_tool_cli.py tests/unit/test_tool_providers.py tests/unit/test_openai_image_tool.py tests/unit/test_orchestration_tools.py tests/unit/test_orchestration_approval.py tests/unit/test_orchestration_access_resolution.py tests/unit/test_app_assembly_module_local.py tests/unit/test_app_assembly_targets.py`
    （209 passed）。
  - 已验证：
    `ruff check src/crxzipple/modules/tool/application/runtime_pool_service.py src/crxzipple/modules/tool/application/service_graph.py src/crxzipple/modules/tool/application/services.py src/crxzipple/modules/tool/application/__init__.py src/crxzipple/app/assembly/tool.py src/crxzipple/modules/orchestration/application/tool_resolver.py src/crxzipple/modules/orchestration/application/ports/tool.py src/crxzipple/modules/orchestration/infrastructure/adapters/tool.py src/crxzipple/modules/tool/application/ports/query.py tests/unit/test_tool_access_architecture.py tests/unit/test_orchestration_access_resolution.py`
    （All checks passed）。
  - 已验证：`cd frontend && npm run typecheck`。

## 2026-05-20 第十九轮施工记录

- Tool source/function lifecycle facts 纳入事件契约：
  - 新增 `tool.source.created|updated|disabled|restored|deleted|discovery_completed|discovery_failed`。
  - 新增 `tool.function.created|updated|stale|deprecated|enabled|disabled|policy_updated`。
  - `EventDefinitionRegistry` 将这些事件注册为 Tool-owned persistent direct events，
    Operations 与 trace read model 都能按同一契约解释。
- Tool owner application 开始在提交事务时发布 source/function 事实：
  - Source create/update/status/discovery 通过 `ToolSourceCommandService` 记录事件并由 UoW
    统一发布。
  - Catalog reconcile 产生的 function created/updated/stale/deprecated 事件接入同一 UoW，
    不再只停留在 reconcile result 内部。
  - Function enable/disable/policy update 由 `ToolFunctionCommandService` 发布对应事件。
- Operations observer/read model 订阅范围补齐：
  - `operations_observer_event_names()` 覆盖 Tool source/function/run/worker/assignment 事实。
  - `/operations/tool` 的最近事件读取补入 source/function named topics，页面可从事件侧向观察
    source discovery、function stale/deprecated 与治理变更。
- 已验证：
  - `PYTHONPATH=src pytest -q tests/unit/test_events.py tests/unit/test_tool_source_service.py tests/unit/test_tool_catalog_reconcile.py tests/unit/test_operations_observation.py tests/unit/test_operations_read_model_boundaries.py`
    （68 passed）。
  - `ruff check src/crxzipple/shared/event_contracts.py src/crxzipple/modules/tool/application/source_service.py src/crxzipple/modules/operations/application/runtime.py src/crxzipple/modules/operations/application/read_models/tool.py tests/unit/test_events.py tests/unit/test_tool_source_service.py`
    （All checks passed）。

## 2026-05-20 第二十轮施工记录

- 复核 `/operations/tool` 已是 projection-first：
  - HTTP 接口通过 `operations_projection_store.get_projection(module="tool", kind="page")`
    读取页面投影，缺失投影时返回 503 提示启动/运行 operations-observer。
  - Tool run 主表和 detail 也从 `kind=table/tool_run_detail` projection 读取。
- Tool Operations read model 补齐 source/function catalog 运维视图：
  - `ToolQueryServiceAdapter` 接入 Tool owner 的 Source query service，但仍通过
    Operations read model port 使用，不访问 discovery provider 或 Settings source config。
  - `/operations/tool` 新增 `source_health`、`discovery_failures`、
    `function_catalog`、`provider_backend_health`、`cli_process_health`。
  - 前端 contract/fixture/i18n 与 Tool 主表 tab 增加 `Sources`，用于展示 source health。
  - Tool lifecycle events 显示上优先运行/assignment/worker 事实，避免启动 catalog sync
    事件把运行事件挤出首屏。
- 已验证：
  - `PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py tests/unit/test_operations_read_model_boundaries.py tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_operations_tool_page_uses_tool_runtime_state tests/unit/test_app_assembly_targets.py tests/unit/test_tool_source_service.py tests/unit/test_events.py`
    （73 passed，分两次运行）。
  - `ruff check ...` 覆盖本轮 Python 改动（All checks passed）。
  - `cd frontend && npm run typecheck`。
  - `cd frontend && npm run build`。
  - 本地 `vite preview --port 4174` 后运行 `cd frontend && npm run audit:operations-layout`
    （Operations layout audit passed）。

## 目标模型

```text
ToolSource
  -> DiscoveryAdapter
  -> ToolFunctionCandidate
  -> CatalogReconcileService
  -> ToolFunction
  -> RuntimeToolPool
  -> ToolRun
  -> Events
  -> Operations Projection
```

### ToolSource

字段建议：

- `source_id`
- `kind`: `local_package | mcp | openapi | cli | provider_backend`
- `display_name`
- `description`
- `config`
- `credential_requirements`
- `runtime_requirements`
- `status`: `active | disabled | error | deleted`
- `revision`
- `config_hash`
- `last_discovered_at`
- `last_discovery_status`
- `created_at`
- `updated_at`

### ToolFunction

字段建议：

- `function_id`
- `source_id`
- `stable_key`
- `name`
- `display_name`
- `description`
- `input_schema`
- `runtime_kind`: `local | remote | sandbox | mcp | openapi | cli | provider_backend`
- `handler_ref`
- `capability_ids`
- `credential_requirements`
- `runtime_requirements`
- `required_effect_ids`
- `safety_level`
- `execution_support`
- `enabled`
- `trust_policy`
- `approval_policy`
- `schema_hash`
- `status`: `active | stale | deprecated | disabled | deleted`
- `created_at`
- `updated_at`

### ToolProviderBackend

字段建议：

- `backend_id`
- `source_id`
- `capability`: `image_generation | web_search | speech | media | browser | custom`
- `display_name`
- `credential_requirements`
- `runtime_ref`
- `priority`
- `enabled`
- `status`

Provider backend 通常不直接生成模型可见的 Tool Function，而是被稳定函数引用。

### ToolRun

现有 `ToolRun` 继续作为执行生命周期 aggregate。升级重点是让 run 的 target 引用稳定
`ToolFunction`，并保存当次运行的 `function_revision/schema_hash/source_revision`，便于历史解释。

## Source 归一规则

### local_package

- `tools/<namespace>/tool.yaml` 只声明 source/package。
- 一个 package 可以产生多个 `ToolFunctionCandidate`。
- Handler 只能通过 manifest-driven typed deps 接收依赖。
- 缺少 required internal dependency 时 app activation fail-fast。
- 缺少外部 credential/runtime readiness 时 source/function 可存在，但 execution gate 拒绝排队并返回 readiness 问题。

### MCP

- Source config 保存 MCP server transport、command/url、env binding ref、timeout、effect defaults。
- Discovery 通过 `tools/list` 产出 candidates。
- Stable key 使用 `mcp.<source_id>.<tool_name>`。
- Runtime 通过 `tools/call` 执行。
- Source disabled 时，runtime pool 不暴露其 functions，但历史 run 保留解释能力。

### OpenAPI

- Source config 保存 spec location、base URL、timeout、security binding defaults。
- Discovery 解析 paths/operations/security schemes。
- Stable key 优先使用 `operationId`，缺失时使用 method + normalized path hash。
- OpenAPI `securitySchemes` 自动生成 credential requirements。
- Runtime 执行时只通过 Access binding id 解析 credential。

### CLI

- Source config 保存 executable、allowed subcommands/argv policy、workspace policy、timeout、
  output limit、streaming mode 和 credential binding refs。
- 初始暴露 guided functions：
  - `cli_help`
  - `cli_execute`
  - `cli_read_output`
  - `cli_cancel`
- `cli_help` 只读取帮助文本，不把帮助文本解析为 catalog function。
- 对复杂 CLI，例如 `ffmpeg`、`git`、`kubectl`，优先使用 guided session，而不是把所有参数
  固化成 function schema。
- 高频稳定流程可 promoted 成独立 Tool Function，例如 `ffmpeg_probe`、
  `ffmpeg_transcode_simple`；promoted function 必须显式声明 subcommand、argv template、
  parameters、effect 和 runtime policy，不能由 help 文本无确认生成。

### provider_backend

- Source config 声明某类稳定能力的 backend，例如 OpenAI Codex image、Fal image、local SD。
- Discovery 产出 backend capability，而非默认产出模型可见 function。
- 稳定 Tool Function 通过 backend policy 选择后端。
- Backend credential/readiness 仍通过 Access 和 Tool readiness 统一展示。

## Application Surface

目标 application services：

- `ToolSourceCommandService`
  - create/update/disable/delete/restore source
  - validate source config
  - trigger discovery
- `ToolSourceQueryService`
  - list/get sources
  - source readiness
  - source discovery history
- `ToolDiscoveryService`
  - adapter routing
  - source-specific discovery
  - candidate validation
- `ToolCatalogReconcileService`
  - stable key diff
  - insert/update/stale/deprecate functions
  - preserve governance fields
- `ToolFunctionQueryService`
  - list/search/get functions
  - filter by source/kind/status/readiness/capability
- `ToolPolicyService`
  - enablement
  - trust
  - approval policy
  - required effects
- `ToolRuntimePoolService`
  - build caller-specific runtime tool pool
  - apply enabled/status/readiness/authorization filters
- `ToolExecutionService`
  - submit inline/background runs
  - execution gate
  - result/artifact normalization
- `ToolBackgroundSchedulerService`
  - assign queued runs to workers
- `ToolWorkerService`
  - worker heartbeat
  - run lease
  - cancellation
  - retry/recovery

## Ports

Tool application 可依赖的 ports：

- `AccessCredentialProviderPort`
  - resolve credential binding
  - check credential readiness
  - list compatible credential assets
- `AuthorizationPolicyPort`
  - check effect/tool permission
  - explain denial
- `EventPublisherPort`
  - publish source/function/run lifecycle events
- `ArtifactWriterPort`
  - externalize file/image/tool output
- `ProcessRunnerPort`
  - run controlled CLI commands
  - stream stdout/stderr
  - cancel process
- `DaemonReadinessPort`
  - check required background services/groups
- `ClockPort`
- `IdGeneratorPort`

禁止事项：

- Tool handler 不能直接接 `AppContainer`。
- Tool handler 不能直接接 owner module concrete service。
- Tool runtime 不能通过字符串 lookup 反查 `container.require(...)`。
- Tool source discovery adapter 不能写 Settings resource 真相。

## Persistence

新增或重构表建议：

- `tool_sources`
- `tool_source_discovery_runs`
- `tool_functions`
- `tool_function_policies`
- `tool_provider_backends`
- `tool_provider_backend_policies`
- 保留并升级现有 `tool_runs` / worker / queue 相关表

Migration 要求：

- 从现有 `tools/*/tool.yaml` 生成内置 source records。
- 从当前 runtime/discovery 结果 reconcile 出初始 function records。
- 当前 Settings `tool-catalog` enablement 必须迁到 Tool-owned policy 表，或通过一次性迁移导入 Tool policy。
- 迁移完成后 Settings 不再作为 Tool enablement 真相源。
- 历史 tool run 不删除；缺少 function record 时用 legacy id 做解释 fallback，但不能作为新执行路径。

## Events

新增或确认事件：

- `tool.source.created`
- `tool.source.updated`
- `tool.source.disabled`
- `tool.source.deleted`
- `tool.discovery.started`
- `tool.discovery.completed`
- `tool.discovery.failed`
- `tool.function.created`
- `tool.function.updated`
- `tool.function.stale`
- `tool.function.deprecated`
- `tool.function.policy_changed`
- `tool.provider_backend.created`
- `tool.provider_backend.updated`
- `tool.provider_backend.disabled`
- 现有 `tool.run.*` 事件继续保留并补充 source/function revision metadata

Operations observer 只消费事件和 Tool query service，不直接扫 source config。

## UI / API 目标

Settings Tool 页面应提供：

- Sources
  - source list
  - source detail drawer
  - create/edit/disable/delete
  - trigger discovery
  - discovery history
- Functions
  - function catalog table
  - status/stale/schema hash/source filter
  - enablement/trust/approval policy
  - credential/readiness summary
- Provider Backends
  - backend list
  - backend capability
  - credential binding
  - priority/default backend
- CLI Sources
  - executable validation
  - argv policy editor
  - guided test console
  - live stdout/stderr
- Test Run
  - choose function
  - form from input schema
  - dry-run/readiness check
  - submit
  - view result/artifacts/errors

Operations Tool 页面应展示：

- active/running/queued/waiting IO/failed counts
- worker pool state
- source health
- credential/readiness risks
- provider backend health
- recent runs
- recent artifacts
- failure distribution

## P0. 基线审查与守卫

- [x] 扫描当前 Tool 代码，列出所有 runtime/discovery 即时拼接路径。
- [x] 扫描 Settings `tool-catalog` 当前实际控制的字段。
- [x] 扫描 Tool HTTP/CLI API，标记哪些是 owner API，哪些只是兼容/调试入口。
- [x] 扫描所有 `tools/*/tool.yaml`，确认 local/openapi/runtime/credential 字段使用情况。
- [x] 扫描所有 `tool.json` filesystem extension 使用情况，决定是否迁为 `ToolSource`
  或明确保留为 local extension source。
- [x] 新增架构测试：生产路径不得从 Settings materializer 直接决定 Tool runtime catalog 真相。
- [x] 新增架构测试：Tool execution path 必须通过 `ToolFunction` 或 compatible catalog record
  解析 target。
- [x] 新增架构测试：Tool handler/runtime 禁止 container/resolver/service locator。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_catalog.py tests/unit/test_tool_settings_integration.py
PYTHONPATH=src pytest -q tests/unit/test_tool_access_architecture.py tests/unit/test_app_assembly_architecture.py
```

## P1. Domain 与持久化模型

- [x] 新增 `ToolSource` domain model。
- [x] 新增 `ToolFunction` domain model，或将现有 `Tool` aggregate 重命名/收敛为
  `ToolFunction` 语义。
- [x] 新增 `ToolProviderBackend` model。
- [x] 新增 source/function/backend repository ports。
- [x] 新增 Postgres persistence models 和 repositories。
- [x] 新增 Alembic migration。
- [x] 为 `ToolRun` 增加 `function_id`、`function_revision`、`source_id`、`source_revision`、
  `schema_hash` metadata。
- [x] 移除或隔离纯 in-memory catalog 在生产路径的使用；只允许测试或 explicit fallback。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_persistence.py tests/unit/test_tool_catalog.py
python -m crxzipple.main db upgrade head
```

## P2. Source Command / Query Service

- [x] 实现 `ToolSourceCommandService`。
- [x] 实现 `ToolSourceQueryService`。
- [x] Source create/update 进行 config validation，但不执行工具调用。
- [x] Source disable/delete 不硬删 functions；应使 functions 退出 runtime pool。
- [x] Source restore 后可重新 discovery/reconcile。
- [x] Source detail 输出 credential requirements、runtime requirements、last discovery 状态。
- [x] HTTP/CLI 入口改为调用 Tool source application。
- [x] Settings Tool owner API 改为调用 Tool source application。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_http.py tests/unit/test_tool_cli.py
PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py
```

## P3. Discovery Candidate Contract

- [x] 定义 `ToolFunctionCandidate`。
- [x] 定义 `ToolProviderBackendCandidate`。
- [x] 定义 `ToolSourceDiscoveryResult`。
- [x] Discovery adapter 只产出 candidate，不直接修改 runtime registry。
- [x] Candidate 必须包含 stable key、schema hash、runtime ref、requirements、capabilities。
- [x] Discovery error 必须持久化到 `tool_source_discovery_runs`。
- [x] Discovery result 不包含 secret value。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_providers.py tests/unit/test_tool_capabilities.py
```

## P4. Catalog Reconcile

- [x] 实现 `ToolCatalogReconcileService`。
- [x] 新 candidate 插入 `ToolFunction`。
- [x] 既有 candidate 更新 schema/description/metadata/hash。
- [x] 消失 candidate 标记 `stale`，达到明确条件后再 `deprecated`。
- [x] Reconcile 不覆盖用户治理字段：
  - enabled
  - trust policy
  - approval policy
  - credential binding override
  - required effect override
- [x] Reconcile 发布 function lifecycle events。
- [x] Reconcile 支持 dry-run preview，用于 Settings UI 展示刷新影响。
- [x] 历史 run 通过旧 revision/schema hash 仍可解释。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_catalog_reconcile.py
```

## P5. Local Package Cutover

- [x] 将 `tools/*/tool.yaml` 解释为 bundled `ToolSource`。
- [x] App activation 时内置 source 先进入 source repository，再 discovery/reconcile。
- [x] Local handler registration 从 function catalog 的 runtime ref 构建，不再以 list 时临时拼接为主。
- [x] `kind: local_package` 支持多个 functions。
- [x] `kind: openapi` 的 bundled package 迁为 OpenAPI source。
- [x] 当前 `LocalToolRuntimeRegistry` 缩小为 local runtime handler registry，不再承担 catalog 真相。
- [x] 删除或改名旧 local discovery 兼容语义；若保留 CLI，必须明确为 source discovery。
- [x] `tools/README.md` 更新为 source authoring contract。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_catalog.py tests/unit/test_tool_execution.py
PYTHONPATH=src pytest -q tests/unit/test_openai_image_tool.py tests/unit/test_tool_workspace.py
```

## P6. MCP / OpenAPI Source

- [x] MCP provider config 迁为 `ToolSource(kind=mcp)`。
- [x] MCP discovery adapter 从 `tools/list` 产出 candidates。
- [x] MCP runtime adapter 从 function runtime ref 执行 `tools/call`。
- [x] MCP source 支持 refresh、disable、delete、discovery history。
- [x] OpenAPI provider config 迁为 `ToolSource(kind=openapi)`。
- [x] OpenAPI discovery adapter 从 spec 产出 candidates。
- [x] OpenAPI runtime adapter 从 function runtime ref 执行 HTTP request。
- [x] OpenAPI credential requirements 从 security schemes 自动投影。
- [x] Settings 不再直接 materialize MCP/OpenAPI provider 为 runtime registry；配置型
  provider 先物化为 `ToolSource`，runtime handler 再从 active source 激活。
- [x] Runtime activation 复用已持久化的 `ToolFunction` operation/definition metadata，
  避免 activation 阶段重复 discovery。
- [x] MCP/OpenAPI source 支持显式 discovery run history，并让 refresh 成为可治理动作。
- [x] Settings Tool UI 接入 source list/detail、refresh、disable/restore、delete 和
  discovery history。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_openapi_access.py tests/unit/test_tool_providers.py
PYTHONPATH=src pytest -q tests/unit/test_tool_settings_integration.py
```

## P7. CLI Guided Source

- [x] 定义 `ToolSource(kind=cli)` config schema。
- [x] 实现 executable validation。
- [x] 实现 argv policy：
  - allowed subcommands
  - denied flags
  - path/root restrictions
  - mutating command approval policy
- [x] 实现 `cli_help` guided function。
- [x] 实现 `cli_execute` guided function。
- [x] 实现 `cli_read_output` guided function。
- [x] 实现 `cli_cancel` guided function。
- [x] 实现 long-running process state persistence。
- [x] Source refresh 后当前 app process 立即替换激活 configured runtime handler。
- [x] 实现 stdout/stderr streaming events。
- [x] 支持 credential binding 注入为 env/config file reference，但不暴露 secret value。
- [x] 为 `ffmpeg` 做一个示例 source，并验证 help/probe/execute 流程。
- [x] 高频 CLI 流程支持 promoted function，但 promoted function 必须仍引用 source/runtime policy。

第二十三轮施工记录：

- 新增 Tool-owned CLI source 后端：
  - `ToolSource(kind=cli)` 支持 configured source create/update、discovery 和 runtime
    activation。
  - CLI source config 接受受控 `command/executable`、`allowed_subcommands`、
    `denied_flags`、`working_directory/allowed_roots`、`timeout_seconds`、
    `output_limit_bytes`。
  - discovery 产出 `cli_help`、`cli_execute`、`cli_read_output`、`cli_cancel`
    四个 `ToolFunction(runtime_kind=cli)`。
  - runtime handler 使用已注入的 Process application service 持久化进程状态和
    stdout/stderr，Tool handler 不持有 container/resolver。
- Settings Tool source editor 已允许新建/编辑 configured CLI source，并要求填写
  allowed subcommands，避免任意 shell 入口。
- 配置型 OpenAPI/MCP/CLI runtime activation 已收口到
  `ToolConfiguredRuntimeActivator`：
  - app 启动时按 active source + active function catalog 激活 runtime handler。
  - `/tools/sources/{id}/refresh` 后只替换该 source 对应的 runtime handler，当前 API
    进程不再需要重启。
  - `ToolRuntimeRegistry` 默认仍拒绝重复注册；只有 configured source activation 使用
    显式 replace 语义。
  - MCP source refresh 会按 source key 替换 cleanup callback，旧 MCP client 立即关闭。
- 当轮遗留的 Provider backend 收敛已在 P8 后续切片关闭。

第二十四轮施工记录：

- 新增 `tool.cli.output_observed` 事件契约：
  - 事件字段包含 `source_id`、`provider`、`process_id`、`session_key`、`stream`、
    `offset/next_offset`、`text/text_length`、`status`、`exit_code` 和运维 display fields。
  - Operations observer 和 Tool operations read model 的事件 topic 白名单已包含该事件。
- CLI guided runtime 在 `cli_execute` 启动进程后，会启动轻量 output observer：
  - 观察者按 stdout/stderr offset 从 Process application service 读取增量。
  - 增量以 `tool.cli.output_observed` 发布到 events backend，`ordering_key` 为
    `process_id`。
  - 终止时发布 `stream=status` 的收尾观察事实，便于 UI console 判断进程结束。
  - 进程输出仍由 Process 模块持久化，Tool 只发布 CLI source 语义下的观察事实。

第二十五轮施工记录：

- CLI source config 支持 `provider.credential_bindings`：
  - `injection=env`：Access binding resolve 后仅注入子进程环境变量。
  - `injection=file`：Access binding resolve 后写入 0600 临时文件，仅把文件路径注入子进程环境变量。
  - 运行 metadata 只记录 binding id、slot、provider、注入方式和 env/file env name，不记录
    secret value。
  - `tool.cli.output_observed` 事件会对本次注入的 secret value 做 redaction，避免
    运维/设置 console 因 CLI 误打印凭证而暴露 secret。
- `cli_execute` 的 `ToolFunction` catalog 会投影对应
  `AccessCredentialRequirementSet`，Access/Settings 能看到 CLI source 的 credential
  requirement。
- Process application service 增加 scoped env override，通用 Process 模块不理解 Tool
  credential，只负责把调用方传入的 env 应用于该进程。
- 临时 credential file 由 CLI output observer 在进程终止后清理；进程启动失败时立即清理。

第二十六轮施工记录：

- CLI source config 支持 `provider.promoted_functions`：
  - 每个 promoted function 从 source config 发现并写入 `ToolFunction` catalog。
  - promoted function 仍通过同一套 `allowed_subcommands`、`denied_flags`、
    `working_directory/allowed_roots`、timeout、output limit 和 credential injection 执行。
  - 参数模板只把稳定高频流程投影成独立 Tool Function，不开放任意 shell 或任意 argv。
- Runtime activation 支持 `cli_promoted_execute`：
  - handler 由 active source + active function metadata 激活。
  - 执行时仍调用 Process application service，继续发布 `tool.cli.output_observed` 增量事件。
- 单测用 fake ffmpeg source 验证：
  - `cli_help` 能读取 help。
  - `cli_execute` 能按 source policy 启动 probe。
  - promoted `FFmpeg Probe` 能引用同一 source/runtime policy 并观察输出。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py tests/unit/test_tool_providers.py
PYTHONPATH=src pytest -q tests/unit/test_tool_http.py
PYTHONPATH=src pytest -q tests/unit/test_events.py -k "tool_and_llm_lifecycle_events or operations_observer_subscriptions"
PYTHONPATH=src pytest -q tests/unit/test_process_cli.py
```

## P8. Provider Backend

- [x] 定义 provider backend domain model。
- [x] 定义 backend capability registry。
- [x] 将 image generation 收敛为稳定 function + backend policy。
- [x] OpenAI image backend 作为 `provider_backend` source 或 local package backend candidate。
- [x] Backend readiness 通过 Access / runtime requirements 汇总。
- [x] 支持默认 backend、fallback backend、disabled backend。
- [x] Tool run metadata 记录实际 backend id。
- [x] UI 展示 backend capability、credential binding、readiness 和最近调用。

第二十七轮施工记录：

- Provider backend 既有 domain/repository/migration 开始进入 source discovery 实链路：
  - package manifest 支持 `provider_backends` 声明。
  - `ToolPackageDiscoveryAdapter` 将声明投影为 `ToolProviderBackendCandidate`。
  - `ToolSourceCommandService.sync_source()` 会把 backend candidate upsert 到
    `tool_provider_backends`，并继续把数量写入 discovery run history。
  - refresh 时保留既有 backend 的 `enabled` 与 disabled/deleted 状态，避免 discovery 覆盖用户治理。
- `tools/openai_image/tool.yaml` 增加 `openai_image.default`
  backend candidate，capability 为 `image_generation`，credential requirement 指向
  `openai-api-key`。
- 后续切片继续补 fallback/default 治理、backend readiness 聚合和
  Settings/Operations 展示。

第二十八轮施工记录：

- `ToolPackageDiscoveryAdapter` 会根据 provider backend metadata 中的
  `stable_functions` 给对应稳定 Tool Function 写入 `provider_backend_policy`。
- 新增 `ToolProviderBackendResolver`：执行提交前读取 `ToolFunction` 的 backend policy，
  从 `tool_provider_backends` 选择 active/enabled/default backend，并在不可用时返回
  结构化 `tool_provider_backend_not_available` 错误。
- Tool run 创建时将实际 backend payload 写入 `run.metadata.provider_backend`，并把同一
  payload 注入 `ToolExecutionContext.provider_backend`，background worker 也会从 run
  metadata 恢复该上下文。
- OpenAI image backend 不再直接硬编码凭证来源；它从 provider backend context 中读取
  `openai_api_key -> access binding id`，再通过 Access credential provider 取凭证。

第二十九轮施工记录：

- `ToolSourceQueryService` 暴露 `list_provider_backends()` /
  `get_provider_backend()`，`/tools/provider-backends` 和
  `/tools/provider-backends/{backend_id}` 返回 backend capability、runtime ref、
  credential requirements、enabled/status 和时间戳。
- Operations Tool read model 不再从 `provider_backend` source/function 反推后端健康，
  而是通过 Tool query port 读取真实 `tool_provider_backends`，并在表格中展示
  backend、capability、credential binding、runtime、status 和 Access readiness。
- Settings Tool Catalog 的 Backends tab 改为读取真实 provider backends，移除发现
  provider/root 伪 backend 列表；顶部 backend 指标也切到 active/issue 统计。

第三十轮施工记录：

- provider backend policy 支持 `fallback_backend_ids`，并自动把 default/fallback 纳入
  allowed backend 集合。
- `ToolProviderBackendResolver` 会按 default -> fallback 顺序选择 backend；disabled、
  deleted、error、capability 不匹配或不在 allowlist 的 backend 不会被选中。
- 当没有可用 backend 时，resolver 返回结构化
  `tool_provider_backend_not_available` 错误，保留 policy 和原因，便于 API/UI 直接展示。

第三十一轮施工记录：

- Operations Tool 的 Provider Backend Health 表从 run metadata 统计 backend 最近 24h
  调用数和失败数，补齐“backend 是否实际被调用”的运维信号。
- Settings Tool Catalog 展示 backend capability、credential binding 与 runtime；
  Operations Tool 展示 capability、credential binding、Access readiness、runtime、status、
  24h calls/failures。

第三十二轮施工记录：

- 新增 `ToolProviderBackendReadinessEvaluator`，provider backend readiness 现在由
  Tool application service 统一汇总 Access credential readiness 与 runtime
  requirements，而不是 Operations 直接拆 credential requirement。
- `/tools/provider-backends` 与 `/tools/provider-backends/{backend_id}` 返回
  `readiness` payload；Settings Tool Catalog Backends tab 展示同一 readiness。
- Operations Tool Provider Backend Health 继续负责运维统计，读取 Tool query port
  返回的 readiness，并结合 run metadata 统计 24h calls/failures。

设计决定：

- Settings Backends tab 不展示最近调用；最近调用/失败属于 Operations 运维统计，
  继续在 Operations Tool 中展示。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_source_service.py tests/unit/test_tool_source_catalog_persistence.py
PYTHONPATH=src pytest -q tests/unit/test_openai_image_tool.py tests/unit/test_tool_source_service.py
PYTHONPATH=src pytest -q tests/unit/test_tool_http.py::ToolHttpTestCase::test_tool_provider_backend_endpoints_list_catalog_backends tests/unit/test_openai_image_tool.py tests/unit/test_tool_source_service.py
PYTHONPATH=src pytest -q tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_operations_tool_overview_uses_tool_runtime_state tests/unit/test_ui_http.py::UiHttpTestCase::test_ui_operations_tool_page_uses_tool_runtime_state tests/unit/test_operations_read_model_boundaries.py
PYTHONPATH=src pytest -q tests/unit/test_tool_provider_backend_service.py tests/unit/test_openai_image_tool.py
cd frontend && npm run typecheck
cd frontend && npm run build
```

## P9. Runtime Pool 与 Execution Gate

- [x] `ToolRuntimePoolService` 只从持久化 `ToolFunction` 构建 runtime pool。
- [x] Pool 构建按 caller/agent/session 上下文过滤：
  - [x] function enabled
  - [x] source enabled
  - [x] function status active
  - [x] Access readiness
  - [x] daemon/runtime readiness
  - [x] Authorization effect policy 保持在 Orchestration `ToolResolver`
        按 run subject/context 处理，不进入 Tool module。
  - [x] approval policy 保持在 Orchestration `ToolResolver`/approval flow
        处理，不进入 Tool module。
- [x] Execution submit 前必须读取 `ToolFunction` 最新 catalog record。
- [x] 对 stale/deprecated/disabled function 返回结构化错误。
- [x] Background queue 记录 function/source revision。
- [x] Worker 执行前再次校验 function/source 状态，避免排队期间配置变化。
- [x] Worker 执行只通过 runtime ref 找 handler，不重新 discovery。
- [x] `list_tools` / `list_enabled_tools` / `get_tool` 优先从持久化 `ToolFunction`
  构建 runtime-facing query surface。
- [x] Result 统一为 `ToolRunResult`，artifact externalization 保持。

说明：上项已覆盖 catalog-backed run；配置型 MCP/OpenAPI 已不再走 legacy provider
fallback。无 `function_id` / 无 catalog record 的旧 manual/test/local filesystem fallback
已在 P13 迁移、删除或改名为测试辅助。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_execution.py tests/unit/test_tool_background.py
```

## P10. Settings / Access / Authorization 接入

- [x] Settings Tool 页面所有写操作改为 Tool owner action。
  已接 Source create/update、refresh、disable/restore/delete、Function enable/disable 和
  test run；Function policy/trust/approval 也已走 Tool owner endpoint。
- [x] Settings 不再保存 Tool enablement 真相；旧资源迁到 Tool policy。
  已删除 Settings enablement materializer 与 runtime overlay；Function enablement
  只由 Tool owner catalog 持有。
- [x] Access requirement catalog 从 Tool query service 读取 sources/functions requirements。
  当前已接 ToolFunction catalog credential requirements；ToolSource-level shared
  requirements 与 provider backend requirements 仍在对应 source/backend 页面补齐。
- [x] Tool credential binding selector 只展示 kind/provider/slot 兼容的 Access assets。
  当前按 active status、credential kind、可用 provider metadata 过滤；slot binding 由
  Tool requirement 与 Access consumer binding 合并结果决定。
- [x] Authorization policy 不写进 Access；ABAC effect 仍由 Authorization 管。
  已有 `test_access_policies.py` 拦截 Access action 创建 internal ABAC policy；
  authorization grant/effect policy 仍走 Authorization module。
- [x] Agent profile 的 tool 免授权/approval 配置通过 Tool policy + Authorization policy 组合完成，
  不让 Agent profile 直接复制 Tool catalog。
- [x] 所有 credential readiness 失败以 Access 结构化原因返回。
  Tool HTTP execution gate 已返回 Access/runtime readiness payload；缺少 env credential、
  OAuth account 和 runtime daemon 的失败路径均已覆盖。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_access_tool_requirements.py tests/unit/test_authorization.py
PYTHONPATH=src pytest -q tests/unit/test_tool_settings_integration.py
```

## P11. Operations Read Model

- [x] Tool source/function/run lifecycle events 纳入 events definition registry。
- [x] operations-observer 消费 Tool source/function/run events。
- [x] `/operations/tool` 读取 projection store 优先。
- [x] Operations Tool read model 增加：
  - source health
  - discovery failures
  - stale/deprecated functions
  - credential readiness risks
  - provider backend health
  - CLI process health
- [x] Operations 不直接调用 Tool discovery provider 或 Settings source config。
- [x] Skeleton/loading/error 状态保持全屏布局稳定。
  Tool Operations 首屏使用 fallback read model 撑住全屏布局；初次 loading 增加
  `aria-busy` 与不改变网格尺寸的 skeleton sheen，避免加载前后大面积跳动。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_operations_observation.py tests/unit/test_operations_read_model_boundaries.py
cd frontend && npm run audit:operations-layout
```

## P12. Frontend Tool Settings

- [x] 按 `docs/ui/settings/tool-catalog.png` 和当前全屏应用风格重做 Tool Settings 页面。
- [x] 主区以 table + right detail drawer 为主，不在首屏堆嵌套卡片。
- [x] Source / Function / Backend / Test Run 分区明确。
- [x] Source create/edit 用 modal 或 drawer，不把大表单常驻首屏。
- [x] Function table 支持 source、status、kind、readiness、enabled、credential filter。
- [x] Detail drawer 展示 schema、runtime ref、requirements、policy、recent runs。
  当前已重排成右侧详情面板；输出 schema、artifact contract 仍等后端 catalog 字段补齐。
- [x] Test Run 面板可直接构造 input schema 表单并查看 result/artifact/error。
- [x] CLI source test console 支持实时输出。
- [x] 所有固定文案进入 i18n。
- [x] Loading/skeleton 与实际数据布局高度一致。
  当前 Tool Settings 在加载、空态、错误态都保留 table + drawer 外框，使用表格内空态提示，
  不再用整页状态替换布局。

第二十一轮施工记录：

- `frontend/src/pages/settings/modules/ToolCatalogSettingsPage.vue` 重排为全屏应用布局：
  顶部指标条 + 主表格 + 右侧 detail drawer。
- 主表格新增 Function / Source / Backend / Run 四个视角；Function 视角支持 source、
  status、runtime、enabled、credential readiness 和搜索过滤。
- 右侧 detail drawer 收拢 Runtime Contract、Function Policy、Credential Slots、
  Contract Test、Recent Runs、Input Schema；Source 视角显示 source overview、
  discovery history 和 source config。
- Source create/edit 仍通过 drawer/modal 触发；首屏不再常驻大表单。

第二十二轮施工记录：

- Tool Settings 页面固定标题、按钮、筛选器、空态、通知、校验错误和 source editor 文案
  已进入 `settings.toolCatalog.*` i18n key；中英文消息表已补齐并做 missing-key 扫描。
- 运行契约、策略、凭据槽、契约测试、最近运行等右侧详情区也不再直接裸写英文固定文案。
- Source editor 已支持 configured CLI source，包含 command/executable、
  allowed subcommands、denied flags、working directory、allowed roots 和 output limit。
- CLI source test console 不新增专用 source test endpoint：Settings 提交
  `/tools/{tool_id}/runs` 后，从返回的 `process_id` 订阅事件总线
  `tool.cli.output_observed`，snapshot 补快进程，增量 event 展示长进程 stdout/stderr。
  这让页面继续消费 Tool run lifecycle 与 Events 真相，不制造第二套测试运行记录。

验收：

```bash
cd frontend && npm run typecheck
cd frontend && npm run build
```

## P13. Cleanup / Cutover

- [x] 删除旧 manual in-process register 作为生产 catalog 真相的路径。
- [x] 删除长期兼容的 Settings tool enablement materialization。
- [x] 删除旧 local discovery alias 语义或迁为 source refresh。
- [x] 删除 runtime list 时触发 discovery 的生产路径。
- [x] 删除 handler 内部 credential/env fallback。
- [x] 删除 provider config 中 direct secret source 支持。
- [x] 删除无法解释的 legacy source kind 命名，统一 source/function 状态。
- [x] 更新 `src/crxzipple/modules/tool/README.md`。
- [x] 更新 `tools/README.md`。
- [x] 更新 `docs/tool-credential-requirements-guide.md`。
- [x] 更新 `docs/ui/runtime-ui-read-model-contracts.md`。
- [x] 更新 `docs/README.md` 当前入口。

第三十三轮施工记录：

- `docs/tool-credential-requirements-guide.md` 补齐 provider backend
  credential/runtime readiness 契约，明确 handler 从 backend context 读取 binding id，
  再通过 Access credential provider 取凭证。
- `docs/ui/runtime-ui-read-model-contracts.md` 补齐 Operations Tool 的
  source/backend/CLI sections，以及 Settings Tool Catalog 的 Function / Source /
  Backend / Run 全屏页面契约。
- `src/crxzipple/modules/tool/README.md` 更新为 source/function/backend catalog
  口径，弱化旧 process-local / local filesystem discovery 说明。
- `docs/README.md` 增加内置 Tool source authoring contract 入口。

第三十四轮施工记录：

- Tool 领域层删除旧 `ToolSourceKind` 命名，改为 `ToolDefinitionOrigin` /
  `definition_origin`，只表达某个 runtime tool definition 的来源。
- Tool Catalog source 继续使用 `ToolCatalogSourceKind.kind` 表达 MCP/OpenAPI/CLI/local
  package 等 source 类型；Access、LLM、Authorization 等模块保留各自独立的
  `source_kind` 语义。
- Tool HTTP / Settings Tool Catalog / Agent resolved tools / Operations Tool read model
  已切换到 `definition_origin` 字段，避免把 runtime definition 来源和 catalog source
  类型混在一个 “source kind” 里。
- 验收：
  - `PYTHONPATH=src pytest -q tests/unit/test_tool_catalog.py tests/unit/test_tool_providers.py tests/unit/test_tool_execution.py tests/unit/test_tool_background.py tests/unit/test_tool_http.py::ToolHttpTestCase::test_tool_endpoints_list_roots_and_tools tests/unit/test_agent_http.py tests/unit/test_orchestration_tools.py`
  - `PYTHONPATH=src python -m ruff check src/crxzipple/modules/tool src/crxzipple/interfaces/authorization.py src/crxzipple/modules/orchestration/application/tool_resolver.py src/crxzipple/modules/agent/application/resolution.py src/crxzipple/modules/agent/interfaces/http.py`
  - `cd frontend && npm run typecheck`

验收：

```bash
rg -n 'manual tool|ToolEnablementService|env:|file:|codex_auth_json|container.require|SimpleNamespace|PortResolver' \
  src/crxzipple/modules/tool tools docs
PYTHONPATH=src pytest -q tests/unit/test_tool_*.py
cd frontend && npm run typecheck
```

## P14. 端到端验收

- [x] `make dev-up` 后 Postgres/Redis/API/daemon/frontend 正常。
- [x] DB migration 到 head 通过。
- [x] 内置 `tools/*/tool.yaml` 全部形成 source records。
- [x] 内置 local/openapi tools 全部形成 function records。
- [x] MCP source 新建、发现、执行、禁用、删除流程通过。
- [x] OpenAPI source 新建、发现、绑定 credential、执行流程通过。
- [x] CLI source 新建、help、execute、read output、cancel 流程通过。
- [x] OpenAI image 通过稳定 `image_generate` function + backend 执行。
- [x] Access 页面能看到 Tool requirements 和 binding readiness。
- [x] Settings Tool 页面能查看 source/detail/history，并 refresh discovery、disable/restore/delete source。
- [x] Settings Tool 页面能 create/update source、启停 function、测试运行。
- [x] Settings Tool 页面能修改 Function policy/trust/approval 常用字段。
- [x] Operations Tool 页面能看到 run、worker、source health、backend health 和 failure。
- [x] Agent 调用 tool 时只收到 runtime pool 允许的 functions。

第三十五轮施工记录：

- 重启 dev stack 后验收当前代码路径：
  - `make dev-status` 显示 Postgres / Redis healthy，API、daemon、frontend 在线。
  - `python -m crxzipple.main db current` 显示 `0052_tool_source_discovery_runs (head)`；
    `db upgrade head` 无待执行 migration。
- Tool catalog 运行库验收：
  - `python -m crxzipple.main tool sources` 返回 13 个 active source records，
    kind 覆盖 `local_package`、`openapi`。
  - `python -m crxzipple.main tool functions` 返回 48 个 active/enabled function
    records，runtime kind 覆盖 `local`、`openapi`。
- Operations Tool projection 验收：
  - `/operations/tool` 返回 `tool_runs`、`workers`、`source_health`、
    `provider_backend_health`、`discovery_failures`、`function_catalog`、
    `cli_process_health`。
  - 当前运行库中 `source_health.total=13`、`provider_backend_health.total=1`、
    `tool_runs.total=50`、`workers.total=2`，tool run 表内能看到 retained failed rows。

第三十六轮施工记录：

- CLI source 端到端烟测在 dev Postgres/Redis 运行库通过：
  - 新建临时 `configured.cli.p14_smoke_*` source。
  - `source-refresh` 发现 `cli_help`、`cli_execute`、`cli_read_output`、
    `cli_cancel` 四个 guided functions。
  - `cli_help` 成功返回帮助输出；`cli_execute` 启动受控 Python 进程；
    `cli_read_output` 读取 stdout；`cli_cancel` 成功终止长运行进程，返回 `killed`。
  - 最后执行 `source-disable` 与 `source-delete`，source 状态为 `deleted`。
- 修复验收暴露出的授权缺口：
  - 默认 Authorization policy 增加
    `allow_cli_source_cancel_from_cli_interface`。
  - 该策略只允许本机 `cli` interface 对带有 `tool.cli.cancel` effect 的 Tool 执行
    `tool.run`，不放开 HTTP/UI/agent。
- 验收：
  - `PYTHONPATH=src pytest -q tests/unit/test_authorization.py tests/unit/test_tool_cli.py tests/unit/test_tool_source_service.py`
  - `PYTHONPATH=src python -m ruff check src/crxzipple/interfaces/authorization.py src/crxzipple/modules/authorization tests/unit/test_authorization.py`

第三十七轮施工记录：

- OpenAPI source 端到端烟测在 dev Postgres/Redis 运行库通过：
  - 新建临时 `configured.openapi.p14_smoke_*` source。
  - 临时 OpenAPI spec 声明 `ApiKeyHeader`，source config 通过
    `credential_bindings` 绑定 `env:P14_OPENAPI_KEY`。
  - `source-refresh` 发现 `p14_smoke_api.echo_message` function。
  - `tool run ... --environment remote` 成功调用本地 HTTP smoke server，
    server 验证 `X-P14-Key` 后返回 `CREDENTIAL OK`，证明 Tool -> Access
    credential provider -> OpenAPI runtime 的凭证注入链路已接通。
  - 最后执行 `source-disable` 与 `source-delete`，source 状态为 `deleted`。

第三十八轮施工记录：

- MCP source 端到端烟测在 dev Postgres/Redis 运行库通过：
  - 新建临时 `configured.mcp.p14_mcp_smoke_*` source。
  - source config 走 Tool-owned `configured_tool_provider`，provider command 指向
    本地 stdio MCP smoke server。
  - `source-refresh` 通过 MCP `tools/list` 发现 `echo`、`sum` 两个 function
    records。
  - `tool run ... --environment remote` 通过已物化的 function record 调用 MCP
    runtime，返回 `MCP LIVE`。
  - 最后执行 `source-disable` 与 `source-delete`，source 状态为 `deleted`。

第三十九轮施工记录：

- OpenAI image 端到端烟测在 dev Postgres/Redis 运行库通过：
  - `bundled.local_package.openai_image` 已物化 `openai_image_generate` 和
    `openai_image_edit` function records。
  - `openai_image_generate` 入队时 metadata 带有
    `provider_backend.backend_id=openai_image.default` 和
    `credential_bindings.openai_api_key=openai-api-key`。
  - 后台 tool worker 消费 run `4a8d5208467c4f8ebf0edac42cc5e2b2`，最终状态
    `succeeded`。
  - 结果 content blocks 包含 `text` 与 `image_ref`，生成图片已外部化为 artifact
    `87998c76783c480181fd3eef9abf34e3`。

第四十轮施工记录：

- P14 并发 CLI 验收暴露出 Browser 状态文件写入原子性问题：
  - 多个 CLI 进程同时装配时，`tool sources` 曾在读取
    `.crxzipple/browser/config/system.json` 时撞上空文件。
  - Tool CLI 不应因为 Browser 状态文件写入中的短暂空窗失败。
- 修复：
  - `modules/browser/infrastructure/state_root.py` 的 JSON 写入改为和 Channel
    state root 一致的文件锁 + 临时文件 + `os.replace` 原子落盘。
  - 该修复不改变 Browser 领域模型或 Tool 装配边界，只消除跨进程读写状态文件的
    半写入窗口。

第四十一轮施工记录：

- 旧 Tool 形态与兼容路径完成退场：
  - 删除生产 API `register_process_local_tool()`、
    `set_process_local_tool_availability()` 和对应 `RegisterToolInput` /
    `SetToolAvailabilityInput` 导出。
  - 删除 `/tools/providers`、`/tools/discover`、CLI `tool providers`、
    CLI `tool discover`。
  - 删除 `FilesystemLocalToolDiscoveryProvider` 和 `local_builtin` runtime registry
    discovery provider；`tools/debug` 也改为 `local_system` provider name。
  - `ToolCatalogService` 只读取持久化 active source + active function；`ToolSubmissionService`
    对不存在的 `ToolFunction` 直接报 `ToolNotFoundError`，不再 fallback 到 runtime
    registry 或 process-local overlay。
  - `ToolRuntimePoolService` 和 Orchestration tool port 不再支持
    `include_process_local_overlay`。
  - Orchestration `ToolResolver` 不再调用 `ensure_local_system_tools_registered()`；
    Tool 可见性只来自 runtime pool / catalog。
- 测试与架构防线：
  - `tests/unit/test_tool_access_architecture.py` 改为验证旧入口不存在。
  - CLI 测试改用 `tool sources` / `tool functions` 和 catalog-backed 行为。
  - Tool IO benchmark 如需临时工具，先物化临时 `ToolSource`/`ToolFunction`，再注册匹配
    handler，不再走 process-local 注册。

第四十二轮施工记录：

- 旧 Tool 形态测试支撑层完成退场：
  - `tests/unit/tool_test_support.py` 不再导出 `RegisterToolInput`、
    `RegisterToolParameterInput`、`SetToolAvailabilityInput`。
  - 单元测试统一通过 `seed_catalog_tool()` 先写入 `ToolSource` / `ToolFunction`
    catalog truth，再按需挂接本地 runtime handler。
  - Orchestration、HTTP、UI、Agent、Turns 等测试不再调用
    process-local registration 或旧 discovery provider。
- 前端 Settings Tool owner API 收口：
  - 移除 `/tools/providers`、`/tools/discover` client 调用。
  - Settings Tool 页面只使用当前 source/function/provider-backend/query/action surface。
- 保留的旧关键词只允许出现在两类位置：
  - 本 checklist / README 中的退场说明。
  - 架构测试里的禁止回潮断言。
- Orchestration stale tool access 行为保持由 `ToolResolver` 产出结构化
  `access_not_ready` payload；runtime pool 不再提前把 orchestration 调用折叠成
  generic tool-not-found。

第四十三轮施工记录：

- Tool Settings 产品闭环继续收口：
  - `/tools/functions` 和 `/tools/functions/{function_id}` 现在直接返回完整
    ToolFunction owner contract，包括 parameters、tags、effect、access/runtime
    requirement sets、credential requirements、execution policy/support、definition
    origin 和 runtime key。
  - Settings Tool 页面详情抽屉改以 `ToolFunction` owner catalog 为主对象；
    `/tools` runtime tool 只作为“当前是否可测试运行”的可运行投影。
  - 函数启停、策略编辑、凭据槽绑定、来源编辑/刷新/停用/删除和契约测试继续落在
    当前 source/function/action surface，不再依赖旧 discovery/provider endpoint。
  - 移除页面里的 `settings/tool-catalog` overlay 读取，避免 Settings 资源快照重新变成
    Tool enablement/policy 的第二真相。
  - 对 stale/deprecated/source inactive 的函数，页面仍能展示 owner contract；测试运行按钮
    会提示该函数未进入 runnable pool。

第四十四轮施工记录：

- ToolRun 历史解释能力完成出口补齐：
  - `ToolRunDTO`、HTTP `ToolRunResponse` 和前端 `ToolRunApiPayload` 显式暴露
    `function_id`、`function_revision`、`source_id`、`source_revision`、`schema_hash`。
  - Tool Settings 的运行表和详情运行表显示目录版本摘要，避免只能靠 run id / tool id
    猜测当时执行的 catalog 版本。
  - 该信息来自提交运行时已落库的 `tool_runs` 字段，不进入 `metadata`，不制造第二套解释
    真相。

验收：

```bash
make dev-up
source scripts/dev/infra-env.sh
python -m crxzipple.main db upgrade head
PYTHONPATH=src pytest -q tests/unit/test_tool_*.py tests/unit/test_access_*.py
cd frontend && npm run typecheck && npm run build
```

## 交付定义

本次升级完成的判断标准：

- Tool Catalog 真相不再由 runtime list/discovery 临时拼接。
- `tool.yaml`、MCP `tools/list`、OpenAPI spec、CLI config、provider backend config 都通过
  Source -> Candidate -> Reconcile 进入 Tool-owned catalog。
- Settings Tool 页面不再直接持有 Tool enablement/policy 真相。
- Access 只处理外部凭证，Authorization 只处理内部授权，职责无混淆。
- Operations Tool 页面只通过事件/projection/query service 观察 Tool 状态。
- 旧兼容路径有明确删除记录，不能留下“新旧都能跑”的双轨。
- 架构测试能阻止 service locator、direct secret source、runtime discovery catalog truth 回潮。
