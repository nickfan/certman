# Docker Compose Quick Guide

**Translation in Progress** | [中文版本 (View Chinese)](../zh-CN/quickguide-docker-compose.md)

This guide is currently being translated from Chinese. For now, please refer to the **[Chinese version](../zh-CN/quickguide-docker-compose.md)** which contains complete working examples.

## Overview (English)

This quick guide demonstrates how to use certman with Docker Compose to:
- Configure certificate settings via TOML files
- Request SSL certificates for domains
- Set up automatic renewal and monitoring
- Export certificates for web servers

## Example Scenario

**Background**: Alice has a domain `mydemo1.com` hosted on AWS Route53 with AWS credentials (Access Key and Secret Key). She needs to request, renew, and export SSL certificates.

This guide walks through:
1. Prerequisites and setup
2. Configuration file creation
3. Certificate validation and issuance
4. Renewal and export procedures
5. Periodic monitoring (recommended for automation)
6. Directory structure and outputs

## Quick Commands

```bash
# Validate configuration
docker compose run --rm certman config-validate

# Request a certificate
docker compose run --rm certman new --name mydemo1

# Renew certificates
docker compose run --rm certman renew --all

# Export certificates
docker compose run --rm certman export --all

# Check certificate status
docker compose run --rm certman check --warn-days 30 --force-renew-days 7
```

## Links

- [中文完整指南](../zh-CN/quickguide-docker-compose.md) - Full Chinese version with complete examples and explanations
- [DNS Provider Setup](dns-providers.md)
- [Production Cookbook](cookbook-compose.md)

---

**Status**: 🔄 English translation in progress  
**ETA**: Coming soon  
**Meanwhile**: Check the [中文版本](../zh-CN/quickguide-docker-compose.md) for complete details
