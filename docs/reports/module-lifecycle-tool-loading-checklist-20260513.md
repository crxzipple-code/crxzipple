# Module Lifecycle and Tool Loading Governance Checklist 2026-05-13

本文档是 app assembly、module 生命周期、tool 包装载与跨模块依赖治理的当前施工清单。
目标不是给 Tool 模块增加特殊生命周期，而是把所有 module 收到统一装配规则下：

```text
construct module cores
export stable ports
plan owner resources
resolve activation plans
apply resolved plans
check readiness
activate runtime
```

## 冻结口径

- 所有 module 对系统平等；不存在 Tool 是底层、Orchestration 是高层这类特殊层级。
- `app/assembly/*` 是 composition root，不是业务服务定位器。
- Module core 构造期只构造自己的 service、repository、runtime registry 和配置视图。
- Module core 不持有 `container`、`PortResolver`、`SimpleNamespace` 或跨模块 lookup lambda。
- Port 只表示显式能力接口；不能把 `PortResolver` 下放给 module 或 handler 当小号 container。
- `tools/*/tool.yaml` 是 Tool module 的内部资源协议，只能由 Tool module 解析；module kernel 不直接读取 tool package manifest。
- Tool package 可以需要其他 module 的能力，但这些依赖必须在 activation/apply 阶段被显式解析并作为构造参数传入 handler。
- 缺少内部 service dependency 是启动/激活错误，不能进入 runtime。
- 缺少外部资源、凭证、OAuth 登录、daemon readiness 是运维配置状态，应在 readiness 中显示 `setup_needed` / `degraded`，而不是 handler 调用时才报错。
- Runtime handler 不允许在执行时动态查 container、resolver、registry 或 owner module service。

## 当前事实

- 旧 `build_container()` 手写装配路径已移除；当前 runtime 由 `app/assembly/runtime.py`
  的 module-local factories、integration factories 和 activation tasks 装配。
- Tool scanned package 已从两段装载收成单次 apply hook：
  - `_build_tool_infrastructure()` 调用 `discover_tool_namespaces()`，只保留 Tool core registries/gateway，不注册 scanned package handler。
  - `runtime_plan()` 在 Tool execution 和 Orchestration runtime factory 之后运行一次
    `tool.activate_packages`；`app/assembly/tool.py` 统一构造
    `ToolPackageApplyContext` 并注册 local/OpenAPI/remote/sandbox handlers。
- Local tool handler 现在接收 manifest-driven `ToolHandlerFactoryDeps`，不再通过 `SimpleNamespace` 迁移 adapter 获取 apply 阶段依赖。
- 旧 `register_scanned_tool_packages(...)` 注册入口已移除；sandbox worker 也改为
  `discover_tool_package_plans()` + `apply_tool_package_plans(...)`，不再绕回旧兼容 wrapper。
- Orchestration runtime factory 通过 `ToolServiceAdapter` 显式依赖 `AppKey.TOOL_SERVICE`。
- Sessions local tools 已改为接收 Session-owned `session_runtime_control` port；当前 Orchestration-backed adapter 在 app assembly 边界装配，旧 `orchestration_*_service_lookup` 查询函数已从 Tool apply adapter 退掉。
- `AppContainer` 仍是最终运行句柄，但 Tool/Operations 相关的 app assembly internal registry、
  state handle 和匿名 context 暴露面已分批收窄。
- 旧 `src/crxzipple/bootstrap/*` 装配路径已退役并删除；运行时装配统一在
  `src/crxzipple/app/assembly/*` 与薄 `src/crxzipple/app/container.py`。

## 2026-05-16 收口状态

本文件保留为当前 Tool 装载和 module lifecycle 目标形态的验收记录，不再表示待迁移
双轨方案。后续施工以
`docs/reports/app-assembly-container-target-checklist-20260514.md` 为主清单：

- P0-P7 的目标形态已经落在 app assembly / activation task / typed deps 路径上。
- 临时兼容路径不得重新引入；若发现和本文件旧施工顺序冲突，以本节和 2026-05-14
  app assembly checklist 为准。
