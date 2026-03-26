# CertMan 控制平面 PRD

> 版本: 1.0
> 日期: 2026-03-26
> 状态: In Review

## 1. 产品定义

CertMan 的目标从单机 CLI 扩展为跨环境证书控制平面，支持三种运行模式：

- `local`: 本地自治模式
- `agent`: 受控节点模式
- `server`: 控制平面模式

核心价值：统一证书生命周期管理、安全分发、事件联动与审计追踪。

## 2. 目标与非目标

### 2.1 目标

1. 保留并复用现有 `certbot/provider/export/check` 内核。
2. 建立 service 层，支撑 CLI、Agent、Server 三入口复用。
3. 支持中心编排任务（job）和节点回执。
4. 内建签名验签与信封加密链路。
5. 建立调度与 webhook 最小闭环。

### 2.2 非目标

1. 不做 cert-manager CRD 替代。
2. 不在初期引入重型分布式队列。
3. 不要求控制平面直接持有所有远端 kubeconfig。

## 3. 用户与场景

- 运维工程师：统一管理多域名、多云证书续签。
- 平台团队：跨环境分发证书到 K8s、VM、文件系统。
- 安全/审计：追踪证书任务、失败原因、事件投递历史。

## 4. 功能需求

| 编号 | 功能 | 优先级 | 验收 |
|---|---|---|---|
| F-01 | 本地签发/续签/检查不回归 | P0 | 现有测试通过 |
| F-02 | 导出服务化与 Hook 执行器 | P0 | `export_service` 与 `hook_runner` 可测 |
| F-03 | Agent 轮询与任务执行 | P0 | 能拉取任务、落地文件、回执 |
| F-04 | 控制平面 API + Job 语义 | P0 | 长任务返回 `202 + job_id` |
| F-05 | 节点签名与验签 | P1 | 签名成功/失败分支可测 |
| F-06 | 证书包信封加密 | P1 | 加解密与错误密钥分支可测 |
| F-07 | 调度器任务生成 | P1 | 到期扫描与补偿任务可测 |
| F-08 | Webhook 订阅与重试 | P1 | 签名、重试、投递记录可测 |

## 5. 非功能需求

| 类别 | 指标 |
|---|---|
| 兼容性 | `test_cli_commands.py` + `test_cert_service.py` 全部通过 |
| 测试 | 总覆盖率目标 >= 80% |
| 安全 | 不硬编码密钥；分发链路加密+签名 |
| 可运维 | 日志输出包含 timestamp/level/module/message 字段 |
| 可扩展 | SQLAlchemy 模型 + Alembic migration 通过 SQLite 和 PostgreSQL 方言验证 |

## 6. 约束

- 语言与运行时：Python 3.12+
- CLI：Typer
- API：FastAPI
- 调度：APScheduler
- 加密：cryptography
- HTTP 客户端：httpx
- 测试：pytest

## 7. 运行模式说明

### 7.1 Local 模式

本地配置驱动，CLI 直接调用 certbot，支持导出与本地 hook。

### 7.2 Agent 模式

节点通过控制面 endpoint 拉取任务，下载密文证书包，验签解密后本地交付并回执。

### 7.3 Server 模式

提供 REST API、任务编排、节点管理、事件发布、调度触发和审计记录。

## 8. 验收标准

1. `test_cli_commands.py` + `test_cert_service.py` 全部通过。
2. `test_agent_mode.py` + `test_node_executor.py` 全部通过。
3. `POST /api/v1/certificates` 返回 `202 + job_id`；`GET /api/v1/jobs/{id}` 返回正确状态。
4. `test_signing.py` + `test_envelope.py` 全部通过，含验签失败和错误密钥分支。
5. `test_scheduler_jobs.py` + `test_webhook_service.py` + `test_hook_runner.py` 全部通过。

## 9. 里程碑

- M1: Phase 0-1（统一内核 + 导出/hook）
- M2: Phase 2-3（agent + control plane API）
- M3: Phase 4-5（安全 + 调度 + webhook）
- M4: Phase 6（文档与部署收尾）
