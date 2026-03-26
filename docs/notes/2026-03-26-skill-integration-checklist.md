# CertMan Skill 接入清单（Local + CTL + MCP）

更新时间：2026-03-26
适用范围：为 AI skill / tool 封装 CertMan 命令与接口调用

## 1. 接入面选择策略

优先级建议：

1. 远程控制面自动化：优先 certmanctl
2. AI 工具化调用：优先 certman-mcp（stdio）
3. 本地单机维护：使用 certman
4. 需要强类型 API 编排：使用 OpenAPI + REST

决策规则：

- 只管理本机证书：走 certman
- 管理 server 上的 job/webhook：走 certmanctl 或 certman-mcp
- 需要稳定退出码：优先 certmanctl
- 需要 LLM 工具调用：优先 certman-mcp

## 2. 命令意图映射

### 2.1 Local（certman）

- 意图：查看配置条目
  - 命令：uv run certman -D data entries
- 意图：签发新证书
  - 命令：uv run certman -D data new --name <entry>
- 意图：续签证书
  - 命令：uv run certman -D data renew --name <entry>
  - 命令：uv run certman -D data renew --all
- 意图：导出证书产物
  - 命令：uv run certman -D data export --name <entry>
- 意图：巡检到期并输出机器可读结果
  - 命令：uv run certman -D data check --json
- 意图：配置校验
  - 命令：uv run certman -D data config-validate
- 意图：日志清理
  - 命令：uv run certman -D data logs-clean --keep-days 30

### 2.2 Remote（certmanctl）

- 意图：控制面健康检查
  - 命令：uv run certmanctl --endpoint <url> health
- 意图：创建签发任务
  - 命令：uv run certmanctl --endpoint <url> cert create --entry-name <entry>
- 意图：查证书相关任务
  - 命令：uv run certmanctl --endpoint <url> cert list
  - 命令：uv run certmanctl --endpoint <url> cert get --entry-name <entry>
- 意图：创建或复用续签任务
  - 命令：uv run certmanctl --endpoint <url> cert renew --entry-name <entry>
- 意图：查询任务
  - 命令：uv run certmanctl --endpoint <url> job get --job-id <job_id>
  - 命令：uv run certmanctl --endpoint <url> job list --subject-id <entry> --status running --limit 50
- 意图：等待任务终态
  - 命令：uv run certmanctl --endpoint <url> job wait --job-id <job_id> --poll-interval 3 --max-wait 120
- 意图：webhook 管理
  - 创建：uv run certmanctl --endpoint <url> webhook create --topic job.completed --endpoint-url <hook_url> --secret <secret>
  - 列表：uv run certmanctl --endpoint <url> webhook list
  - 查询：uv run certmanctl --endpoint <url> webhook get --id <id>
  - 更新：uv run certmanctl --endpoint <url> webhook update --id <id> --status inactive
  - 删除：uv run certmanctl --endpoint <url> webhook delete --id <id>

### 2.3 MCP（certman-mcp）

启动：

- uv run certman-mcp --endpoint http://127.0.0.1:8000
- 可选：设置 CERTMAN_MCP_TOKEN

工具面：

- health
- cert_create / cert_list / cert_get / cert_renew
- job_get / job_list / job_wait
- webhook_create / webhook_list / webhook_get / webhook_update / webhook_delete

## 3. 参数约束与校验清单

通用输入校验：

- endpoint 必须是 http/https URL，禁止空字符串
- entry_name、job_id、subscription_id 不可为空
- webhook endpoint-url 必须是 URL
- webhook secret 不可为空
- job list limit 范围 1-200
- output 仅允许 text 或 json

安全与兼容：

- Bearer token 优先走环境变量注入
- 不在日志中打印 secret/token
- 对 path 参数执行 URL 编码（已在 ctl/mcp 内部处理）
- query 参数使用参数字典编码（已在 ctl/mcp 内部处理）

## 4. Skill Preflight（执行前检查）

每次 skill 调用前建议执行：

1. 运行时探活
- uv run certmanctl --endpoint <url> health

2. 命令能力检查
- uv run certman --help
- uv run certmanctl --help
- uv run certmanctl job wait --help

3. 接口契约检查（可选）
- GET <url>/openapi.json

4. 配置与目录检查（local 场景）
- data/conf/config.toml 是否存在
- data/run 与 data/output 目录可写

## 5. 失败码与错误分层

### 5.1 certmanctl 退出码

- 0：成功
- 1：业务失败或等待超时（例如 job wait 超时，或 failed 终态）
- 3：网络层失败（NETWORK_ERROR）
- 4：API 层失败（API_ERROR）

### 5.2 certman check 退出码

- 0：正常
- 10：告警（接近到期）
- 20：强制续签窗口
- 30：证书缺失或条目异常

### 5.3 Skill 错误分类建议

- TransportError：网络不可达、DNS、连接拒绝
- ApiError：控制面返回业务错误
- TimeoutError：等待终态超时
- ValidationError：输入参数不合法

## 6. 推荐的 Skill 执行流程

### 场景 A：签发并等待完成

1. health
2. cert create
3. job wait
4. 成功则输出 job 结果
5. 失败则输出错误分类 + 原始错误码

### 场景 B：续签巡检闭环

1. local check --json
2. 若 exit code 为 20，触发 cert renew
3. job wait
4. 记录结果并输出摘要

### 场景 C：Webhook 配置变更

1. webhook list 读取现状
2. webhook update 或 create
3. webhook get 复核

## 7. 文档与事实源

建议 skill 优先读取：

1. docs/zh-CN/cli-help-reference.md
2. docs/en/cli-help-reference.md
3. docs/zh-CN/api-access.md
4. docs/en/api-access.md
5. /openapi.json（运行时事实源）

---

维护说明：

- 若命令参数发生变化，优先更新 cli-help-reference，再更新本清单。
- 若 API 路径或 schema 变化，更新 api-access 与 openapi 校验用例。