- `tools/*` handler 不接收 container/resolver/SimpleNamespace；测试 fake 只能在测试
  辅助层适配，不能回流生产 handler。
- `AppContainer` 仅保留 `require/get/has/snapshot/close`，不再提供属性式服务定位器。

## 2026-05-13 施工记录

- 已新增 app assembly lifecycle primitives：`PortRegistry`、`ModuleActivationPlan`、
  `ResolvedActivationPlan`、`ReadinessReport` 和依赖分类。
- 已新增 Tool package plan API：`discover_tool_package_plans()`、
  `load_tool_package_plan()`、`ToolPackagePlan`、`ToolHandlerPlan`、`ToolOpenApiPlan`、
  `ToolRuntimePlan`。
- 已新增 P0 依赖图：
  `docs/reports/module-lifecycle-tool-loading-dependency-map-20260513.md`。
- 已把 scanned package 注册从两阶段收成单一 hook：
  `_build_tool_infrastructure()` 不再注册 scanned package，`runtime_plan()` 在 Tool execution
  与 orchestration runtime graph 完成后通过 `tool.activate_packages` 统一注册一次。
- 已新增架构测试守卫单次 apply hook，防止回到 `include_local=False` /
  `include_runtimes=False` 的二段注册。
- 已新增 handler 运行路径架构守卫，扫描 `tools/*` handler 与 Tool runtime 路径，禁止
  `AppContainer`、`SimpleNamespace`、`PortResolver`、`container` service locator 与
  `orchestration_*_lookup` 回潮。

## P4/P5 验收审查 2026-05-13

P4 生产代码已落地：app assembly 主路径只调用 `activate_tool_packages(...)`，由
`app/assembly/tool_packages.py` 构造 `ToolPackageApplyContext`；Tool package 先解析
`ResolvedToolPackageActivation` 再一次性 apply。P5 readiness 已覆盖
Access credential、OAuth account 与 daemon runtime，剩余口径继续升级为生产代码守卫。

P3 已完成项：

- Tool scanned package 已从两段装载收成单次 apply hook。
- `_build_tool_infrastructure()` 只负责 Tool core registries/gateway，不注册
  scanned package handler。
- `runtime_plan()` 在 owner module service/port 就绪后统一执行一次
  `tool.activate_packages`；直接 `ToolPackageApplyContext` 构造收在
  `app/assembly/tool_packages.py`。
- 架构测试已守住薄 `app/container.py` 不执行 tool package apply，且
  `app/assembly/tool.py` 只声明 activation task，`app/assembly/tool_packages.py`
  统一保留 `ToolPackageApplyContext` 与 `activate_tool_packages(...)`，防止
  `include_local=False` / `include_runtimes=False` 二段装载回潮。

P4 已落地项：

- `app/assembly/tool.py` 只声明 Tool package activation task；
  `app/assembly/tool_packages.py` 统一保留 `ToolPackageApplyContext` 与
  `activate_tool_packages(...)`；旧 `register_tool_namespaces(...)`
  入口已移除，不再作为兼容路径保留。
- native/local tool factory 已完成 openai_image、memory、workspace、command、sessions、
  skills、mobile、browser 的 manifest-driven typed deps 迁移。
- `OpenAIImageDeps(credential_provider=...)` 这类 typed deps 是目标形态；sessions 已用
  `session_runtime_control` port 取代旧 lookup lambda 与直接 Orchestration service deps。
- 依赖缺失不能继续通过 `getattr(container, "...", None)` 在 handler 内判断；required
  internal service dependency 应在 resolve/apply 阶段 fail-fast。

P5 已落地项：

- Tool execution path 已接入 `ToolAccessReadinessPort`，执行入口在创建/排队 run
  之前先检查 Tool manifest 声明的 credential/access requirements。
- Tool infrastructure 已提供 `AccessServiceToolReadinessAdapter`，由 Tool 声明
  requirement，Access 负责 binding/readiness/setup 真相。
- OpenAI image 工具缺少 `openai-api-key` binding 时，Tool/Access readiness 先返回
  setup 状态，执行入口拒绝排队，不再进入 handler 后才报错。
