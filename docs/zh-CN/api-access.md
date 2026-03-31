# API 与 AI 接入

本文描述 CertMan 当前对机器侧暴露的正式接入面。

## 1. 控制面文档地址

当 `certman-server` 运行在 `http://127.0.0.1:8000` 时，实时 API 文档地址为：

- Swagger UI：`http://127.0.0.1:8000/docs`
- ReDoc：`http://127.0.0.1:8000/redoc`
- OpenAPI JSON：`http://127.0.0.1:8000/openapi.json`

## 2. 当前正式对外接口

当前支持：

- `certman-server` 暴露的 HTTP REST API
- FastAPI 自动生成的 OpenAPI schema
- Prometheus 指标接口：`GET /metrics`
- `certmanctl` 作为面向运维的 REST CLI 封装
- `certman-mcp` 提供的 stdio MCP Server（封装控制面 API）

## 2.1 MCP 启动示例

```bash
uv run certman-mcp --endpoint http://127.0.0.1:8000
```

该 MCP Server 使用 stdio 传输，提供 health、证书任务、job 查询/等待、webhook CRUD、只读配置查询/校验等工具。

配置查询接口现在会带上可选的 `delivery_targets` 信息，便于运维侧或 MCP 客户端判断 `aws-acm`、`k8s-ingress` 这类扩展交付是否启用。

说明：

1. `cert_create` 与 `cert_renew` 为异步语义，仅返回 `job_id`，需配合 `job_wait` 等待终态。
2. 当前事件主题为 job 级（`job.queued`、`job.completed`、`job.failed`），证书级事件属于后续 addon/plugin 集成规划。
3. `job_list` 支持 `target_scope` 参数（用于多环境/多集群分段查询）。

## 2.2 REST Token 鉴权策略（server 模式）

证书/job 相关 REST 鉴权由 server 配置控制：

- `[server].token_auth_enabled = false`（默认）：相关接口默认放开。
- `[server].token_auth_enabled = true`：受保护接口要求 Bearer token。

Token 解析优先级（override）：

1. `entries[].token`（item 级）
2. `global.token`
3. 未配置 token

当鉴权开关开启时：

- 缺少 token：`401 AUTH_MISSING_TOKEN`
- token 不匹配：`401 AUTH_INVALID_TOKEN`
- 当前目标没有可用 token（item/global 都空）：`500 AUTH_TOKEN_CONFIG_ERROR`

## 2.3 Node-Agent 协议面（机器对机器）

当前节点协议接口：

- `POST /api/v1/node-agent/poll`
- `GET /api/v1/node-agent/events`（SSE）
- `POST /api/v1/node-agent/subscribe`
- `POST /api/v1/node-agent/heartbeat`
- `POST /api/v1/node-agent/result`
- `POST /api/v1/node-agent/callback`

说明：

1. `poll/subscribe` 响应中的 assignment 可携带 `bundle_token` 与 `bundle_token_expires_at`。
2. 当 `[server].bundle_token_required = true`（默认）时，下载 bundle 必须附带该短时 token。
3. `events` 为签名 SSE 通道，事件类型包含 `connected/assignment/timeout`，建议 agent 配置优先 `control_plane.prefer_sse=true`。
4. 推荐回退链路：`events -> subscribe -> poll`。

示例配置：

```toml
[global]
token = "global-token"

[server]
token_auth_enabled = true

[[entries]]
name = "site-a"
token = "site-a-token"
```

## 3. `certmanctl` 与 REST 的对应关系

| `certmanctl` | REST endpoint |
| --- | --- |
| `health` | `GET /health` |
| `cert create --entry-name <name>` | `POST /api/v1/certificates` |
| `cert list` | `GET /api/v1/certificates` |
| `cert get --entry-name <name>` | `GET /api/v1/certificates/{entry_name}` |
| `cert renew --entry-name <name>` | `POST /api/v1/certificates/{entry_name}/renew` |
| `job get --job-id <id>` | `GET /api/v1/jobs/{job_id}` |
| `job list ...` | `GET /api/v1/jobs?...` |
| `job wait --job-id <id>` | 轮询 `GET /api/v1/jobs/{job_id}` 直到进入终态 |
| `webhook create` | `POST /api/v1/webhooks` |
| `webhook list` | `GET /api/v1/webhooks` |
| `webhook get --id <id>` | `GET /api/v1/webhooks/{id}` |
| `webhook update --id <id>` | `PUT /api/v1/webhooks/{id}` |
| `webhook delete --id <id>` | `DELETE /api/v1/webhooks/{id}` |
| `config list` | `GET /api/v1/config/entries` |
| `config show --entry-name <name>` | `GET /api/v1/config/entries/{entry_name}` |
| `config validate --entry-name ...` | `POST /api/v1/config/validate` |

证书任务提交接口当前都具备 queued 级幂等性：

- `POST /api/v1/certificates` 返回 `{"job_id": "...", "created": bool}`
- `POST /api/v1/certificates/{entry_name}/renew` 返回 `{"job_id": "...", "created": bool}`

## 3.1 `certman-mcp` 工具与 REST 对应

| MCP tool | REST endpoint |
| --- | --- |
| `health` | `GET /health` |
| `cert_create` | `POST /api/v1/certificates` |
| `cert_list` | `GET /api/v1/certificates` |
| `cert_get` | `GET /api/v1/certificates/{entry_name}` |
| `cert_renew` | `POST /api/v1/certificates/{entry_name}/renew` |
| `job_get` | `GET /api/v1/jobs/{job_id}` |
| `job_list` | `GET /api/v1/jobs?...` |
| `job_wait` | 轮询 `GET /api/v1/jobs/{job_id}` |
| `webhook_create` | `POST /api/v1/webhooks` |
| `webhook_list` | `GET /api/v1/webhooks` |
| `webhook_get` | `GET /api/v1/webhooks/{id}` |
| `webhook_update` | `PUT /api/v1/webhooks/{id}` |
| `webhook_delete` | `DELETE /api/v1/webhooks/{id}` |
| `config_list` | `GET /api/v1/config/entries` |
| `config_get` | `GET /api/v1/config/entries/{entry_name}` |
| `config_validate` | `POST /api/v1/config/validate` |

## 4. 面向 AI 的接入建议

推荐顺序：

1. 读取 `/openapi.json`
2. 使用 OpenAPI 中的请求/响应样例
3. 直接调用 REST，或在需要稳定运维 UX 时调用 `certmanctl`

如果目标是稳定退出码和命令式操作，优先用 `certmanctl`。
如果目标是生成 typed client 或直接挂工具，优先用 REST + OpenAPI。

若服务端开启 token 鉴权，请通过 `certmanctl --token`（或环境变量 `CERTMAN_SERVER_TOKEN`）传递 Bearer token。

若节点协议启用 bundle token（默认开启），请确保 agent 使用 poll/subscribe 返回的 `bundle_token` 下载 bundle，且处理过期重试。

## 5. cert-manager addon/plugin 规划状态

与 cert-manager 的协作能力当前登记为 addon/plugin/extension 规划项，本期不实现。

规划文档：

- `docs/plans/2026-03-27-cert-manager-addon-plugin-plan.md`
