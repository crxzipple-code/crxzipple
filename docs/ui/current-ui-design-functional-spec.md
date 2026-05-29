# 当前 UI 设计稿功能信息总结

本文档来自对 `docs/ui` 下当前 PNG 设计稿的重新阅读，用来作为后续前端和后台设计的施工基准。

## 结论先行

旧版 UI 评审和启动计划已清理，不再作为当前验收标准。当前前端和后台设计应以这些 PNG 设计稿为主：

- `docs/ui/workbench.png`
- `docs/ui/trace.png`
- `docs/ui/trace-graph.png`
- `docs/ui/operations/*.png`
- `docs/ui/settings/*.png`

这套 UI 不是把旧 overview 换一层颜色。它表达的是完整 Agent Runtime 控制台：

- Workbench 是运行态工作台，服务日常 run / turn 执行、干预、结果和关联资产查看。
- Trace 是跨模块事件链路定位工具，服务 timeline、graph、inspector、payload、linked entity 和故障归因。
- Operations 是各运行模块的运维台，每个模块有独立运营问题、表格、队列、异常和恢复动作。
- Settings 是配置管理台，服务 profiles、catalogs、assets、contracts、defaults、environment、audit 和 backup。

后台不能只提供几个 overview count。前端也不能在浏览器里拼接安全关键事实。后续应围绕页面需要的 read model、action route、validation、audit、trace link 来设计。

## 全局信息架构

### 顶层导航

顶层为四个主入口：

- `Workbench`
- `Operations`
- `Trace`
- `Settings`

导航项上有未处理数量 badge，例如 Operations `2`、Trace `3`。右上角固定包含搜索、通知、用户身份和权限状态。Operations 中还显示当前角色，例如 `Admin (可操作)`，这意味着动作可用性必须由后端权限结果驱动。

### 共同 UI 模式

所有页面都采用深色控制台风格，但功能结构不是单一模板：

- 左侧导航或筛选栏用于确定上下文。
- 中间是主数据面板，通常是指标卡、表格、时间线、图或编辑器。
- 右侧是 inspector、summary、quick actions 或安全动作区。
- 多数页面支持 `View in Trace`、`View in Workbench`、`Open Operations`、`View Artifact` 这类跨面跳转。
- 行级操作、危险操作和配置变更都需要权限、确认、审计。
- 状态以 `Healthy / Warning / Error / Running / Failed / Active / Draft / Inactive` 等稳定枚举呈现，不应由前端从原始日志推断。

### 共同后台契约

这些页面至少需要一组跨模块共享契约：

- `TraceContext`：trace_id、run_id、session_key、turn_id、step_id、event_id、tool_run_id、llm_invocation_id 等。
- `LinkedEntity`：实体类型、id、display name、owner module、跳转目标、复制值。
- `RuntimeAction`：动作 id、label、owner module、风险等级、权限状态、审计要求、执行 endpoint。
- `ModuleHealthSummary`：健康、告警、错误、最近更新时间、降级状态。
- `ConfigResolution`：配置来源、继承层级、覆盖路径、effective value、resolution trace。
- `ValidationResult`：配置校验、契约校验、连接测试、dry-run 结果。
- `AuditRef`：操作人、时间、资源、变更 diff、理由、IP/user agent。

## Workbench

### 页面定位

Workbench 是 Agent run 的日常操作台，不是聊天页。它把用户输入、turn 切换、执行步骤、工具调用、产物、进度、暂停/停止和追踪入口放在同一上下文里。

### 主要区域

左侧 `Threads`：

- 新建任务按钮。
- 任务筛选：全部、运行中、已完成、失败。
- 任务卡片包含标题、Agent、状态、当前步骤、等待授权/错误原因、更新时间。
- 底部有帮助、设置和当前用户。

中间 run 面板：

- 顶部连接状态和最近更新时间。
- run header 包含封面/产物预览、标题、运行状态、开始时间、运行时长、工具调用次数、Agent、Model、停止运行和更多菜单。
- turn 横向切换，展示当前 Turn 和历史 Turn 的状态、耗时。
- 主体可在执行步骤和时间视图之间切换。
- 执行步骤包括 `User Input`、`LLM Thinking`、`Tool Call`、`Tool Result`、`Final Response`。
- tool result 支持展示 artifact 缩略图、文件名、分辨率、大小，并提供查看大图和查看 trace。
- 底部有当前进度条、已运行时间、预计剩余时间、排队时长。
- 输入区支持继续对话、工具菜单和发送。

