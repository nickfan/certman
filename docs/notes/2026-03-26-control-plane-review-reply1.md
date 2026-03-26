# CertMan 控制平面文档评审回复（第一轮）

> 日期: 2026-03-26
> 回复人: Senior DevOps (Claude)
> 评审对象: docs/notes/2026-03-26-control-plane-review.md
> 回复目的: 对同事评审意见逐项分析，明确认可、部分认可、不认可及补充发现

---

## 0. 总体判断

同事的评审报告质量较高，问题分类合理，大部分发现有据可查。但部分建议存在**过度设计倾向**，对 MVP 阶段项目施加了不必要的重量级流程和抽象。以下逐项回应。

**核心结论：**

- 11 条发现中，**完全认可 6 条**，**部分认可 4 条**，**不认可 1 条**。
- 同事 **遗漏了 5 个问题**，应补充纳入修订范围。
- 建议修订优先级应围绕 **"能否开始写代码"** 这个判断标准，而不是追求文档的理论完备性。

---

## 1. 逐项回应

### 1.1 Critical 级别

#### C1. MVP 架构口径与目标架构口径冲突

**判定：✅ 认可，但降为 High**

同事发现准确——设计文档已默认 SQLite/SQLAlchemy/Worker，而实施计划 Task 8 仍写"先用内存 job store 做最小闭环"，确实存在口径冲突。

但这不是 Critical：

1. **冲突的本质是实施计划没更新**，不是架构方向有分歧。设计文档选择 SQLite + SQLAlchemy 是正确的（部署简单、已有 ADR 支撑），实施计划应直接对齐，而不需要"拆分两层架构"。
2. **引入"内存 job store → SQLite"的两阶段演进反而增加复杂度**。SQLite 本身就是零依赖数据库，没有先用内存再迁移的必要。

**修订建议：**

- 删除 Task 8 中"先用内存 job store"的表述，直接从 SQLite 开始。
- 在设计文档和实施计划的每个 Phase 中标注 "MVP 范围" vs "后续增强"。
- 不需要同事建议的"显式拆分两层架构文档"——一个文档内用标记区分即可（KISS 原则）。

---

#### C2. API 契约不完整，无法形成可测基线

**判定：✅ 认可**

这是所有 Critical 中最有价值的发现。当前设计文档只有路由前缀和一个简化的 job 响应示例，确实不足以作为 Phase 3 的实施基线。

**同意同事的补充范围，但加一条约束：**

- API 契约应以 **Pydantic 模型定义为基准**，而不是写 OpenAPI YAML。原因：项目用 FastAPI + Pydantic，模型即契约，文档里写 Python shape 定义比写 JSON Schema 更实用。
- 补充契约应限定在 **6 个核心端点**（同事列出的那 6 个），不做全量枚举。
- **Job 状态机是必须的**，应明确定义：`queued → running → completed | failed | cancelled`，包含状态转换时机和不可逆约束。

**修订建议：**

新增独立文档 `docs/plans/api-contract-control-plane.md`，包含：

1. 统一响应 envelope（成功 / 错误）
2. 6 个核心端点的请求体与响应体（用 Pydantic-style 伪代码）
3. Job 状态机图
4. 幂等策略说明（`Idempotency-Key` header 或 natural key）
5. 错误码规范（HTTP 状态码 + 业务错误码）

---

#### C3. 安全设计缺乏运行闭环与失败边界

**判定：⚠️ 部分认可，降为 High**

同事列出的缺失项确实存在，但：

1. **安全设计不需要在 Phase 0 之前完全闭合**——Phase 4 才涉及安全实现，且 Phase 2（Agent）的最小闭环可以先用 shared secret 做简化验证，Phase 4 再替换为完整的 Ed25519/X25519 链路。
2. **"安全验收矩阵"在启动实施前编写是过早优化**。安全链路的细节设计应在 Phase 3~4 之间补充，而不是现在。

**但以下两项必须在 Phase 2 前明确：**

1. **节点首次注册与信任建立流程**——Agent 怎么拿到 server 的公钥？Server 怎么验证新 agent 的身份？这是 Phase 2 的前置依赖。
2. **bundle 下载授权边界**——Agent 是否只能下载分配给自己的 bundle？

其余项目（密钥轮换、nonce TTL、时钟漂移容忍）可以在 Phase 4 设计细化时补充。

**修订建议：**

- 在设计文档安全章节增加"节点注册流程"和"授权边界"两小节。
- Phase 4 开始前再补充完整的安全验收矩阵。

---

#### C4. 审计追踪承诺未落地

**判定：✅ 认可**

PRD 将审计追踪列为核心价值（"统一证书生命周期管理、安全分发、事件联动与**审计追踪**"），但 ER 图中没有 AuditEvent 实体，验收标准中也没有审计可查询的条目。这是产品承诺与设计脱节。