- OAuth account credential binding 已纳入同一 Tool readiness 门禁；binding 存在但
  account/token 不存在、失效或过期时，执行入口拒绝排队。
- Tool execution path 已接入 `ToolRuntimeReadinessPort`；缺 daemon service 或 daemon
  group readiness 时，执行入口在创建/排队 run 之前拒绝调用。
- Tool infrastructure 已提供 `DaemonServiceToolRuntimeReadinessAdapter`，支持
  `daemon:<service_key>` 与 `daemon-group:<group>` requirement。
- Tool package manifest 中的 `external_requirement` dependency 会同步投影为
  runtime readiness requirement，不会作为 handler factory deps 注入。
- Browser 工具目录已收敛为 `bundled.local_package.browser` source 下的 `browser.*`
  profile-context functions，source/function/prompt metadata 来自 `tools/browser/tool.yaml`；
  profile 诊断/启动由 Browser module query/control surface 和 daemon readiness 负责。
- Required internal service dependency 已在 Tool package apply 阶段 fail-fast；缺依赖时
  `build_runtime_services()` 不返回，后续 tool/orchestration runtime event service 不会构建。
- `GET /tools/{tool_id}/readiness` 暴露工具级 readiness；`POST /tools/{tool_id}/runs`
  对未就绪工具返回 409。
- Operations Tool read model 已优先读取 Tool service readiness，用于区分 credential
  setup required；daemon runtime readiness 也从同一工具 readiness 入口进入。
- Operations Tool 风险表已读取合并 Tool readiness，区分 Access 与 Runtime 分类，并把
  runtime readiness 问题导向 Daemon 运维面。

P5 当前剩余项：

- 无。P6/P7 已继续收窄 `app/container.py` / `AppContainer`，并补上防回潮守卫。

P6 已落地项：

- `_ToolInfrastructure` 已更名为 `_ToolCoreRuntimeHandle`，scanned package 列表以
  `tool_package_plans` 表达为待 apply 的安装计划，不再暗示二段注册状态。
- `AppContainer` 已移除 app assembly 内部 Tool registry 暴露面：
  `tool_discovery_registry`、`sandbox_tool_registry`。
- `AppContainer` 已移除 `credential_provider` 别名；Access 作为凭证治理能力的公开入口
  保持 `access_service`。
- `AppContainer` 已移除一批只属于 app assembly/infrastructure 的配置快照和 state handle：
  `channel_system_config`、`browser_system_config`、`browser_runtime_state_store`、
  `browser_profile_probe_service`、`mobile_system_config`、`mobile_state_root`、
  `mobile_runtime_state_store`、`daemon_state_root`、`daemon_spec_syncers`。
- Operations source read model 已从匿名 `SimpleNamespace` 收成显式
  `OperationsSourceReadModelContext`；context 只列出运维投影需要读取的 owner
  application/query service，不再携带未使用的 assembly config/store/audit 别名。
- Events read model 通过 `OperationsSourceReadModelContext` 的 observer runtime 引用读取
  运维观察者状态，避免旧的 materializer 构造后再给匿名 context 赋值但无法回灌的问题。
- 架构测试已钉住 runtime event service 构建顺序：Tool package apply、Access/Daemon
  readiness adapter 注入必须由 app assembly 显式声明；tool/orchestration/operations/event
  relay runtime event service 必须由 target-specific `runtime_plan()` 构建。
- 架构测试已钉住 Tool handler/runtime 路径不得持有 `AppContainer`、`SimpleNamespace`、
  `PortResolver`、`container` 或 `orchestration_*_lookup`。
- OpenAI image 工具已移除旧 `_legacy_deps` fallback；handler 只能接收
  `OpenAIImageDeps` 或 manifest-driven `ToolHandlerFactoryDeps`。
- runtime infrastructure、event runtime builder 和 core/runtime application service graph 已全部迁入
  `app/assembly/*`；薄 `app/container.py` 只包装 `ApplicationRegistry`。
- 架构测试已加入 `app/container.py` 120 行以内守卫，防止 runtime lookup facade 继续吸收基础设施细节。