右侧 inspector：

- tabs：Overview、Debug、Memory、Agent。
- 运行概览展示状态、运行时长、开始时间、工具调用、LLM 调用、tokens、预估费用。
- 当前 Turn 摘要展示正在使用的工具、进度和摘要文本。
- 关联资产列出 Tool Run、LLM Invocation、Artifact。
- 快捷操作包括查看 Trace、在 Operations 中查看、导出当前 Run。

### 后台设计含义

Workbench 需要一个面向 run 的聚合读模型，而不是前端拼接多个底层接口：

- run 列表和筛选统计。
- run detail、turn list、current turn、step timeline。
- step 级状态、耗时、owner、输入摘要、输出摘要、错误摘要。
- artifact summary 和 preview metadata。
- linked entities 和 trace link。
- progress、estimated remaining、queue delay。
- 可执行动作：new run、send message、stop run、resume/continue、open artifact、export run。

写操作应回到 owner module，例如 run 控制属于 orchestration，artifact 查看属于 artifacts，tool 详情属于 tool，权限判断属于 authorization/access。

## Trace

### 页面定位

Trace 是跨模块链路定位工具。它需要同时支持按时间排查和按因果图排查。

### Timeline 视图

左侧 `Search & Filter`：

- Timeline / Graph 视图切换。
- 快速搜索，支持 ID、关键词、错误。
- 常用 ID：Trace ID、Run ID、Session Key、Tool Run ID、LLM Invocation ID、Event ID、Artifact ID。
- 时间范围选择。
- 结果状态筛选：Success、Partial、Failed、Cancelled、Running。
- Event Family 筛选：Channel、Orchestration、LLM、Tool、Events、Observation。
- 仅显示关键事件 toggle。

中间 timeline：

- trace header 支持复制 trace id、View in Workbench、Export。
- trace summary 展示 session、run、turn、结果、开始时间、耗时、事件数、过滤状态。
- 表格列包括本地时间、相对开始、事件、关联实体。
- 事件行展示 owner、surface_id、family、实体 id 和复制按钮。

右侧 Event Inspector：

- 上下事件切换。
- 事件状态、类型、标签。
- tabs：Overview、Payload、Logs、Events、Linked。
- 基本信息包括 Event ID、Event Name、Family、Timestamp、Duration、Owner、Surface ID、Source Event、Observation ID、Caused By。
- 关联实体包括 Tool Run、Run、Session Key、Turn ID。
- 快捷操作包括打开 Workbench、打开 Tool Operations、打开 LLM Operations、查看 Artifact、复制 cURL。

### Graph 视图

Graph 视图表达跨模块因果：

- 支持布局、分组、显示事件名称、耗时、ID。
- 支持缩放、适配视图、minimap。
- 按 lane/group 展示 Channel、Orchestration、LLM、Tool、Events、Observation、Error。
- 节点包含事件名称、owner/service、实体 id、耗时、成功/失败状态。
- 边区分因果关系和影响关系。
- 右侧 inspector 在失败节点上展示错误码、错误信息、组织、模型、请求 ID 等摘要。

### 后台设计含义

Trace 后台需要事件流 read model 和 graph read model：

- timeline events，支持搜索、时间、状态、family、owner、key_event 过滤。
- graph nodes/edges/lane read model。
- event payload、payload diff、logs、linked events。
- linked entity resolver。
- payload 脱敏和访问控制。
- `copy as cURL` 所需的可复现请求摘要。

Trace 不能直接消费 raw event stream 后在前端做完整因果推断。后端应给出稳定 timeline 和 graph read model。

## Operations

### Operations 共同结构

Operations 左侧是模块导航，每个模块有健康、告警、错误计数：

- Orchestration
- Tool
- LLM
- Access
- Channels
- Memory
- Skills
- Events
- Daemon

页面顶部包含 last updated、auto refresh、View in Trace、当前角色。每个模块页都有自己的指标卡、tabs、表格、异常队列和动作，不应复用一套空泛 overview。

