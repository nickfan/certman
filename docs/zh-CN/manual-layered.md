# 三层运维手册（CLI / Agent / Service）

本手册聚焦抽象参数、边界行为、状态机与接口契约，适合作为实施和审计参考。

## 1. 层级职责边界

- CLI 层：人机交互入口，直接执行 certbot 生命周期操作。
- Service 层：任务编排与状态持久化，暴露 API 与 webhook。
- Agent 层：节点侧执行代理，通过签名消息与控制面通信。

## 2. 全局配置参数（config.toml）

| 参数 | 作用 | 默认值 | 影响层 |
| --- | --- | --- | --- |
| run_mode | 运行模式 local/agent/server | local | 三层 |
| global.data_dir | 数据根目录 | data | 三层 |
| global.acme_server | 证书环境 staging/prod | staging | CLI/Service |
| global.email | certbot 注册邮箱 | `admin@example.com` | CLI/Service |
| global.letsencrypt_dir | certbot 状态目录 | letsencrypt | CLI/Service |
| server.db_path | 控制面数据库 | data/run/certman.db | Service/Agent |
| server.listen_host | API 监听地址 | 0.0.0.0 | Service |
| server.listen_port | API 监听端口 | 8000 | Service |
| server.signing_key_path | 服务端签名私钥 | null | Service/Agent |
| server.bundle_token_required | 是否要求短时 bundle token | true | Service/Agent |
| server.bundle_token_ttl_seconds | bundle token 有效期（秒） | 300 | Service/Agent |
| scheduler.enabled | 调度全局开关 | false | Service/Scheduler |
| scheduler.mode | 调度模式 loop/cron | loop | Scheduler |
| scheduler.scan_interval_seconds | loop 间隔秒数 | 300 | Scheduler |
| scheduler.cron_expr | cron 表达式（5段） | `0 * * * *` | Scheduler |
| scheduler.cron_poll_seconds | cron 轮询时钟间隔 | 15 | Scheduler |
| scheduler.renew_before_days | 提前 N 天入队 renew | 30 | Scheduler |
| control_plane.endpoint | 控制面地址 | 无 | Agent |
| control_plane.poll_interval_seconds | 轮询周期（秒） | 30 | Agent |
| control_plane.prefer_sse | 是否优先 SSE 事件通道 | false | Agent |
| control_plane.sse_wait_seconds | SSE 单次等待秒数 | 25 | Agent |
| control_plane.prefer_subscribe | 是否优先 subscribe 长轮询 | false | Agent |
| control_plane.subscribe_wait_seconds | subscribe 等待秒数 | 25 | Agent |
| node_identity.node_id | 节点唯一标识 | 无 | Agent |
| node_identity.private_key_path | 节点私钥路径 | 无 | Agent |
| entries[].target_type | 旧版单目标类型（generic/nginx/openresty/k8s-ingress） | generic | Service/Agent |
| entries[].target_scope | 目标作用域（环境/集群标签） | null | Service/Agent |
| entries[].delivery_targets[] | 推荐使用的多目标交付列表（如 `aws-acm`、`k8s-ingress`） | [] | Service/Agent |
| entries[].delivery_targets[].enabled | 可选交付目标的显式开关 | true | Service/Agent |

## 3. CLI 命令手册

### 3.1 config-validate

用途：校验配置与必要环境变量。

```bash
uv run certman -D data config-validate --name site-a

# 需要全量校验时显式使用 --all
uv run certman -D data config-validate --all
```

失败条件：

- 条目启用 account_id 但对应 provider 变量缺失。
- run_mode 与必选块不匹配（如 agent 缺 control_plane）。

### 3.2 new

用途：首次签发或强制重签。

```bash
uv run certman -D data new --name site-a --force --verbose
```

关键参数：

- --name：条目名。
- --force：即使已有 lineage 也重签。
- --export/--no-export：是否自动导出。

### 3.3 renew

用途：续签一个或全部条目。