handler lookup 迁移面：

- 当前允许存在的位置：无。Tool package apply 只接收 `ToolPackageApplyContext`；
  app assembly 主路径不得再构造 handler `SimpleNamespace`。
- 当前禁止扩散的位置：`src/crxzipple/modules/tool` 与 `tools/*` 的 handler/factory 不得把
  `SimpleNamespace`、`PortResolver`、`container`、`resolver` 当稳定依赖接口。
- 下一步迁移顺序：在已落地的 Access credential、OAuth account、daemon runtime
  readiness 与 internal dependency startup gates 之上，补 Operations Tool 页面状态分类。
- 验收口径：typed deps 迁移完成后，architecture tests 应从文档守卫升级为生产代码守卫，
  检查无二段装载、无 handler service locator、无 runtime lookup。

## 目标结构

```text
Tool module core
  owns: catalog, discovery registry, runtime registries, scheduler, worker, tool service graph
  exports: tool.execution, tool.catalog, tool.handler_registry/apply surface
  does not know: access, memory, orchestration, agent, session, browser, mobile

Access module
  exports: credential provider / readiness / setup / audit application ports

Memory module
  exports: memory query/context ports

Orchestration module
  imports: tool.execution
  exports: orchestration query/control/scheduler ports

Tool package
  owned by Tool module resource scanner
  declares handler specs and required dependencies
  receives explicit deps during apply
  returns final handler registrations
```

运行态目标：

```text
orchestration -> ToolExecutionPort
tool core -> no cross-module owner service
tool handler -> explicit constructor deps only
```

## P0. 现状基线与防回潮守卫

- [x] 新增 app assembly/module lifecycle 架构守卫测试，记录当前禁止项。
- [x] 守卫：`src/crxzipple/modules/tool` 与 `tools/*` 的 handler 运行路径不得持有 `AppContainer`。
- [x] 守卫：tool handler 构造不得接收 `SimpleNamespace`、`PortResolver`、`container`、`resolver` 这类服务定位器对象。
- [x] 守卫：tool handler 执行路径不得出现 `orchestration_*_lookup` 延迟查询。
- [x] 守卫：`app/container.py` 中不得构造 `register_tool_namespaces(SimpleNamespace(...))`；只能由已命名的 tool package activation task 触发 apply。
- [x] 补一份当前依赖图快照，标记 Tool local handler 实际依赖的 service/port。

验收：

```bash
rg -n 'apply_tool_package_plans\\(' src/crxzipple/app/assembly/tool_packages.py
rg -n 'SimpleNamespace\\(' src/crxzipple/app src/crxzipple/modules/tool tools
rg -n 'orchestration_.*_lookup|PortResolver|container\\.' src/crxzipple/modules/tool tools
PYTHONPATH=src pytest -q tests/unit/test_tool_access_architecture.py tests/unit/test_openai_image_tool.py
```

## P1. 引入统一 module lifecycle primitives

- [x] 新增 `src/crxzipple/app/module_lifecycle.py`。
- [x] 定义 app assembly 内部类型：
  - `ModuleRuntimeHandle`
  - `ModulePortExport`
  - `ModuleActivationPlan`
  - `ResolvedActivationPlan`
  - `ReadinessIssue`
  - `ReadinessReport`
- [x] 定义 assembly-only `PortRegistry`，仅用于 activation plan 解析，不下放给 module/handler。
- [x] 定义 activation plan 的依赖分类：
  - `service_dependency`：缺失即启动失败。
  - `external_requirement`：缺失进入 readiness/setup。
  - `optional_dependency`：缺失时禁用对应能力并记录原因。
- [x] 文档化 lifecycle 顺序：`construct -> export -> plan -> resolve -> apply -> readiness -> activate`。
- [x] 保持 domain/application/infrastructure DDD 边界不变；lifecycle 只在 app assembly boundary 使用。

验收：

```bash
PYTHONPATH=src python -m compileall -q src/crxzipple/app
PYTHONPATH=src pytest -q tests/unit/test_module_lifecycle.py tests/unit/test_app_assembly_registry.py
```

