# English Documentation Guide

**[← Back to Main Docs](../../README.md) | [中文指南](../zh-CN/README.md)**

## Documentation Index

### 🚀 Quick Start

- **[Quick Guide (quickguide-docker-compose.md)](quickguide-docker-compose.md)** - Get started in 5 minutes with concrete examples
  - Best for first-time users
  - Complete workflow: config → issue → renew → export → check

- **[Layered Quick Guide (quickguide-layered.md)](quickguide-layered.md)** - 15-minute startup for CLI / Agent / Service
  - Includes minimum closed loop across local, control plane, and node agent
  - Best for teams migrating from local-only mode

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

- **[Layered Cookbook (cookbook-layered.md)](cookbook-layered.md)** - real scenarios organized by runtime layer
  - CLI: onboarding and daily checks
  - Service: orchestration, dedupe, and webhook delivery
  - Agent: signed polling, result reporting, replay defense

- **[Layered Manual (manual-layered.md)](manual-layered.md)** - parameter model and protocol contracts
  - config parameter impact map
  - API contracts, state machine, concurrency and security baseline

- **[API & AI Access (api-access.md)](api-access.md)** - OpenAPI endpoints, remote CLI usage, and current AI integration surface
  - `/docs`, `/redoc`, `/openapi.json`
  - `certmanctl` to REST mapping
  - MCP availability status

- **[CLI Help Reference (cli-help-reference.md)](cli-help-reference.md)** - Local/remote CLI options and `--help` discovery guide
  - `certman` command/options quick map
  - `certmanctl` command/options quick map
  - Skill preflight suggestions

### ⚡ DNS Provider Documentation

- **[DNS Providers Configuration (../dns-providers.md)](../dns-providers.md)** - Setup guides for all supported providers
  - AWS Route53
  - Cloudflare
  - Aliyun DNS

### 📋 Additional Resources

- [Kubernetes Service Design (../k8s-service-design.md)](../k8s-service-design.md)
- [Dual CLI Modes (dual-cli-modes.md)](dual-cli-modes.md)
- [Dual CLI Program Plan (../notes/plans/2026-03-26-dual-cli-program.md)](../notes/plans/2026-03-26-dual-cli-program.md)
- [cert-manager Addon/Plugin Plan (../plans/2026-03-27-cert-manager-addon-plugin-plan.md)](../plans/2026-03-27-cert-manager-addon-plugin-plan.md)
- [cert-manager Collaboration Modes (../certman-cert-manager-collaboration-modes.md)](../certman-cert-manager-collaboration-modes.md)
- [cert-manager Local Implementation Handbook (../plans/2026-03-27-cert-manager-local-implementation.md)](../plans/2026-03-27-cert-manager-local-implementation.md)
- [Independent Scheduler Architecture (../k8s-service-design.md)](../k8s-service-design.md)
- Release notes & Version history

---

## Recommended Reading Path

### First-time users (15 minutes)

1. Read main README (overview)
2. Follow Quick Guide with examples
3. Run Layered Quick Guide for full CLI/Agent/Service flow
4. Optional: Compare with Cookbook Scenario 1

### Production deployment (30 minutes)

1. Quick Guide + Layered Cookbook scenarios (pick 2-3)
2. Layered Manual for parameter and boundary controls
3. DNS Provider configuration
4. If using K8s: Scenario 5 + k8s-service-design.md

### Troubleshooting

→ Jump to Cookbook "Troubleshooting Guide" section

---

## File Structure

```text
docs/
├── zh-CN/                          # Chinese documentation
│   ├── README.md
│   ├── quickguide-docker-compose.md
│   ├── cookbook-compose.md
│   ├── quickguide-layered.md
│   ├── cookbook-layered.md
│   ├── manual-layered.md
│   └── dns-providers.md
├── en/                             # English documentation (← you are here)
│   ├── README.md
│   ├── quickguide-docker-compose.md
│   ├── cookbook-compose.md
│   ├── quickguide-layered.md
│   ├── cookbook-layered.md
│   ├── manual-layered.md
│   └── dns-providers.md
├── dns-providers.md                # Shared (referenced by all)
├── k8s-service-design.md           # Shared
└── notes/, plans/                  # Internal notes
```

---

## Quick Links

- 🔗 [Main README](../../README.md)
- 🔗 [Quick Start Guide](quickguide-docker-compose.md)
- 🔗 [Production Scenarios](cookbook-compose.md)
- 🔗 [Layered Quick Guide](quickguide-layered.md)
- 🔗 [Layered Cookbook](cookbook-layered.md)
- 🔗 [Layered Manual](manual-layered.md)
- 🔗 [API & AI Access](api-access.md)
- 🔗 [CLI Help Reference](cli-help-reference.md)
- 🔗 [Provider Setup](../dns-providers.md)
- 🔗 [Dual CLI Modes](dual-cli-modes.md)

---

## Contributing

To add or translate documentation:

1. English docs go in `docs/en/`
2. Chinese docs go in `docs/zh-CN/`
3. Keep shared content (dns-providers.md, k8s-service-design.md) in `docs/`