**修订建议：**

同意同事建议的审计实体定义，补充到 ER 图：

```
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

审计写入时机：证书签发/续签/失败、Agent 注册/离线、Job 状态变更、安全事件（验签失败/解密失败）。

审计实体实现可安排在 Phase 3（Job Service 同期），不作为 Phase 0 阻塞项。

---

### 1.2 High 级别

#### H1. 部署与当前仓库基线脱节

**判定：✅ 认可**

当前仓库实际基线：

| 组件 | 状态 |
|---|---|
| `config.py` 运行模式配置 | ✅ 已实现（run_mode/control_plane/node_identity/hooks） |
| `models/` Pydantic 领域模型 | ✅ 已实现（CertificateRecord/JobRecord/NodeIdentityRecord） |
| `services/cert_service.py` | ✅ 已实现（issue/renew/check） |
| `cli.py` 本地命令 | ✅ 已实现 |
| `exporter.py` 导出 | ✅ 已实现（但未服务化） |
| Dockerfile | ⚠️ 单入口（certman） |
| docker-compose.yml | ⚠️ 单服务 |
| pyproject.toml scripts | ⚠️ 仅注册 `certman` |
| DB 层 | ❌ 未开始 |
| Agent/Server/Worker | ❌ 未开始 |
| Security 模块 | ❌ 未开始 |

**修订建议：**

在 progress 文档开头增加"当前基线"章节，用上表格式明确标注已实现 / 半成品 / 未开始。

**重要补充：实施计划中多个 Task 描述与实际基线不符**（详见下方"遗漏问题"章节）。

---

#### H2. 数据层"可平滑迁移"承诺缺少支撑设计

**判定：⚠️ 部分认可**

同事建议引入"Repository 或等价持久化抽象层"——**我不认可这条建议**。

理由：

1. SQLAlchemy ORM **本身就是持久化抽象层**。它的 Session + Model 模式已经将业务代码与具体数据库解耦。
2. 在 SQLAlchemy 之上再包一层 Repository Pattern 是经典的过度抽象，对这个项目的规模来说增加了不必要的间接层。
3. CertMan 不是微服务平台，不需要为"随时切换存储后端"做架构预留。SQLite → PostgreSQL 的迁移路径已经由 SQLAlchemy 方言切换 + Alembic 迁移覆盖。

**认可的部分：**

- 需要引入 Alembic 做 schema migration——这是实际运维必须的。
- 应在设计文档 ADR-02 中补充说明迁移策略：`SQLAlchemy + Alembic migration`，不做额外 repository 抽象。

**修订建议：**

- ADR-02 补充："迁移策略依赖 SQLAlchemy 方言切换 + Alembic schema migration，不引入额外 repository 抽象层。"
- Phase 0 task 列表增加："引入 Alembic，创建 initial migration。"

---

#### H3. Hook、Webhook、EventBus 阶段关系表达混乱

**判定：✅ 认可**

设计图把 HookRunner 放在 EventBus 下游，但 progress 文档中 HookRunner 在 Phase 1，EventBus 在 Phase 5。读者会误以为 Phase 1 依赖 Phase 5 的组件。

实际上这是两个完全不同的东西：

| 能力 | 机制 | Phase |
|---|---|---|
| 本地 Hook | 同步调用外部命令（shell exec） | Phase 1 |
| 领域事件 | 进程内 EventBus（pub/sub） | Phase 5 |
| Webhook | 基于领域事件的 HTTP 外呼 | Phase 5 |

**修订建议：**

- 设计文档 Component 图中将 HookRunner 从 EventBus 下游移出，改为 CertService 的直接依赖。
- 增加注释明确：Phase 1 的 HookRunner 是同步 shell 命令执行器，不依赖 EventBus。
- EventBus 作为 Phase 5 的新增组件，驱动 Webhook 投递，与 HookRunner 并列而非包含关系。

---

#### H4. 可观测性与运维闭环不足

**判定：⚠️ 部分认可**

同事列出了 5 类缺失（指标、健康检查、告警、结构化日志、Runbook），作为目标态需求完全正确。但对 MVP 阶段来说，优先级应该分层：

**MVP 必须（Phase 3 同期）：**

1. `GET /health` 健康检查（已在 Phase 3 task 列表中）
2. 结构化日志格式（JSON lines，包含 timestamp/level/module/message/correlation_id）

**后续增强（Phase 6 或更后）：**

3. Prometheus 指标（证书到期天数、任务成功率、Agent 心跳延迟）
4. SLI/SLO 定义
5. 告警规则

**运维 Runbook：**

同意新增 `docs/ops/runbook.md`，但内容应随 Phase 推进逐步填充，而不是在文档修订阶段写完整 Runbook。

---

### 1.3 Medium 级别

#### M1. 进度文档缺乏 DoD / Entry Criteria

**判定：⚠️ 部分认可**

同事建议为每个 Phase 增加进入条件、完成定义、评审证据、风险退出条件。方向正确，但对当前项目规模来说过重。

**折中建议：**

为每个 Phase 增加一行 **Definition of Done**，格式统一为：

```
DoD: [验证命令通过] + [新增测试全绿] + [覆盖率 >= 80%] + [无 Critical lint issue]
```

不需要 Entry Criteria（Phase 依赖关系图已经隐含了进入条件）。
不需要 Review Evidence 模板（代码 review 在 PR 中完成，不需要在进度文档中预设格式）。

---

#### M2. 不可判定的验收条件

**判定：✅ 认可**

将模糊表述改为可测试语句：

| 原文 | 改为 |
|---|---|
| 现有 CLI 行为保持一致 | 现有 test_cli_commands.py + test_cert_service.py 全部通过 |
| 结构化日志、明确错误上下文 | 日志输出包含 timestamp/level/module/message 字段 |
| 数据层可平滑迁移 | SQLAlchemy 模型 + Alembic migration 通过 SQLite 和 PostgreSQL 方言验证 |

---

#### M3. PRD 状态"Draft Accepted"矛盾

**判定：✅ 认可**

当前文档仍在评审中，状态应改为 `In Review`。待修订完成后改为 `Accepted`。

---

## 2. 评审遗漏的问题

### E1. `_entry_domains` 函数重复（DRY 违反）

**严重级别：High**

`_entry_domains` 函数在两个文件中完整重复：

- [certman/cli.py](../../../certman/cli.py#L16)（第 16 行）
- [certman/services/cert_service.py](../../../certman/services/cert_service.py#L49)（第 49 行）

实施计划 Phase 0 Task 0.1 已经提到了"`_entry_domains` 去重并统一位置"，但设计文档和 PRD 中都没有标注这个已知技术债。

**修订建议：**

Phase 0 的优先任务应包含消除此重复，将 `_entry_domains` 统一到一个位置（建议放在 `certman/models/certificate.py` 或新建 `certman/domains.py`）。

---

### E2. 实施计划 Task 描述与代码基线不符

**严重级别：High**

实施计划多个 Task 使用 "Create" 描述，但对应文件已经存在：

| Task | 描述 | 实际状态 |
|---|---|---|
| Task 2 | Create certman/models/certificate.py | ✅ 已存在 |
| Task 2 | Create certman/models/job.py | ✅ 已存在 |
| Task 2 | Create certman/models/node.py | ✅ 已存在 |
| Task 2 | Create certman/models/__init__.py | ✅ 已存在 |
| Task 3 | Create certman/services/cert_service.py | ✅ 已存在 |

这些应改为 **Modify**（强化/扩展），否则实施人员可能误删已有代码重新创建。

**修订建议：**

实施计划应校准每个 Task 的 Files 列表，区分 Create / Modify / Test。

---

### E3. Server 模式缺少配置校验

**严重级别：Medium**

`config.py` 中 `_validate_run_mode` 仅校验 `agent` 模式的必填项，对 `server` 模式没有任何校验。

Server 模式至少应校验：

1. 数据库配置存在且可连接
2. 监听地址/端口配置存在
3. 密钥配置存在（用于签名 agent 响应）

**修订建议：**

Phase 3 开始前，在设计文档中补充 server 模式的配置要求，并在 `_validate_run_mode` 中增加 server 模式校验。

---

### E4. 缺少 Agent ↔ Server 版本兼容策略

**严重级别：Medium**

Agent 和 Server 会独立部署和升级。如果 API 发生 breaking change，旧版 Agent 可能无法正常工作。

当前没有任何文档提到版本协商机制。

**修订建议：**

- API 路径已经包含 `/api/v1/` 版本前缀，这是好的起点。
- 在 API 契约文档中补充一条规则：Agent poll 响应中包含 `min_agent_version` 字段，Agent 启动时上报自身版本。
- 短期不需要复杂的版本协商协议，但应在设计文档中明确意图。

---

### E5. 缺少错误处理分层策略

**严重级别：Medium**

当前 `CertService` 中的错误处理混合了多个层级（certbot 错误、文件系统错误、配置错误），直接向上传播到 CLI 层。当引入 API 层（FastAPI）和 Agent 层后，不同层需要不同的错误表示：

- CLI 层：exit code + 人类可读消息
- API 层：HTTP 状态码 + JSON 错误响应
- Agent 层：回执中的错误报告

当前没有统一的错误类型体系。

**修订建议：**

在设计文档中增加"错误处理策略"小节：

- 定义业务异常基类（`CertManError`）和子类（`EntryNotFoundError`、`CertbotError`、`SecurityError`）
- CLI 层：catch → exit code + echo
- API 层：FastAPI exception handler → HTTP 响应
- Agent 层：catch → result 回执

---

## 3. 修订优先级建议（调整后）

基于"能否开始 Phase 0 编码"这个判断标准重新排列优先级：

### 第一优先级（Phase 0 开始前必须完成）

| 编号 | 修订项 | 原意见 | 调整 |
|---|---|---|---|
| 1 | 实施计划 Task 描述校准（Create → Modify） | 遗漏 | 新增 |
| 2 | Progress 文档增加"当前基线"章节 | H1 | 保持 |
| 3 | 删除 Task 8 "内存 job store" 表述，统一为 SQLite | C1 | 简化 |
| 4 | PRD 状态改为 `In Review` | M3 | 保持 |
| 5 | 不可判定验收条件改为可测试语句 | M2 | 保持 |
| 6 | 每个 Phase 增加 DoD 行 | M1 | 简化 |

### 第二优先级（Phase 2 开始前必须完成）

| 编号 | 修订项 | 原意见 | 调整 |
|---|---|---|---|
| 7 | 新增 API 契约文档（6 个核心端点 + Job 状态机） | C2 | 保持 |
| 8 | 设计文档补充节点注册流程和授权边界 | C3 | 缩小范围 |
| 9 | ER 图增加 AuditEvent 实体 | C4 | 保持 |
| 10 | Component 图修正 HookRunner 位置 | H3 | 保持 |
| 11 | 增加错误处理分层策略 | 遗漏 | 新增 |

### 第三优先级（Phase 3 开始前完成）

| 编号 | 修订项 | 原意见 | 调整 |
|---|---|---|---|
| 12 | ADR-02 补充 Alembic 迁移策略 | H2 | 简化（去掉 Repository 抽象） |
| 13 | 补充 server 模式配置校验要求 | 遗漏 | 新增 |
| 14 | 补充 Agent/Server 版本兼容说明 | 遗漏 | 新增 |
| 15 | 新增 `docs/ops/runbook.md` 骨架 | H4 | 延后，随 Phase 逐步填充 |

---

## 4. 对同事建议的不认可项

### 4.1 不认可：引入 Repository 抽象层（H2）

理由已在 H2 回应中详述。SQLAlchemy ORM 已经是充分的持久化抽象。在其上再加 Repository 层违反 YAGNI 和 KISS 原则。这个项目不是微服务平台，不需要为假设的存储后端切换做架构预留。

### 4.2 不认可：Phase 0 前完成完整安全验收矩阵（C3）

安全链路在 Phase 4 实现，完整的安全验收矩阵可以在 Phase 3~4 之间补充。现阶段只需要确认节点注册流程和授权边界。

### 4.3 不认可：为每个 Phase 增加 Entry Criteria / Review Evidence / 风险退出条件（M1）

对当前团队规模和项目阶段来说过重。一行 DoD 定义 + 依赖关系图已经足够。

---

## 5. 可立即执行的修订动作清单

以下修订可在本轮 review 确认后立即执行：

- [ ] **prd-control-plane.md**: 状态改为 `In Review`；验收标准改为可测试语句
- [ ] **design-control-plane.md**: Component 图修正 HookRunner 位置；节点注册流程小节；ER 图增加 AuditEvent；ADR-02 补充迁移策略
- [ ] **progress-control-plane.md**: 增加"当前基线"章节；每个 Phase 增加 DoD；标注 MVP vs 后续增强
- [ ] **2026-03-24-certman-control-plane.md**: Task 文件列表校准（Create → Modify）；删除 Task 8 "内存 job store"；增加 Alembic 初始化 task
- [ ] **新增 api-contract-control-plane.md**: 6 个核心端点契约 + Job 状态机 + 错误码规范 + 统一响应 envelope

---

## 6. 总结

| 维度 | 同事评审 | 本轮补充/调整 |
|---|---|---|
| 发现质量 | 高 | 补充 5 条遗漏 |
| 修订建议可行性 | 中等（部分过重） | 简化 3 条建议 |
| 优先级排列 | 偏理论化 | 调整为以"能否开始编码"为判断标准 |
| MVP 意识 | 不足（混合了 MVP 和目标态） | 明确区分 |

**最终判断：**

经过本轮 review-reply，如果按 §5 清单执行修订，文档将达到 **可作为 Phase 0~1 实施基线** 的水平。Phase 2+ 的实施基线可在 Phase 0~1 执行期间通过第二优先级修订补齐。
