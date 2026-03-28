# Agent 通道后续迭代计划

**文档日期：** 2026-03-28  
**适用版本：** certman v0.1.0 之后  
**依据：** [complex-hybrid-certificate-topology.md §11 后续建议](../zh-CN/complex-hybrid-certificate-topology.md)

> **✅ 状态更新（2026-03-28）：** P0、P1-A、P1-B 均已在本次迭代中全量完成。回归测试 48 passed。
> 本文档保留作历史参考，后续迭代历史见 [2026-03-28-COMPLETION-REPORT.md](2026-03-28-COMPLETION-REPORT.md)。

---

## 背景

v0.1.0 已完成以下落地：

- poll / subscribe 双路任务拉取
- heartbeat / callback 状态回报
- 短时 bundle\_token（默认强制）
- NodeExecutor 多适配器（nginx / openresty / k8s-ingress）
- k8s-ingress apply 模式 + 基础回滚

以下三项为 §11 "后续建议"，本文将其拆解为可执行任务，并标注优先级。

---

## 优先级定义

| 级别 | 含义 |
|------|------|
| P0   | 阻塞生产稳定性或安全合规，需在下一个 minor release 前完成 |
| P1   | 显著提升运维质量，目标下一个 minor release 内完成 |
| P2   | 长期改善，排期灵活 |

---

## P0 — k8s-ingress 适配器增强

### 问题描述

当前 k8s-ingress 适配器在以下场景缺乏安全保障：
- 未提前校验 kubectl 权限是否足够（RBAC 缺失会导致 apply 静默失败或报错混乱）。
- apply 失败后的回滚依赖 `kubectl apply` 的幂等性，缺少 `--dry-run=server` 预检步骤。
- 失败分类粒度粗，运维告警无法区分"证书内容错误"与"集群连接失败"。

### 目标

| # | 子目标 | 验收条件 |
|---|--------|----------|
| 1 | `--dry-run=server` 预检 | apply 前先执行 dry-run；dry-run 失败时任务状态置 `failed`，附带 dry-run 错误详情，不进入正式 apply 流程 |
| 2 | RBAC 诊断 | 在节点注册或首次 apply 时，主动检查 `kubectl auth can-i` 所需权限（`get/patch/update secrets`, `get/patch ingresses`），缺权限时输出结构化诊断信息 |
| 3 | 失败分类 | 错误码至少区分：`dry_run_failed` / `rbac_denied` / `apply_failed` / `rollback_failed` / `connect_timeout` |
| 4 | 回滚策略完善 | 回滚失败时记录原始 manifest 至 job 日志，以便人工恢复；回滚后触发 callback 汇报实际状态 |

### 涉及模块

- `certman/delivery/k8s.py` — dry-run 逻辑、RBAC 检查、失败分类
- `certman/models/job.py` — 新增错误码枚举（或扩充现有 status 字段）
- `tests/test_node_executor.py` — 补充 dry_run_failed / rbac_denied 场景测试

### 估算

3–4 天（实现 + 单测覆盖）。

---

## P1-A — subscribe 升级为可选 SSE/WebSocket 通道 ✅

> **已完成：** `GET /api/v1/node-agent/events` SSE 端点、`NodePoller._events()` 客户端、三层回退链、配置字段 `prefer_sse`/`sse_wait_seconds`、全量单测 + 集成测试。

### 原始问题描述

当前 `/subscribe` 为 HTTP 长轮询：每次请求在服务端挂起最长 25 秒（`subscribe_wait_seconds`），到期或有任务时返回。  
场景扩大后（100+ agent 节点同时在线），长轮询的连接数压力会传导到应用层线程池与数据库查询，增加基础设施成本。

### 目标

