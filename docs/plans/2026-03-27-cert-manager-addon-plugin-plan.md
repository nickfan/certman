# CertMan 与 cert-manager 协作（Addon/Plugin/Extension）规划登记

> 日期: 2026-03-27
> 状态: 规划登记（本期不实现）
> 范围: 仅设计、边界、里程碑与验收口径

## 1. 背景与目标

当前 CertMan 已具备本地 CLI、控制面 API、worker、webhook 与 MCP 接入能力。为与 K8s 生态协同，需要将与 cert-manager 的协作能力规划为可插拔扩展（addon/plugin/extension），避免把主干产品收敛为单一 K8s 控制器。

目标：

1. 明确与 cert-manager 的上游/下游协作模式。
2. 以插件化形态设计，保持 CertMan 核心内核稳定。
3. 本期只完成规划登记，不修改主链路实现。

## 2. 本期范围（In Scope）

1. 架构边界定义与术语统一。
2. 协作模式与事件契约草案。
3. 风险、依赖、分期里程碑登记。
4. 文档化当前不做项（Out of Scope），避免误解为立即开发。

## 3. 本期不做（Out of Scope）

1. 不新增 cert-manager CRD Controller 实现。
2. 不新增 cert-manager webhook/issuer adapter 代码。
3. 不改动现有 certman-server API 行为。
4. 不改动 worker 调度策略与证书分发链路。
5. 不引入新的集群级 RBAC 与部署清单。

## 4. 协作模式设计

### 4.1 下游协作（cert-manager -> CertMan）

定位：CertMan 订阅或监听 cert-manager 证书更新事件，并触发后续分发或审计。

建议形态：

1. `certman-cert-sync` addon（独立部署）监听 `Certificate/Secret` 变化。
2. 同步器将变化写入 CertMan 入站事件接口（后续版本新增）。
3. CertMan 统一做分发、审计与 webhook 外发。

### 4.2 上游协作（CertMan -> cert-manager）

定位：cert-manager 通过扩展适配器向 CertMan 请求签发/续签。

建议形态：

1. `certman-external-issuer` plugin 对接 cert-manager external issuer 模式。
2. 适配器把 `CertificateRequest` 映射为 CertMan job。
3. 适配器轮询 job 状态并回填目标 Secret。

## 5. 事件与接口演进草案（后续期）

建议新增证书语义事件（区别于现有 `job.*` 事件）：

1. `certificate.issued`
2. `certificate.renewed`
3. `certificate.distributed`
4. `certificate.imported`（来自 cert-manager 下游同步）

建议统一最小字段：

1. `entry_name`
2. `primary_domain`
3. `cert_fingerprint`
4. `not_after`
5. `version`
6. `source`（`certman` / `cert-manager`）

## 6. 风险与依赖

主要风险：

1. cert-manager 资源模型与 CertMan entry 模型映射不一致。
2. 多来源更新导致冲突与覆盖顺序不明确。
3. Secret 变更频繁带来的事件风暴与幂等压力。
4. 跨命名空间 RBAC 范围过大带来安全风险。

关键依赖：

1. 稳定的证书版本标识（指纹/version）。
2. 证书入站事件接口（含幂等键）。
3. 统一的重试/死信策略与审计记录。

## 7. 分期建议

Phase A（优先）：下游协作 MVP

1. 设计并实现入站事件接口。
2. 开发 `certman-cert-sync` watcher addon。
3. 实现去重、重试、审计。

Phase B：上游协作 MVP

1. 开发 `certman-external-issuer` plugin。
2. 跑通 `CertificateRequest -> Job -> Secret` 闭环。
3. 完成 RBAC 最小权限模板。

Phase C：生产化

1. 多集群/多命名空间策略。
2. 观测指标与告警。
3. 回滚策略与灰度发布。

## 8. 验收口径（仅规划登记）

1. 文档中明确“本期不实现”且无歧义。
2. 上下游两种协作模式均有边界定义。
3. 有可执行分期和依赖清单。
4. 与现有控制面定位一致，不改变当前里程碑节奏。
