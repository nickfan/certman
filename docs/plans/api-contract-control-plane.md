# CertMan 控制平面 API 契约

> 版本: 1.0
> 日期: 2026-03-26
> 状态: Draft（Phase 2 开始前冻结）

---

## 1. 统一响应 Envelope

所有 API 端点（`/health` 除外）均通过统一 `ApiResponse` 包装响应体。

```python
class ApiResponse(BaseModel):
    success: bool
    data: Any | None = None
    error: ErrorDetail | None = None

class ErrorDetail(BaseModel):
    code: str       # 业务错误码，见 §4
    message: str    # 人类可读说明
```

> `/health` 作为显式例外，直接返回轻量裸响应 `{"status": "ok"}`，不经过 envelope 包装。

---

## 2. 核心端点契约

| 端点 | 方法 | 请求体 | 响应 | 幂等 |
|---|---|---|---|---|
| `/health` | GET | — | `{"status":"ok"}` | Y |
| `/api/v1/certificates` | POST | `IssueCertRequest(entry_name)` | `202 + ApiResponse(data={"job_id": ...})` | N |
| `/api/v1/certificates` | GET | — | `ApiResponse(data=[JobResponse, ...])` | Y |
| `/api/v1/certificates/{entry_name}` | GET | — | `ApiResponse(data=[JobResponse, ...])` | Y |
| `/api/v1/certificates/{entry_name}/renew` | POST | — | `202 + ApiResponse(data={"job_id": ..., "created": bool})` | Y (subject-level dedupe) |
| `/api/v1/jobs` | GET | query: `subject_id?`, `status?`, `limit?` | `ApiResponse(data=[JobResponse, ...])` | Y |
| `/api/v1/jobs/{id}` | GET | — | `ApiResponse(data=JobResponse)` | Y |
| `/api/v1/nodes/register` | POST | `NodeRegisterRequest` | `201/200 + ApiResponse(data=NodeRegisterResponse)` | Y (node_id natural key) |
| `/api/v1/node-agent/poll` | POST | `PollRequest(node_id, signature)` | `ApiResponse(data=PollResponse)` | N |
| `/api/v1/node-agent/result` | POST | `ResultReport(job_id, status, ...)` | `ApiResponse(data=AckResponse)` | Y (job_id natural key) |
| `/api/v1/webhooks` | POST | `WebhookSubscriptionRequest` | `201 + ApiResponse(data={"id": ...})` | Y (topic+endpoint natural key) |
| `/api/v1/webhooks` | GET | query: `topic?`, `status?` | `ApiResponse(data=[WebhookResponse, ...])` | Y |
| `/api/v1/webhooks/{id}` | GET | — | `ApiResponse(data=WebhookResponse)` | Y |
| `/api/v1/webhooks/{id}` | PUT | `UpdateWebhookRequest` | `ApiResponse(data=WebhookResponse)` | Y |
| `/api/v1/webhooks/{id}` | DELETE | — | `ApiResponse(data={"deleted": true})` | Y |

### 关键请求/响应模型（Pydantic 伪代码）

```python
class IssueCertRequest(BaseModel):
    entry_name: str

class JobResponse(BaseModel):
    job_id: str
    job_type: str
    status: Literal["queued", "running", "completed", "failed", "cancelled"]
    subject_id: str
    node_id: str | None
    attempts: int
    result: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime

class WebhookResponse(BaseModel):
    id: str
    topic: str
    endpoint: str
    status: str
    created_at: datetime
    updated_at: datetime

class PollRequest(BaseModel):
    node_id: str
    signature: str     # Ed25519 对 {node_id, timestamp, nonce} 的签名（Base64）
    timestamp: int     # Unix 秒，服务端校验 ±60s 内有效
    nonce: str
    agent_version: str  # 用于版本兼容检查

class PollResponse(BaseModel):
    assignments: list[TaskAssignment]
    min_agent_version: str

class NodeRegisterResponse(BaseModel):
    node_id: str
    status: str
    created: bool
    public_key_fingerprint: str
    poll_endpoint: str

class TaskAssignment(BaseModel):
    job_id: str
    job_type: str
    bundle_url: str
    bundle_signature: str   # server Ed25519 对 bundle 的签名

class ResultReport(BaseModel):
    job_id: str
    status: Literal["completed", "failed"]
    output: str | None
    error: str | None
    signature: str      # Ed25519 对 {job_id, status, output_hash} 的签名
```

---

## 2.1 实时文档与 AI 接入面

- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI schema: `/openapi.json`
- 提供 `certman-mcp`（stdio）作为 MCP 接入；也可直接通过 REST + OpenAPI 接入

---

## 3. Job 状态机

```
queued → running → completed
                 → failed
queued → cancelled  （仅 server 端可取消）
```

**不可逆约束**: `completed` / `failed` / `cancelled` 为终态，不可回退。

---

## 4. 错误码规范

| HTTP 状态码 | 业务错误码前缀 | 场景 |
|---|---|---|
| 400 | `INVALID_*` | 请求体 Pydantic 校验失败 |
| 401 | `AUTH_*` | 签名验证失败 / 节点未授权 |
| 404 | `NOT_FOUND_*` | 资源不存在 |
| 409 | `CONFLICT_*` | 幂等冲突（已存在相同 key） |
| 422 | `SEMANTIC_*` | 业务逻辑拒绝（如终态 job 尝试取消） |
| 426 | `UPGRADE_REQUIRED` | Agent 版本低于 min_agent_version |
| 500 | `INTERNAL_*` | 服务端未预期异常 |

---

## 5. Agent 输入输出约束

- poll 请求**必须**携带 `node_id` + Ed25519 签名 + `timestamp` + `nonce`（防重放）
- bundle 下载仅限分配给本节点的任务（server 校验 node_id）
- result 必须携带 `job_id` + 执行状态 + 签名
- 未 approved 节点发起的 poll 请求返回 `401 AUTH_NODE_NOT_APPROVED`

---

## 6. 版本兼容

- API 路径包含 `/api/v1/` 版本前缀。
- Agent poll 响应中包含 `min_agent_version` 字段。
- Agent 启动时在 poll 请求中上报 `agent_version`。
- 当 `agent_version < min_agent_version` 时，server 返回 `426 Upgrade Required`。
- v1 API 在同一 major version 内保持向后兼容。
