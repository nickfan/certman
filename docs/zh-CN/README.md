# 中文文档 Guide (中文)

**[← 返回主文档](../../README.zh-CN.md) | [English Guide](../en/README.md)**

## 文档导航

### 🚀 快速开始

- **[快速指南 (quickguide-docker-compose.md)](quickguide-docker-compose.md)** - 5分钟上手，用明确的例子展示完整工作流
  - 适合第一次使用，以 AWS Route53 + mydemo1.com 为例
  - 覆盖配置、申请、续签、导出、检查全流程

- **[三层快速指南 (quickguide-layered.md)](quickguide-layered.md)** - 15分钟跑通 CLI / Agent / Service
  - 包含本地、控制面、受控节点三层最小闭环
  - 适合从单机模式迁移到控制面模式

### 📚 实战手册

- **[Cookbook (cookbook-compose.md)](cookbook-compose.md)** - 7个生产环境真实场景
  - 场景1: 新域名接入（Route53）
  - 场景2: 每日监控告警（纯巡检）
  - 场景3: 完全自动化续签（Cron/K8s）
  - 场景4: 多Provider管理（Route53+Cloudflare+Aliyun）
  - 场景5: 导出给Kubernetes Secret
  - 场景6: 使用Docker Hub镜像
  - 场景7: Windows + Task Scheduler 自动化
  - 附加: 完整的故障排查指南

- **[三层场景手册 (cookbook-layered.md)](cookbook-layered.md)** - 按层级拆分的真实运维场景
  - CLI: 新域名接入、每日巡检
  - Service: 任务编排、去重与回调
  - Agent: 签名轮询、结果上报、防重放

- **[三层运维手册 (manual-layered.md)](manual-layered.md)** - 参数抽象与协议约束
  - 配置参数影响范围
  - API 契约、状态机、并发与安全基线

- **[API 与 AI 接入 (api-access.md)](api-access.md)** - OpenAPI 地址、远程 CLI 用法与 AI 接入现状
  - `/docs`、`/redoc`、`/openapi.json`
  - `certmanctl` 与 REST 的对应关系
  - MCP 可用性说明

- **[CLI 帮助参考 (cli-help-reference.md)](cli-help-reference.md)** - Local/Remote CLI 参数速查与 `--help` 使用
  - `certman` 命令与参数映射
  - `certmanctl` 命令与参数映射
  - skill preflight 建议

### ⚡ DNS Provider 文档

- **[DNS Providers 配置 (../dns-providers.md)](../dns-providers.md)** - 三个Provider的详细配置和凭据管理
  - AWS Route53
  - Cloudflare
  - Aliyun DNS

### 📋 其他文档

- [Kubernetes 部署设计 (../k8s-service-design.md)](../k8s-service-design.md)
- [双 CLI 模式说明 (dual-cli-modes.md)](dual-cli-modes.md)
- [双 CLI 实施总方案 (../notes/plans/2026-03-26-dual-cli-program.md)](../notes/plans/2026-03-26-dual-cli-program.md)
- [cert-manager 协作扩展规划 (../plans/2026-03-27-cert-manager-addon-plugin-plan.md)](../plans/2026-03-27-cert-manager-addon-plugin-plan.md)

---

## 推荐阅读顺序

### 新手上手 (15分钟)

1. 先读 README.zh-CN（了解整体）
2. 再看快速指南（跟着例子做）
3. 跳转三层快速指南，完成 CLI/Agent/Service 闭环
4. 可选：对照 Cookbook 场景 1 加深理解

### 想做生产部署 (30分钟)

1. 快速指南 + 三层场景手册（选2-3个）
2. 三层运维手册（参数与边界）
3. DNS Provider 配置文档
4. 若涉及K8s，查看场景5和k8s-service-design.md

### 排查问题

→ 直接跳到 Cookbook 最后的"故障排查指南"

---

## 文件位置说明

```text
docs/
├── zh-CN/                          # 中文文档（含README导航）
│   ├── README.md                   # ← 你在这里
│   ├── quickguide-docker-compose.md
│   ├── cookbook-compose.md
│   ├── quickguide-layered.md
│   ├── cookbook-layered.md
│   ├── manual-layered.md
│   └── dns-providers.md
├── en/                             # 英文文档
│   ├── README.md
│   ├── quickguide-docker-compose.md
│   ├── cookbook-compose.md
│   ├── quickguide-layered.md
│   ├── cookbook-layered.md
│   ├── manual-layered.md
│   └── dns-providers.md
├── dns-providers.md                # 共用（所有语言都参考）
├── k8s-service-design.md           # 共用
└── notes/, plans/                  # 内部备忘
```

---

## 快速链接

- 🔗 [主仓库 README](../../README.md) (English)
- 🔗 [中文 README](../../README.zh-CN.md) (中文)
- 🔗 [快速开始](quickguide-docker-compose.md)
- 🔗 [生产场景](cookbook-compose.md)
- 🔗 [三层快速指南](quickguide-layered.md)
- 🔗 [三层场景手册](cookbook-layered.md)
- 🔗 [三层运维手册](manual-layered.md)
- 🔗 [API 与 AI 接入](api-access.md)
- 🔗 [CLI 帮助参考](cli-help-reference.md)
- 🔗 [双 CLI 模式说明](dual-cli-modes.md)