### Orchestration

页面定位：调度总览，关注队列、锁、worker、approval、失败 run。

关键数据：

- Overall Health、Ingress Queue、Active Runs、Run Queue、Backpressure、Approval Waiting、Failed。
- Scheduler Status：event loop、last tick、tick lag、dispatch latency、queue age、throughput、success rate。
- Backpressure by reason：lane lock、worker、approval、access、executor busy、other。
- Stuck Runs：queued > 5m、running no events、lane lock expired、worker lease expired。
- Policy & Limits：per-lane concurrency、global concurrency、worker capacity、approval timeout、lease timeout、lane lock TTL、queue retention。
- Run Queue 表：priority、run id、lane key、enqueued at、agent target、wait reason、wait time、actions。
- Lane Locks、Executor Overview、Ingress Queue、Recent Failures、Ops Event Log。

动作：

- Open Run
- Open Trace
- Cancel Run
- Requeue
- Force Release Lane

后台需要 scheduler snapshot、queue snapshot、lane lock state、executor leases、stuck run detector、failure summary、ops event log 和受权限保护的调度动作。

### Tool Runtime

页面定位：工具调用运行态，关注 tool run、worker、等待原因、产物、策略和 access block。

关键数据：

- Overall Health、Tool Runs、Running、Waiting、Failed、Avg Duration。
- tabs：Tool Runs、Workers、Running Tools、Waiting Tools、Failed Tools、Long Running、Artifacts、Strategies。
- Recent Tool Runs：time、tool、run id、source run/step、status、execution mode、holds worker、duration、result/output。
- Tool Types by runs。
- Auth Missing / Access Blocked。
- Worker Pool Overview。
- Tool Queue grouped by reason。
- Long Running Tool Runs。
- Inline Risk。
- Failed Tools。
- Recent Artifacts。

后台需要 tool run 索引、worker pool、工具类型统计、执行模式、等待原因、access blocking link、artifact link、策略和 inline 风险统计。

### LLM Runtime

页面定位：LLM 调用运行态，关注 provider、resolver、rate limit、streaming、token、latency、错误。

关键数据：

- Overall Health、Invocations、Tokens、Streaming、Errors、Avg Latency。
- Provider Access & Health。
- Provider Auth / Access Blocked。
- Model Resolver。
- LLM Rate Limiter。
- Streaming Requests。
- Recent Invocations。
- Latency、Token Usage、Invocation Rate charts。
- Stream Health。
- Execution Blocking Risk。
- Token Usage / Pricing。
- Fallback / Resolver Problems。
- Context Window Pressure。
- Model Availability。
- Error Summary。

后台需要 invocation index、provider/model availability、resolver decision、fallback chain、rate limiter state、stream state、token accounting、latency metrics、pricing/source config 和错误分类。

### Access

页面定位：访问与凭证管理中心的运行态视角，关注缺失、过期、认证失败和授权阻塞。

关键数据：

- Access Assets、Missing Access、Expiring Soon、Auth Success Rate、Failed Auth。
- tabs：Overview、Requirements、Access Assets、Missing Access、API Keys、OAuth Connections、Auth Status、Setup Flows、Usage。
- Requirements 表：consumer、module、slot、expected kind、binding、readiness、setup、last checked、actions。
- Missing Access 表：asset/requirement、kind、status、required by、slot、last failed、affected、impact、actions。
- Credential Health。
- Provider Auth / Access Blocked。
- Credentials by Kind。
- Expiring Soon。
- Auth Success Rate。
- Authentication Status。
- Access Usage。
- Recent Access Events。
- Fallback / Resolver Problems。
- Setup Flows。

后台需要凭证元数据读模型和 requirement catalog，不能返回 secret。还需要 consumer linkage、slot binding、认证验证状态、过期/轮换状态、setup flow registry、access audit 和重试/设置动作。

### Channels

页面定位：渠道运行与消息中心，关注 intake、delivery、retry、dead letter 和 run/turn/session 绑定。

关键数据：

