# CertMan 跨环境证书控制平面架构设计

> 评估日期: 2026-03-24
> 状态: 设计草案（已按最新定位修订）

---

## 1. 目标重定义

CertMan 的目标不是做单一 K8s 集群里的 TLS Secret 控制器，而是做一个跨云、跨区域、跨网络环境的证书控制平面。

它需要统一处理以下能力：

1. 证书管理：新建、续签、撤销、下载、验证
2. 证书分发：向 K8s、VM、本地文件系统、反向代理、对象存储、私有系统 API 分发
3. 事件机制：Webhook 订阅、投递、重试、死信、审计
4. 安全传输：跨公网环境下通过非对称身份认证、内容加密、安全分发证书材料
5. 双模式运行：
   - 本地自治模式：CLI 结合本地 YAML/TOML 配置独立运行，完成本地证书管理
   - 受控节点模式：CLI/Agent 绑定中心控制面，接收任务、下载证书、订阅事件并触发本地动作

这意味着 CertMan 的产品定位应当从“CLI 工具服务化”升级为“控制平面 + 节点执行器 + 分发适配器”的体系。

---

## 2. 核心设计原则

### 2.1 设计原则

1. KISS：保留当前 CLI 的核心 issuing/renew/export/check 能力，不重写底层 certbot 工作流
2. YAGNI：不把产品收窄为 K8s Secret 管理器，也不一开始引入过重的微服务拆分
3. SRP：控制平面负责策略与编排，节点负责本地执行与交付
4. 安全优先：身份认证、任务签名、内容加密、重放防护必须是内建能力
5. 跨环境优先：K8s 只是一个目标环境，不是产品边界
6. 兼容当前 CLI：原有命令能力继续保留，作为本地模式与节点模式的共用执行内核

### 2.2 非目标

1. 不把 CertMan 设计成 cert-manager 的替代 CRD 控制器
2. 不要求控制平面直接持有所有远端集群 kubeconfig
3. 不默认接管业务系统的 TLS 生命周期
4. 不把 DNS provider 凭据下发到所有分发节点

---

## 3. 运行模式

### 3.1 模式 A：本地自治模式

CLI 直接使用本地配置与本地状态目录运行。

适用场景：

1. 单节点或单环境证书管理
2. 内网独立部署
3. 无中心控制面的离线场景
4. 运维手工或本地计划任务驱动

运行特征：

1. 本地配置文件定义域名、DNS provider、凭据来源、导出位置、hook
2. CLI 直接调用 certbot 完成签发与续签
3. 本地任务调度器或操作系统 cron 驱动 renew/check/export
4. 签发后可执行本地 hook，例如重启 nginx、reload envoy、更新本地文件

### 3.2 模式 B：受控节点模式

CLI 或轻量 Agent 作为执行节点运行，连接中心控制平面。

适用场景：

1. 多云、多区域、多网络环境统一证书治理
2. 私网节点仅允许出站访问公网
3. 需要中心化审计、编排、Webhook 分发与安全策略控制

运行特征：

1. 节点预配置私钥文件位置、节点身份、控制面入口地址
2. 节点主动向控制平面注册并建立安全连接
3. 节点接收任务、下载加密证书包、完成本地落地
4. 节点接收事件后执行本地动作，例如重启 nginx、reload ingress、刷新缓存
5. 节点可订阅指定证书、证书组或事件主题

### 3.3 模式兼容原则

两种模式必须共用同一套核心执行逻辑，而不是分叉成两套系统。

共享内核：

1. 证书生命周期服务
2. 验证服务
3. 导出与落地服务
4. Hook 执行服务

差异只体现在：

1. 配置来源
2. 调度来源
3. 任务来源
4. 身份认证与分发链路

---

## 4. 总体架构

### 4.1 高层拓扑

