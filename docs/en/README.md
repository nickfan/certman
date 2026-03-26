# English Documentation Guide

**[← Back to Main Docs](../../README.md) | [中文指南](../zh-CN/README.md)**

## Documentation Index

### 🚀 Quick Start

- **[Quick Guide (quickguide-docker-compose.md)](quickguide-docker-compose.md)** - Get started in 5 minutes with concrete examples
  - Best for first-time users
  - Complete workflow: config → issue → renew → export → check

### 📚 Production Handbook

- **[Cookbook (cookbook-compose.md)](cookbook-compose.md)** - 7 real-world production scenarios
  - Scenario 1: Adding a new domain (Route53)
  - Scenario 2: Daily monitoring alerts (check-only)
  - Scenario 3: Full automation (Cron/K8s)
  - Scenario 4: Multi-provider management
  - Scenario 5: Export to Kubernetes Secrets
  - Scenario 6: Using Docker Hub images
  - Scenario 7: Windows + Task Scheduler automation
  - Bonus: Complete troubleshooting guide

### ⚡ DNS Provider Documentation

- **[DNS Providers Configuration (../dns-providers.md)](../dns-providers.md)** - Setup guides for all supported providers
  - AWS Route53
  - Cloudflare
  - Aliyun DNS

### 📋 Additional Resources

- [Kubernetes Service Design (../k8s-service-design.md)](../k8s-service-design.md)
- Release notes & Version history

---

## Recommended Reading Path

**First-time users (15 minutes)**
1. Read main README (overview)
2. Follow Quick Guide with examples
3. Optional: Compare with Cookbook Scenario 1

**Production deployment (30 minutes)**
1. Quick Guide + relevant Cookbook scenarios (pick 2-3)
2. DNS Provider configuration
3. If using K8s: Scenario 5 + k8s-service-design.md

**Troubleshooting**
→ Jump to Cookbook "Troubleshooting Guide" section

---

## File Structure

```
docs/
├── zh-CN/                          # Chinese documentation
│   ├── README.md
│   ├── quickguide-docker-compose.md
│   └── cookbook-compose.md
├── en/                             # English documentation (← you are here)
│   ├── README.md
│   ├── quickguide-docker-compose.md
│   └── cookbook-compose.md
├── dns-providers.md                # Shared (referenced by all)
├── k8s-service-design.md           # Shared
└── notes/, plans/                  # Internal notes
```

---

## Quick Links

- 🔗 [Main README](../../README.md)
- 🔗 [Quick Start Guide](quickguide-docker-compose.md)
- 🔗 [Production Scenarios](cookbook-compose.md)
- 🔗 [Provider Setup](../dns-providers.md)

---

## Contributing

To add or translate documentation:
1. English docs go in `docs/en/`
2. Chinese docs go in `docs/zh-CN/`
3. Keep shared content (dns-providers.md, k8s-service-design.md) in `docs/`

