import type { Locale } from "./index";

type CopyPair = readonly [en: string, zh: string];

const copyPairs = [
  ["Overview", "概览"],
  ["Debug", "调试"],
  ["Memory", "记忆"],
  ["Agent", "智能体"],
  ["Access", "访问"],
  ["Channels", "通道"],
  ["Events", "事件"],
  ["Agents", "智能体"],
  ["Environments", "环境"],
  ["Skills", "技能"],
  ["Skill", "技能"],
  ["Tool", "工具"],
  ["Tools", "工具"],
  ["LLM", "LLM"],
  ["Daemon", "守护进程"],
  ["Settings", "设置"],
  ["Runs", "运行"],
  ["Run", "运行"],
  ["Tool Run", "工具运行"],
  ["Turn", "轮次"],
  ["Trace", "链路"],
  ["Payload", "载荷"],
  ["Input", "输入"],
  ["Result", "结果"],
  ["Context", "上下文"],
  ["Surface", "Surface"],
  ["Mapping", "映射"],
  ["Logs", "日志"],
  ["Metadata", "元数据"],
  ["Capabilities", "能力"],
  ["Usage", "使用情况"],
  ["Models", "模型"],
  ["Providers", "供应方"],
  ["Errors", "错误"],
  ["Error", "错误"],
  ["Invocations", "调用"],
  ["Streaming Requests", "流式请求"],
  ["Rate Limits", "限流"],
  ["Token Usage", "Token 使用"],
  ["Retrieval Logs", "检索日志"],
  ["Retrieval", "检索"],
  ["Source Files", "来源文件"],
  ["Sources", "来源"],
  ["Consumers", "消费者"],
  ["Health", "健康"],
  ["Status", "状态"],
  ["Active", "活跃"],
  ["Healthy", "健康"],
  ["Warning", "警告"],
  ["Failed", "失败"],
  ["Invalid", "无效"],
  ["Running", "运行中"],
  ["Waiting", "等待中"],
  ["Pending", "待处理"],
  ["Queued", "排队中"],
  ["Rebuilding", "重建中"],
  ["Scanning", "扫描中"],
  ["Indexed", "已索引"],
  ["Succeeded", "已成功"],
  ["Completed", "已完成"],
  ["Cancelled", "已取消"],
  ["Success", "成功"],
  ["Inactive", "未激活"],
  ["Draft", "草稿"],
  ["Valid", "有效"],
  ["Allowed", "允许"],
  ["Ready", "就绪"],
  ["Enabled", "已启用"],
  ["Disabled", "已禁用"],
  ["Available", "可用"],
  ["Forbidden", "禁止"],
  ["Configured", "已配置"],
  ["Installed", "已安装"],
  ["Registered", "已注册"],
  ["Revoked", "已撤销"],
  ["Updated", "已更新"],
  ["Total", "总计"],
  ["Details", "详情"],
  ["Detail", "详情"],
  ["Docs", "文档"],
  ["Action", "操作"],
  ["Actions", "操作"],
  ["Open", "打开"],
  ["Source", "来源"],
  ["Owner", "所有者"],
  ["Type", "类型"],
  ["Channel", "通道"],
  ["Event", "事件"],
  ["Auth", "认证"],
  ["Chat", "聊天"],
  ["Code", "代码"],
  ["Data", "数据"],
  ["NLP", "NLP"],
  ["Name", "名称"],
  ["Category", "类别"],
  ["Description", "描述"],
  ["Result", "结果"],
  ["Reason", "原因"],
  ["Issue", "问题"],
  ["Count", "数量"],
  ["Trend", "趋势"],
  ["Impact", "影响"],
  ["Latency", "延迟"],
  ["Duration", "运行时长"],
  ["Mode", "模式"],
  ["Scope", "范围"],
  ["Input", "输入"],
  ["Output", "输出"],
  ["Email", "邮件"],
  ["Metrics", "指标"],
  ["Contracts", "契约"],
  ["Dependencies", "依赖"],
  ["Registry", "注册表"],
  ["Mappings", "映射"],
  ["Stores", "存储"],
  ["Resource", "资源"],
  ["Role", "角色"],
  ["User", "用户"],
  ["Time", "时间"],
  ["Changes", "变更"],
  ["History", "历史"],
  ["Audit", "审计"],
  ["Reviewer", "审核人"],
  ["Ticket", "工单"],
  ["Policy", "策略"],
  ["Config", "配置"],
  ["Profile", "画像"],
  ["Model", "模型"],
  ["Provider", "供应方"],
  ["Environment", "环境"],
  ["System", "系统"],
  ["Organization", "组织"],
  ["Production", "生产"],
  ["Prod", "生产"],
  ["Prod Only", "仅生产"],
  ["Staging", "预发"],
  ["Dev", "开发"],
  ["Development", "开发"],
  ["All", "全部"],
  ["None", "无"],
  ["Yes", "是"],
  ["Yes (System)", "是（系统）"],
  ["No", "否"],
  ["Off", "关闭"],
  ["Full", "完整"],
  ["Guarded", "受控"],
  ["Low", "低"],
  ["Medium", "中"],
  ["Moderate", "中等"],
  ["High", "高"],
  ["Critical", "严重"],
  ["Admin", "管理员"],
  ["Edit", "编辑"],
  ["View", "查看"],
  ["Create", "创建"],
  ["Add", "添加"],
  ["New", "新建"],
  ["Import", "导入"],
  ["Imported", "已导入"],
  ["Export", "导出"],
  ["Download", "下载"],
  ["Clone", "克隆"],
  ["Archive", "归档"],
  ["Delete", "删除"],
  ["Disable", "停用"],
  ["Revoke", "撤销"],
  ["Rotate", "轮换"],
  ["Search", "搜索"],
  ["Local", "本地"],
  ["Filters", "筛选"],
  ["Last updated:", "最近更新："],
  ["Last heartbeat:", "最近心跳："],
  ["Auto refresh", "自动刷新"],
  ["View in Trace", "查看链路"],
  ["Open in Trace", "打开链路"],
  ["Open Trace", "打开链路"],
  ["Open Access", "打开访问配置"],
  ["Open Artifact", "打开产物"],
  ["View in Run", "查看运行"],
  ["View all", "查看全部"],
  ["View details", "查看详情"],
  ["View metrics", "查看指标"],
  ["View JSON", "查看 JSON"],
  ["View YAML", "查看 YAML"],
  ["View all logs", "查看全部日志"],
  ["View all issues", "查看全部问题"],
  ["View Health Details", "查看健康详情"],
  ["View Audit Logs", "查看审计日志"],
  ["View Resolution Trace", "查看解析链路"],
  ["View full trace", "查看完整链路"],
  ["View full report", "查看完整报告"],
  ["View full resolution trace", "查看完整解析链路"],
  ["View All Artifacts", "查看全部产物"],
  ["View All Tool Settings", "查看全部工具设置"],
  ["View All LLM Settings", "查看全部 LLM 设置"],
  ["View All Observability Settings", "查看全部可观测性设置"],
  ["View All Guardrail Settings", "查看全部护栏设置"],
  ["View Overrides (6 environments)", "查看覆盖（6 个环境）"],
  ["View Dependencies", "查看依赖"],
  ["View Precedence Details", "查看优先级详情"],
  ["View Detailed Impact Report", "查看详细影响报告"],
  ["Run Validation", "运行校验"],
  ["By Setting", "按设置"],
  ["Last 24 hours", "最近 24 小时"],
  ["Quick Actions", "快捷操作"],
  ["Current role: Admin (operable)", "当前角色：管理员（可操作）"],
  ["Current role: Admin (operable)", "当前角色: Admin (可操作)"],
  ["Role: Admin", "角色：管理员"],
  ["Config Source:", "配置来源："],
  ["Inherited From:", "继承自："],
  ["Config Version:", "配置版本："],
  ["Last Saved:", "最近保存："],
  ["Audit History", "审计历史"],
  ["Audit Logs", "审计日志"],
  ["Settings Overview", "设置总览"],
  ["Agent Profiles", "智能体画像"],
  ["LLM Profiles", "LLM 配置"],
  ["New LLM Profile", "新建 LLM 配置"],
  ["Manage large language model providers and configurations used by agents.", "管理智能体使用的大语言模型供应方与配置。"],
  ["All Providers", "全部供应方"],
  ["All Status", "全部状态"],
  ["Model Configuration", "模型配置"],
  ["Connection & Auth", "连接与认证"],
  ["Safety & Filtering", "安全与过滤"],
  ["Fallback Policy", "兜底策略"],
  ["Tags & Metadata", "标签与元数据"],
  ["Provider & Access", "供应方与访问"],
  ["No secrets stored here", "此处不存储密钥"],
  ["Network Egress", "网络出口"],
  ["View Access Asset", "查看访问资产"],
  ["View capability details", "查看能力详情"],
  ["Profile Status", "配置状态"],
  ["Default Profile", "默认配置"],
  ["Inactive profiles cannot be selected for runs.", "未激活配置不能被运行选择。"],
  ["Effective Configuration Preview", "生效配置预览"],
  ["View full configuration (JSON)", "查看完整配置（JSON）"],
  ["Context Window", "上下文窗口"],
  ["Rate Limit", "速率限制"],
  ["Output Limit", "输出限制"],
  ["Adapter Type", "适配器类型"],
  ["Model / Version", "模型 / 版本"],
  ["Used By", "使用方"],
  ["Runs (24h)", "运行（24h）"],
  ["Temperature", "温度"],
  ["Tool Calling", "工具调用"],
  ["Health & Diagnostics", "健康与诊断"],
  ["Test Now", "立即测试"],
  ["Connection", "连接"],
  ["Last Test", "最近测试"],
  ["Error Rate", "错误率"],
  ["Latency (p95)", "延迟（p95）"],
  ["View diagnostics", "查看诊断"],
  ["Capability", "能力"],
  ["Supported", "已支持"],
  ["Tool Catalog", "工具目录"],
  ["Discover, register, and manage tools that agents can use during execution.", "发现、注册并管理智能体执行期间可使用的工具。"],
  ["Import Tool Package", "导入工具包"],
  ["Register Tool", "注册工具"],
  ["All Tools", "全部工具"],
  ["Built-in Tools", "内置工具"],
  ["Custom Tools", "自定义工具"],
  ["Imported Packages", "已导入包"],
  ["Deprecated", "已废弃"],
  ["All Categories", "全部类别"],
  ["Runtime Strategy", "运行时策略"],
  ["Exec Mode", "执行模式"],
  ["Input Schema", "输入 Schema"],
  ["Output Schema", "输出 Schema"],
  ["Authentication & Access", "认证与访问"],
  ["Effects & Requirements", "效果与需求"],
  ["Testing & Debug", "测试与调试"],
  ["Owner / Package", "所有者 / 包"],
  ["Provider / Adapter", "供应方 / 适配器"],
  ["Base Spec / URL", "基础规范 / URL"],
  ["Created At", "创建时间"],
  ["Runtime Backend", "运行时后端"],
  ["Default Version", "默认版本"],
  ["Required Access Assets (1)", "必需访问资产（1）"],
  ["View in Access Center", "在访问中心查看"],
  ["View in Skill Catalog", "在技能目录中查看"],
  ["Used by Skills (4)", "被技能使用（4）"],
  ["Capabilities Provided", "提供的能力"],
  ["View capability contract", "查看能力契约"],
  ["Required Effects", "必需效果"],
  ["View effect guidelines", "查看效果指南"],
  ["Risk & Approval", "风险与审批"],
  ["View risk policy", "查看风险策略"],
  ["Effect Level", "效果等级"],
  ["Approval Required", "需要审批"],
  ["Allow Session Grant", "允许会话授权"],
  ["Supported Surfaces", "支持的 Surface"],
  ["View surface matrix", "查看 Surface 矩阵"],
  ["Artifact Output", "产物输出"],
  ["View artifact schema", "查看产物 Schema"],
  ["Contract Test", "契约测试"],
  ["Run Full Test", "运行完整测试"],
  ["Check", "检查项"],
  ["Last Run", "最近运行"],
  ["Pass", "通过"],
  ["Passed", "已通过"],
  ["Built-in", "内置"],
  ["Streaming", "流式"],
  ["API Credential", "API 凭据"],
  ["Remote API (HTTP)", "远程 API（HTTP）"],
  ["Input Schema Validation", "输入 Schema 校验"],
  ["Dry Run", "试运行"],
  ["Auth & Access Check", "认证与访问检查"],
  ["Artifact Schema Check", "产物 Schema 检查"],
  ["Skill Catalog", "技能目录"],
  ["Define reusable skills that declare capability requirements and execution guidance.", "定义可复用技能，声明能力需求与执行指导。"],
  ["New Skill", "新建技能"],
  ["All Skills", "全部技能"],
  ["My Skills", "我的技能"],
  ["System Skills", "系统技能"],
  ["SKILL.md Preview", "SKILL.md 预览"],
  ["Input Contract", "输入契约"],
  ["Output Contract", "输出契约"],
  ["Required Files", "必需文件"],
  ["System Skill", "系统技能"],
  ["Capability Requirements", "能力需求"],
  ["Access Requirements", "访问需求"],
  ["Manage capability mappings", "管理能力映射"],
  ["Access Type", "访问类型"],
  ["Purpose", "用途"],
  ["Required", "必需"],
  ["Fallback", "兜底"],
  ["Scope Hint", "范围提示"],
  ["Required Files / Resources", "必需文件 / 资源"],
  ["View all files", "查看全部文件"],
  ["Compatibility", "兼容性"],
  ["View compatibility matrix", "查看兼容性矩阵"],
  ["Min Runtime Version", "最低运行时版本"],
  ["Compatible Surfaces", "兼容 Surface"],
  ["Deprecation Status", "废弃状态"],
  ["Skill Package Source", "技能包来源"],
  ["Open repository", "打开仓库"],
  ["Source Type", "来源类型"],
  ["Repository", "仓库"],
  ["Path", "路径"],
  ["All required access available", "所有必需访问均可用"],
  ["Ready", "就绪"],
  ["Run Contract Tests", "运行契约测试"],
  ["Resolution Preview", "解析预览"],
  ["Declared Requirement", "已声明需求"],
  ["Capability Mapping", "能力映射"],
  ["Resolved Tool / Access / Runtime", "已解析工具 / 访问 / 运行时"],
  ["Access Authorization", "访问授权"],
  ["Execution Readiness", "执行就绪度"],
  ["Memory Config", "记忆配置"],
  ["Access Assets", "访问资产"],
  ["Configure memory stores, sources, indexing, policies, and retrieval strategies.", "配置记忆存储、来源、索引、策略和检索策略。"],
  ["Backend", "后端"],
  ["Backend Type", "后端类型"],
  ["Index", "索引"],
  ["Index / Namespace", "索引 / 命名空间"],
  ["Indexed Items", "已索引项目"],
  ["Store", "存储"],
  ["Operation", "操作"],
  ["Progress", "进度"],
  ["Items", "项目"],
  ["Job", "任务"],
  ["Doc", "文档"],
  ["File", "文件"],
  ["Size", "大小"],
  ["Score", "分数"],
  ["Query (excerpt)", "查询（摘录）"],
  ["Top K", "Top K"],
  ["Hit Count", "命中数"],
  ["Top Results", "高分结果"],
  ["Used In Run / Turn", "用于运行 / 轮次"],
  ["Last Indexed", "最近索引"],
  ["Last Modified", "最近修改"],
  ["Last Scanned", "最近扫描"],
  ["Next Scan", "下次扫描"],
  ["Write / Flush", "写入 / 刷新"],
  ["Top K 6 / Hit Count 5", "Top K 6 / 命中数 5"],
  ["Dimensions", "维度"],
  ["Region", "区域"],
  ["Retrieval & Query", "检索与查询"],
  ["Namespace / Partitioning", "命名空间 / 分区"],
  ["Retention & TTL", "保留与 TTL"],
  ["Consumers & Requests", "消费者与请求"],
  ["Monitoring & Usage", "监控与使用"],
  ["Avg. Top-K", "平均 Top-K"],
  ["Last 24h", "最近 24h"],
  ["Resolvable", "可解析"],
  ["Asset", "资产"],
  ["Preview how this store is resolved for a given context.", "预览该存储在给定上下文中的解析方式。"],
  ["Skills declare memory needs. Resolver decides which store to use.", "技能声明记忆需求，解析器决定使用哪个存储。"],
  ["View health dashboard", "查看健康仪表盘"],
  ["View usage analytics", "查看使用分析"],
  ["These actions are destructive and require confirmation and permission.", "这些操作具有破坏性，需要确认和权限。"],
  ["Manage API keys, tokens, credentials, and other external access assets used across the platform.", "管理平台内使用的 API Key、Token、凭据和其他外部访问资产。"],
  ["New Asset", "新建资产"],
  ["Import Asset", "导入资产"],
  ["All Assets", "全部资产"],
  ["API Keys", "API Key"],
  ["OAuth Connections", "OAuth 连接"],
  ["Secrets", "密钥"],
  ["Certificates", "证书"],
  ["All Types", "全部类型"],
  ["Asset ID", "资产 ID"],
  ["Provider / Service", "供应方 / 服务"],
  ["Required By", "被依赖方"],
  ["Expires At", "过期时间"],
  ["Credentials", "凭据"],
  ["Permissions & Scope", "权限与范围"],
  ["Usage & Invocations", "使用与调用"],
  ["Rotation & Expiry", "轮换与过期"],
  ["Validation & Health", "校验与健康"],
  ["Setup & Integration", "配置与集成"],
  ["Secret Version & Fingerprint", "密钥版本与指纹"],
  ["Secret Storage", "密钥存储"],
  ["Asset Owner", "资产所有者"],
  ["Fingerprint", "指纹"],
  ["Version", "版本"],
  ["Last Rotated", "最近轮换"],
  ["Last Updated", "最近更新"],
  ["Setup Method", "配置方式"],
  ["Created With", "创建方式"],
  ["Manual API Key", "手动 API Key"],
  ["Environment Scope", "环境范围"],
  ["Permissions / Capabilities", "权限 / 能力"],
  ["Granted by provider", "由供应方授予"],
  ["Result: Allowed", "结果：允许"],
  ["Affected Runs / Blocked Consumers", "受影响运行 / 阻塞消费者"],
  ["Potentially Affected Runs", "可能受影响运行"],
  ["Blocked Consumers", "被阻塞消费者"],
  ["Danger Zone", "危险区"],
  ["Access Actions", "访问操作"],
  ["Rotate Secret Now", "立即轮换密钥"],
  ["Revoke Asset", "撤销资产"],
  ["Disable Asset", "停用资产"],
  ["Delete Asset Reference", "删除资产引用"],
  ["Test Connection", "测试连接"],
  ["Consumers", "消费者"],
  ["Metric", "指标"],
  ["Value", "值"],
  ["Connection Test", "连接测试"],
  ["Permission Check", "权限检查"],
  ["Last Validation", "最近校验"],
  ["Next Validation", "下次校验"],
  ["Secret value remains server-side", "密钥值保留在服务端"],
  ["Retrieval Policies", "检索策略"],
  ["Skill Requirements", "技能需求"],
  ["Channels / Runtimes", "通道 / 运行时"],
  ["Click any count in the table above to filter assets by consumer type.", "点击上表任意数量，按消费者类型筛选资产。"],
  ["Channel Profiles", "通道配置"],
  ["Surfaces", "Surface"],
  ["Service", "服务"],
  ["Authentication", "认证"],
  ["Permissions", "权限"],
  ["Delivery & Retry", "投递与重试"],
  ["Retry", "重试"],
  ["Backoff", "退避"],
  ["Monitoring", "监控"],
  ["Website", "网站"],
  ["WebSocket", "WebSocket"],
  ["Global", "全局"],
  ["Manage in Access Assets", "在访问资产中管理"],
  ["Reuse active session, otherwise create new", "复用活跃会话，否则创建新会话"],
  ["Validate mapping with real payloads before saving.", "保存前使用真实载荷校验映射。"],
  ["Web application chat interface for end users.", "面向终端用户的 Web 应用聊天界面。"],
  ["+ New Channel", "+ 新建通道"],
  ["+ Add Sample", "+ 添加样例"],
  ["Event Contracts", "事件契约"],
  ["Central registry of event contracts that define what is published, by whom, and who consumes or observes them.", "事件契约中心注册表，定义发布内容、发布方以及消费方或观察方。"],
  ["All surface_id", "全部 surface_id"],
  ["Subscribers", "订阅方"],
  ["Observers", "观察者"],
  ["Subscribers (3)", "订阅方（3）"],
  ["Consumers (3)", "消费者（3）"],
  ["Observers (1)", "观察者（1）"],
  ["At-least-once", "至少一次"],
  ["Event-Driven", "事件驱动"],
  ["Operational", "运营"],
  ["Original fact event", "原始事实事件"],
  ["Filtered downstream event", "过滤后的下游事件"],
  ["Derived observation", "派生观察"],
  ["System contracts are read-only", "系统契约为只读"],
  ["Learn more about modes", "了解模式详情"],
  ["Runtime Defaults", "运行时默认值"],
  ["Backup & Restore", "备份与恢复"],
  ["Protect your platform data and recover from any failure with confidence.", "保护平台数据，并在故障后可靠恢复。"],
  ["Encrypted storage", "加密存储"],
  ["Dry-run required", "需要试运行"],
  ["Backups", "备份"],
  ["Restore", "恢复"],
  ["Schedules", "计划"],
  ["Storage", "存储"],
  ["Last Successful Backup", "最近成功备份"],
  ["Total Backups", "备份总数"],
  ["Total Data Protected", "已保护数据总量"],
  ["Next Scheduled Backup", "下次计划备份"],
  ["Daily at 01:00 AM (UTC)", "每日 01:00 AM（UTC）"],
  ["Across all environments", "跨全部环境"],
  ["Compressed size", "压缩大小"],
  ["Backup Scope", "备份范围"],
  ["Full runtime", "完整运行时"],
  ["Restore Safety", "恢复安全"],
  ["Compatibility check", "兼容性检查"],
  ["Restore dry-run", "恢复试运行"],
  ["Admin approval", "管理员审批"],
  ["Rollback point created", "已创建回滚点"],
  ["Start Restore Flow", "启动恢复流程"],
  ["Encryption & Retention", "加密与保留"],
  ["KMS Key", "KMS Key"],
  ["Default Retention", "默认保留"],
  ["Legal Hold", "法务保留"],
  ["Backup manifest is restorable", "备份清单可恢复"],
  ["Secrets are metadata-only", "密钥仅保留元数据"],
  ["View all restore events", "查看全部恢复事件"],
  ["Configuration", "配置"],
  ["Configuration Health", "配置健康"],
  ["Configuration Issues", "配置问题"],
  ["Configuration Distribution", "配置分布"],
  ["Configuration Inheritance", "配置继承"],
  ["Configuration Sources & Versioning", "配置来源与版本"],
  ["Editable Configurations", "可编辑配置"],
  ["Read-only Contracts", "只读契约"],
  ["Useful Links", "常用链接"],
  ["Recent Changes", "最近变更"],
  ["Runtime Configuration Precedence", "运行时配置优先级"],
  ["Runtime Defaults (System/Platform)", "运行时默认值（系统 / 平台）"],
  ["Editing: System/Platform Defaults", "正在编辑：系统 / 平台默认值"],
  ["Validation / Dry Run", "校验 / 试运行"],
  ["Export Contract", "导出契约"],
  ["Change History", "变更历史"],
  ["Change History & Rollback", "变更历史与回滚"],
  ["Save Changes", "保存变更"],
  ["Cancel", "取消"],
  ["General", "通用"],
  ["Execution", "执行"],
  ["Runtime", "运行时"],
  ["Effects", "效果"],
  ["Limits & Quotas", "限制与配额"],
  ["Guardrails", "护栏"],
  ["Observability", "可观测性"],
  ["Security", "安全"],
  ["Advanced", "高级"],
  ["Configuration Scope", "配置范围"],
  ["Inherited By", "继承方"],
  ["Precedence", "优先级"],
  ["Validation Status", "校验状态"],
  ["All Environments", "全部环境"],
  ["42 Agents", "42 个智能体"],
  ["Lowest", "最低"],
  ["Lowest precedence", "最低优先级"],
  ["Valid", "有效"],
  ["Tool Execution Defaults", "工具执行默认值"],
  ["LLM Defaults", "LLM 默认值"],
  ["Observability Defaults", "可观测性默认值"],
  ["Safety & Guardrail Defaults", "安全与护栏默认值"],
  ["Change Management", "变更管理"],
  ["Audit Requirement", "审计要求"],
  ["Default LLM Profile", "默认 LLM 配置"],
  ["Fallback LLM Profile", "兜底 LLM 配置"],
  ["Fallback Profiles", "兜底配置"],
  ["Rate Limiter", "限流器"],
  ["Max Output Tokens", "最大输出 Token"],
  ["Execution Mode", "执行模式"],
  ["Source (Run / Step)", "来源（运行 / 步骤）"],
  ["Holds Worker", "占用工作器"],
  ["Result / Output", "结果 / 输出"],
  ["Affected Runs (24h)", "受影响运行（24h）"],
  ["Oldest Wait", "最长等待"],
  ["% of Queue", "队列占比"],
  ["Timeout", "超时"],
  ["Retry Policy", "重试策略"],
  ["Exponential", "指数退避"],
  ["Max Concurrency", "最大并发"],
  ["Event Retention", "事件保留"],
  ["Key Event Sampling", "关键事件采样"],
  ["Log Retention", "日志保留"],
  ["Verbose Trace Sampling", "详细链路采样"],
  ["Effective Defaults Contract", "生效默认值契约"],
  ["Environment Overrides", "环境覆盖"],
  ["Change Impact Preview", "变更影响预览"],
  ["Preview (New Run with No Overrides)", "预览（无覆盖的新运行）"],
  ["Tool Timeout", "工具超时"],
  ["LLM Profile", "LLM 配置"],
  ["Trace Sampling", "链路采样"],
  ["Access Assets Scope", "访问资产范围"],
  ["Configuration Validation", "配置校验"],
  ["Precedence & Inheritance", "优先级与继承"],
  ["Environment Variables", "环境变量"],
  ["Environments", "环境"],
  ["Environments (5)", "环境（5）"],
  ["Variables", "变量"],
  ["Variables (86)", "变量（86）"],
  ["Secrets (12)", "密钥（12）"],
  ["Groups", "分组"],
  ["Groups (4)", "分组（4）"],
  ["Deployment", "部署"],
  ["Manage isolated configuration used to deploy and run agents, skills, and integrations.", "管理用于部署和运行智能体、技能与集成的隔离配置。"],
  ["Environments provide deployment-scoped configuration and secrets.", "环境提供部署范围内的配置与密钥。"],
  ["Environment overrides System/Platform Defaults.", "环境会覆盖系统 / 平台默认值。"],
  ["Primary production environment with guarded overrides and audited activation.", "主生产环境，包含受控覆盖和审计激活。"],
  ["Activation changes require validation, impact preview, and an approval note.", "激活变更需要校验、影响预览和审批备注。"],
  ["Activation requires approval", "激活需要审批"],
  ["Secret metadata valid", "密钥元数据有效"],
  ["Variables resolved", "变量已解析"],
  ["Access scope allowed", "访问范围已允许"],
  ["Override layer: deployment", "覆盖层：部署"],
  ["Dry-run Impact", "试运行影响"],
  ["Edit variables", "编辑变量"],
  ["Manage secrets", "管理密钥"],
  ["Manage groups", "管理分组"],
  ["Set as Default", "设为默认"],
  ["Restore previous environment snapshot", "恢复上一份环境快照"],
  ["View resolution trace", "查看解析链路"],
  ["View health dashboard", "查看健康仪表盘"],
  ["Understand environment model and best practices.", "了解环境模型和最佳实践。"],
  ["Import / Export", "导入 / 导出"],
  ["Secrets resolved through Access Assets", "密钥通过访问资产解析"],
  ["Agent Memory (Default)", "智能体记忆（默认）"],
  ["Memory Stores", "记忆存储"],
  ["Memory Policies", "记忆策略"],
  ["Memory Injection Impact", "记忆注入影响"],
  ["Embedding Model", "Embedding 模型"],
  ["Access Asset", "访问资产"],
  ["Lifecycle", "生命周期"],
  ["Store Lifecycle & Health", "存储生命周期与健康"],
  ["Policy Resolution Preview", "策略解析预览"],
  ["Resolved Memory Store", "已解析记忆存储"],
  ["Access Evaluation", "访问评估"],
  ["Source Configuration", "来源配置"],
  ["Indexer Configuration", "索引器配置"],
  ["Access & Security", "访问与安全"],
  ["Safe maintenance operations", "安全维护操作"],
  ["Rescan Sources", "重新扫描来源"],
  ["All Agents", "全部智能体"],
  ["Agent Profiles", "智能体画像"],
  ["New Agent Profile", "新建智能体画像"],
  ["Define and manage agent configurations that control behavior, runtime settings, and policy.", "定义并管理控制行为、运行时设置与策略的智能体配置。"],
  ["Learn more", "了解更多"],
  ["Basic Information", "基础信息"],
  ["LLM Configuration", "LLM 配置"],
  ["Runtime Preferences", "运行时偏好"],
  ["Access Grants (ABAC)", "访问授权（ABAC）"],
  ["Tool Policy (ABAC)", "工具策略（ABAC）"],
  ["Skill Preferences", "技能偏好"],
  ["Memory & Context", "记忆与上下文"],
  ["Run Scope & Limits", "运行范围与限制"],
  ["Effective Configuration", "生效配置"],
  ["Validation", "校验"],
  ["All Statuses", "全部状态"],
  ["All Scopes", "全部范围"],
  ["Name (A-Z)", "名称（A-Z）"],
  ["Updated At", "更新时间"],
  ["Updated By", "更新人"],
  ["Last Used", "最近使用"],
  ["Default", "默认"],
  ["General Purpose", "通用用途"],
  ["Tags", "标签"],
  ["Avatar", "头像"],
  ["Change Avatar", "更换头像"],
  ["Compare with...", "对比..."],
  ["Profile Actions", "画像操作"],
  ["Clone Profile", "克隆画像"],
  ["Export as YAML", "导出为 YAML"],
  ["Archive Profile", "归档画像"],
  ["Run Scope", "运行范围"],
  ["Access Grant Scope", "访问授权范围"],
  ["Change Impact", "变更影响"],
  ["Profile Resolution Trace", "画像解析链路"],
  ["Skill Set Resolution", "技能集解析"],
  ["Access Grants", "访问授权"],
  ["Default Skills", "默认技能"],
  ["Default LLM", "默认 LLM"],
  ["Fallback LLM", "兜底 LLM"],
  ["Agent Profile", "智能体画像"],
  ["System/Platform", "系统 / 平台"],
  ["Active Sessions", "活跃会话"],
  ["Upcoming Runs", "即将运行"],
  ["Dependent Profiles", "依赖画像"],
  ["Risk Level", "风险等级"],
  ["Validation Summary", "校验摘要"],
  ["Summary", "摘要"],
  ["All checks passed", "全部检查通过"],
  ["Runtime Settings", "运行时设置"],
  ["Channel Profiles", "通道配置"],
  ["Settings /", "设置 /"],
  ["Runtime Binding", "运行时绑定"],
  ["Required Access Assets", "必需访问资产"],
  ["Run / Turn Binding Preview", "运行 / 轮次绑定预览"],
  ["Allowed Actions Policy (ABAC)", "允许操作策略（ABAC）"],
  ["Callback / Webhook Health", "回调 / Webhook 健康"],
  ["Message Mapping Preview", "消息映射预览"],
  ["Edit Mapping", "编辑映射"],
  ["Incoming: Channel Payload", "入站：通道载荷"],
  ["Outgoing: Agent Response", "出站：智能体响应"],
  ["Channel Payload", "通道载荷"],
  ["Mapping Contract Test", "映射契约测试"],
  ["Sample Payloads", "样例载荷"],
  ["Run Intake Test", "运行入口测试"],
  ["Run Delivery Test", "运行投递测试"],
  ["Test with Sample Payload", "使用样例载荷测试"],
  ["New Channel", "新建通道"],
  ["Event Contracts", "事件契约"],
  ["Create Extension Contract", "创建扩展契约"],
  ["All Contracts", "全部契约"],
  ["System Contracts", "系统契约"],
  ["Custom Events", "自定义事件"],
  ["Extension Surfaces", "扩展表面"],
  ["All Owners", "全部所有者"],
  ["All Publication Modes", "全部发布模式"],
  ["All Compatibility", "全部兼容性"],
  ["All Sensitivity", "全部敏感级"],
  ["Read-only", "只读"],
  ["View as JSON", "以 JSON 查看"],
  ["Payload Schema", "载荷 Schema"],
  ["Example Payloads", "样例载荷"],
  ["Identity", "身份"],
  ["Publication", "发布"],
  ["Contract", "契约"],
  ["Governance", "治理"],
  ["Event Name", "事件名称"],
  ["Owner ID", "所有者 ID"],
  ["Display Name", "展示名称"],
  ["Topic Pattern", "主题模式"],
  ["Publication Mode", "发布模式"],
  ["Producer", "生产方"],
  ["Payload Completeness", "载荷完整度"],
  ["Determinism", "确定性"],
  ["Delivery Guarantees", "投递保证"],
  ["Schema Version", "Schema 版本"],
  ["Compatibility", "兼容性"],
  ["Sensitivity / PII", "敏感性 / PII"],
  ["Default Redaction", "默认脱敏"],
  ["Classification", "分类"],
  ["Access Policy", "访问策略"],
  ["Compatibility Report", "兼容性报告"],
  ["Audit Logs", "审计日志"],
  ["View and search audit logs for system activity and changes across the platform.", "查看并搜索平台范围内系统活动和变更的审计日志。"],
  ["Filter saved locally", "筛选已本地保存"],
  ["Records are immutable", "记录不可变更"],
  ["Log Details", "日志详情"],
  ["IP Address", "IP 地址"],
  ["User Agent", "用户代理"],
  ["All Actions", "全部操作"],
  ["All Resources", "全部资源"],
  ["All Users", "全部用户"],
  ["Backup & Restore", "备份与恢复"],
  ["Restore Dry Run", "恢复试运行"],
  ["Create Backup", "创建备份"],
  ["Next Scheduled Backup", "下次计划备份"],
  ["Restore Audit Log", "恢复审计日志"],
  ["Create Config Backup", "创建配置备份"],
  ["Run Restore Dry-run", "运行恢复试运行"],
  ["Tool Runtime", "工具运行时"],
  ["Monitor tool execution, queues, workers, artifacts, and policies", "监控工具执行、队列、worker、产物与策略"],
  ["Monitor the full tool path from trigger to completion: queueing, scheduling, execution, I/O waits, artifact output, and policy governance.", "监控工具从触发到完成的全链路：排队、调度、执行、I/O 等待、产物产出与策略治理。"],
  ["Overall Health", "整体健康"],
  ["Tool Runs (24h)", "工具运行（24h）"],
  ["Active Tool Runs", "活跃工具运行"],
  ["Failed Tool Runs", "失败工具运行"],
  ["Failed (24h)", "失败（24h）"],
  ["Avg Duration", "平均时长"],
  ["Tool Runs", "工具运行"],
  ["Workers", "工作器"],
  ["Artifacts", "产物"],
  ["Strategies", "策略"],
  ["Recent Tool Runs", "最近工具运行"],
  ["Tool Types", "工具类型"],
  ["(by Runs)", "（按运行）"],
  ["(24h)", "（24h）"],
  ["(Runtime)", "（运行时）"],
  ["(Global)", "（全局）"],
  ["(by LLM Profile)", "（按 LLM 配置）"],
  ["(Declared by Skills)", "（由技能声明）"],
  ["(Top 5)", "（前 5）"],
  ["(Top 6)", "（前 6）"],
  ["(Top 10 by Volume)", "（按容量前 10）"],
  ["(Access asset health)", "(授权资产健康度)"],
  ["(real-time)", "(实时)"],
  ["(example)", "(示例)"],
  ["Auth Missing / Access Blocked", "认证缺失 / 访问阻塞"],
  ["Worker Pool Overview", "工作器池总览"],
  ["Total Workers", "工作器总数"],
  ["Idle", "空闲"],
  ["Busy", "繁忙"],
  ["Offline", "离线"],
  ["Inline Blocking Risk", "Inline 阻塞风险"],
  ["Tool Queue", "工具队列"],
  ["(Grouped by Reason)", "（按原因分组）"],
  ["Inline Risk", "Inline 风险"],
  ["(Last 24h)", "（最近 24h）"],
  ["Recent Artifacts", "最近产物"],
  ["Browser Automation", "浏览器自动化"],
  ["Image Generation", "图片生成"],
  ["OpenAPI / HTTP", "OpenAPI / HTTP"],
  ["LLM Adjacent", "LLM 相关"],
  ["MCP", "MCP"],
  ["Local Process", "本地进程"],
  ["Provider Access", "供应方访问"],
  ["Failed / Auth Required", "失败 / 需要认证"],
  ["403 Forbidden / Provider Access", "403 Forbidden / 供应方访问"],
  ["Navigation Failed", "导航失败"],
  ["API Key Missing", "缺少 API Key"],
  ["Login Required", "需要登录"],
  ["Waiting for Worker", "等待工作器"],
  ["Waiting for Auth / Access", "等待认证 / 访问"],
  ["Waiting for Lane / Capacity", "等待 Lane / 容量"],
  ["Retry Backoff", "重试退避"],
  ["Tool Categories", "工具分类"],
  ["Orchestration & planning workers", "编排与规划工作器"],
  ["Tool execution workers", "工具执行工作器"],
  ["Channel & messaging workers", "通道与消息工作器"],
  ["LLM request/response workers", "LLM 请求 / 响应工作器"],
  ["Memory index & retrieval", "记忆索引与检索"],
  ["System & utilities", "系统与工具服务"],
  ["Recent Invocations", "最近调用"],
  ["LLM Runtime", "LLM 运行时"],
  ["Invocations (24h)", "调用（24h）"],
  ["Tokens (24h)", "Token（24h）"],
  ["Streaming (24h)", "流式（24h）"],
  ["Errors (24h)", "错误（24h）"],
  ["Avg Latency (P95)", "平均延迟（P95）"],
  ["Provider Access & Health", "供应方访问与健康"],
  ["Provider Auth / Access Blocked", "供应方认证 / 访问阻塞"],
  ["Model Resolver", "模型解析器"],
  ["LLM Rate Limiter", "LLM 限流器"],
  ["Latency (P95)", "延迟（P95）"],
  ["Invocation Rate (RPS)", "调用速率（RPS）"],
  ["Stream Health", "流式健康"],
  ["Execution Blocking Risk", "执行阻塞风险"],
  ["Fallback / Resolver Problems", "兜底 / 解析问题"],
  ["Context Window Pressure", "上下文窗口压力"],
  ["Model Availability", "模型可用性"],
  ["Error Summary", "错误摘要"],
  ["Agent Default", "智能体默认"],
  ["Explicit Override", "显式覆盖"],
  ["Fallback Used", "已使用兜底"],
  ["No Match / Error", "无匹配 / 错误"],
  ["Availability", "可用性"],
  ["Reachable", "可达"],
  ["Impact (24h)", "影响（24h）"],
  ["Affected Invocations", "受影响调用"],
  ["Provider / Model", "供应方 / 模型"],
  ["Request ID", "请求 ID"],
  ["Run ID", "运行 ID"],
  ["Run / Step", "运行 / 步骤"],
  ["Run / Trace / Turn", "运行 / 链路 / 轮次"],
  ["Run / Turn / Step", "运行 / 轮次 / 步骤"],
  ["Started At", "开始时间"],
  ["Completed At", "完成时间"],
  ["Fallback To", "兜底至"],
  ["Requested", "请求项"],
  ["Error Type", "错误类型"],
  ["Queue Depth", "队列深度"],
  ["Waiting for quota", "等待配额"],
  ["Waiting for provider", "等待供应方"],
  ["Throughput (5m)", "吞吐（5m）"],
  ["Queue Wait (P95)", "队列等待（P95）"],
  ["Token-based (RPM/TPM)", "基于 Token（RPM/TPM）"],
  ["First Token Latency (P95)", "首 Token 延迟（P95）"],
  ["Stream Duration (P95)", "流持续时间（P95）"],
  ["Disconnect Rate", "断连率"],
  ["Avg Reconnects / Stream", "平均重连 / 流"],
  ["Currently Holding Worker", "当前占用工作器"],
  ["Awaiting Provider", "等待供应方"],
  ["Execution Mode (24h)", "执行模式（24h）"],
  ["Cache Read", "缓存读取"],
  ["Cache Write", "缓存写入"],
  ["Memory Injection High", "记忆注入偏高"],
  ["Avg Utilization", "平均利用率"],
  ["High (>90%)", "高（>90%）"],
  ["Truncated", "已截断"],
  ["Total 56.3M tokens", "总计 56.3M Token"],
  ["Connecting", "连接中"],
  ["Closing", "关闭中"],
  ["Auth Required", "需要认证"],
  ["Quota Not Enabled", "配额未启用"],
  ["Rate Limit Reached", "达到速率限制"],
  ["Rate Limited", "已限流"],
  ["Provider rate limited", "供应方已限流"],
  ["Model not available", "模型不可用"],
  ["Auth required", "需要认证"],
  ["Auth missing", "认证缺失"],
  ["Unavailable", "不可用"],
  ["Limited", "受限"],
  ["Access Usage", "访问使用"],
  ["Recent Access Events", "最近访问事件"],
  ["Missing Access", "缺失访问权限"],
  ["Credential Health", "凭据健康"],
  ["Authentication Status", "认证状态"],
  ["Access Assets", "访问资产"],
  ["Grants", "授权"],
  ["OAuth Apps", "OAuth 应用"],
  ["Auth Status", "认证状态"],
  ["Setup Flows", "配置流程"],
  ["Expiring Soon", "即将过期"],
  ["Auth Success Rate", "认证成功率"],
  ["Failed Auth", "认证失败"],
  ["Require attention", "需要关注"],
  ["Within 7 days", "7 天内"],
  ["Provider Auth / Access Blocked", "供应方认证 / 访问阻塞"],
  ["Credentials by Kind", "按类型统计凭据"],
  ["Top Consumers", "高频消费者"],
  ["View all missing access", "查看全部缺失访问"],
  ["View all fallback / resolver problems (12)", "查看全部兜底 / 解析问题（12）"],
  ["View all setup flows", "查看全部配置流程"],
  ["Total impacted", "总受影响"],
  ["Affected", "受影响"],
  ["Affected (24h)", "受影响（24h）"],
  ["Asset / Service", "资产 / 服务"],
  ["Flow Type", "流程类型"],
  ["Last Failed", "最近失败"],
  ["Kind", "类型"],
  ["By", "由"],
  ["Used (Fallback)", "使用项（兜底）"],
  ["API Key", "API Key"],
  ["OAuth", "OAuth"],
  ["OAuth App", "OAuth 应用"],
  ["Bearer Token", "Bearer Token"],
  ["Auth File", "认证文件"],
  ["Bot Token", "Bot Token"],
  ["Missing API Key", "缺少 API Key"],
  ["Missing OAuth", "缺少 OAuth"],
  ["Invalid Credentials", "凭据无效"],
  ["Access Failed", "访问失败"],
  ["Access Revoked", "访问已撤销"],
  ["API Key Created", "API Key 已创建"],
  ["OAuth Token Refreshed", "OAuth Token 已刷新"],
  ["Setup", "配置"],
  ["Renew", "续期"],
  ["View Limits", "查看限制"],
  ["View Trace", "查看链路"],
  ["Memory Stores", "记忆存储"],
  ["Index Health", "索引健康"],
  ["Retrieval Trace", "检索链路"],
  ["Memory Usage", "记忆使用"],
  ["Recent Retrieval Logs", "最近检索日志"],
  ["Source Scan Status", "来源扫描状态"],
  ["Events Over Time", "事件趋势"],
  ["Events by Surface", "按表面统计事件"],
  ["Owners by Volume", "按容量统计所有者"],
  ["Contract Compatibility", "契约兼容性"],
  ["Recent Events", "最近事件"],
  ["Consumer Health", "消费者健康"],
  ["Observer Mapping Failures", "观察者映射失败"],
  ["Owners", "所有者"],
  ["Topic", "主题"],
  ["Topics", "主题"],
  ["Subscriptions", "订阅"],
  ["Event Inspector", "事件检查器"],
  ["Event Stream", "事件流"],
  ["Dead Letters", "死信"],
  ["Delivery Success Rate", "投递成功率"],
  ["Subscription Lag", "订阅延迟"],
  ["Observer Failures", "观察者失败"],
  ["Ingested", "已摄入"],
  ["Delivered", "已投递"],
  ["Accepted", "已接收"],
  ["Processing", "处理中"],
  ["Rejected", "已拒绝"],
  ["Dropped", "已丢弃"],
  ["Matched", "已匹配"],
  ["Reobserve", "重新观察"],
  ["Producers", "生产方"],
  ["Breaking Mismatches", "破坏性不匹配"],
  ["Incompatible Events", "不兼容事件"],
  ["Event ID", "事件 ID"],
  ["Surface ID", "Surface ID"],
  ["Time (UTC+8)", "时间（UTC+8）"],
  ["% of Total", "总占比"],
  ["Trend (24h)", "趋势（24h）"],
  ["Event ID (Cursor)", "事件 ID（Cursor）"],
  ["Consumer / Observer", "消费者 / 观察者"],
  ["Ack Rate (24h)", "确认率（24h）"],
  ["Lag (Events)", "延迟（事件）"],
  ["Fail Rate", "失败率"],
  ["Last Consumed", "最近消费"],
  ["Source Event -> Target", "来源事件 -> 目标"],
  ["Last Occurred", "最近发生"],
  ["Events (24h)", "事件（24h）"],
  ["Partitions", "分区"],
  ["Retention", "保留"],
  ["Oldest", "最早"],
  ["Observer", "观察者"],
  ["Subscriber", "订阅方"],
  ["Subscription", "订阅"],
  ["Last Acked", "最近确认"],
  ["Input Topics", "输入主题"],
  ["Success Rate (24h)", "成功率（24h）"],
  ["Failures (24h)", "失败（24h）"],
  ["Event contracts and runtime health. Monitor production, delivery, subscriptions, and observation across the system.", "事件契约与运行时健康。监控生产、投递、订阅和系统内观察。"],
  ["All times are in UTC+8. Event payloads are redacted unless explicitly opened.", "所有时间均为 UTC+8。除非显式打开，事件载荷默认脱敏。"],
  ["Drain Overview", "排空总览"],
  ["Service Sets", "服务集"],
  ["Service Set", "服务集"],
  ["Daemons", "守护进程"],
  ["Manage runtime processes and service sets that power Agent Runtime.", "管理支撑 Agent Runtime 的运行时进程和服务集。"],
  ["Refresh every 10s", "每 10 秒刷新"],
  ["Health Checks", "健康检查"],
  ["Processes", "进程"],
  ["Processes (18)", "进程（18）"],
  ["Alerts", "告警"],
  ["Process Health", "进程健康"],
  ["Restart Summary", "重启摘要"],
  ["Dependency Health", "依赖健康"],
  ["Draining Service Sets", "排空中的服务集"],
  ["Total In-Flight Events", "总飞行中事件"],
  ["Estimated Completion", "预计完成"],
  ["Drain Progress", "排空进度"],
  ["Stop Intake", "停止入口"],
  ["All Service Sets", "全部服务集"],
  ["All Nodes", "全部节点"],
  ["Columns", "列"],
  ["(All Service Sets)", "（全部服务集）"],
  ["Crash", "崩溃"],
  ["Manual", "手动"],
  ["Deploy", "部署"],
  ["Start", "启动"],
  ["Stop", "停止"],
  ["Restart", "重启"],
  ["Drain", "排空"],
  ["Reload Config", "重载配置"],
  ["Links to Operations", "关联操作页"],
  ["Select service set or process", "选择服务集或进程"],
  ["Some actions require elevated permissions.", "部分操作需要更高权限。"],
  ["Dependency", "依赖"],
  ["Process Name", "进程名称"],
  ["Worker Loop", "工作循环"],
  ["Node / Host", "节点 / 主机"],
  ["Container / Instance", "容器 / 实例"],
  ["PID", "PID"],
  ["Port(s)", "端口"],
  ["Heartbeat", "心跳"],
  ["Config Status", "配置状态"],
  ["Restart Policy", "重启策略"],
  ["Last Started", "最近启动"],
  ["Supervisor", "监督器"],
  ["Drain Status", "排空状态"],
  ["Config Version", "配置版本"],
  ["Restarts (24h)", "重启（24h）"],
  ["Stopped", "已停止"],
  ["Unhealthy", "不健康"],
  ["Outdated", "已过期"],
  ["Up to date", "已是最新"],
  ["Uptime", "运行时长"],
  ["Last Heartbeat", "最近心跳"],
  ["Expected < 30s", "预期 < 30s"],
  ["Search agent profiles...", "搜索智能体画像..."],
  ["Search LLM profiles...", "搜索 LLM 配置..."],
  ["Search memory stores...", "搜索记忆存储..."],
  ["Search channels...", "搜索通道..."],
  ["Search contracts...", "搜索契约..."],
  ["Search environments...", "搜索环境..."],
  ["Search backups...", "搜索备份..."],
  ["Search logs...", "搜索日志..."],
  ["Search skills...", "搜索技能..."],
  ["Search assets...", "搜索资产..."],
  ["Search processes...", "搜索进程..."],
  ["Enter reason for this change...", "输入本次变更原因..."],
  ["Access and credential management center for API keys, OAuth apps, bearer tokens, and system access dependencies by access asset.", "访问与凭证管理中心，按 Access Asset 维度管理 API Keys、OAuth 应用、Bearer Token 与系统访问依赖。"],
  ["Memory and knowledge management center for stores, indexing, retrieval, writes, sources, and links to runs, turns, and steps.", "记忆与知识管理中心，监控 Memory 存储、索引、检索、写入、来源与关联到 Run / Turn / Step。"],
  ["Monitor message ingress, delivery channels, surface bindings, dead-letter queues, and channel-level failures.", "监控消息入口、投递通道、Surface 绑定、死信队列与通道级失败。"],
  ["Monitor LLM invocations, streaming, rate limits, routing, tokens, and errors", "监控 LLM 调用、流式、限流、解析、Token 与错误"],
  ["Monitor LLM invocations, streaming, rate limits, routing, tokens, and errors.", "监控 LLM 调用、流式、限流、解析、Token 与错误。"],
  ["Note: all times use system time. Open Trace for key causal chains.", "说明：所有时间均为系统时间，关键因果链请前往 Trace 页面。"],
  ["Channel events can jump back to Trace; dead-letter replay is recorded in the operations audit.", "通道事件可回跳 Trace；死信 replay 会进入操作审计。"],
  ["All times use system time. Click any run or card for details; inspect the full permission chain in Trace.", "所有时间均为系统时间；点击任意运行或卡片可查看详情，完整权限链请在 Trace 中查看。"],
  ["Click a row for details", "点击行查看详情"],
  ["Workbench", "工作台"],
  ["Invocation Context", "调用上下文"],
  ["Assignment History", "分配历史"],
  ["Run Events", "运行事件"],
  ["No input payload.", "没有输入载荷。"],
  ["No result payload.", "没有结果载荷。"],
  ["No invocation context.", "没有调用上下文。"],
  ["No assignments recorded for this run.", "该运行没有分配记录。"],
  ["No observed events retained for this run.", "该运行没有保留的观察事件。"],
  ["No artifacts recorded for this run.", "该运行没有产物记录。"],
  ["Note: times use system time. Click any run for details, request/response summaries, and linked Trace.", "说明：时间均为系统时间；点击任意运行可查看详情、请求/响应摘要与关联 Trace。"],
  ["All tool workers operational", "所有工具工作器运行正常"],
  ["All systems operational", "所有系统运行正常"],
  ["Operator attention recommended", "建议操作员关注"],
  ["All LLM services operational", "所有 LLM 服务运行正常"],
  ["All channels accepting traffic", "所有通道正常接收流量"],
  ["All memory systems operational", "所有记忆系统运行正常"],
  ["All skill packages are healthy", "所有技能包健康"],
  ["All access assets operational", "所有访问资产运行正常"],
  ["Messages In", "入站消息"],
  ["Messages Out", "出站消息"],
  ["Retrying", "重试中"],
  ["Dead Letter", "死信"],
  ["Web / SSE", "Web / SSE"],
  ["Feishu / Lark", "飞书 / Lark"],
  ["Webhook", "Webhook"],
  ["Intake Events", "入口事件"],
  ["Delivery Events", "投递事件"],
  ["Channel Status", "通道状态"],
  ["Message Flow", "消息流"],
  ["Delivery Trend", "投递趋势"],
  ["Top Channels", "高频通道"],
  ["Dead Letter Queue", "死信队列"],
  ["Recent Messages", "最近消息"],
  ["Failures by Category", "按类别统计失败"],
  ["Channel Bindings", "通道绑定"],
  ["View all channels", "查看全部通道"],
  ["View all messages", "查看全部消息"],
  ["Replay selected", "重放已选"],
  ["Rate limited", "已限流"],
  ["Auth failed", "认证失败"],
  ["Payload invalid", "载荷无效"],
  ["Recipient unavailable", "收件方不可用"],
  ["Observed", "已观察"],
  ["Outbound", "出站"],
  ["Inbound", "入站"],
  ["Bound Agent", "绑定智能体"],
  ["Channel Profile", "通道配置"],
  ["Message ID", "消息 ID"],
  ["Direction", "方向"],
  ["Run / Session", "运行 / 会话"],
  ["Inbound (24h)", "入站（24h）"],
  ["Outbound (24h)", "出站（24h）"],
  ["P95", "P95"],
  ["Replay", "重放"],
  ["Drop", "丢弃"],
  ["Inspect", "检查"],
  ["Local CLI", "本地 CLI"],
  ["REST API", "REST API"],
  ["Workbench", "工作台"],
  ["SMTP", "SMTP"],
  ["Other", "其他"],
  ["Installed Skills", "已安装技能"],
  ["Available Skills", "可用技能"],
  ["Resolutions", "解析"],
  ["Retries", "重试"],
  ["Resolution Success Rate", "解析成功率"],
  ["Missing Capabilities", "缺失能力"],
  ["Resolution Failures", "解析失败"],
  ["Resolution Outcomes", "解析结果"],
  ["Recently Resolved Skills", "最近解析的技能"],
  ["Top Used Skills", "高频技能"],
  ["Access Requirements", "访问需求"],
  ["Capability Requirements", "能力需求"],
  ["Resolution Logs", "解析日志"],
  ["Resolver Detail", "解析器详情"],
  ["Declared Requirements", "已声明需求"],
  ["Resolver Mapping", "解析器映射"],
  ["Skill Package Sources", "技能包来源"],
  ["Skill Inspector", "技能检查器"],
  ["Failure Rate", "失败率"],
  ["Skill resolution and package health. Monitor packages, resolution results, requirements, and compatibility across the system.", "技能解析与包健康。监控包、解析结果、需求和系统兼容性。"],
  ["From all sources", "来自全部来源"],
  ["Requires attention", "需要关注"],
  ["Import / Normalize", "导入 / 规范化"],
  ["Upload Package", "上传包"],
  ["Drag and drop", "拖放"],
  ["Manifest", "清单"],
  ["Requirements", "需求"],
  ["Versions", "版本"],
  ["Categories", "类别"],
  ["Compatible", "兼容"],
  ["Trusted", "可信"],
  ["Unverified", "未验证"],
  ["External (Hub)", "外部（Hub）"],
  ["External (Git)", "外部（Git）"],
  ["Resolved", "已解析"],
  ["Partially Resolved", "部分解析"],
  ["Skipped", "已跳过"],
  ["Satisfied", "已满足"],
  ["Missing", "缺失"],
  ["Optional", "可选"],
  ["Capability Type", "能力类型"],
  ["Required Item", "必需项"],
  ["Required By (Skill)", "被依赖方（技能）"],
  ["Required By (Skills)", "被依赖方（技能）"],
  ["At", "时间点"],
  ["Resolved By", "解析来源"],
  ["Resolved To", "解析到"],
  ["Reason (if failed)", "原因（如失败）"],
  ["Used In (Run / Step)", "用于（运行 / 步骤）"],
  ["Used In Runs", "用于运行"],
  ["Used Runs (24h)", "使用运行（24h）"],
  ["Success Rate", "成功率"],
  ["Default Skill", "默认技能"],
  ["Winner", "胜出项"],
  ["Prompt Preference", "Prompt 偏好"],
  ["Tool Preference", "工具偏好"],
  ["Model Preference", "模型偏好"],
  ["Conflicts / Overrides", "冲突 / 覆盖"],
  ["Conflicts / Overrides (3)", "冲突 / 覆盖（3）"],
  ["Safety / Trust", "安全 / 信任"],
  ["Contains Scripts", "包含脚本"],
  ["High Risk Tools Requested", "请求高风险工具"],
  ["Trust Level", "信任级别"],
  ["Web / Chat", "Web / Chat"],
  ["Agent / Plan", "智能体 / 计划"],
  ["API / Batch", "API / 批处理"],
  ["retained tool run records", "保留的工具运行记录"],
  ["2 queued", "2 个排队中"],
  ["12 queued", "12 个排队中"],
  ["This is the lowest precedence layer. These values are inherited and can be overridden by upper layers.", "这是最低优先级层。这些值会被继承，也可以被上层覆盖。"],
  ["Applies to all environments unless overridden.", "除非被覆盖，否则适用于全部环境。"],
  ["18 Skills, 11 Channels, 6 Environments.", "18 个技能、11 个通道、6 个环境。"],
  ["Lower layers override upper layers; Turn/Run has highest priority.", "较低层会覆盖较高层；Turn / Run 拥有最高优先级。"],
  ["No issues found with current defaults.", "当前默认值未发现问题。"],
  ["Values flow from left (lowest) to right (highest). Higher layers override lower layers when values conflict.", "配置值从左侧（最低）流向右侧（最高）。发生冲突时，高优先级层会覆盖低优先级层。"],
  ["If a value is not set in a higher layer, the value from the nearest lower layer will be used.", "如果高层未设置某个值，将使用最近低层的值。"],
  ["Inline only for short, local tools. Avoid inline for long-running or I/O tools.", "Inline 仅适用于短耗时本地工具。长运行或 I/O 工具请避免 Inline。"],
  ["See which environments override these defaults.", "查看哪些环境覆盖了这些默认值。"],
  ["Simulate how these defaults resolve for a target.", "模拟这些默认值如何解析到目标。"],
  ["Preview effective configuration for a new run when no overrides are set in higher layers.", "预览高层无覆盖时，新运行的生效配置。"],
  ["Shows estimated impact of changing values in this layer.", "展示修改这一层配置的预估影响。"],
  ["Will be affected", "将受影响"],
  ["Impact Level", "影响等级"],
  ["Review history and rollback if needed.", "查看历史，并在需要时回滚。"],
  ["A reason is required to save changes to system defaults.", "保存系统默认值变更需要填写原因。"],
  ["Background (default)", "后台（默认）"],
  ["Background", "后台"],
  ["Inline", "内联"],
  ["Platform Default", "平台默认"],
  ["Default Policy", "默认策略"],
  ["System Defaults", "系统默认值"],
  ["2 attempts, Exponential", "2 次尝试，指数退避"],
  ["30 days", "30 天"],
  ["Key 100% / Verbose 20%", "关键 100% / 详细 20%"],
  ["More", "更多"],
  ["18 items", "18 项"],
  ["Run Simulation", "运行模拟"],
  ["PII Redaction Policy", "PII 脱敏策略"],
  ["Safety Guardrail Policy", "安全护栏策略"],
  ["Toxicity Filter Policy", "毒性过滤策略"],
  ["Prompt Injection Guard Policy", "Prompt 注入护栏策略"],
  ["Monitor the impact of Inline tools on the main thread", "关注 Inline 工具对主线程的影响"],
  ["Currently Inline tool runs", "当前仍为 Inline 的工具运行数"],
  ["Inline Share (Runs)", "Inline 占比 (Runs)"],
  ["Inline timeouts", "Inline 超时次数"],
  ["Recommendation: move long-running tools to Background execution", "建议：将长耗时工具改为 Background 执行"],
  ["JPG, PNG or SVG. Max size 1MB.", "支持 JPG、PNG 或 SVG，最大 1MB。"],
  ["Manage run scope & limits", "管理运行范围与限制"],
  ["Manage approval behavior", "管理审批行为"],
  ["View impact details", "查看影响详情"],
  ["Session Source", "会话来源"],
  ["Session", "会话"],
  ["Turn / Run", "轮次 / 运行"],
  ["Prod, Staging, Dev", "生产、预发、开发"],
  ["Prod, Staging", "生产、预发"],
  ["Prod, Dev", "生产、开发"],
  ["Staging, Dev", "预发、开发"],
  ["User Session, API / Batch", "用户会话、API / 批处理"],
  ["Profile-level", "画像级"],
  ["Session-level", "会话级"],
  ["One-time Approval", "一次性审批"],
  ["Setting Category", "设置类别"],
  ["Value Used", "使用值"],
  ["Overrides", "覆盖"],
  ["LLM: Default", "LLM：默认"],
  ["LLM: Temperature", "LLM：温度"],
  ["Memory: Retrieval Store", "记忆：检索存储"],
  ["Tool Policy: openai_api", "工具策略：openai_api"],
  ["Session Override", "会话覆盖"],
  ["Allow", "允许"],
  ["Default Skills (from profile)", "默认技能（来自画像）"],
  ["User Specified (session)", "用户指定（会话）"],
  ["Surface Recommendations", "Surface 推荐"],
  ["Surface:", "Surface："],
  ["Excluded / Not Allowed", "已排除 / 不允许"],
  ["8 skills", "8 个技能"],
  ["2 skills", "2 个技能"],
  ["3 skills", "3 个技能"],
  ["1 skill", "1 个技能"],
  ["8 applied", "8 项生效"],
  ["2 applied", "2 项生效"],
  ["LLM Profiles", "LLM 配置"],
  ["2 valid", "2 个有效"],
  ["6 valid", "6 个有效"],
  ["Overview", "概览"],
  ["Access Grants (6)", "访问授权（6）"],
  ["Default Skills (8)", "默认技能（8）"],
  ["Metadata", "元数据"],
  ["Last Saved:", "最近保存："],
] as const satisfies readonly CopyPair[];

