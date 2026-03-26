# 中文文档 Guide (中文)

**[← 返回主文档](../../README.zh-CN.md) | [English Guide](../en/README.md)**

## 文档导航

### 🚀 快速开始

- **[快速指南 (quickguide-docker-compose.md)](quickguide-docker-compose.md)** - 5分钟上手，用明确的例子展示完整工作流
  - 适合第一次使用，以 AWS Route53 + mydemo1.com 为例
  - 覆盖配置、申请、续签、导出、检查全流程

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

### ⚡ DNS Provider 文档

- **[DNS Providers 配置 (../dns-providers.md)](../dns-providers.md)** - 三个Provider的详细配置和凭据管理
  - AWS Route53
  - Cloudflare
  - Aliyun DNS

### 📋 其他文档

- [Kubernetes 部署设计 (../k8s-service-design.md)](../k8s-service-design.md)

---

## 推荐阅读顺序

**新手上手 (15分钟)**
1. 先读 README.zh-CN（了解整体）
2. 再看快速指南（跟着例子做）
3. 可选：对照Cookbook场景1加深理解

**想做生产部署 (30分钟)**
1. 快速指南 + Cookbook 的相关场景（选2-3个）
2. DNS Provider 配置文档
3. 若涉及K8s，查看场景5和k8s-service-design.md

**排查问题**
→ 直接跳到 Cookbook 最后的"故障排查指南"

---

## 文件位置说明

```
docs/
├── zh-CN/                          # 中文文档（含README导航）
│   ├── README.md                   # ← 你在这里
│   ├── quickguide-docker-compose.md
│   └── cookbook-compose.md
├── en/                             # 英文文档
│   ├── README.md
│   ├── quickguide-docker-compose.md
│   └── cookbook-compose.md
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