- Messages In、Messages Out、Delivery Success Rate、Retrying、Dead Letter。
- tabs：Overview、Web/SSE、Feishu/Lark、Webhook、Intake Events、Delivery Events、Retries、Dead Letter。
- Channel Status。
- Message Flow：intake、processing、delivery、outcome。
- Delivery Trend。
- Top Channels by Volume。
- Dead Letter Queue。
- Recent Messages。
- Failures by Category。
- Channel Bindings。

后台需要 intake/delivery 事件索引、channel binding、message normalization、retry state、dead letter actions、message to run/turn/session link。

### Memory

页面定位：记忆与知识管理运行态，关注 store、index、retrieval、write/flush、source scan。

关键数据：

- Memory Stores、Index Health、Source Documents、Chunks/Vectors、Retrieval Hit Rate、Write/Flush Success、Errors。
- tabs：Overview、Stores、Sources、Index Jobs、Retrieval Logs、Write/Flush、Source Files、Errors。
- Memory Stores 表。
- Index Health 和 Index Jobs。
- Retrieval Performance。
- Retrieval Trace。
- Write / Flush。
- Memory Usage。
- Recent Retrieval Logs。
- Source Scan Status。
- Source Files。

后台需要 store/source/index/job/retrieval/write read models，支持 run/turn/step link，并对 query、document、chunk 内容做脱敏。

### Skills

页面定位：技能解析与包健康，关注 installed/available、capability、access requirement、resolver、conflict。

关键数据：

- Installed Skills、Available Skills、Resolution Success Rate、Missing Capabilities、Resolution Failures。
- tabs：Overview、Installed Skills、Available Skills、Resolutions、Requirements、Missing Capabilities、Conflicts/Overrides、Versions、Categories、Configuration。
- Recently Resolved Skills。
- Resolution Outcomes。
- Top Used Skills。
- Missing Capabilities。
- Access Requirements。
- Capability Requirements。
- Resolution Logs。
- Resolver Detail。
- Import / Normalize。
- Skill Package Sources。
- Conflicts / Overrides。
- Profile Usage。
- Skill Inspector。

后台需要 skill package registry、manifest、capability requirement、access requirement、resolver trace、compatibility、trust/safety metadata 和 profile usage。

### Events

页面定位：事件契约与运行健康，关注生产、投递、订阅、观察、dead letter、contract compatibility。

关键数据：

- Total Events、Ingested、Delivered、Delivery Success Rate、Dead Letters、Subscription Lag、Observer Failures。
- tabs：Overview、Event Stream、Owners、Surfaces、Topics、Subscriptions、Observers、Contracts、Registry、Dead Letters、Mappings、Settings。
- Events Over Time。
- Events by Surface。
- Owners by Volume。
- Contract Compatibility。
- Recent Events。
- Consumer Health。
- Observer Mapping Failures。
- Topics、Subscriptions、Observers、Dead Letters。
- Event Inspector。

动作：

- Replay Original
- Retry Delivery
- Retry Observation
- View payload JSON
- View in Trace

后台需要 event stream metrics、topic/subscription/observer health、contract registry linkage、dead letter queue、observer mapping failure、脱敏 payload 和 replay/retry/reobserve 动作。

### Daemons

页面定位：Runtime 进程与服务集管理，关注 service set、process、dependency、drain、restart、heartbeat。

关键数据：

- Service Sets、Processes、Healthy、Unhealthy、Restarts、Uptime、Last Heartbeat。
- tabs：Overview、Service Sets、Processes、Logs、Metrics、Health Checks、Dependencies、Configuration、Alerts、Audit。
- Service Sets。
- Drain Overview。
- Dependency Health。
- Processes 表，支持 service set、status、node 过滤和 column 配置。
- Process Health。
- Restart Summary。
- Quick Actions：Start、Stop、Restart、Drain、Reload Config。
- Links to Operations。

后台需要 daemon process/service set/dependency/health check read model，以及受权限保护的进程动作和审计。

## Settings

### Settings 共同结构

Settings 是配置管理台。它和 Operations 的区别是：

- Settings 展示配置、契约、资产、默认值、环境、审计、备份。
- Operations 展示运行时健康、队列、阻塞、失败和恢复。

Settings 页面共同模式：