const enToZh = new Map<string, string>(copyPairs);
const zhToEn = new Map<string, string>(copyPairs.map(([en, zh]) => [zh, en] as const));

const enTerms = new Map([
  ["assets", "资产"],
  ["asset", "资产"],
  ["agents", "智能体"],
  ["agent profiles", "智能体画像"],
  ["backups", "备份"],
  ["channels", "通道"],
  ["configs", "配置"],
  ["configuration", "配置"],
  ["contracts", "契约"],
  ["credentials", "凭据"],
  ["details", "详情"],
  ["environments", "环境"],
  ["events", "事件"],
  ["groups", "分组"],
  ["issues", "问题"],
  ["logs", "日志"],
  ["metrics", "指标"],
  ["profiles", "画像"],
  ["processes", "进程"],
  ["process", "进程"],
  ["nodes", "节点"],
  ["observers", "观察者"],
  ["resources", "资源"],
  ["runs", "运行"],
  ["settings", "设置"],
  ["skills", "技能"],
  ["subscribers", "订阅方"],
  ["surfaces", "Surface"],
  ["variables", "变量"],
  ["secrets", "密钥"],
  ["stores", "存储"],
  ["tools", "工具"],
]);
const zhTerms = new Map([...enTerms].map(([en, zh]) => [zh, en] as const));

