# CertMan 控制平面文档评审记录

> 日期: 2026-03-26
> 评审范围: 需求分析、架构设计、实施计划、部署与运维可行性
> 评审对象:
> - docs/plans/prd-control-plane.md
> - docs/plans/design-control-plane.md
> - docs/plans/progress-control-plane.md
> - docs/plans/2026-03-24-certman-control-plane.md
> - docs/k8s-service-design.md
> - Dockerfile
> - docker-compose.yml
> - pyproject.toml

## 1. 评审结论摘要

当前这组文档已经具备较好的方向性和模块拆分基础，能够说明项目目标、主要组件与演进方向，但尚未达到“可直接作为稳定实施与验收基线”的程度。

主要问题不在产品方向，而在以下三个方面尚未闭合：

1. MVP 与目标态架构口径未统一。
2. API、安全、审计缺少可测试的明确验收标准。
3. 部署、运维、密钥管理、可观测性等 DevOps 闭环尚未落地到文档基线。

综合判断：

- 可以作为方向性方案文档。
- 还不能直接作为最终实施与评审基线。

## 2. 总体评价

### 2.1 优点

1. 产品方向清晰，已经从单机 CLI 正确提升为跨环境证书控制平面。
2. 运行模式划分合理，local / agent / server 三模式边界基本明确。
3. 保留 certbot/provider/config/export/check 内核的演进路径合理，风险控制方向正确。
4. 先统一执行内核，再扩展 agent、server、安全链路的顺序基本正确。
5. 文档已覆盖 PRD、架构设计、进度规划，形成了初步文档体系。

### 2.2 当前主要缺口

1. 文档中混合了“当前仓库基线”“MVP 实施态”“目标态架构”，导致实现口径不稳定。
2. 文档中的很多验收项仍是方向性表达，而不是严格可测试条目。
3. 安全设计只写了机制，尚未写清楚运行边界、失败路径和运维流程。
4. 进度文档更像任务列表，不足以作为阶段评审与交付判断基线。

## 3. 关键问题清单

## 3.1 Critical

### C1. MVP 架构口径与目标架构口径冲突

现象：

- 设计文档中已经把 worker、scheduler、SQLite、SQLAlchemy 作为既定架构组件。
- 原始实施计划仍强调先做单进程模块化。
- 原始计划 Task 8 仍写着先用内存 job store 做最小闭环。

影响：

- 实施人员无法判断当前阶段应该按哪一层架构验收。
- reviewer 无法统一判断某阶段是否完成。
- 会直接影响 API、测试、部署和失败处理设计。

修订建议：

1. 将文档明确拆分为两层：
   - MVP 基线架构
   - 目标态架构
2. 每个 Phase 必须标注自己对应哪一层架构。
3. 所有图表需明确说明是“当前阶段”还是“最终目标态”。

### C2. API 契约不完整，无法形成可测基线

现象：

- PRD 只定义了长任务返回 `202 + job_id`。
- 设计文档只列出路由前缀和一个简化的 job 响应样例。
- 实施计划将 health/list 与异步任务状态语义拆分在不同任务中。

缺失：

1. 请求体定义
2. 成功响应结构
3. 错误响应结构
4. 状态码规范
5. Job 状态机
6. 幂等语义
7. 分页/过滤/排序规范

影响：

- 实施时容易出现“接口能跑但不可稳定 review”的情况。
- 后续测试无法按统一契约编写。

修订建议：

在设计文档中增加“最小 API 契约”章节，至少覆盖：

- POST /api/v1/certificates
- GET /api/v1/jobs/{job_id}
- POST /api/v1/node-agent/poll
- GET /api/v1/node-agent/jobs/{id}/bundle
- POST /api/v1/node-agent/jobs/{id}/result
- GET /health

并统一定义：

- 成功响应 envelope
- 错误响应 envelope
- 任务状态机
- 幂等策略

### C3. 安全设计缺乏运行闭环与失败边界

现象：

文档已提到以下概念：

- Ed25519 签名
- X25519 / AES-GCM 信封加密
- message_id / nonce / expires_at / payload_hash

但未明确：

1. 节点首次注册与信任建立流程
2. 公私钥生成、轮换、吊销流程
3. nonce 去重的存储位置和 TTL
4. 时钟漂移容忍范围
5. bundle 下载授权边界
6. 验签失败/解密失败的错误处理与审计记录

影响：

- 安全链路可能只停留在“有算法”，而不是“可验收的安全机制”。
- reviewer 无法判断是否真正具备抗重放与最小授权能力。

修订建议：

增加“安全验收矩阵”，逐项定义：

- 输入
- 校验规则
- 失败结果
- 审计字段
- 测试场景

### C4. 审计追踪承诺未落地

现象：

- PRD 中将审计追踪列为核心价值。
- 设计文档 ER 图中尚无完整 AuditEvent / AuditLog 模型。
- 验收标准中没有“审计可查询”的明确条目。

影响：

- 产品承诺与实际交付目标不一致。
- 后续可能只有 webhook 投递记录，没有真正的审计追踪能力。

修订建议：

增加审计实体，至少包含：

- actor
- action
- resource_type
- resource_id
- result
- correlation_id
- timestamp
- source / node_id

并在 PRD 中新增一条可测试验收项：关键操作必须产生可查询审计记录。

## 3.2 High

### H1. 部署与当前仓库基线脱节

现象：

- 设计文档已经默认三入口和多组件部署。
- 当前实际仓库仍只有单入口 certman。
- Dockerfile 与 docker-compose.yml 仍是单服务单入口。