## P2. 拆出 Tool core 与 Tool package install plan

- [x] 新增 `src/crxzipple/modules/tool/application/activation.py`。
- [x] 新增 Tool install plan 类型：
  - `ToolPackagePlan`
  - `ToolHandlerPlan`
  - `ToolRuntimePlan`
  - `ToolOpenApiPlan`
  - `ToolDependencyRequirement`
  - `ToolHandlerRegistration`
- [x] `tool_packages.py` 保留 `tools/*/tool.yaml` 解析职责，并新增 plan API；旧注册 API 已移除。
- [x] Tool module 解析 `tool.yaml`，module lifecycle/kernel 不直接解析 tool resource。
- [x] `tool.yaml` 中 native/local tool 的 credential requirement 继续归 Tool manifest contract，不升级为 module descriptor。
- [x] `LocalToolRuntimeRegistry`、`ToolRuntimeRegistry`、`ToolDiscoveryRegistry` 的创建留在 Tool core。
- [x] Tool core 构建时不注册任何 scanned package handler。

验收：

```bash
PYTHONPATH=src pytest -q tests/unit/test_tool_catalog.py tests/unit/test_tool_providers.py
PYTHONPATH=src pytest -q tests/unit/test_tool_settings_integration.py tests/unit/test_openapi_access.py
```

## P3. Tool package 单次 apply

- [x] 移除 `_build_tool_infrastructure()` 中的 scanned package `register_tool_namespaces(...)`。
- [x] 移除 `_build_runtime_services()` 中的第二次 scanned package `register_tool_namespaces(...)`。
- [x] 新增明确的 `resolve_tool_package_activations(...)`：只解析 install/apply activation。
- [x] 新增明确的 `apply_tool_package_plans(...)`：一次性安装 local/openapi/runtime handlers。
- [x] 调整 `runtime_plan()` 顺序：
  - 构建 Tool core。
  - 构建 core services。
  - 构建 Tool service graph，导出 `ToolExecutionPort`。
  - 构建 Orchestration service graph，注入 `ToolExecutionPort`。
  - 所有 owner module service/port 就绪后，执行 Tool package apply。
  - readiness 通过后再启动 runtime event service、worker、scheduler、executor。
- [x] 内置 OpenAPI provider 与 settings 配置型 OpenAPI provider 的装载路径分清：配置型 provider 仍由 Tool config 管理，scanned package 只在 package apply 阶段装载；重复 provider/runtime 注册 fail-fast，不静默覆盖。
- [x] 对同一 namespace/tool id 重复安装做 fail-fast 或 idempotent guard，不能静默覆盖 handler。

验收：

```bash
rg -n 'apply_tool_package_plans\\(' src/crxzipple/app/assembly/tool_packages.py
PYTHONPATH=src pytest -q \
  tests/unit/test_tool_catalog.py \
  tests/unit/test_tool_providers.py \
  tests/unit/test_tool_access_architecture.py \
  tests/unit/test_access_tool_integration.py \
  tests/unit/test_openai_image_tool.py
```

## P4. Handler factory 显式依赖化

- [x] 替换 `_build_local_handler(entrypoint, container)` 风格接口。
- [x] 每个 native/local tool factory 声明自己的 required deps，不接收 resolver/container。
- [x] OpenAI image 已先迁移为 manifest-driven factory deps：`tools/openai_image/tool.yaml` 声明 `credential_provider` / `artifact_service` / image config，`tool_packages.py` 不再按 `namespace == "openai_image"` 特判。
- [x] Factory 接收 typed deps 或明确字段对象，例如：

```python
@dataclass(frozen=True)
class OpenAIImageDeps:
    credential_provider: CredentialProvider
```