```text
                        ┌─────────────────────────────┐
                        │   CertMan Control Plane     │
                        │-----------------------------│
                        │ API / Auth / Scheduler      │
                        │ Certificate Metadata        │
                        │ Distribution Orchestrator   │
                        │ Webhook Event Bus           │
                        │ Audit / Policy / Registry   │
                        └──────────────┬──────────────┘
                                       │
                          mTLS + signed tasks + encrypted payload
                                       │
          ┌────────────────────────────┼────────────────────────────┐
          │                            │                            │
          ▼                            ▼                            ▼
┌───────────────────┐        ┌───────────────────┐        ┌───────────────────┐
│ K8s Connector     │        │ VM Connector      │        │ Local Node CLI    │
│ / Agent           │        │ / Service         │        │ (自治模式)        │
│-------------------│        │-------------------│        │-------------------│
│ Pull tasks        │        │ Pull tasks        │        │ Local config      │
│ Decrypt bundle    │        │ Decrypt bundle    │        │ Local schedule    │
│ Write Secret      │        │ Write files       │        │ Local hooks       │
│ Run hooks         │        │ Reload services   │        │ certbot direct    │
└───────────────────┘        └───────────────────┘        └───────────────────┘
```

### 4.2 控制平面与数据平面

#### 控制平面职责

1. 管理证书元数据与分发策略
2. 管理节点注册、身份、公钥、授权范围
3. 编排计划任务与人工触发任务
4. 触发续签、验证、分发、回滚、Webhook
5. 记录审计日志、告警与失败恢复信息

#### 数据平面职责

1. 实际执行 certbot 工作流
2. 实际下载加密证书包并本地解密
3. 将证书写入目标介质
4. 执行本地 hook 与健康检查
5. 回传 ACK、结果、错误与摘要

---

## 5. 服务边界

### 5.1 控制平面服务

1. Certificate Service
   - 证书生命周期编排
   - 元数据管理
   - 策略查询

2. Credential Vault Service
   - DNS provider 凭据托管
   - 加密存储
   - 凭据轮换与审计

3. Distribution Orchestrator
   - 将证书分发到不同目标环境
   - 管理分发版本、分发记录、回滚

4. Node Registry Service
   - 节点注册
   - 节点身份、公钥、能力、授权范围管理

5. Scheduler Service
   - 定时续签
   - 定时校验
   - 补偿重试
   - 死信队列

6. Webhook Event Service
   - 事件总线
   - Webhook 订阅与投递
   - 回调签名、重试、死信

7. Audit and Compliance Service
   - 审计日志
   - 合规告警
   - 过期风险监控

### 5.2 节点侧能力

1. Connector Runtime
   - 与控制面安全连接
   - 拉取任务
   - 任务验签与幂等校验

2. Delivery Executor
   - 写入本地文件
   - 更新 K8s Secret
   - 上传对象存储
   - 调用本地 API

3. Hook Runner
   - 执行自定义命令或脚本
   - 例如重启 nginx、reload haproxy、刷新 ingress

4. Validation Probe
   - 本地 TLS 验证
   - 文件校验
   - 服务 reload 成功检查

---

## 6. 核心领域模型

### 6.1 主要实体

1. Certificate
   - id
   - primary_domain
   - secondary_domains
   - issuer
   - status
   - not_after
   - renewal_policy_id
   - distribution_policy_id

2. CertificateBundle
   - cert.pem
   - chain.pem
   - fullchain.pem
   - privkey.pem
   - fingerprint
   - version

3. ManagedEntry
   - 与当前 CLI 的 EntryConfig 对齐
   - 描述域名、provider、凭据引用、hook、导出策略

4. DistributionTarget
   - type: k8s | filesystem | object-storage | http-api | local-service
   - endpoint
   - target_scope
   - auth_profile
   - write_policy

5. NodeIdentity
   - node_id
   - node_type
   - public_key
   - tls_client_cert
   - allowed_targets
   - allowed_certificates

6. WebhookSubscription
   - topic
   - endpoint
   - signing_key_id
   - retry_policy

7. Job
   - job_id
   - type: issue | renew | validate | distribute | revoke | hook
   - subject_id
   - status
   - attempts
   - next_run_at

### 6.2 当前 CLI 的映射关系

当前的 EntryConfig 应保留，并逐步提升为 ManagedEntry 的本地表达形式。

映射原则：

1. 本地模式：ManagedEntry 完全来自本地 TOML/YAML
2. 受控模式：ManagedEntry 可来自控制面下发的策略快照
3. 底层 certbot 参数生成逻辑继续复用当前 cli.py 中的行为

---

## 7. API 设计

### 7.1 控制平面外部 API

#### 证书管理

