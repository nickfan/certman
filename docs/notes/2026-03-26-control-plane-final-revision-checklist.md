# CertMan 控制平面文档最终修订清单

> 日期: 2026-03-26
> 合并来源: reply1 (Claude) + reply2 (Codex) + reply3 (Copilot Senior DevOps)
> 用途: 作为文档修订与 Phase 0 启动的执行基线

---

## 0. 文档链

| 文档 | 路径 |
|---|---|
| PRD | `docs/plans/prd-control-plane.md` |
| 设计 | `docs/plans/design-control-plane.md` |
| 进度 | `docs/plans/progress-control-plane.md` |
| 实施计划 | `docs/plans/2026-03-24-certman-control-plane.md` |
| API 契约（新增） | `docs/plans/api-contract-control-plane.md` |
| 评审 reply1 | `docs/notes/2026-03-26-control-plane-review-reply1.md` |
| 评审 reply2 | `docs/notes/2026-03-26-control-plane-review-reply2.md` |

---

## 1. 修订执行层级

按依赖关系和阻塞性分为三层，逐层执行。

---

### 第一层：立即修订（Phase 0 编码启动前完成）

这些修订均为文档层面修改，不涉及代码变更。完成后即可启动 Phase 0 编码。

---

#### R01. PRD 状态修正

- **文件**: `docs/plans/prd-control-plane.md`
- **位置**: 文档头部 `> 状态: Draft Accepted`
- **动作**: 改为 `> 状态: In Review`
- **来源**: reply1 M3 ✅ → reply2 §1 采纳
- **理由**: 文档仍在评审中，不应标注已接受

---

#### R02. PRD 验收标准改为可测试语句

- **文件**: `docs/plans/prd-control-plane.md`
- **位置**: §8 验收标准（5 条）
- **动作**: 按下表逐条改写

| 原文 | 改为 |
|---|---|
| 现有 CLI 本地模式不回归 | `test_cli_commands.py` + `test_cert_service.py` 全部通过 |
| Agent 能拉取任务、落地证书、执行 hook、回传结果 | `test_agent_mode.py` + `test_node_executor.py` 全部通过 |
| Server 能提交证书任务并查询 job 状态 | `POST /api/v1/certificates` 返回 `202 + job_id`；`GET /api/v1/jobs/{id}` 返回正确状态 |
| 分发链路具备签名与内容加密 | `test_signing.py` + `test_envelope.py` 全部通过，含验签失败和错误密钥分支 |
| scheduler、webhook、hook runner 均具备可测试闭环 | `test_scheduler_jobs.py` + `test_webhook_service.py` + `test_hook_runner.py` 全部通过 |

- **同步修改** §5 非功能需求表格：

| 原文 | 改为 |
|---|---|
| 现有 CLI 行为保持一致 | `test_cli_commands.py` + `test_cert_service.py` 全部通过 |
| 结构化日志、明确错误上下文 | 日志输出包含 timestamp/level/module/message 字段 |
| 数据层可从 SQLite 平滑迁移 | SQLAlchemy 模型 + Alembic migration 通过 SQLite 和 PostgreSQL 方言验证 |

- **来源**: reply1 M2 ✅ → reply2 §1.2 采纳

---

#### R03. progress 文档增加「当前仓库基线」章节

- **文件**: `docs/plans/progress-control-plane.md`
- **位置**: 在 §1 总体里程碑之后、§2 Phase 看板之前，新增 §1.5
- **动作**: 插入如下章节