影响：

- 文档没有清晰表达当前仓库现状与目标态差距。
- 实施顺序和部署顺序容易混乱。

修订建议：

在进度文档中增加“当前基线”列，明确：

- 已实现
- 半成品
- 未开始

并将 Docker / Compose / entrypoint 演进列为明确交付物。

### H2. 数据层“可平滑迁移”承诺缺少支撑设计

现象：

- PRD 承诺 SQLite 可平滑迁移。
- 设计文档没有 repository 抽象、schema version、migration 策略。
- DevOps 文档中也没有备份恢复设计。

影响：

- 后续如果实现直接绑定 SQLite 细节，迁移 PostgreSQL 并不平滑。

修订建议：

补充以下设计：

1. Repository 或等价持久化抽象层
2. 数据库 schema version / migration 方案
3. SQLite 备份与恢复策略
4. PostgreSQL 迁移边界说明

### H3. Hook、Webhook、EventBus 的阶段关系表达混乱

现象：

- 设计图把 HookRunner 放在 EventBus 下游。
- 进度文档中 HookRunner 在 Phase 1，而 EventBus/Webhook 在 Phase 5。

影响：

- 读者会误解本地同步 hook 依赖后期事件总线。
- 不利于分阶段实施。

修订建议：

文档需要明确区分两类能力：

1. 本地同步 hook
2. 领域事件驱动的 webhook / event bus

并在图中标注 MVP 和后续演进关系。

### H4. 可观测性与运维闭环不足

当前缺失：

1. 指标体系
2. 健康检查和 readiness 语义
3. 告警规则
4. 结构化日志标准字段
5. 故障排查 Runbook

影响：

- 方案能实现，但不易运维。
- 后期会出现“功能完成但上线风险高”的情况。

修订建议：

新增运维类文档与章节：

- 健康检查定义
- readiness / liveness 语义
- 关键指标 SLI/SLO
- 日志字段规范
- 故障排查 Runbook

## 3.3 Medium

### M1. 进度文档尚未形成真正可执行的评审基线

现象：

- 当前只有 Todo、预计时长和验证命令。
- 没有 Entry Criteria、Definition of Done、Review Evidence。
- 还不足以支持阶段性交付判断。

修订建议：

为每个 Phase 增加：

1. 进入条件
2. 完成定义
3. 评审证据
4. 风险退出条件

### M2. 目标表述有部分不可判定项

例如：

- 现有 CLI 行为保持一致
- 结构化日志、明确错误上下文
- 数据层可平滑迁移

这些适合作为方向，不适合作为验收条件。

修订建议：

将这些表述改写为可测试语句，例如：

- 不回归命令清单
- 日志必备字段
- 迁移验证策略

### M3. PRD 状态表述不清晰

问题：

`Draft Accepted` 是冲突状态，不利于治理。

修订建议：

改为单一状态，例如：

- Draft
- In Review
- Accepted
- Approved for Implementation

## 4. DevOps 专项评审结论

## 4.1 当前主要部署问题

1. Dockerfile 仅支持单入口，不支持 certman-agent / certman-server。
2. docker-compose.yml 仅定义单服务，不支持 server / agent / worker 分拆。
3. pyproject.toml 当前仅注册 `certman` 一个脚本入口。

这些问题不是文档错误本身，而是文档没有把“当前基线与目标态差距”明确建模。

## 4.2 当前运维缺口

1. 无密钥轮换与吊销流程
2. 无 SQLite 备份与恢复策略
3. 无健康检查与 readiness 规范
4. 无任务并发控制策略
5. 无 webhook 退避参数定义
6. 无版本兼容策略（agent / server）
7. 无升级与回滚 Runbook

## 4.3 DevOps 修订建议

建议新增一份运维文档：

- docs/ops/runbook.md

建议至少覆盖：

1. 启动方式
2. 升级方式
3. 回滚方式
4. 数据库备份恢复
5. 密钥轮换
6. 常见故障排查
7. 健康检查
8. 日志与监控

## 5. 文档修订优先级建议

### 第一优先级

1. 统一 MVP 架构与目标态架构口径
2. 补齐 API 契约与任务状态机
3. 补齐安全验收矩阵
4. 补齐审计模型与验收标准

### 第二优先级

1. 补齐当前基线与目标态差距说明
2. 修订 progress 文档为可执行评审基线
3. 增加部署与运维闭环章节

### 第三优先级

1. 增加运维 Runbook
2. 增加更完整的部署拓扑图
3. 增加配置优先级和环境差异说明

## 6. 建议的修订范围

建议直接修订以下主文档：

1. docs/plans/prd-control-plane.md
2. docs/plans/design-control-plane.md
3. docs/plans/progress-control-plane.md

建议新增以下辅助文档：

1. docs/ops/runbook.md
2. 可选：docs/plans/api-contract-control-plane.md

## 7. 最终判断

当前文档状态：

- 方向性：良好
- 可沟通性：良好
- 可实施性：中等
- 可评审性：中等偏弱
- 可验收性：不足
- 可运维性：不足

结论：

这组文档可以作为下一轮修订的基础稿，但应在修订后再作为实施与 review 基线。

## 8. 后续建议动作

建议下一步按顺序执行：

1. 修订 PRD，使其从“方向文档”变成“可验收文档”。
2. 修订设计文档，使其显式区分 MVP 与目标态。
3. 修订 progress 文档，加入 DoD 与评审证据。
4. 新增运维 Runbook，补齐 DevOps 闭环。
5. 完成后再交由 Claude / Codex 做二轮复核。