1. POST /api/v1/certificates
2. GET /api/v1/certificates
3. GET /api/v1/certificates/{id}
4. POST /api/v1/certificates/{id}/renew
5. POST /api/v1/certificates/{id}/revoke
6. GET /api/v1/certificates/{id}/download
7. GET /api/v1/certificates/{id}/validations

#### 分发管理

1. POST /api/v1/distributions/targets
2. GET /api/v1/distributions/targets
3. POST /api/v1/distributions/jobs
4. GET /api/v1/distributions/jobs/{job_id}
5. POST /api/v1/distributions/jobs/{job_id}/retry

#### 节点管理

1. POST /api/v1/nodes/register
2. POST /api/v1/nodes/auth/refresh
3. GET /api/v1/nodes/{node_id}
4. POST /api/v1/nodes/{node_id}/disable
5. GET /api/v1/nodes/{node_id}/deliveries

#### Webhook 管理

1. POST /api/v1/webhooks/subscriptions
2. GET /api/v1/webhooks/subscriptions
3. GET /api/v1/webhooks/deliveries
4. POST /api/v1/webhooks/subscriptions/{id}/test

### 7.2 节点拉取与回执 API

1. POST /api/v1/node-agent/poll
2. GET /api/v1/node-agent/jobs/{job_id}/bundle
3. POST /api/v1/node-agent/jobs/{job_id}/ack
4. POST /api/v1/node-agent/jobs/{job_id}/result
5. POST /api/v1/node-agent/webhook-events/ack

### 7.3 长任务语义

长耗时操作统一返回 202 Accepted 与 job_id。

示例：

```json
{
  "job_id": "job_20260324_001",
  "status": "queued",
  "status_url": "/api/v1/distributions/jobs/job_20260324_001"
}
```

---

## 8. 安全模型

### 8.1 身份认证

采用双层认证：

1. 控制面用户认证
   - 管理 API 使用 OIDC/JWT 或企业 SSO
   - RBAC 控制新建、续签、撤销、下载、分发等权限

2. 节点身份认证
   - 每个节点独立身份
   - 首次注册通过一次性注册令牌
   - 注册后颁发短期 mTLS 客户端证书或等价节点凭据

### 8.2 非对称信任模型

每个节点至少维护两套密钥：

1. 身份密钥对
   - 用于 mTLS 与节点身份识别

2. 内容接收密钥对
   - 控制面只持有节点公钥
   - 证书包加密后只能由对应节点解密

### 8.3 内容加密

采用信封加密：

1. 控制面生成一次性对称数据密钥
2. 用数据密钥加密证书包内容（AES-256-GCM）
3. 用节点公钥加密数据密钥
4. 节点收到密文后本地解密并立即落地

这样可以做到：

1. 控制面不长期保存明文私钥
2. 中间链路被截获时也无法解密证书内容

### 8.4 消息验签与重放防护

每个任务消息必须带：

1. message_id
2. node_id
3. nonce
4. issued_at
5. expires_at
6. sequence
7. payload_hash
8. detached_signature

节点处理前校验：

1. 签名有效
2. 时间窗有效
3. nonce 未重复
4. sequence 不回退
5. payload_hash 一致

### 8.5 下载与分发最小暴露原则

1. 默认不开放明文私钥长期下载链接
2. 下载接口必须短期授权、带审计
3. 分发节点只拿到自己有权解密的证书包
4. DNS provider 凭据仅存在于签发工作节点或控制面密钥托管系统

---

## 9. Webhook 与事件模型

### 9.1 事件主题

1. certificate.issued
2. certificate.renewed
3. certificate.revoked
4. certificate.expiring
5. distribution.succeeded
6. distribution.failed
7. validation.failed
8. node.offline

### 9.2 Webhook 投递要求

1. 事件至少一次投递
2. 事件携带 event_id 供消费方幂等处理
3. 请求体必须签名
4. 仅对网络错误与 5xx 自动重试
5. 超过重试阈值后进入死信队列

### 9.3 节点本地动作触发

支持以下动作类型：

1. shell command
2. local script
3. systemd service restart/reload
4. http callback to local service

典型示例：

1. 证书更新后执行 nginx -s reload
2. 证书更新后重启本地 docker 容器
3. 证书更新后调用内部配置刷新接口

---

## 10. 计划任务模型

### 10.1 本地自治模式计划任务

1. 本地到期扫描
   - 每 6 小时扫描一次