export function localizeStaticCopyTree(root: HTMLElement, locale: Locale): void {
  if (typeof document === "undefined") return;
  localizeElement(root, locale);
  for (const element of root.querySelectorAll<HTMLElement>("[placeholder], [title], [aria-label]")) {
    localizeElement(element, locale);
  }

  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement;
      if (!parent || parent.closest("script, style, code, pre, svg, textarea, [data-i18n-skip], [data-user-content]")) {
        return NodeFilter.FILTER_REJECT;
      }
      return node.nodeValue?.trim() ? NodeFilter.FILTER_ACCEPT : NodeFilter.FILTER_REJECT;
    },
  });

  while (walker.nextNode()) {
    localizeTextNode(walker.currentNode as Text, locale);
  }
}

function localizeElement(element: HTMLElement, locale: Locale): void {
  if (element.closest("[data-i18n-skip], [data-user-content]")) return;

  for (const attribute of ["placeholder", "title", "aria-label"] as const) {
    const value = element.getAttribute(attribute);
    if (!value) continue;
    const nextValue = localizeStaticCopy(value, locale);
    if (nextValue !== value) {
      element.setAttribute(attribute, nextValue);
    }
  }
}

function localizeTextNode(node: Text, locale: Locale): void {
  const value = node.nodeValue ?? "";
  const nextValue = localizeStaticCopy(value, locale);
  if (nextValue !== value) {
    node.nodeValue = nextValue;
  }
}