```bash
uv run certman -D data renew --all --force
```

关键参数：

- --all 与 --name 二选一。
- --dry-run：走 staging 流程，不落盘。

### 3.4 check

用途：巡检，不默认执行续签。

```bash
uv run certman -D data check --warn-days 30 --force-renew-days 7
```

抽象阈值公式：

- 告警阈值：days_left <= warn_days
- 强制阈值：days_left <= force_renew_days

建议关系：force_renew_days < warn_days。

### 3.5 export

用途：将 certbot live 目录导出到 `data/output/entry_name/`。

```bash
uv run certman -D data export --name site-a --overwrite
```

### 3.6 oneshot-issue / oneshot-renew（纯参数模式）

用于自动化/AI 技能调用，不依赖配置文件：

```bash
uv run certman -D data oneshot-issue -d example.com -d *.example.com -sp aliyun --email ops@example.com --ak <ak> --sk <sk> -o /tmp/example
uv run certman -D data oneshot-renew -d example.com -d *.example.com -sp aliyun --email ops@example.com --ak <ak> --sk <sk> -o /tmp/example
```

provider 凭据要求：

- aliyun/route53：`--ak` + `--sk`
- cloudflare：`--api-token`

### 3.7 本地 config/env 命令

`certman config`：支持 `list/show/add/edit/remove/init`。

`certman env`：支持 `.env` 的 `list/set/unset`。

## 4. Service API 手册

### 4.0 实时 API 文档

- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`
- Prometheus Metrics: `/metrics`

这些地址由 `certman-server` 直接暴露。

### 4.1 证书相关 API

证书/job REST 鉴权策略：

- 默认关闭：`[server].token_auth_enabled = false`
- 开启后要求 Bearer token，解析优先级：`entries[].token` > `global.token`
- 已开启但当前目标无有效 token：`500 AUTH_TOKEN_CONFIG_ERROR`
- 已开启且缺少 token：`401 AUTH_MISSING_TOKEN`
- 已开启且 token 错误：`401 AUTH_INVALID_TOKEN`

POST /api/v1/certificates

请求：

```json
{"entry_name":"site-a"}
```

响应（202）：

```json
{"success":true,"data":{"job_id":"...","created":true}}
```

若同条目已经存在 queued 的 issue job，则复用已有 job，并返回 `created=false`。

GET /api/v1/certificates

- 返回最近的证书相关 job（`issue` + `renew`）。

GET /api/v1/certificates/{entry_name}

- 返回某个配置条目的 job 列表。

POST /api/v1/certificates/{entry_name}/renew

```json
{"success":true,"data":{"job_id":"...","created":true}}
```

若同条目已经存在 queued 的 renew job，则复用已有 job，并返回 `created=false`。

### 4.2 Job API

GET /api/v1/jobs

- 支持 `subject_id`、`status`、`target_scope`、`limit` 查询过滤。

GET /api/v1/jobs/{job_id}

状态枚举：queued, running, completed, failed, cancelled。

### 4.3 Webhook API

POST /api/v1/webhooks

请求：

```json
{"topic":"job.completed","endpoint":"https://ops.example/hook","secret":"topsecret"}
```

GET /api/v1/webhooks

- 按 topic/status 过滤并返回订阅列表。

GET /api/v1/webhooks/{subscription_id}

- 查询单个订阅。

PUT /api/v1/webhooks/{subscription_id}

- 更新 endpoint、secret 或 status。

DELETE /api/v1/webhooks/{subscription_id}

- 删除订阅。

### 4.4 节点注册 API

POST /api/v1/nodes/register

- 需要一次性 registration token。
- 接收 PEM 编码的 Ed25519 公钥。
- 返回后续 agent poll 用的 `poll_endpoint`。

### 4.5 只读配置 API

- `GET /api/v1/config/entries`
- `GET /api/v1/config/entries/{entry_name}`
- `POST /api/v1/config/validate`

## 5. Agent 协议手册

### 5.1 poll

POST /api/v1/node-agent/poll

请求字段：

- node_id: 节点 ID
- timestamp: 秒级时间戳
- nonce: 一次性随机串
- agent_version: agent 版本
- signature: Ed25519 签名

语义：

- 服务端校验签名。
- nonce 入库，重复 nonce 返回 409（防重放）。
- 成功后尝试分配任务并回传 bundle_signature；当开启短时令牌策略时还会返回 `bundle_token` 与 `bundle_token_expires_at`。

### 5.2 subscribe

POST /api/v1/node-agent/subscribe

语义：

- 与 poll 使用同一签名和 nonce 规则。
- 服务端执行长轮询，等待作业事件或超时。
- 命中任务时直接返回 assignments，未命中返回空列表并由 agent 回退到 poll。

### 5.2.1 events (SSE)

GET /api/v1/node-agent/events

语义：

- 使用签名查询参数建立 SSE 通道（`node_id/timestamp/nonce/signature`）。
- 连接建立后先发送 `connected` 事件，再在任务到达时发送 `assignment` 事件。
- 若等待窗口超时则发送 `timeout` 事件；agent 应按 `events -> subscribe -> poll` 链路回退。

### 5.3 heartbeat

POST /api/v1/node-agent/heartbeat

语义：

- 轻量活跃探测，更新节点在线状态。
- 失败时不改变 job 状态，仅作为链路监控信号。

### 5.4 callback / result

POST /api/v1/node-agent/result

请求字段：

- node_id, job_id, status(completed|failed)
- output/error
- timestamp, nonce, signature

约束：

- 仅 running 任务可更新结果。
- 任务 node_id 必须与上报 node_id 一致（若已绑定）。
- 签名覆盖 job_id/status/output/error 组合载荷。

POST /api/v1/node-agent/callback

- 语义与 result 一致，保留给节点回调语义化入口。

## 6. 远程 CLI 手册（`certmanctl`）

主要命令：

- `certmanctl health`
- `certmanctl cert create|list|get|renew`
- `certmanctl job get|list|wait`
- `certmanctl webhook create|list|get|update|delete`
- `certmanctl config list|show|validate`

`certmanctl` 本质是 REST 的运维 CLI 封装，适合 shell 自动化和偏命令式的远程操作。

## 7. MCP 状态

- 本仓库已提供 `certman-mcp` 的 stdio MCP Server。
- 可通过 `uv run certman-mcp --endpoint http://127.0.0.1:8000` 启动，并作为控制面 REST API 的工具封装层使用。

当前 MCP 工具包含：health、cert_*、job_*、webhook_*、config_list/config_get/config_validate。

其中 `job_list` 支持 `target_scope` 过滤，便于多环境分批观测。

## 7.1 Scheduler 运行模式

- 常驻模式：`uv run certman-scheduler run --data-dir data --config-file config.toml --loop`
- 一次性模式：`uv run certman-scheduler once --data-dir data --config-file config.toml --force-enable`
- 作用域调度：在上述命令追加 `--target-scope <scope>`
- K8s CronJob 示例：`k8s/certman-scheduler-cronjob.yaml`

## 8. 状态机与并发语义

- job 创建初始状态：queued。
- worker/agent 认领：queued -> running（原子更新）。
- 执行完成：running -> completed 或 failed。
- 同 subject 的 renew 任务在 queued/running 上唯一，避免重复堆积。

## 9. 安全参数建议

- nonce TTL：默认 3600 秒，建议与最大重试窗口一致。
- 节点时间偏差：建议控制在 60 秒内。
- 签名密钥轮换：按季度轮换，轮换期保持双公钥兼容（若后续实现）。

## 10. 生产建议基线

- 每日 check + 告警，不把续签逻辑塞入告警路径。
- server 与 worker 共享同一 db_path 并做持久化备份。
- 针对 agent 通信链路监控 401/409 比率，快速发现时钟与重放异常。