- 左侧配置导航。
- 列表加详情编辑。
- 右侧 summary、resolution preview、validation 或危险动作区。
- Save Changes、Import/Export、Validation/Dry Run、Audit History。
- 系统 contract 通常只读，自定义 extension 才可创建或编辑。
- 所有变更要有 validation、impact、audit。

### Settings Overview

关键数据：

- Read-only Contracts。
- Editable Configurations。
- Agent Profiles、LLM Profiles、Tools、Skills、Channels、Events、Access Assets counts。
- Configuration Health。
- Recent Changes。
- Configuration Distribution。
- Configuration Issues。
- Configuration Inheritance。
- Configuration Sources & Versioning。
- Quick Actions。
- Useful Links。

后台需要 settings 聚合索引、配置健康、问题列表、最近变更、分布统计、继承摘要、版本同步状态。

### Agent Profiles

页面定位：定义 agent 行为、runtime、policy。

关键数据：

- Agent profile 列表：name、default LLM、fallback LLM、status、scope、updated、access grants。
- detail tabs：Basic Information、LLM Configuration、Runtime Preferences、Access Grants、Tool Policy、Memory & Context、Run Scope & Limits、Effective Configuration、Validation。
- Profile Actions：clone、export YAML、compare、archive。
- Summary：overview、access grants、metadata。
- Run Scope、Access Grant Scope、Change Impact。
- Profile Resolution Trace。
- Validation Summary。

后台需要 profile CRUD、profile resolution、access grant summary、scope evaluation、change impact 和 validation。Skill package、manifest、enablement 与 applicability 留在 Skills/Skill Enablement 面。

### LLM Profiles

页面定位：管理 LLM owner module 持有的模型配置。Settings 页面只作为业务视图入口，真相、写入和运行探测都走 LLM 模块 API。

关键数据：

- LLM profile 列表：id、provider、api family、model、model family、context window、capabilities、Access credential binding id、concurrency limit、enabled status。
- Profile detail：provider、api family、model、context、timeout、concurrency、Access credential binding id、capabilities、default params。
- Owner actions：通过结构化表单新增、保存、enable、disable profile；普通用户不直接编辑 JSON；凭证字段必须从 Access 已登记的 credential binding 下拉选择，不能手填 `env:` / `file:`。
- Probe：通过 `/llms/{id}/invoke` 运行最小探测，并展示 status、finish reason、usage、request id、文本或错误。

后台依赖 `/llms`、`POST /llms`、`/llms/{id}`、`PUT /llms/{id}`、`/llms/{id}/enable|disable`、`/llms/{id}/invoke`，以及 `/ui/access` 提供 Access credential binding 选项。LLM Profile 只保存 `credential_binding_id`，不得直接保存 `env:` / `file:` / `codex_auth_json` 等凭证来源；来源真相属于 Access credential binding。Provider health、usage diagnostics、版本、审计、resolution trace 如果需要展示，必须来自 LLM/Operations/Audit 的真实 API；不能在 Settings 前端合成。secret readiness 仍由 Access 管理。

### Tool Catalog

页面定位：工具发现、注册和工具运行契约管理。

关键数据：

- tabs：All Tools、Built-in Tools、Custom Tools、Imported Packages、Deprecated。
- tool 列表：source、type、runtime strategy、exec mode、category、status、risk、version。
- detail tabs：Basic Information、Input Schema、Output Schema、Runtime Strategy、Authentication & Access、Effects & Requirements、Capabilities Provided、Runtime Backend、Risk & Approval、Supported Surfaces、Artifact Output、Testing & Debug、Version History、Changelog。
- Credential Requirements / Required Access Assets：显示 slot、expected kind、provider、binding、readiness 和 setup 入口；普通用户不能粘贴 raw secret。
- Used by Skills。
- Capabilities Provided、Required Effects、Risk & Approval、Supported Surfaces、Artifact Output。
- Effective Configuration Preview。
- Contract Test。

后台需要 tool definition registry、schema storage/test、runtime strategy、access/effect/risk contract、capability mapping、artifact contract 和 test result。

### Skill Catalog

页面定位：可复用技能包和技能契约管理。

关键数据：