function localizeStaticCopy(value: string, locale: Locale): string {
  const leading = value.match(/^\s*/)?.[0] ?? "";
  const trailing = value.match(/\s*$/)?.[0] ?? "";
  const text = value.trim();
  if (!text) return value;

  const localized = locale === "zh-CN"
    ? localizeEnglishToChinese(text)
    : localizeChineseToEnglish(text);

  return localized === text ? value : `${leading}${localized}${trailing}`;
}

function localizeEnglishToChinese(text: string): string {
  const exact = enToZh.get(text);
  if (exact) return exact;

  const showingDash = text.match(/^Showing ([\d,]+)-([\d,]+) of ([\d,]+)$/);
  if (showingDash) return `显示 ${showingDash[1]}-${showingDash[2]}，共 ${showingDash[3]}`;

  const showingTo = text.match(/^Showing ([\d,]+) to ([\d,]+) of ([\d,]+) results$/);
  if (showingTo) return `显示 ${showingTo[1]}-${showingTo[2]}，共 ${showingTo[3]} 条结果`;

  const showingItems = text.match(/^Showing ([\d,]+) to ([\d,]+) of ([\d,]+) (.+)$/);
  if (showingItems) {
    const term = translateEnglishTerm(showingItems[4]);
    if (term !== showingItems[4]) return `显示 ${showingItems[1]}-${showingItems[2]}，共 ${showingItems[3]} 个${term}`;
  }

  const rowsPerPage = text.match(/^Rows per page ([\d,]+)$/);
  if (rowsPerPage) return `每页 ${rowsPerPage[1]} 行`;

  const lastHeartbeat = text.match(/^Last heartbeat: (.+)$/);
  if (lastHeartbeat) return `最近心跳：${lastHeartbeat[1]}`;

  const lastSaved = text.match(/^Last Saved: (.+)$/);
  if (lastSaved) return `最近保存：${translateEnglishTime(lastSaved[1])}`;

  const validation = text.match(/^Validation: (.+)$/);
  if (validation) return `校验：${translateEnglishTerm(validation[1])}`;

  const accessGrants = text.match(/^Access Grants \((\d+)\)$/);
  if (accessGrants) return `访问授权（${accessGrants[1]}）`;

  const defaultSkills = text.match(/^Default Skills \((\d+)\)$/);
  if (defaultSkills) return `默认技能（${defaultSkills[1]}）`;

  const labeledCount = text.match(/^(.+) \((\d+)\)$/);
  if (labeledCount) {
    const term = translateEnglishTerm(labeledCount[1]);
    if (term !== labeledCount[1]) return `${term}（${labeledCount[2]}）`;
  }

  const timeAgo = translateEnglishTime(text);
  if (timeAgo !== text) return timeAgo;

  const agentLabel = text.match(/^Agent: (.+)$/);
  if (agentLabel) return `智能体：${agentLabel[1]}`;

  const selectedActor = text.match(/^Selected Actor: (.+)$/);
  if (selectedActor) return `已选操作者：${selectedActor[1]}`;

  const forAgentProfile = text.match(/^For agent profile: (.+)$/);
  if (forAgentProfile) return `适用于智能体画像：${forAgentProfile[1]}`;

  const createdBy = text.match(/^Created by (.+) on (.+)$/);
  if (createdBy) return `由 ${createdBy[1]} 于 ${createdBy[2]} 创建`;

  const inRelativeTime = text.match(/^in (\d+) (minute|minutes|hour|hours|day|days|week|weeks)$/);
  if (inRelativeTime) return `${inRelativeTime[1]} ${translateEnglishTimeUnit(inRelativeTime[2])}后`;

  const labeledNumber = text.match(/^(Background|Inline) ([\d,]+)$/);
  if (labeledNumber) return `${translateEnglishTerm(labeledNumber[1])} ${labeledNumber[2]}`;

  const fromRequest = text.match(/^From request: (.+)$/);
  if (fromRequest) return `来自请求：${fromRequest[1]}`;

  const environmentKeys = text.match(/^Environment for (\d+) keys$/);
  if (environmentKeys) return `${environmentKeys[1]} 个 Key 的环境`;

  const delta = text.match(/^([+-]?\d+(?:\.\d+)?(?:%|s)?) vs yesterday$/);
  if (delta) return `较昨日 ${delta[1]}`;

  const nowDelta = text.match(/^(\d+) vs now$/);
  if (nowDelta) return `较当前 +${nowDelta[1]}`;

  const countUnit = text.match(/^(\d+) (queued|results|documents|grants|skills|items|valid|applied)$/);
  if (countUnit) return `${countUnit[1]} ${translateEnglishCountUnit(countUnit[2])}`;

  const countPhrase = text.match(/^(\d+) (agent profiles)$/);
  if (countPhrase) return `${countPhrase[1]} 个${translateEnglishTerm(countPhrase[2])}`;

  const timeout = text.match(/^Timeout after (\d+)s$/);
  if (timeout) return `${timeout[1]}s 后超时`;

  const viewAll = text.match(/^View all(?: (.+))?$/);
  if (viewAll) return viewAll[1] ? `查看全部${translateEnglishTerm(viewAll[1])}` : "查看全部";

  const view = text.match(/^View (.+)$/);
  if (view) return `查看${translateEnglishTerm(view[1])}`;

  const manage = text.match(/^Manage (.+)$/);
  if (manage) return `管理${translateEnglishTerm(manage[1])}`;

  const search = text.match(/^Search (.+)\.\.\.$/);
  if (search) return `搜索${translateEnglishTerm(search[1])}...`;

  const all = text.match(/^All (.+)$/);
  if (all) return `全部${translateEnglishTerm(all[1])}`;

  const create = text.match(/^Create (.+)$/);
  if (create) return `创建${translateEnglishTerm(create[1])}`;

  const add = text.match(/^Add (.+)$/);
  if (add) return `添加${translateEnglishTerm(add[1])}`;

  const newItem = text.match(/^New (.+)$/);
  if (newItem) return `新建${translateEnglishTerm(newItem[1])}`;

  const configSource = text.match(/^Config Source: (.+)$/);
  if (configSource) return `配置来源：${translateEnglishTerm(configSource[1])}`;

  const inherited = text.match(/^Inherited From: (.+)$/);
  if (inherited) return `继承自：${translateEnglishTerm(inherited[1])}`;

  const configVersion = text.match(/^Config Version: (.+)$/);
  if (configVersion) return `配置版本：${configVersion[1]}`;

  return text;
}