```markdown
## 1.5 当前仓库基线

| 组件 | 文件 | 状态 | 说明 |
|---|---|---|---|
| 运行模式配置 | `certman/config.py` | ✅ 已实现 | `run_mode` / `control_plane` / `node_identity` / `hooks` 配置结构已就位 |
| Pydantic 领域模型 | `certman/models/*.py` | ✅ 已实现 | `CertificateRecord` / `JobRecord` / `NodeIdentityRecord` 已定义 |
| 核心服务 | `certman/services/cert_service.py` | ✅ 已实现 | `issue()` / `renew()` / `check()` 编排已完成 |
| CLI 入口 | `certman/cli.py` | ✅ 已实现 | Typer 命令已注册 |
| 导出 | `certman/exporter.py` | ⚠️ 已实现但未服务化 | 函数式实现，未抽取为服务 |
| pyproject.toml | `pyproject.toml` | ⚠️ 仅注册 `certman` | 缺少 `certman-agent` / `certman-server` 入口；缺少 fastapi/httpx/cryptography/sqlalchemy 依赖 |
| Dockerfile | `Dockerfile` | ⚠️ 单入口 | 仅 `ENTRYPOINT ["uv", "run", "certman"]` |
| docker-compose.yml | `docker-compose.yml` | ⚠️ 单服务 | 仅 `certman` 服务 |
| DB 层 | — | ❌ 未开始 | SQLite + SQLAlchemy + Alembic 均未引入 |
| Agent / Server / Worker | — | ❌ 未开始 | |
| Security 模块 | — | ❌ 未开始 | |
| 配置示例 | `data/conf/config.example.toml` | ⚠️ 不完整 | 缺少 `run_mode` / `control_plane` / `node_identity` / `hooks` 示例段 |

### 已知技术债

1. `_entry_domains()` 函数在 `certman/cli.py` L16 与 `certman/services/cert_service.py` L49 重复实现（DRY 违反）。
2. `_validate_run_mode()` 仅校验 `agent` 模式，未校验 `server` 模式。
```

- **来源**: reply1 H1 ✅ + E1/E3 → reply2 §1.3/§1.5 采纳 → reply3 F1/F2 补充

---

#### R04. progress 文档为每个 Phase 增加 DoD

- **文件**: `docs/plans/progress-control-plane.md`
- **位置**: §4 每个 Phase 的验证命令之后
- **动作**: 为每个 Phase 增加通用 DoD + phase-specific 退出项

**通用 DoD（所有 Phase 共用）:**

```
✅ 验证命令通过
✅ 新增测试全绿
✅ 覆盖率 >= 80%
✅ 无 Critical lint issue
```

**Phase-specific 退出项:**

| Phase | 专项退出项 |
|---|---|
| Phase 0 | ① Alembic `initial` migration 可正常 upgrade/downgrade ② `_validate_run_mode` 覆盖 server 模式校验 ③ `config.example.toml` 包含 agent/server 最小配置示例 |
| Phase 1 | ① `export_entry()` 通过 `ExportService` 调用而非直接函数引用 ② HookRunner 执行失败时错误可被上层捕获 |
| Phase 2 | ① `uv run certman-agent --help` 可正常输出 ② Agent 空轮询 → 退出闭环可测 ③ Dockerfile 支持 CMD 覆盖 |
| Phase 3 | ① `uv run certman-server --help` 可正常输出 ② `GET /health` 返回 200 ③ `POST /api/v1/certificates` 返回 202 + job_id ④ 最小 Compose 骨架（server + worker）可 up |
| Phase 4 | ① 签名验签成功/失败分支可测 ② 加密解密 + 错误密钥分支可测 ③ 节点注册握手闭环可测 |
| Phase 5 | ① 到期扫描 → 自动生成续签任务可测 ② Webhook 签名 + 重试 + 投递记录可测 |
| Phase 6 | ① 三入口 `--help` 均正常 ② 全量回归通过 ③ 覆盖率总计 >= 80% ④ README 运行示例可执行 |

- **来源**: reply1 M1 部分认可 → reply2 §2.3 修正（需增加专项退出项）→ reply3 采纳

---

#### R05. 实施计划 Task 描述校准 Create → Modify

- **文件**: `docs/plans/2026-03-24-certman-control-plane.md`
- **位置**: Task 2 和 Task 3 的 `**Files:**` 段
- **动作**: 按下表修正

| Task | 原描述 | 改为 |
|---|---|---|
| Task 2 | `Create: certman/models/__init__.py` | `Modify: certman/models/__init__.py` |
| Task 2 | `Create: certman/models/certificate.py` | `Modify: certman/models/certificate.py` |
| Task 2 | `Create: certman/models/job.py` | `Modify: certman/models/job.py` |
| Task 2 | `Create: certman/models/node.py` | `Modify: certman/models/node.py` |
| Task 3 | `Create: certman/services/cert_service.py` | `Modify: certman/services/cert_service.py` |

- **来源**: reply1 E2 ✅ → reply2 §1.5 采纳

---

#### R06. 删除 Task 8 "内存 job store" 表述

- **文件**: `docs/plans/2026-03-24-certman-control-plane.md`
- **位置**: Task 8 → Step 3 `先用内存 job store 实现最小闭环。`
- **动作**: 改为 `基于 SQLite + SQLAlchemy 实现 job 持久化与状态查询。`
- **来源**: reply1 C1 ✅（SQLite 零依赖，无需内存→SQLite 两阶段演进） → reply2 §1 采纳

---

#### R07. 设计图修正 HookRunner 与 EventBus 关系

- **文件**: `docs/plans/design-control-plane.md`
- **位置**: §2.3 Component (Server) 的 mermaid 图
- **动作**: 将 HookRunner 从 EventBus 下游移除，改为 CertService 的直接依赖

修改前：
```
CERT --> EVENT[EventBus]
EVENT --> HOOK[HookRunner]
EVENT --> WEBHOOK
```

修改后：
```
CERT --> HOOK[HookRunner]
CERT --> EVENT[EventBus]
EVENT --> WEBHOOK
```

并在图后增加注释：

```markdown
> **Note:** HookRunner（Phase 1）是同步 shell 命令执行器，直接由 CertService 调用，不依赖 EventBus。
> EventBus（Phase 5）是进程内事件发布机制，驱动 Webhook 投递，与 HookRunner 并列而非包含关系。
```

- **来源**: reply1 H3 ✅ → reply2 §1.4 采纳

---

#### R08. 设计 ER 图增加 AUDIT_EVENT

- **文件**: `docs/plans/design-control-plane.md`
- **位置**: §5 ER 关系图
- **动作**: 在 ER 图中增加 AUDIT_EVENT 实体及关联

```mermaid
AUDIT_EVENT {
  string id PK
  string actor
  string action
  string resource_type
  string resource_id
  string result
  string correlation_id
  string source_node_id
  datetime created_at
}
```

关联: `JOB ||--o{ AUDIT_EVENT : generates`、`NODE ||--o{ AUDIT_EVENT : generates`

写入时机: 证书签发/续签/失败、Agent 注册/离线、Job 状态变更、安全事件（验签失败/解密失败）。

- **来源**: reply1 C4 ✅ → reply2 §1.2 采纳

---

#### R09. 实施计划增加 Alembic 初始化任务

- **文件**: `docs/plans/2026-03-24-certman-control-plane.md`
- **位置**: Phase 0 → 在 Task 2 之后新增 Task 2.5
- **动作**: 新增任务

```markdown
### Task 2.5: 引入 Alembic 与 initial migration

**Files:**
- Create: certman/db/__init__.py
- Create: certman/db/engine.py
- Create: alembic.ini
- Create: alembic/env.py
- Create: alembic/versions/001_initial.py
- Test: tests/test_db.py

**Step 1: Write the failing test**

验证 migration upgrade 后表结构存在，downgrade 后表被移除。

**Step 2: Run test to verify it fails**

Run: pytest tests/test_db.py -q
Expected: FAIL

**Step 3: Write minimal implementation**

创建 SQLAlchemy engine helper + Alembic 配置 + initial migration（仅包含 CERTIFICATE/JOB/NODE/AUDIT_EVENT 核心表；WEBHOOK_SUBSCRIPTION/WEBHOOK_DELIVERY 通过 Phase 5 增量 migration 引入）。同时在依赖更新任务中显式加入 `alembic`，并在依赖变更后刷新锁文件；未更新锁文件不得进入容器构建与 CI 验证。

**Step 4: Run test to verify it passes**

Run: pytest tests/test_db.py -q
Expected: PASS
```

- **来源**: reply1 H2 部分认可 → reply2 §5 采纳 → reply3 采纳

---

#### R10. progress 增加 Phase 0 配置示例任务

- **文件**: `docs/plans/progress-control-plane.md`
- **位置**: §4 Phase 0 检查项列表
- **动作**: 增加一条

```markdown
- [ ] 0.6 更新 `config.example.toml`，增加 `run_mode` / `control_plane` / `node_identity` / `hooks` 最小配置示例段
```

- **来源**: reply3 F1 补充（config.example.toml 当前仅有 `[global]` 段，完全没有 agent/server 配置模板）

---

### 第二层：Phase 2 开始前必须完成

Phase 0 编码可与第二层修订并行推进。但 Phase 2 Agent 链路涉及安全协议和 API 契约，必须先冻结以下设计决策。

---

#### R11. 新增 API 契约文档

- **文件**: `docs/plans/api-contract-control-plane.md`（新建）
- **内容范围**:

1. **统一响应 envelope**（`/health` 作为显式例外，可返回轻量裸响应）

```python
class ApiResponse(BaseModel):
    success: bool
    data: Any | None = None
    error: ErrorDetail | None = None

class ErrorDetail(BaseModel):
    code: str       # 业务错误码
    message: str    # 人类可读
```

2. **6 个核心端点契约**（用 Pydantic-style 伪代码）

| 端点 | 方法 | 请求体 | 响应 | 幂等 |
|---|---|---|---|---|
| `/health` | GET | — | `{"status":"ok"}` | Y |
| `/api/v1/certificates` | POST | `IssueCertRequest` | `202 + ApiResponse(data={"job_id": ...})` | `Idempotency-Key` header |
| `/api/v1/jobs/{id}` | GET | — | `ApiResponse(data=JobResponse)` | Y |
| `/api/v1/node-agent/poll` | POST | `PollRequest(node_id, signature)` | `ApiResponse(data=PollResponse)` | N |
| `/api/v1/node-agent/result` | POST | `ResultReport(job_id, status, ...)` | `ApiResponse(data=AckResponse)` | Y (job_id natural key) |
| `/api/v1/webhooks` | POST | `WebhookSubscription` | `201 + ApiResponse(data={"id": ...})` | Y (topic+endpoint natural key) |

3. **Job 状态机**

```
queued → running → completed
                 → failed
queued → cancelled (仅 server 端可取消)
```

不可逆约束: `completed`/`failed`/`cancelled` 为终态，不可回退。

4. **错误码规范**

| HTTP 状态码 | 业务错误码前缀 | 场景 |
|---|---|---|
| 400 | `INVALID_*` | 请求体校验失败 |
| 401 | `AUTH_*` | 签名验证失败 |
| 404 | `NOT_FOUND_*` | 资源不存在 |
| 409 | `CONFLICT_*` | 幂等冲突 |
| 422 | `SEMANTIC_*` | 业务逻辑拒绝 |
| 500 | `INTERNAL_*` | 服务端异常 |

5. **Agent 输入输出约束**

   - poll 请求必须携带 `node_id` + Ed25519 签名
   - bundle 下载仅限分配给本节点的任务
   - result 必须携带 `job_id` + 执行状态 + 签名

- **来源**: reply1 C2 ✅ → reply2 §1.1 采纳

---

#### R12. 冻结最小安全基线

- **文件**: `docs/plans/design-control-plane.md`
- **位置**: §6 ADR-03 之后新增 §6.5 "安全最小基线"
- **动作**: 新增以下内容（设计层冻结，Phase 4 实现）

```markdown
### 6.5 安全最小基线（Phase 2 开发前置条件）

以下设计约束在进入 Phase 2 编码前必须冻结，Phase 4 实现。不采用 shared secret 过渡方案。

1. **节点注册与信任建立**
   - Agent 首次连接时提交 Ed25519 公钥。
   - Server 侧管理员确认（approve）后节点进入 active 状态。
   - 未 approved 节点的 poll 请求返回 403。

2. **签名字段与验签边界**
   - Agent → Server: 对 `{node_id, timestamp, nonce, payload_hash}` 做 Ed25519 签名。
   - Server → Agent: 对 bundle 做 Ed25519 签名，Agent 用 server 公钥验签。

3. **bundle 下载授权**
   - Agent 仅能下载 `node_id` 匹配的 bundle。
   - Server 在 bundle URL 中嵌入短时效 token（或使用签名请求验证）。

4. **失败事件审计**
   - 签名验证失败、解密失败、未授权 poll 均写入 AUDIT_EVENT。
```

- **来源**: reply1 C3 部分认可 → reply2 §2.1 修正（拒绝 shared secret）→ reply3 A 精化（Phase 0 编码可并行，Phase 2 前冻结）

---

#### R13. 明确轻量持久化访问边界

- **文件**: `docs/plans/design-control-plane.md`
- **位置**: §6 ADR-02 补充
- **动作**: ADR-02 增加以下内容

```markdown
### ADR-02 补充: 持久化访问边界

- 迁移策略: SQLAlchemy 方言切换 + Alembic schema migration。
- 不引入重型 Repository Pattern / 抽象基类 / DI 注入。
- 采用模块级函数集作为轻量 Store 边界:
  - `certman/db/job_store.py` — `create_job(session, ...)` / `get_job(session, id)` / `update_status(session, id, status)`
  - `certman/db/audit_store.py` — `write_event(session, ...)` / `query_events(session, filters)`
  - `certman/db/node_store.py` — `register_node(session, ...)` / `get_node(session, id)` / `update_last_seen(session, id)`
- Store 函数接收 `Session` 作为参数，统一返回 ORM 实体或原始持久化记录；Pydantic/领域模型转换放在 service 层完成。
- Service 层通过 import 调用 Store 函数，不做接口继承。
```

- **来源**: reply1 H2 不认可 Repository → reply2 §2.2 修正（需要轻量边界）→ reply3 B 精化（具体形态为模块级函数集）

---

#### R14. server 模式配置校验

- **文件**: `docs/plans/design-control-plane.md`
- **位置**: §7 API 分层与契约之后新增 §7.5
- **动作**: 增加 server 模式配置要求说明

```markdown
### 7.5 Server 模式配置要求

`_validate_run_mode` 应增加 server 模式校验（Phase 0 实施）:

1. `server.db_path`（或 `database.url`）存在且可写入
2. `server.listen_host` + `server.listen_port` 配置存在
3. `server.signing_key_path` 存在（Ed25519 私钥，用于签名 Agent 响应）

配置边界应拆分而非复用同一对象：

- 保留 `control_plane.endpoint` 仅用于 `agent` 模式
- 新增独立 `server`（或 `api` + `database`）配置块承载监听地址、数据库路径、签名私钥
- `_validate_run_mode` 分别校验 agent/server 所需字段，避免把 server 运行配置塞入 `ControlPlaneConfig`
```

- **来源**: reply1 E3 → reply2 §5 第二层第4项 → reply3 F2 精化

---

#### R15. Agent/Server 版本兼容说明

- **文件**: `docs/plans/api-contract-control-plane.md`（R11 新建文档中增加一节）
- **动作**: 增加版本兼容规则

```markdown
## 版本兼容

- API 路径包含 `/api/v1/` 版本前缀。
- Agent poll 响应中包含 `min_agent_version` 字段。
- Agent 启动时在 poll 请求中上报 `agent_version`。
- 当 agent_version < min_agent_version 时，server 返回 `426 Upgrade Required`。
- v1 API 在同一 major version 内保持向后兼容。
```

- **来源**: reply1 E4 → reply2 未充分展开 → reply3 采纳

---

#### R16. 错误处理分层策略

- **文件**: `docs/plans/design-control-plane.md`
- **位置**: §6 ADR 之后新增 §6.8
- **动作**: 增加错误处理策略小节

```markdown
### 6.8 错误处理策略

定义业务异常基类与子类:

- `CertManError` — 基类
  - `EntryNotFoundError` — 条目不存在
  - `CertbotError` — certbot 执行失败
  - `SecurityError` — 签名/加密/认证失败
  - `JobStateError` — 非法状态转换
  - `ConfigurationError` — 配置校验失败

各入口层的错误表示:

| 入口 | 错误处理 |
|---|---|
| CLI | catch → exit code + 人类可读 stderr |
| API | FastAPI exception_handler → HTTP 状态码 + JSON envelope |
| Agent | catch → result 回执中的 error 字段 |
```

- **来源**: reply1 E5 → reply2 未涉及 → reply3 采纳

---

### 第三层：中期实现前移项

Phase 0-1 编码期间逐步落实，不阻塞 Phase 0 启动。

---

#### R17. 多入口脚本分阶段注册

- **文件**: `pyproject.toml` + `docs/plans/2026-03-24-certman-control-plane.md`
- **动作**: 在实施计划中明确分阶段注册

| Phase | 入口 | pyproject.toml scripts |
|---|---|---|
| Phase 2 | `certman-agent` | `certman-agent = "certman.node_agent.agent:main"` |
| Phase 3 | `certman-server` | `certman-server = "certman.server:main"` |
| Phase 3 | `certman-worker` | `certman-worker = "certman.worker:main"` |

- **来源**: reply2 §4.1 → reply3 C 精化（锚定到具体 Phase 而非 "Phase 3 左右"）

---

#### R18. Dockerfile 支持多命令启动

- **文件**: `Dockerfile` + `docker-compose.yml`
- **分阶段执行**:

| Phase | 改动 |
|---|---|
| Phase 2 | 镜像保持 uv 作为统一启动器，调整为 `ENTRYPOINT ["uv", "run"]` + `CMD ["certman"]`；Compose 通过 `command` 覆盖为 `certman-agent` / `certman-server` / `certman-worker` |
| Phase 3 | docker-compose.yml 增加 `certman-server` + `certman-worker` 双服务骨架 |
| Phase 6 | 完整生产 Compose（server + worker + scheduler + agent） |

- **来源**: reply2 §4.1 → reply3 C 精化

---

#### R19. Alembic migration 基线 + 备份恢复最小策略

- **文件**: `docs/plans/progress-control-plane.md` 或日后 `docs/ops/runbook.md`
- **动作**: 在后续 runbook 中至少覆盖

1. migration 前自动备份 SQLite 文件
2. `alembic downgrade -1` 回滚约束
3. `data/run/` 下关键状态目录的备份范围
4. agent/server 版本不一致时的历史任务处理策略

- **来源**: reply2 §4.2 → reply3 采纳

---

## 2. 当前代码基线交叉验证摘要

以下为三轮评审中所有涉及代码基线断言的验证结果：

| 断言 | 验证结果 | 来源 |
|---|---|---|
| `pyproject.toml` 缺少 fastapi/httpx/cryptography/sqlalchemy | ✅ 确认缺失 | grep pyproject.toml |
| `pyproject.toml` 仅注册 `certman` 脚本 | ✅ `certman = "certman.cli:main"` 唯一入口 | grep pyproject.toml |
| Dockerfile 单入口 | ✅ `ENTRYPOINT ["uv", "run", "certman"]` | Dockerfile L15 |
| docker-compose 单服务 | ✅ 仅 `certman` 服务 | docker-compose.yml |
| `_entry_domains` 重复 | ✅ `cli.py` L16 与 `cert_service.py` L49 一致 | 代码比对 |
| `_validate_run_mode` 仅校验 agent | ✅ 仅 `if self.run_mode == "agent"` 分支 | config.py L86 |
| `config.example.toml` 无 agent/server 配置 | ✅ 仅 `[global]` 段 | config.example.toml 全文 |
| models/*.py 已存在 | ✅ certificate.py/job.py/node.py/__init__.py 均存在 | 文件系统 |
| cert_service.py 已存在 | ✅ 含 IssueResult/RenewResult/CertService 完整实现 | 文件系统 |

---

## 3. 三轮评审立场差异汇总

| 主题 | reply1 (Claude) | reply2 (Codex) | reply3 (Copilot) | 最终采纳 |
|---|---|---|---|---|
| shared secret 过渡 | ✅ 建议作为 MVP 过渡 | ❌ 拒绝 | ❌ 拒绝 | **不采用**。ADR-03 已选型 Ed25519，双轨实现代价大于收益 |
| Repository Pattern | ❌ 不需要 | ⚠️ 需要轻量边界 | ⚠️ 需要但限定为模块级函数集 | **采纳轻量 Store** — 纯函数集，不做抽象基类/DI |
| Phase DoD | 一行通用模板 | 通用 + 2-4 条专项 | 通用 + 专项，锚定验证命令 | **通用 DoD + phase-specific 退出项** |
| 容器化前移 | Phase 6 | Phase 3 左右 | Phase 2/3 分步 | **Phase 2 注册 agent 入口，Phase 3 注册 server + Compose 骨架** |
| Phase 0 是否可开始编码 | 修完§5可启动 Phase 0-1 | Phase 0 文档修订可启动，但不含 DB/Agent | Phase 0 core refactoring 可先行 | **第一层修订完成后 Phase 0 编码即可启动** |
| 安全设计冻结时间点 | Phase 3-4 之间 | Phase 2 前 | Phase 2 前（设计冻结），Phase 4（代码实现） | **Phase 2 前冻结设计，Phase 4 实现代码** |

---

## 4. 执行序列与并行度

```
┌─────────────────────────────────────────────────────┐
│ 第一层文档修订 (R01-R10)                            │ ← 立即开始
│   └─ 完成后 → Phase 0 编码启动                      │
├─────────────────────────────────────────────────────┤
│ 第二层设计冻结 (R11-R16)        │ Phase 0 编码       │ ← 并行
│   └─ 完成后 → Phase 2 可启动    │ (config/models/db) │
├─────────────────────────────────────────────────────┤
│ 第三层实现前移 (R17-R19)                            │ ← 随 Phase 2/3 落地
└─────────────────────────────────────────────────────┘
```

---

## 5. 签署

- [ ] 第一层修订完成确认
- [ ] 第二层设计冻结确认
- [ ] Phase 0 编码启动确认