- tabs：All Skills、My Skills、System Skills、Deprecated。
- skill 列表：category、capability requirements、access requirements、supported surfaces、status、version、owner/package。
- detail tabs：Overview、SKILL.md Preview、Input Contract、Output Contract、Capability Requirements、Access Requirements、Memory & Context、Supported Surfaces、Required Files/Resources、Runtime Settings、Testing & Debug、Version History、Change Log。
- Capability Requirements。
- Access Requirements。
- Supported Surfaces。
- Resolution Preview。
- Required Files / Resources。
- Compatibility。
- Skill Package Source。
- Contract Test。
- Effective Configuration Preview。

后台需要 skill manifest、package source、contract metadata、resolver mapping、access/capability evaluation、resource list、compatibility 和测试结果。

### Skill Draft Review

页面定位：审阅由 agent 或人工创建的 governed skill draft。它不是直接编辑 skill package 文件的入口，而是 Skills owner module 的 draft lifecycle 控制面。

关键数据：

- Draft 队列：draft id、skill name、intent、status、target source/scope、actor、created by run/turn、updated、validation readiness。
- Draft 详情：manifest 摘要、SKILL.md body preview、support files、requirements、target owner source、base fingerprint、reason。
- Validation：errors、warnings、missing tools、missing access、missing authorization effects、unsupported surfaces/platforms、readiness status。
- Diff：manifest diff、instructions unified diff、support file diffs、summary。
- Lifecycle actions：Create Draft、Update Draft、Validate、Build Diff、Apply、Reject、Delete。
- Apply 风险提示：owner truth write、readonly/system source、base fingerprint conflict、missing validation、missing diff。
- Trace / Workbench links：created_by_run_id、created_by_turn_id、draft lifecycle events、approval request。

交互约束：

- 列表只承担选择和筛选，不展示大段 diff 或 instructions。
- 详情区需要足够空间展示 validation 和 diff，不应嵌套多层卡片。
- Apply 必须走 authorization approval，普通保存/validate/diff/reject 走 Skills application action 并记录 audit。
- 删除 draft 只删除 draft truth，不删除已 apply 的 owner package。
- 已 applied/rejected/expired 的 draft 应只读，除 delete 外不允许继续 update。

后台需要 `/skills/drafts` CRUD、validate、diff、apply、reject、delete，以及 draft audit/readiness/projection。Settings 前端只调用 Skills application API，不直接写 skill package 文件，也不从 Operations projection 反推 draft truth。

### Memory Config

页面定位：配置 memory stores、source、index、policy、retrieval strategy。

关键数据：

- tabs：Memory Stores、Retrieval Strategies、Memory Policies、Embedding Models。
- store 列表：type、backend、scope、status、consumers、last updated。
- detail tabs：Basic Information、Source Configuration、Indexer Configuration、Retrieval & Query、Retention & TTL、Namespace / Partitioning、Access & Security、Lifecycle、Monitoring & Usage、Consumers & Requests、Advanced Options、Change Log。
- Quick Actions：Rescan Sources、Rebuild Index。
- Danger Zone：Delete Store Data。
- Consumers、Memory Injection Impact、Policy Resolution Preview、Store Lifecycle & Health。

后台需要 memory config CRUD、store lifecycle action、index/source scan action、policy resolution、consumer list、health linkage 和高风险动作审计。

### Access Assets

页面定位：管理 API keys、tokens、credentials、OAuth、certificates 等外部访问资产。

关键数据：

- tabs：All Assets、API Keys、OAuth Connections、Secrets、Certificates。
- asset 列表：asset id、type、provider/service、environment、status、validation、required by、last used、expires、owner。
- detail tabs：Overview、Credentials、Permissions & Scope、Usage & Invocations、Rotation & Expiry、Validation & Health、Setup & Integration、Audit Logs。
- Test Connection、Rotate、Revoke。
- Consumers、Usage、Validation & Health、Affected Runs / Blocked Consumers。
- Policy Resolution Preview。
- Credential Binding Registry：通过 Access action 登记 env/file/codex auth json 等 server-side source reference；不得在 UI 收集或提交 raw secret。其他模块（如 LLM Profile、Tool Provider、Channel Account）只选择 `credential_binding_id` 或 OAuth account 引用。
- Credential Requirement Catalog：展示 Tool / Channel / LLM / Memory 等模块声明的 credential requirements，包括 consumer、slot、expected kind、provider、binding、readiness、setup flow 和最近审计。
- Danger Zone：rotate secret now、revoke、disable、invalidate sessions、delete reference。