- [x] OpenAI image handler 构造后只持有 `OpenAIImageDeps`，执行路径不查 `container`、`access_service` 或默认环境 resolver。
- [x] Memory local tools 已迁移为 manifest-driven factory deps：`memory_runtime_service` 缺失时 apply 阶段 fail-fast，工具不再直接组合 file service 与 context resolver。
- [x] Workspace/command local tools 已迁移为 manifest-driven factory deps：`session_workspace_lookup` 与 `process_service` 不再由 handler 执行路径动态查 container。
- [x] Sessions local tools 已迁移为 manifest-driven factory deps：`session_service` 与 `session_runtime_control` 由 apply 阶段解析；Tool 不再命名或接收 Orchestration services。
- [x] Skills local tool 已迁移为 manifest-driven factory deps：只依赖 `skill_manager`；不再把 local runtime registry 暴露成 skill tool 依赖。
- [x] Mobile local tools 已迁移为 manifest-driven factory deps：`mobile_facade` 与 `mobile_result_serializer` 缺失时 apply 阶段 fail-fast。
- [x] Browser local tools 已迁移为 manifest-driven factory deps：browser runtime/profile deps 由各 tool manifest 声明，执行路径不再查 `container`。
- [x] 删除 `orchestration_*_service_lookup`；sessions 工具通过 Session application 暴露的 `session_runtime_control` port 表达运行控制能力，Orchestration-backed 实现在 Tool 之外装配。
- [x] Browser/mobile/process/memory/session/skill 工具逐个改为 typed deps。
- [x] app assembly 主路径不再用 `getattr(container, "...", None)` 判断 handler 依赖；缺 required dep 在 resolve/apply 阶段失败。
- [x] 对已声明 dependency 的 Tool package，缺 required service dependency 在 apply 阶段 fail-fast。

验收：

```bash
rg -n 'getattr\\(container|SimpleNamespace|orchestration_.*_lookup|container\\.' \
  src/crxzipple/modules/tool tools
rg -n 'namespace == "openai_image"|namespace != "openai_image"' \
  src/crxzipple/modules/tool/infrastructure/tool_packages.py
PYTHONPATH=src pytest -q \
  tests/unit/test_openai_image_tool.py \
  tests/unit/test_tool_access_architecture.py \
  tests/unit/test_tool_providers.py
```

## P5. Readiness 与外部资源治理

- [x] Tool package apply/execute 阶段区分 internal service dependency 与 external credential readiness。
- [x] 缺 internal service dependency：启动/激活失败，不启动 worker/orchestration executor。
- [x] 缺 Access credential binding：工具保留在 catalog，Tool/Access readiness 显示 setup 状态，执行入口拒绝排队。
- [x] 缺 OAuth account/token：工具保留在 catalog，Tool/Access readiness 显示 setup 状态，执行入口拒绝排队。
- [x] 缺 daemon readiness：工具保留在 catalog，readiness 显示 `setup_needed` 或 `degraded`，执行入口拒绝排队。
- [x] OpenAI image 工具不再在 handler 调用后返回 `OpenAI image tools require Access credential binding.`；该状态提前出现在 Tool/Access readiness。
- [x] Access requirement catalog 与 Tool catalog 的 readiness 链接保持唯一来源：Tool 声明 requirement，Access 管 binding/readiness/setup。
- [x] Operations Tool 页面显示 credential setup required 与 external runtime degraded/setup needed 的不同状态；service dependency failure 保持启动失败，不在运行面伪造状态。

验收：

```bash
PYTHONPATH=src pytest -q \
  tests/unit/test_access_tool_integration.py \
  tests/unit/test_openai_image_tool.py \
  tests/unit/test_tool_http.py \
  tests/unit/test_access_read_models.py \
  tests/unit/test_ui_access_http.py
```

## P6. Container 降噪与 AppContainer 收窄

- [x] `runtime_plan()` / app assembly 保留 composition root 职责，但不手写具体 tool handler 的构造。
- [x] `_ToolInfrastructure` 更名/收窄为 Tool core runtime handle，不携带 scanned namespace 注册状态。
- [x] `_RuntimeServices` 不再承担 tool package 二次注册。
- [x] `AppContainer` 字段分批收窄，优先把仅 app assembly 内部需要的 registry/store 从公开字段中移除。
- [x] browser/mobile/daemon/ocr 基础设施 builder 迁入 `app/assembly/*`。
- [x] event backend、event contract registry、event definition registry 与 runtime event service builder 迁入
  `app/assembly/events.py` / `app/assembly/event_runtime.py`。
