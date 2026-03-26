# Docker Compose Cookbook - Production Scenarios

**Translation in Progress** | [中文版本 (View Chinese)](../zh-CN/cookbook-compose.md)

This cookbook is currently being translated from Chinese. For complete production scenarios and examples, please refer to the **[Chinese version](../zh-CN/cookbook-compose.md)**.

## Overview (English)

This handbook covers 7 real-world production scenarios:

### Scenario 1: Adding a New API Domain
Requesting and configuring SSL certificates for a new service domain on Route53.

### Scenario 2: Daily Monitoring Alerts
Setting up monitoring without automatic remediation - useful for auditing and manual approval workflows.

### Scenario 3: Full Automation
Implementing complete hands-off certificate renewal with Cron jobs or Kubernetes CronJobs.

### Scenario 4: Multi-Provider Management
Managing domains across different DNS providers (Route53, Cloudflare, Aliyun) in a single instance.

### Scenario 5: Kubernetes Integration
Exporting certificates and updating Kubernetes Ingress TLS secrets automatically.

### Scenario 6: Docker Hub Images
Using pre-built Docker Hub images instead of local builds.

### Scenario 7: Windows Automation
Setting up Windows Task Scheduler for automatic certificate renewal on Windows Server.

### Bonus: Complete Troubleshooting Guide
6 common issues with diagnostic steps and solutions.

## Links

- [中文完整手册](../zh-CN/cookbook-compose.md) - Full Chinese version with all 7 scenarios + troubleshooting
- [Quick Guide](quickguide-docker-compose.md)
- [DNS Provider Configuration](dns-providers.md)
- [Kubernetes Deployment Guide](../k8s-service-design.md)

## Quick Reference

### Common Commands

```bash
# Check all certificates
docker compose run --rm certman check --warn-days 30 --force-renew-days 7

# Renew certificates
docker compose run --rm certman renew --all

# Export certificates
docker compose run --rm certman export --all

# Export with auto-fix
docker compose run --rm certman check --warn-days 30 --force-renew-days 7 --fix
```

### Exit Codes
- `0`: OK
- `10`: Warning (expires within 30 days)
- `20`: Renewal needed
- `30`: Certificate missing

---

**Status**: 🔄 English translation in progress  
**ETA**: Coming soon  
**Meanwhile**: Refer to [中文版本](../zh-CN/cookbook-compose.md) for complete details with all scenarios and troubleshooting