2. 本地自动续签
   - 到期前 30 天进入窗口
   - 到期前 20 天开始尝试

3. 本地导出校验
   - 签发或续签后立即校验输出文件

4. 本地 hook 执行
   - 更新后触发 reload 或自定义操作

### 10.2 控制平面计划任务

1. 证书库存巡检
   - 每 6 小时一次
   - 统计即将过期证书、失败分发、离线节点

2. 自动续签编排
   - 每天定时运行
   - 将符合条件的证书推入续签任务队列

3. 分发补偿任务
   - 检查分发未 ACK 的任务
   - 进入重试或死信

4. 节点健康探测
   - 检查节点心跳与最近回执

5. Webhook 重试任务
   - 按退避策略重投失败事件

### 10.3 推荐重试策略

指数退避：

1. 1 分钟
2. 5 分钟
3. 15 分钟
4. 1 小时
5. 6 小时
6. 24 小时

失败分类：

1. 瞬时错误：自动重试
2. 限流错误：退避并扩散时间
3. 配置错误：停止重试并告警
4. 安全错误：立即拒绝并告警

---

## 11. 与当前 CLI 的演进路径

### 11.1 保留项

保留当前模块并继续作为核心执行内核：

1. certbot_runner.py
2. providers.py
3. certs.py
4. exporter.py
5. logging_.py
6. runtime_logging.py
7. config.py
8. config_merge.py

### 11.2 需要抽取的能力

从 cli.py 中抽取为可复用服务层：

1. Issue workflow
2. Renew workflow
3. Check workflow
4. Export workflow
5. Hook workflow

### 11.3 建议的新目录结构

```text
certman/
├── api/
├── scheduler/
├── services/
├── node_agent/
├── hooks/
├── security/
├── delivery/
├── models/
└── cli.py
```

### 11.4 CLI 双入口建议

1. certman
   - 保留现有本地 CLI 能力

2. certman-agent
   - 节点执行器模式
   - 用于注册控制面、接收任务、处理分发、执行 hook

3. certman-server
   - 控制平面 API

---

## 12. K8s 在整个体系中的角色

K8s 是众多分发目标之一，而不是 CertMan 的唯一边界。

在 K8s 中建议定义两类角色：

1. 控制面部署环境
   - 运行 certman-server、scheduler、worker

2. 目标集群连接器环境
   - 运行 certman-agent
   - 负责本地 Secret 落地与本地 hook

注意：

1. 不要求控制面直接操作所有远端集群 API
2. 不默认接管 cert-manager 资源
3. 只有当目标集群明确把 Secret 分发交给 certman-agent 时，才落地相应 Secret

---

## 13. 最终判断

CertMan 应该被定义为：

跨网络、跨环境、支持本地自治与中心编排双模式的证书控制平面。

它的三条主线是：

1. 证书生命周期管理
2. 安全分发与本地落地执行
3. 事件驱动的自动化联动

相对于原方案，最关键的修正是：

1. 从“K8s 内服务化”升级为“跨环境控制平面”
2. 从“同步 TLS Secret”升级为“多目标分发框架”
3. 从“API Key + 普通下载”升级为“节点身份 + 加密内容分发”
4. 从“仅 CLI 封装”升级为“CLI、Agent、Control Plane 共用核心内核”

---

## 14. 当前实装状态（2026-03-26）

### 14.1 已实装功能

#### CLI / 本地自治模式
- ✅ `certman` 命令及配置系统（TOML/YAML，支持 entry、hook、provider）
- ✅ 本地证书生命周期（issue/renew/check/export）
- ✅ 多 provider 支持（cloudflare、route53、aliyun）
- ✅ Hook 执行框架（shell 命令触发）
- ✅ 本地自治模式配置验证

#### 控制平面服务器
- ✅ FastAPI HTTP Server (`certman-server`)
- ✅ 配置系统升级为 server mode（`run_mode="server"`）
- ✅ SQLAlchemy 数据库层（Alembic migration）
- ✅ Job 模型与队列系统（issue/renew type）
- ✅ Health endpoint (`GET /health`)

