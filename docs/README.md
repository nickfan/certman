# Documentation Hub

**[English](en/) | [中文](zh-CN/)**

Welcome to certman documentation! Choose your language:

## 📚 Available Documentation

### 🇬🇧 English Documentation
- **[Documentation Guide](en/)** - Complete navigation and guides
  - [Quick Start Guide](en/quickguide-docker-compose.md)
  - [Production Cookbook](en/cookbook-compose.md)
  - [DNS Provider Setup](en/dns-providers.md)

### 🇨🇳 中文文档
- **[文档导航](zh-CN/)** - 完整导航和所有指南
  - [快速指南](zh-CN/quickguide-docker-compose.md)
  - [场景手册](zh-CN/cookbook-compose.md)
  - [DNS Provider 配置](zh-CN/dns-providers.md)

---

## 📋 Shared Documentation

These documents are used by all language versions:

- **DNS Providers**: [dns-providers.md](dns-providers.md) - Setup for Route53, Cloudflare, and Aliyun
- **Kubernetes Deployment**: [k8s-service-design.md](k8s-service-design.md) - K8s integration guide

---

## 🚀 Quick Navigation

### For English Users
1. Start with [English Quick Guide](en/quickguide-docker-compose.md)
2. Explore [Production Scenarios](en/cookbook-compose.md)
3. Setup your DNS provider using [DNS Providers Guide](en/dns-providers.md)

### 对于中文用户
1. 从 [中文快速指南](zh-CN/quickguide-docker-compose.md) 开始
2. 查看 [生产场景手册](zh-CN/cookbook-compose.md)
3. 按照 [DNS Provider 配置](zh-CN/dns-providers.md) 设置域名解析

---

## 📁 Directory Structure

```
docs/
├── README.md                       # ← You are here
├── dns-providers.md                # Shared (all languages)
├── k8s-service-design.md           # Shared (all languages)
│
├── en/
│   ├── README.md                   # English navigation
│   ├── quickguide-docker-compose.md
│   ├── cookbook-compose.md
│   ├── dns-providers.md            # Link to parent
│   └── ...
│
└── zh-CN/
    ├── README.md                   # 中文导航
    ├── quickguide-docker-compose.md
    ├── cookbook-compose.md
    ├── dns-providers.md            # Link to parent
    └── ...
```

---

## ❓ Help & Support

- **Having trouble?** → Check [Troubleshooting Guide](zh-CN/cookbook-compose.md#故障排查指南) (中文) or [English equivalent](en/cookbook-compose.md#troubleshooting-guide)
- **DNS issues?** → See [DNS Provider Setup](dns-providers.md)
- **K8s deployment?** → Read [K8s Design Guide](k8s-service-design.md)

---

**Last Updated**: 2026-03-26