function localizeChineseToEnglish(text: string): string {
  const exact = zhToEn.get(text);
  if (exact) return exact;

  const showingDash = text.match(/^显示 ([\d,]+)-([\d,]+)，共 ([\d,]+)$/);
  if (showingDash) return `Showing ${showingDash[1]}-${showingDash[2]} of ${showingDash[3]}`;

  const showingTo = text.match(/^显示 ([\d,]+)-([\d,]+)，共 ([\d,]+) 条结果$/);
  if (showingTo) return `Showing ${showingTo[1]} to ${showingTo[2]} of ${showingTo[3]} results`;

  const showingItems = text.match(/^显示 ([\d,]+)-([\d,]+)，共 ([\d,]+) 个(.+)$/);
  if (showingItems) {
    const term = translateChineseTerm(showingItems[4]);
    if (term !== showingItems[4]) return `Showing ${showingItems[1]} to ${showingItems[2]} of ${showingItems[3]} ${term}`;
  }

  const rowsPerPage = text.match(/^每页 ([\d,]+) 行$/);
  if (rowsPerPage) return `Rows per page ${rowsPerPage[1]}`;

  const lastHeartbeat = text.match(/^最近心跳：(.+)$/);
  if (lastHeartbeat) return `Last heartbeat: ${lastHeartbeat[1]}`;

  const lastSaved = text.match(/^最近保存：(.+)$/);
  if (lastSaved) return `Last Saved: ${translateChineseTime(lastSaved[1])}`;

  const validation = text.match(/^校验：(.+)$/);
  if (validation) return `Validation: ${translateChineseTerm(validation[1])}`;

  const accessGrants = text.match(/^访问授权（(\d+)）$/);
  if (accessGrants) return `Access Grants (${accessGrants[1]})`;

  const defaultSkills = text.match(/^默认技能（(\d+)）$/);
  if (defaultSkills) return `Default Skills (${defaultSkills[1]})`;

  const labeledCount = text.match(/^(.+)（(\d+)）$/);
  if (labeledCount) {
    const term = translateChineseTerm(labeledCount[1]);
    if (term !== labeledCount[1]) return `${term} (${labeledCount[2]})`;
  }

  const timeAgo = translateChineseTime(text);
  if (timeAgo !== text) return timeAgo;

  const agentLabel = text.match(/^智能体：(.+)$/);
  if (agentLabel) return `Agent: ${agentLabel[1]}`;

  const selectedActor = text.match(/^已选操作者：(.+)$/);
  if (selectedActor) return `Selected Actor: ${selectedActor[1]}`;

  const forAgentProfile = text.match(/^适用于智能体画像：(.+)$/);
  if (forAgentProfile) return `For agent profile: ${forAgentProfile[1]}`;

  const createdBy = text.match(/^由 (.+) 于 (.+) 创建$/);
  if (createdBy) return `Created by ${createdBy[1]} on ${createdBy[2]}`;

  const inRelativeTime = text.match(/^(\d+) (分钟|小时|天|周)后$/);
  if (inRelativeTime) return `in ${inRelativeTime[1]} ${translateChineseTimeUnit(inRelativeTime[2], Number(inRelativeTime[1]))}`;

  const labeledNumber = text.match(/^(后台|内联) ([\d,]+)$/);
  if (labeledNumber) return `${translateChineseTerm(labeledNumber[1])} ${labeledNumber[2]}`;

  const fromRequest = text.match(/^来自请求：(.+)$/);
  if (fromRequest) return `From request: ${fromRequest[1]}`;

  const environmentKeys = text.match(/^(\d+) 个 Key 的环境$/);
  if (environmentKeys) return `Environment for ${environmentKeys[1]} keys`;

  const delta = text.match(/^较昨日 ([+-]?\d+(?:\.\d+)?(?:%|s)?)$/);
  if (delta) return `${delta[1]} vs yesterday`;

  const nowDelta = text.match(/^较当前 \+(\d+)$/);
  if (nowDelta) return `${nowDelta[1]} vs now`;

  const countUnit = text.match(/^(\d+) (个排队中|个结果|份文档|项授权|个技能|项|个有效|项生效)$/);
  if (countUnit) return `${countUnit[1]} ${translateChineseCountUnit(countUnit[2])}`;

  const countPhrase = text.match(/^(\d+) 个智能体画像$/);
  if (countPhrase) return `${countPhrase[1]} agent profiles`;

  const timeout = text.match(/^(\d+)s 后超时$/);
  if (timeout) return `Timeout after ${timeout[1]}s`;

  const viewAll = text.match(/^查看全部(.+)$/);
  if (viewAll) return `View all ${translateChineseTerm(viewAll[1])}`;

  const view = text.match(/^查看(.+)$/);
  if (view) return `View ${translateChineseTerm(view[1])}`;

  const manage = text.match(/^管理(.+)$/);
  if (manage) return `Manage ${translateChineseTerm(manage[1])}`;

  const create = text.match(/^创建(.+)$/);
  if (create) return `Create ${translateChineseTerm(create[1])}`;

  const add = text.match(/^添加(.+)$/);
  if (add) return `Add ${translateChineseTerm(add[1])}`;

  const newItem = text.match(/^新建(.+)$/);
  if (newItem) return `New ${translateChineseTerm(newItem[1])}`;

  const configSource = text.match(/^配置来源：(.+)$/);
  if (configSource) return `Config Source: ${translateChineseTerm(configSource[1])}`;

  const inherited = text.match(/^继承自：(.+)$/);
  if (inherited) return `Inherited From: ${translateChineseTerm(inherited[1])}`;

  const configVersion = text.match(/^配置版本：(.+)$/);
  if (configVersion) return `Config Version: ${configVersion[1]}`;

  return text;
}