#### 核心 API 端点（Phase 4）
| 端点 | 实装状态 | 备注 |
|------|--------|------|
| `POST /api/v1/certificates` | ✅ 完成 | 创建 issue job，返回 job_id，202 Accepted |
| `GET /api/v1/jobs/{job_id}` | ✅ 完成 | 查询 job 状态（queued/claimed/completed/failed） |
| `POST /api/v1/webhooks` | ✅ 完成 | 创建 webhook 订阅，支持签名验证 |
| `POST /api/v1/nodes/register` | ⏳ 实装中 | 节点使用一次性 token 注册 |

#### 安全与身份认证
- ✅ Ed25519 签名密钥对支持（在 server config 中）
- ✅ 消息签名与验证框架（Node-Agent 通信）
- ✅ Nonce 与 sequence 重放防护（已实装在 agent 模型）

#### 后台工作进程
- ✅ `certman-worker` 进程（--loop 模式）
- ✅ Job 声明与处理（claim_next_job）
- ✅ 异步任务驱动（30s 轮询间隔可配）
- ✅ Event 发布/订阅基础框架

#### 事件驱动能力
- ✅ EventBus 框架（内存实装）
- ✅ Webhook 订阅表与投递框架
- ✅ Job 事件发布（job.queued/completed/failed）

#### Docker & Kubernetes 部署
- ✅ Docker 镜像构建（Dockerfile 完整）
- ✅ Docker Compose 支持（3 个服务 + volume + network）
- ✅ Kubernetes 部署清单（配置、PVC、Deployment、Service）
- ✅ Kind 1.34 成功演练及运行验证

### 14.2 进行中/部分实装

| 功能 | 状态 | 说明 |
|------|------|------|
| Node Registry Service | ⏳ 框架就位 | 数据库表已定义，API 端点待完成 |
| Credential Vault | ⏳ 基础实装 | 支持嵌入式 + 环境变量，长期 vault 服务待规划 |
| Distribution Orchestrator | ⏳ 骨架设计 | Job 类型框架就位（distribute），具体算法待完成 |
| Audit Logging | ⏳ 路由级记录 | 基础 HTTP 日志，精细审计日志待增强 |
| Webhook 重试 & 死信队列 | ⏳ 设计完成 | 基础框架存在，完整重试策略待优化 |

### 14.3 待规划/设计中

| 功能 | 优先级 | 说明 |
|------|--------|------|
| Agent 节点模式 | 高 | 节点侧执行引擎、任务拉取、本地写入 |
| 证书分发到 K8s Secret | 高 | 与通过 kubeconfig 的远端集群交互 |
| 证书分发到对象存储 | 中 | S3/OSS 分发适配器 |
| OIDC/RBAC 用户认证 | 中 | 管理 API 的用户级访问控制 |
| 内容加密（信封加密） | 中 | AES-256-GCM + RSA/Ed25519 包装 |
| mTLS 节点通信 | 中 | 客户端证书颁发与验证 |
| 全链路审计与合规 | 低 | 详细的操作->结果追踪与告警 |

### 14.4 验证矩阵

#### 本地运行验证（✅ PASS）
```
pytest -q --tb=short        → 78/78 PASSED
docker build -t certman:local . → SUCCESS
docker compose up -d        → 3 services running
docker compose API smoke    → /health 200, /api/v1/certificates 404 (entry not found)
```

#### Kubernetes 验证（✅ PASS on Kind 1.34）
```
kind create cluster --image kindest/node:v1.34.0  → Created
kind load docker-image certman:local               → Loaded
kubectl apply -f k8s-rehearsal.yaml                → All objects created
Pod:  certman-server-xxx Ready=1/1, Running        → Healthy
HTTP: kubectl port-forward svc/certman-server 8001:8000
   GET  /health → 200 OK
   POST /api/v1/certificates → 404 entry not found (expected)
```

### 14.5 下一步行动项

**短期（本周）：**
1. 补充 k8s 部署中的 worker 容器与端到端 job 流验证
2. 添加完整配置示例（item_site-a.toml）到 ConfigMap
3. 在 kind 环境中验证 job 从提交 → worker 处理 → 完成的完整链路
4. 验证 webhook 事件投递（job.queued/completed）

**中期（2 周内）：**
1. 实装 POST /api/v1/nodes/register 与节点注册表
2. 实装 agent 节点侧的任务拉取与本地执行框架
3. 测试受控节点模式下的简单分发

**长期（规划中）：**
1. Credential Vault 服务化
2. K8s Secret 分发适配器
3. 用户认证与 RBAC
4. 信封加密与 mTLS