后台需要 secret-safe metadata，不能返回 secret。还需要 validation、rotation、usage、consumer mapping、policy resolution、blocked consumers、危险动作权限和审计。配置类写入必须通过 Access action / Settings audit 边界落地，运行时 readiness 和 setup session 仍归 Access。

### Channel Profiles

页面定位：配置渠道接入、投递、路由、绑定和消息映射。

关键数据：

- channel 列表：Web Chat、Lark、Slack、WhatsApp、Webhook、Email。
- tabs：General、Authentication、Configuration、Runtime Binding、Message Mapping、Delivery & Retry、Permissions、Monitoring。
- Basic Information。
- Surfaces：intake surface、delivery surface。
- Credential Requirements / Required Access Assets。
- Routing Rules。
- Run / Turn Binding Preview。
- Allowed Actions Policy。
- Delivery Policy。
- Callback / Webhook Health。
- Message Mapping Preview。
- Mapping Contract Test。
- Sample Payloads。

后台需要 channel profile CRUD、routing/binding dry-run、mapping preview/test、delivery policy、credential requirement slots、access asset link、callback health 和 authorization policy linkage。

### Event Contracts

页面定位：事件契约中心，定义谁发布、谁消费、谁观察。

关键数据：

- tabs：All Contracts、System Contracts、Custom Events、Extension Surfaces。
- contract 列表：event name、owner、surface_id、display name、topic pattern、publication mode、schema version、compatibility、consumers、observers、read-only、sensitivity。
- detail tabs：Overview、Payload Schema、Example Payloads、Metadata、Subscribers、Consumers、Observers、Version History、Compatibility Report。
- Identity、Publication、Contract、Governance。
- Subscribers、Consumers、Observers、Compatibility Report、Publication Mode Guide。
- Create Extension Contract，但系统 contract 只读。

后台需要 contract registry、schema/version metadata、compatibility report、sensitivity/PII、publisher/consumer/observer link、自定义 extension contract 写入和审计。

### Runtime Defaults

页面定位：Settings-owned runtime control defaults。它只管理系统运行控制面的全局默认值，
例如 orchestration lease、heartbeat、executor 并发、auto compaction、tool worker retry、
lease、heartbeat 和并发。Runtime Defaults 不是 Agent/LLM/Tool/Access/Memory/Skill/Channel
的业务配置入口，也不是 Operations 运行观察页。

关键数据：

- Orchestration Safety：run lease、heartbeat、executor max concurrent assignments。
- Tool Worker Control：run max attempts、worker lease、heartbeat、max in flight、
  default/image/shared-state/remote concurrency。
- Compaction：enabled、reserve tokens、soft threshold tokens。
- Effective Preview：当前 effective value、source、resource version、environment override。
- Impact / Apply Requirement：restart required、daemon restart required、future hot apply。
- Validation / Save Reason / Audit：保存必须提供 reason，写入 Settings action audit。
- Version / Change History：resource version、published at、actor、rollback。

后台需要 Settings-owned `runtime-defaults/defaults` resource、typed schema validation、
effective materializer、typed assembly config、impact report、change history、save reason
和审计。env 只作为首次 seed 或显式 import/reseed 来源；已存在 resource 不得被启动 seed
静默覆盖。前端不得展示 LLM Defaults、Security Defaults、Observability Defaults 等未接通假面板。

### Environment

页面定位：部署环境维度的隔离配置。

关键数据：

- tabs：Environments、Variables、Secrets、Groups、Import / Export。
- environment 列表：prod、staging、dev、test、local。
- selected environment detail：overview、variables、secrets、groups、access assets、history。
- Override Summary。
- Configuration Validation。
- Precedence & Inheritance。
- Access Assets Scope。
- Environment Activation。
- Environment Variables、Secrets、Groups、Import/Export、Change Management。

后台需要 environment CRUD、变量/secret metadata、override diff、validation、activation policy、access scope 和 rollback/history。

### Audit Logs

页面定位：系统活动和配置变更审计。