function translateEnglishTerm(value: string): string {
  const normalized = value.trim();
  const exact = enToZh.get(normalized);
  if (exact) return exact;

  const suffix = normalized.match(/\s*\([^)]*\)\s*$/)?.[0] ?? "";
  const withoutCount = normalized.replace(/\s*\([^)]*\)\s*$/, "");
  const lower = withoutCount.toLowerCase();
  const translated = enTerms.get(lower) ?? withoutCount;
  return `${translated}${suffix}`;
}

function translateChineseTerm(value: string): string {
  const normalized = value.trim();
  const exact = zhToEn.get(normalized);
  if (exact) return exact;

  const suffix = normalized.match(/\s*[（(][^)）]*[)）]\s*$/)?.[0] ?? "";
  const withoutCount = normalized.replace(/\s*[（(][^)）]*[)）]\s*$/, "");
  const translated = zhTerms.get(withoutCount) ?? withoutCount;
  return `${translated}${suffix}`;
}

function translateEnglishTime(value: string): string {
  const normalized = value.trim();
  const relative = normalized.match(/^(\d+) (minute|minutes|hour|hours|day|days|week|weeks) ago$/);
  if (!relative) return value;

  const unit = {
    minute: "分钟",
    minutes: "分钟",
    hour: "小时",
    hours: "小时",
    day: "天",
    days: "天",
    week: "周",
    weeks: "周",
  }[relative[2]];

  return `${relative[1]} ${unit}前`;
}