| # | 子目标 | 验收条件 |
|---|--------|----------|
| 1 | 服务端 SSE 事件流端点 | 新增 `GET /api/v1/node-agent/events`（SSE），agent 持久连接后通过 `data:` 事件接收任务就绪通知；连接断开后自动重连 |
| 2 | agent 侧可选切换 | config 新增 `prefer_sse: bool = False`；为 `true` 时 agent 优先使用 SSE，SSE 失败回退到 subscribe 长轮询 |
| 3 | WebSocket（可选扩展） | 若 SSE 无法满足双向需求（如 heartbeat 复用），可进一步提供 `WS /api/v1/node-agent/ws`；WS 与 SSE 二选一，默认不启用 |
| 4 | 向后兼容 | `/subscribe` 接口保留，`prefer_subscribe` / `prefer_sse` 均为 false 时仍默认使用 poll |

### 涉及模块

- `certman/api/routes/node_agent.py` — 新增 SSE/WS 路由
- `certman/node_agent/agent.py` — SSE 客户端逻辑、回退策略
- `certman/config.py` — `prefer_sse` 字段
- `tests/test_api_node_agent.py` — SSE 连接 + 断线重连测试

### 估算

5–7 天（含 SSE 集成测试，WS 扩展另计）。

---

## P1-B — agent 通道可观测性 ✅

> **已完成：** 11 个 Prometheus 指标已定义并埋点，`/metrics` 端点已集成，6 个 告警规则已交付。

### 原始问题描述

当前缺乏以下运行时指标，难以判断 agent 通道健康状态：
- subscribe 触发率（事件唤醒 vs 超时返回的比例）
- bundle\_token 过期率（agent 持 token 下载时 401 的频率）
- callback 成功率

### 目标

| # | 指标名称 | 采集方式 | 告警基线建议 |
|---|----------|----------|--------------|
| 1 | `agent_subscribe_wakeup_ratio` | subscribe 返回时记录触发来源（event / timeout），计算比值 | 事件唤醒率 < 50% 告警（说明长轮询超时为主，事件推送失效） |
| 2 | `agent_bundle_token_expired_total` | `/bundles/{job_id}` 401 计数器 | 单节点 5 分钟内 > 3 次告警（TTL 配置过短或时钟偏差过大） |
| 3 | `agent_callback_success_ratio` | callback 接口 2xx vs 非 2xx 统计 | 成功率 < 95% 告警 |
| 4 | 指标暴露格式 | Prometheus `/metrics` 端点（`prometheus_client` 已在依赖中） | — |
| 5 | 告警规则示例 | 提供 `docs/examples/alert-rules.yaml`（Prometheus AlertManager 格式） | — |

### 涉及模块

- `certman/api/routes/node_agent.py` — 在 subscribe / bundles / callback 路由中埋点
- `certman/server.py` 或 `certman/exporter.py` — 注册 Prometheus metrics
- `docs/examples/alert-rules.yaml`（新增）
- `tests/test_api_node_agent.py` — 验证指标计数器在触发后递增

### 估算

3–4 天（含告警规则文档）。

---

## 交付顺序建议

> **已交付状态：** P0、P1-A、P1-B 均在同一迭代中完成。

```
v0.1.1 (P0 + P1-A + P1-B)  <- 已完成
  ├── k8s-ingress dry-run + RBAC 诊断 + 失败分类
  ├── subscribe 升级 SSE（期期 SSE 客户端 + 服务端 + 三层回退）
  └── agent 通道 Prometheus 指标 + 告警规则

v0.2.0 (待规划)
  ├── WebSocket 可选双向通道
  ├── Redis Pub/Sub 支持（多进程扩展）
  └── OpenTelemetry 链路追踪
```

---

## 相关文档索引

| 文档 | 说明 |
|------|------|
| [complex-hybrid-certificate-topology.md](../zh-CN/complex-hybrid-certificate-topology.md) | 混合拓扑全景，§6 当前协议链路，§11 实现状态 |
| [manual-layered.md](../zh-CN/manual-layered.md) | 完整配置字段参考（bundle_token、prefer_subscribe 等） |
| [api-access.md](../zh-CN/api-access.md) | §2.3 Node-Agent 协议接口表 |
| [cookbook-layered.md](../zh-CN/cookbook-layered.md) | 场景 10 subscribe/heartbeat/callback 用法示例 |
