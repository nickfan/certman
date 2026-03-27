# Documentation Hub

**[English](en/) | [中文](zh-CN/)**

Welcome to certman documentation! Choose your language:

## 📚 Available Documentation

### 🇬🇧 English Documentation

- **[Documentation Guide](en/)** - Complete navigation and guides
  - [Quick Start Guide](en/quickguide-docker-compose.md)
  - [Production Cookbook](en/cookbook-compose.md)
  - [Layered Quick Guide (CLI/Agent/Service)](en/quickguide-layered.md)
  - [Layered Cookbook (CLI/Agent/Service)](en/cookbook-layered.md)
  - [Layered Manual (CLI/Agent/Service)](en/manual-layered.md)
  - [API & AI Access](en/api-access.md)
  - [CLI Help Reference](en/cli-help-reference.md)
  - [DNS Provider Setup](en/dns-providers.md)
  - [Dual CLI Modes (Local + Control Plane Client)](en/dual-cli-modes.md)

### 🇨🇳 中文文档

- **[文档导航](zh-CN/)** - 完整导航和所有指南
  - [快速指南](zh-CN/quickguide-docker-compose.md)
  - [场景手册](zh-CN/cookbook-compose.md)
  - [三层快速指南（CLI/Agent/Service）](zh-CN/quickguide-layered.md)
  - [三层场景手册（CLI/Agent/Service）](zh-CN/cookbook-layered.md)
  - [三层运维手册（CLI/Agent/Service）](zh-CN/manual-layered.md)
  - [API 与 AI 接入](zh-CN/api-access.md)
  - [CLI 帮助参考](zh-CN/cli-help-reference.md)
  - [DNS Provider 配置](zh-CN/dns-providers.md)
  - [双 CLI 模式（Local + Control Plane Client）](zh-CN/dual-cli-modes.md)

---

## 📋 Shared Documentation

These documents are used by all language versions:

- **DNS Providers**: [dns-providers.md](dns-providers.md) - Setup for Route53, Cloudflare, and Aliyun
- **Kubernetes Deployment**: [k8s-service-design.md](k8s-service-design.md) - K8s integration guide
- **Dual CLI Program**: [notes/plans/2026-03-26-dual-cli-program.md](notes/plans/2026-03-26-dual-cli-program.md) - Requirement, architecture, and implementation plan
- **cert-manager 协作扩展规划**: [plans/2026-03-27-cert-manager-addon-plugin-plan.md](plans/2026-03-27-cert-manager-addon-plugin-plan.md) - Addon/Plugin/Extension planning registry (this phase is design-only)
- **cert-manager 协作模式图解**: [certman-cert-manager-collaboration-modes.md](certman-cert-manager-collaboration-modes.md) - 业务流程图与时序图（模式A/B/C/D）
- **本地实施与验证手册**: [plans/2026-03-27-cert-manager-local-implementation.md](plans/2026-03-27-cert-manager-local-implementation.md) - kind + cert-manager + CertMan 实施步骤
- **独立调度架构**: [k8s-service-design.md](k8s-service-design.md) - §16 说明 scheduler 与 API/worker 解耦策略
- **本地配置管理命令**: [plans/2026-03-27-cert-manager-local-implementation.md](plans/2026-03-27-cert-manager-local-implementation.md) - §10 包含 config/env 命令与三环境运行方式

---

## 🚀 Quick Navigation

### For English Users

1. Start with [English Quick Guide](en/quickguide-docker-compose.md)
2. Use [Layered Quick Guide](en/quickguide-layered.md) for CLI/Agent/Service startup
3. Explore [Layered Cookbook](en/cookbook-layered.md) and [Layered Manual](en/manual-layered.md)
4. Setup your DNS provider using [DNS Providers Guide](en/dns-providers.md)

### 对于中文用户

1. 从 [中文快速指南](zh-CN/quickguide-docker-compose.md) 开始
2. 用 [三层快速指南](zh-CN/quickguide-layered.md) 跑通 CLI/Agent/Service
3. 查看 [三层场景手册](zh-CN/cookbook-layered.md) 与 [三层运维手册](zh-CN/manual-layered.md)
4. 按照 [DNS Provider 配置](zh-CN/dns-providers.md) 设置域名解析

---

## 📁 Directory Structure

```text
docs/
├── README.md                       # ← You are here
├── dns-providers.md                # Shared (all languages)
├── k8s-service-design.md           # Shared (all languages)
│
├── en/
│   ├── README.md                   # English navigation
│   ├── quickguide-docker-compose.md
│   ├── cookbook-compose.md
│   ├── quickguide-layered.md
│   ├── cookbook-layered.md
│   ├── manual-layered.md
│   ├── dns-providers.md            # Link to parent
│   └── ...
│
└── zh-CN/
    ├── README.md                   # 中文导航
    ├── quickguide-docker-compose.md
    ├── cookbook-compose.md
    ├── quickguide-layered.md
    ├── cookbook-layered.md
    ├── manual-layered.md
    ├── dns-providers.md            # Link to parent
    └── ...
```

---

## ❓ Help & Support

- **Having trouble?** → Check [Troubleshooting Guide](zh-CN/cookbook-compose.md#故障排查指南) (中文) or [English equivalent](en/cookbook-compose.md#troubleshooting-guide)
- **DNS issues?** → See [DNS Provider Setup](dns-providers.md)
- **K8s deployment?** → Read [K8s Design Guide](k8s-service-design.md)

---

**Last Updated**: 2026-03-27
