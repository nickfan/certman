# CertMan 双 CLI 模式改造方案（需求分析 + 设计实现 + 实施计划）

日期：2026-03-26  
状态：M2 进行中（MVP 第一批命令已落地）  
负责人：待定

## 1. 背景与目标

当前 certman 同时承载本地运维与控制面能力，但用户心智上存在混用风险。

- 简单用户希望只关心本地证书生命周期（new/renew/export/check）。
- 平台化用户希望像 docker client 一样，通过命令行调用 server REST API。

本次方案目标如下。

1. 保持本地 CLI 极简、低认知成本。
1. 明确拆分远程控制面客户端入口。
1. 统一 server/worker/agent 作为分布式控制面组件。
1. 支持单机原生、容器化、分布式三种部署形态。

## 2. 需求分析

### 2.1 用户分层需求

1. Local 用户（占大多数）。

- 不关心 server、job、webhook。
- 期望命令短、少参数、可离线。
- 关注成功率与排障简单性。

1. Platform 用户（控制面运维）。

- 需要远程接口查询与资源管理。
- 需要可脚本化 JSON 输出。
- 需要稳定错误码和鉴权机制。

1. 运维/平台工程团队。

- 需要组件解耦与职责清晰。
- 需要从单机平滑演进到分布式。
- 需要文档与测试可追踪。

### 2.2 功能需求

必须满足以下能力。

1. 两种 CLI 入口。

- `certman`：纯本地 local 模式（保留现有语义）。
- `certmanctl`：控制面 remote client 模式（封装 REST）。

1. 组件职责稳定。

- `certman-server`：控制面 API。
- `certman-worker`：后台任务执行。
- `certman-agent`：节点代理执行。

1. 远程命令能力。

- 证书任务提交与查询。
- webhook CRUD。
- node 查询与状态操作（后续可扩）。

1. 兼容要求。

- 现有 `certman` 命令与脚本不破坏。
- 退出码语义保持兼容。

### 2.3 非功能需求

1. 安全。

- Token 鉴权（MVP）。
- TLS 校验默认开启。

1. 可观测性。

- 远程命令输出 request_id/job_id。
- 统一错误码映射。

1. 可扩展性。

- 后续可支持 context/profile、多环境切换、mTLS。

## 3. 概念模型与命名设计

### 3.1 命令入口

1. `certman`。

- 定位：Local Operator CLI。
- 面向：本地简单用户。

1. `certmanctl`。

- 定位：Control Plane Client CLI。
- 面向：控制面运维与自动化。

1. `certman-server`。

- 定位：Control Plane API。

1. `certman-worker`。

- 定位：Job Worker。

1. `certman-agent`。

- 定位：Node Agent。

### 3.2 术语统一

1. local 模式：`certman` 直连本地服务层。
1. remote/client 模式：`certmanctl` 通过 REST 调 `certman-server`。
1. control plane：`server + worker`。
1. distributed runtime：`server + worker + agent (+ certmanctl)`。

## 4. 设计实现方案

### 4.1 CLI 命令面拆分

#### `certman`（仅 local）

保留现有命令。

- entries
- new
- renew
- export
- check
- config-validate
- logs-clean

原则：不引入 endpoint/token 远程参数，避免污染本地 UX。

#### `certmanctl`（仅 remote）

MVP 命令建议。

- `certmanctl health`
- `certmanctl cert create|get|list|renew`
- `certmanctl job get|list|wait`
- `certmanctl webhook create|update|delete|list`

全局参数如下。

- `--endpoint`
- `--token`
- `--timeout`
- `--output text|json`
- `--context`（M2 引入）

### 4.2 分层架构

1. CLI 层。

- 参数解析。
- 输出格式控制。

1. Transport 层。

- `LocalTransport`（仅 certman）。
- `RestTransport`（仅 certmanctl）。

1. Domain/Service 层。

- 复用现有 service。
- server 端补齐 REST API 契约。

1. Formatter 层。

- text/json 统一结构。

1. Error 层。

- HTTP/业务错误码到 CLI 退出码映射。

### 4.3 安全与稳定性

1. 鉴权。

- Bearer token（MVP）。
- 后续扩展 scope。

1. 网络策略。

- connect/read timeout 分离。
- 幂等 GET 重试（指数退避）。
- POST 默认不自动重试。

1. TLS。

- 默认 verify=true。
- 支持自定义 CA。
- `--insecure` 仅开发环境。

## 5. 实施计划（里程碑）

### M1：文档与契约先行（当前阶段）

目标：冻结命名、职责、命令契约。

交付：

1. 本方案文档（本文件）。
1. 中英文对外文档页（dual-cli-modes）。
1. 文档导航更新。

### M2：MVP 编码（下一阶段）

目标：可用的 `certmanctl` 最小闭环。

范围：

1. 新增 `certmanctl` 入口。
1. health/job/webhook/cert 基础远程命令。
1. 统一错误码与输出。
1. 回归确保 `certman` 本地命令不回归。

### M3：增强与生产化

范围：

1. context/profile。
1. 完整 cert 操作与 wait 流程。
1. 鉴权增强（scope）。
1. e2e（native + compose + k8s）。

## 6. 测试与验收计划

### 6.1 测试层次

1. 单元测试。

- `certmanctl` 参数解析。
- REST client 错误映射。

1. 集成测试。

- 对接 FastAPI TestClient/ASGI。
- 覆盖 cert/job/webhook 接口。

1. e2e。

- compose：server+worker+client。
- k8s：server+worker+agent+client。

### 6.2 验收标准

1. `certman` 原有命令行为不变。
1. `certmanctl` 远程命令可执行且输出稳定。
1. 文档可独立指导部署与使用。
1. 核心测试通过并形成报告。

## 7. 风险与回滚

1. 风险：远程命令与本地命令语义冲突。

- 缓解：入口硬隔离（certman vs certmanctl）。

1. 风险：用户误用 token/endpoint。

- 缓解：上下文机制 + 明确错误提示。

1. 风险：改造影响现有脚本。

- 缓解：不改 `certman` 旧参数；新增入口实现。

回滚策略：

1. `certmanctl` 独立发布，可灰度禁用。
1. `certman` 保持原路径，不受远程改造影响。

## 8. 下一步执行清单（编码前）

1. 冻结 `certmanctl` 命令契约（参数/输出/退出码）。
1. 冻结 server API 对应映射表。
1. 评审测试清单与 CI 任务编排。
1. 进入编码实现与测试核验报告阶段。