关键数据：

- 日期范围、action、resource、user、status、搜索、filters、export。
- audit table：time、user、action、resource type、resource、status、IP address。
- 右侧 Log Details：time、user、action、resource、status、IP、user agent、changes diff。

后台需要 audit log query、过滤、分页、导出、resource link 和 diff model。

### Backup & Restore

页面定位：备份与恢复，保护配置、sessions、events、artifacts、memory indexes、access metadata。

关键数据：

- Backups / Restore tabs。
- Last Successful Backup、Total Backups、Total Data Protected、Next Scheduled Backup。
- backup 列表：name、type、scope、environment、size、status、created、created by、retention、actions。
- Backup Scope。
- Restore Safety：dry run、compatibility check、destructive confirmation。
- Encryption & Retention。
- Quick Actions：view storage、restore dry-run、restore destructive、download backup。
- Restore Audit Log。

后台需要 backup manifest、scope metadata、schedule、storage policy、restore dry-run、compatibility report、destructive restore guard 和 restore audit。

## 前端设计出发点

后续前端不应先做一个通用 dashboard，再把模块数据塞进去。应该按 surface 建模：

- Workbench：运行态主体验，重点是 run/turn/step/asset 的状态流和可操作性。
- Trace：timeline/graph/inspector 三件套，重点是查找、因果、跳转。
- Operations：模块独立页面，重点是每个运行模块的健康、阻塞、队列、失败和恢复动作。
- Settings：配置编辑和验证，重点是 list/detail、effective preview、resolution、audit。

前端组件可以复用，但页面 read model 不应强行统一：

- 可复用组件：AppShell、ModuleNav、MetricCard、StatusBadge、Tabs、DataTable、Inspector、Timeline、GraphCanvas、ActionButton、DangerZone、ConfigEditor。
- 不应复用为一个万能 `OperationsOverview`。
- 每个 Operations 模块页应有自己的 typed API、fixtures、empty/error/loading 状态和动作集合。

## 后台设计出发点

后续后台应围绕当前运行 surface 补齐 read model 和 action surface。Operations 页面以
`/operations/{module}` 为读取入口，由 `modules/operations` 的 observer/materializer
把事件和通用 query service 物化到 `operations_projections`，前端不再新增页面级 UI
聚合路由来承载 Operations 真相。

推荐分层：

- 业务模块拥有自己的运行事实，只提供通用 application service、query service、事件和 runtime metrics。
- `modules/operations` 侧向消费这些事实，负责 Operations 页面 projection、权限过滤、降级诊断、action route 描述和审计入口。
- `frontend` 的 Operations 页面只消费 `/operations/{module}` 及受控的 Operations action surface，不直接调用 owner module API 拼接运维真相。
- 写操作仍由对应业务模块 application service 执行，但应通过 Operations action surface 表达 reason、risk、permission 和 audit 语义。
- trace、linked entity、audit、config resolution 作为跨模块共享 contract。

优先补齐的 read model：

- `WorkbenchRunReadModel`
- `TraceTimelineReadModel`
- `TraceGraphReadModel`
- `OperationsOrchestrationReadModel`
- `OperationsToolReadModel`
- `OperationsLlmReadModel`
- `OperationsAccessReadModel`
- `OperationsChannelsReadModel`
- `OperationsMemoryReadModel`
- `OperationsSkillsReadModel`
- `OperationsEventsReadModel`
- `OperationsDaemonReadModel`
- `SettingsOverviewReadModel`
- 每个 Settings 配置页的 list/detail/effective/validation/audit read model。

## 下一步落地顺序

建议下一步先做设计对齐，而不是继续盲目扩页面：

1. 以前端路由为骨架，确认四个主 surface 和 Operations/Settings 子路由。
2. 为每个页面写 typed read model schema，先覆盖页面真实字段。
3. 用 fixtures 对齐设计稿，确保模块间内容差异真实存在。
4. 后台为各业务模块补通用 query/event 事实，由 `operations-observer` 物化 Operations projections。
5. 最后再接真实 API、权限、动作、审计和 trace 跳转。

验收时应看页面是否回答了该模块的真实运营问题，而不是看颜色、卡片数量或是否有泛化 overview。
