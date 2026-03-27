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
| global.email | certbot 注册邮箱 | admin@example.com | CLI/Service |
| global.letsencrypt_dir | certbot 状态目录 | letsencrypt | CLI/Service |
| server.db_path | 控制面数据库 | data/run/certman.db | Service/Agent |
| server.listen_host | API 监听地址 | 0.0.0.0 | Service |
| server.listen_port | API 监听端口 | 8000 | Service |
| server.signing_key_path | 服务端签名私钥 | null | Service/Agent |
| control_plane.endpoint | 控制面地址 | 无 | Agent |
| control_plane.poll_interval_seconds | 轮询周期（秒） | 30 | Agent |
| node_identity.node_id | 节点唯一标识 | 无 | Agent |
| node_identity.private_key_path | 节点私钥路径 | 无 | Agent |

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

用途：将 certbot live 目录导出到 data/output/<entry>/。

```bash
uv run certman -D data export --name site-a --overwrite
```

## 4. Service API 手册

### 4.0 实时 API 文档

- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

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
{"success":true,"data":{"job_id":"..."}}
```

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

- 支持 `subject_id`、`status`、`limit` 查询过滤。

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
- 成功后尝试分配任务并回传 bundle_signature。

### 5.2 result

POST /api/v1/node-agent/result

请求字段：

- node_id, job_id, status(completed|failed)
- output/error
- timestamp, nonce, signature

约束：

- 仅 running 任务可更新结果。
- 任务 node_id 必须与上报 node_id 一致（若已绑定）。
- 签名覆盖 job_id/status/output/error 组合载荷。

## 6. 远程 CLI 手册（`certmanctl`）

主要命令：

- `certmanctl health`
- `certmanctl cert create|list|get|renew`
- `certmanctl job get|list|wait`
- `certmanctl webhook create|list|get|update|delete`

`certmanctl` 本质是 REST 的运维 CLI 封装，适合 shell 自动化和偏命令式的远程操作。

## 7. MCP 状态

- 本仓库已提供 `certman-mcp` 的 stdio MCP Server。
- 可通过 `uv run certman-mcp --endpoint http://127.0.0.1:8000` 启动，并作为控制面 REST API 的工具封装层使用。

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
