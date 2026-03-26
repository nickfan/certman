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
- `certmanctl` 作为面向运维的 REST CLI 封装
- `certman-mcp` 提供的 stdio MCP Server（封装控制面 API）

## 2.1 MCP 启动示例

```bash
uv run certman-mcp --endpoint http://127.0.0.1:8000
```

该 MCP Server 使用 stdio 传输，提供 health、证书任务、job 查询/等待、webhook CRUD 等工具。

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

## 4. 面向 AI 的接入建议

推荐顺序：

1. 读取 `/openapi.json`
2. 使用 OpenAPI 中的请求/响应样例
3. 直接调用 REST，或在需要稳定运维 UX 时调用 `certmanctl`

如果目标是稳定退出码和命令式操作，优先用 `certmanctl`。
如果目标是生成 typed client 或直接挂工具，优先用 REST + OpenAPI。