- [x] core/runtime application service graph 迁入 `app/assembly/runtime.py` 及各 module assembly 文件。
- [x] Operations projection context 中继续可以聚合 owner services，但不能成为通用业务服务定位器。
- [x] runtime event service、worker、scheduler、executor 的启动必须晚于 readiness。

验收：

```bash
PYTHONPATH=src python -m compileall -q src/crxzipple
PYTHONPATH=src pytest -q tests/unit/test_app_assembly_architecture.py tests/unit/test_operations_observation.py
```

## P7. 回归测试与端到端验收

- [x] 增加测试：tool namespace 只扫描一次，local/openapi/runtime handler 只 apply 一次。
- [x] 增加测试：重复 tool id/namespace 不会静默覆盖。
- [x] 增加测试：OpenAI image handler 构造后直接持有 `credential_provider`，不在执行时查 container/resolver。
- [x] 增加测试：缺 required internal dependency 时 activation fail-fast。
- [x] 增加测试：缺 `openai-api-key` binding 时工具 catalog/readiness 提前显示 setup required，执行入口拒绝排队。
- [x] 增加测试：HTTP `GET /tools/{tool_id}/readiness` 与 `POST /tools/{tool_id}/runs` 对缺 Access requirement 工具返回一致的未就绪状态，且不创建 run。
- [x] 增加测试：缺 OAuth account/token 时 Tool readiness 提前显示 setup required，执行入口拒绝排队。
- [x] 增加测试：缺 daemon readiness 时 Tool readiness 提前显示 setup needed，执行入口拒绝排队；daemon ready 后可正常执行。
- [x] 增加测试：orchestration 构建只依赖 `ToolExecutionPort`，不依赖 tool handler install 状态。
- [x] 增加测试：tool background worker 和 orchestration executor 只在 readiness 后启动。

建议回归命令：

```bash
git diff --check
PYTHONPATH=src pytest -q \
  tests/unit/test_openai_image_tool.py \
  tests/unit/test_tool_providers.py \
  tests/unit/test_tool_catalog.py \
  tests/unit/test_tool_access_architecture.py \
  tests/unit/test_access_tool_integration.py \
  tests/unit/test_openapi_access.py
PYTHONPATH=src pytest -q \
  tests/unit/test_orchestration.py \
  tests/unit/test_orchestration_worker.py \
  tests/unit/test_app_assembly_architecture.py
cd frontend && npm run typecheck
cd frontend && npm run build
```

## 施工顺序

1. 先做 P0，建立守卫和现状依赖图，避免继续扩大 service-locator/lookup。
2. 做 P1，补最小 lifecycle primitives，但不急着迁所有 module。
3. 做 P2/P3，只收 Tool 装载链路：先让 scanned packages 单次 plan/apply。
4. 做 P4，逐个 handler 改 typed deps，先从 OpenAI image、memory、browser/mobile、orchestration 相关工具开始。
5. 做 P5，把“能否调用”提前到 readiness，不再让用户调用后才看到缺凭证。
6. 做 P6，收窄 `app/container.py` 和 `AppContainer`，避免新的服务定位器产生。
7. 做 P7，补齐回归和人工验收，再移除临时兼容路径。

## 完成定义

- `app/container.py` 不参与注册 scanned tool package；Tool package 只通过 activation task 单次 apply。
- `tools/*` handler 不接收 container/resolver/SimpleNamespace。
- Tool core 不 import 或持有 access/memory/orchestration/session/skill/browser/mobile owner service。
- Orchestration 只通过 `ToolExecutionPort` 调用 Tool。
- 内部 service dependency 缺失时启动失败；外部资源缺失时 readiness 明确显示 setup/degraded。
- OpenAI image、OpenAPI tool、memory/browser/mobile/process/session/skill 等内置工具均通过单次 apply 安装。
- Operations/Settings 页面显示的工具可用性来自 readiness，不来自运行时错误兜底。