function translateChineseTime(value: string): string {
  const normalized = value.trim();
  const relative = normalized.match(/^(\d+) (分钟|小时|天|周)前$/);
  if (!relative) return value;

  const unit = {
    "分钟": Number(relative[1]) === 1 ? "minute" : "minutes",
    "小时": Number(relative[1]) === 1 ? "hour" : "hours",
    "天": Number(relative[1]) === 1 ? "day" : "days",
    "周": Number(relative[1]) === 1 ? "week" : "weeks",
  }[relative[2]];

  return `${relative[1]} ${unit} ago`;
}

function translateEnglishTimeUnit(value: string): string {
  return {
    minute: "分钟",
    minutes: "分钟",
    hour: "小时",
    hours: "小时",
    day: "天",
    days: "天",
    week: "周",
    weeks: "周",
  }[value] ?? value;
}

function translateChineseTimeUnit(value: string, count: number): string {
  return {
    "分钟": count === 1 ? "minute" : "minutes",
    "小时": count === 1 ? "hour" : "hours",
    "天": count === 1 ? "day" : "days",
    "周": count === 1 ? "week" : "weeks",
  }[value] ?? value;
}

function translateEnglishCountUnit(value: string): string {
  return {
    queued: "个排队中",
    results: "个结果",
    documents: "份文档",
    grants: "项授权",
    skills: "个技能",
    items: "项",
    valid: "个有效",
    applied: "项生效",
  }[value] ?? value;
}

function translateChineseCountUnit(value: string): string {
  return {
    "个排队中": "queued",
    "个结果": "results",
    "份文档": "documents",
    "项授权": "grants",
    "个技能": "skills",
    "项": "items",
    "个有效": "valid",
    "项生效": "applied",
  }[value] ?? value;
}
