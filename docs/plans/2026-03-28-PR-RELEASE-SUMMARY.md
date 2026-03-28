# PR / Release 变更摘要

**版本：** v0.1.1  
**日期：** 2026-03-28  
**分支：** `master` → release  
**回归测试：** 48 passed ✅

---

## 概述

本次 release 在 v0.1.0 基础上交付三项功能增强，全部向后兼容，无破坏性 API 变更：

| 优先级 | 功能 | 测试 |
|--------|------|------|
| P0 | k8s-ingress 适配器：dry-run 预检 + RBAC 诊断 + 失败分类 + 回滚 | 10 个单测 ✅ |
| P1-A | Node-Agent SSE 通道：服务端 + 客户端三层回退链 | 4 个新测 ✅ |
| P1-B | Agent 通道可观测性：Prometheus 指标 + 告警规则 | 2 个新测 ✅ |

---

## 变更详情

### P0 — k8s-ingress 适配器增强

**文件：** `certman/delivery/k8s.py`（新增 ~350 行）  
**测试：** `tests/test_k8s_delivery.py`（新增 ~200 行，10 个用例）

**新增能力：**

- `--dry-run=server` 预检：apply 前验证 manifest，失败则任务置 `failed`，不进入真正 apply
- RBAC 诊断：注册/首次 apply 时主动 `kubectl auth can-i` 检查 `get/create/update secrets`，缺权限时输出结构化日志
- 7 种错误码（`K8sErrorCode` 枚举）：`DRY_RUN_FAILED` / `RBAC_DENIED` / `APPLY_FAILED` / `ROLLBACK_FAILED` / `CONNECT_TIMEOUT` / `MANIFEST_INVALID` / `CLUSTER_UNREACHABLE`
- 失败回滚：apply 失败前先 `kubectl get secret` 保存快照，失败后尝试恢复；回滚也失败时记录原始 manifest 到 job 日志
- `K8sDeliveryResult` 不可变数据类（`@dataclass(frozen=True)`）作为统一返回值

---

### P1-A — Node-Agent SSE 通道

**文件（服务端）：** `certman/api/routes/node_agent.py`（+120 行）  
**文件（客户端）：** `certman/node_agent/poller.py`（+74 行）  
**文件（配置）：** `certman/config.py`（+4 行）  
**文件（CLI 入口）：** `certman/node_agent/agent.py`（+4 行）  
**测试：** `tests/test_node_poller_sse.py`（新增），`tests/test_api_node_agent.py`（+64 行）

**新增 API 端点：**

```
GET /api/v1/node-agent/events
  认证：Query 参数 Ed25519 签名（与 poll/subscribe 相同）
  响应：text/event-stream (SSE)
  事件类型：connected | assignment | timeout
  保活：注释行 `: keepalive`，每 10 秒
```

**事件流行为：**

1. 连接后立即发送 `event: connected`
2. 若有待处理 job，立即发送 `event: assignment\ndata: [...]`
3. 否则挂起等待 `subscription_event_bus.wait_for_update(sse_wait_seconds)`
4. 被唤醒后检查 job，有则发送 assignment，超时则发送 `event: timeout`

**客户端回退链（NodePoller）：**

```
prefer_sse=true → _events()
  ├─ 成功（有 assignment） → 返回 assignments 列表
  ├─ timeout（无任务）    → 返回 []
  └─ 失败/404             → None → 回退到 _subscribe()
                                      └─ 失败 → 直接 httpx.post /poll
```

**新配置字段：**

```yaml
control_plane:
  prefer_sse: false           # 默认关闭，true 时优先 SSE
  sse_wait_seconds: 25        # SSE 服务端等待窗口（秒）
```

---

### P1-B — Agent 通道可观测性

**文件（指标定义）：** `certman/monitoring/metrics.py`（新增 ~75 行）  
**文件（导出端点）：** `certman/api/app.py`（+10 行）  
**文件（告警规则）：** `docs/examples/alert-rules.yaml`（新增 ~250 行）  
**测试：** `tests/test_api_node_agent.py`（+2 个指标验证用例）

**新增端点：**

```
GET /metrics
  格式：Prometheus text format
  认证：无（建议在内网 Pod 级别访问）
```

**Prometheus 指标（11 个）：**

| 指标 | 类型 | 说明 |
|------|------|------|
| `certman_agent_poll_total` | Counter | node_id, endpoint 维度的请求计数 |
| `certman_agent_subscribe_wakeup_total` | Counter | 唤醒源（event/timeout）统计 |
| `certman_agent_subscribe_wait_seconds` | Histogram | 订阅等待时长分布 |
| `certman_agent_bundle_token_expired_total` | Counter | token 过期次数 |
| `certman_agent_bundle_token_invalid_total` | Counter | token 无效次数 |
| `certman_agent_bundle_download_success_total` | Counter | 成功下载 bundle 次数 |
| `certman_agent_callback_result_total` | Counter | 回调结果（status/outcome） |
| `certman_agent_callback_result_seconds` | Histogram | 回调延迟分布 |
| `certman_agent_auth_failure_total` | Counter | 认证失败次数 |
| `certman_active_nodes` | Gauge | 当前活跃节点总数 |
| `certman_server` | Info | 服务器版本元信息 |

**告警规则（6 条，`docs/examples/alert-rules.yaml`）：**

| 告警 | 触发条件 | 级别 |
|------|----------|------|
| SubscribeEventWakeupRateLow | 事件唤醒率 < 50% | warning |
| BundleTokenExpiredRateHigh | token 过期率 > 10% | warning |
| CallbackSuccessRateLow | 回调成功率 < 95% | warning |
| ActiveNodesDropped | 20min 内节点数下降 20% | **critical** |
| AgentAuthFailureRateHigh | 认证失败率 > 1%/min | warning |
| SubscribeLatencyHigh | p95 延迟 > 30s | warning |

---

## 依赖变更

```toml
# pyproject.toml 新增
prometheus-client>=0.21.1
```

---

## 文档变更

| 文档 | 变更内容 |
|------|----------|
| `docs/zh-CN/manual-layered.md` | 新增 `prefer_sse`/`sse_wait_seconds` 配置项、§5.2.1 events (SSE) 协议节 |
| `docs/en/manual-layered.md` | 同上（英文版） |
| `docs/zh-CN/api-access.md` | Node-Agent 协议表新增 `GET /events` 和 `/metrics`，更新回退链说明 |
| `docs/en/api-access.md` | 同上（英文版） |
| `docs/skills/certman-operator/SKILL.md` | 低延迟分发节更新为 SSE 优先 |
| `docs/skills/certman-operator/references/command-map.md` | MCP surface 表新增 SSE/metrics 行 |
| `docs/examples/alert-rules.yaml` | 新增 Prometheus AlertManager 规则文件 |
| `docs/plans/P1-A-sse-event-channel-design.md` | SSE 通道架构设计文档 |

---

## 测试覆盖

```
新增测试文件：
  tests/test_k8s_delivery.py        10 个单测（k8s 适配器）
  tests/test_node_poller_sse.py      2 个单测（SSE 客户端回退）

扩展测试文件：
  tests/test_api_node_agent.py      +4 个测（SSE 端点 + 指标端点）

最终回归（全量）：
  48 passed（test_api_node_agent + test_node_executor + test_scheduler_*
             + test_job_service + test_agent_mode + test_node_poller_sse
             + test_k8s_delivery）
```

---

## 升级指南

向后完全兼容，无需修改现有配置。如需启用新功能：

**启用 SSE 通道（可选）：**

```yaml
control_plane:
  prefer_sse: true
  sse_wait_seconds: 25
```

**启用 Prometheus 抓取（可选）：**

```yaml
# prometheus.yml
scrape_configs:
  - job_name: certman
    static_configs:
      - targets: ['certman-api:8000']
    metrics_path: /metrics
```

**导入告警规则（可选）：**

```bash
# 将 docs/examples/alert-rules.yaml 复制到 AlertManager 规则目录
cp docs/examples/alert-rules.yaml /etc/prometheus/rules/certman.yaml
```

---

## Commit 建议

```
feat(p0): k8s-ingress dry-run/RBAC/rollback adapter

- Add K8sErrorCode enum (7 codes) and K8sDeliveryResult dataclass
- Implement --dry-run=server pre-check before apply
- Add kubectl auth can-i RBAC diagnostics
- Add rollback with pre-apply snapshot and callback on failure
- Add 10 unit tests covering all error paths

feat(p1-a): SSE event channel for node-agent

- Add GET /api/v1/node-agent/events SSE endpoint (Ed25519 auth)
- Implement NodePoller._events() with httpx.stream() SSE client
- Add 3-tier fallback: SSE → subscribe → poll
- Add prefer_sse / sse_wait_seconds config fields
- Add 4 tests (server SSE delivery + client fallback)

feat(p1-b): Prometheus observability for agent channel

- Add certman/monitoring/metrics.py with 11 metrics
- Expose GET /metrics endpoint (Prometheus text format)
- Instrument all node-agent routes with metric counters
- Add docs/examples/alert-rules.yaml (6 alert rules)
- Add prometheus-client>=0.21.1 dependency

docs: sync manual, API access, skill docs for P0/P1-A/P1-B
```
