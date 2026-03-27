# Docker Compose Quick Guide

This guide provides a runnable end-to-end workflow with current config schema and command behavior.

Reference Chinese version: [../zh-CN/quickguide-docker-compose.md](../zh-CN/quickguide-docker-compose.md)

## Scenario

Alice owns `mydemo1.com` on AWS Route53 and wants to issue, renew, and export certificates with certman.

## 1. Prerequisites

1. Docker and Docker Compose are available.
2. You are at project root (where `docker-compose.yml` exists).
3. Route53 credentials are ready.

## 2. Prepare Config Files

Create `data/conf/config.toml`:

```toml
run_mode = "local"

[global]
email = "alice@mydemo1.com"
acme_server = "staging"
scan_items_glob = "item_*.toml"
```

Create `data/conf/item_mydemo1.toml`:

```toml
description = "mydemo1.com via route53"
primary_domain = "mydemo1.com"
secondary_domains = ["www.mydemo1.com"]
dns_provider = "route53"
account_id = "demo_route53"
```

Create `data/conf/.env`:

```bash
CERTMAN_AWS_DEMO_ROUTE53_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
CERTMAN_AWS_DEMO_ROUTE53_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
CERTMAN_AWS_DEMO_ROUTE53_REGION=us-east-1
```

Note: `account_id = "demo_route53"` is normalized to `DEMO_ROUTE53` for env lookup.

## 3. Validate Configuration

```bash
# recommended: validate one target entry
docker compose run --rm certman config-validate --name mydemo1

# explicit full merged-entry validation
docker compose run --rm certman config-validate --all
```

List merged entries:

```bash
docker compose run --rm certman entries
```

## 4. Issue Certificate

```bash
docker compose run --rm certman new --name mydemo1
```

Expected output artifacts:

1. `data/output/mydemo1/fullchain.pem`
2. `data/output/mydemo1/privkey.pem`
3. `data/output/mydemo1/cert.pem`

## 5. Renew and Export

```bash
# renew one entry
docker compose run --rm certman renew --name mydemo1

# renew all entries
docker compose run --rm certman renew --all

# export one entry
docker compose run --rm certman export --name mydemo1

# export all entries
docker compose run --rm certman export --all
```

## 6. Routine Health Check

```bash
# inspect only
docker compose run --rm certman check --warn-days 30 --force-renew-days 7

# inspect and auto-fix
docker compose run --rm certman check --warn-days 30 --force-renew-days 7 --fix
```

Exit codes:

1. `0`: healthy
2. `10`: warning
3. `20`: force-renew threshold reached
4. `30`: missing certificate or entry failure

## 7. Pure-Parameter One-Shot Mode (No Config)

For AI/automation integration, you can run one-shot issue/renew in blocking mode without `config.toml` or `item_*.toml`.

```bash
# one-shot issue
uv run certman --data-dir data oneshot-issue \
  -d mydemo1.com -d *.mydemo1.com \
  -sp route53 \
  --email alice@mydemo1.com \
  --ak <aws-ak> --sk <aws-sk> \
  --aws-region us-east-1 \
  -o /tmp/mydemo1

# one-shot renew
uv run certman --data-dir data oneshot-renew \
  -d mydemo1.com -d *.mydemo1.com \
  -sp route53 \
  --email alice@mydemo1.com \
  --ak <aws-ak> --sk <aws-sk> \
  --aws-region us-east-1 \
  -o /tmp/mydemo1
```

## 8. Independent Scheduler (Loop / Once / CronJob)

Scheduler is a standalone process and does not run inside API server process.

```bash
# long-running scheduler
docker compose up certman-server certman-worker certman-scheduler

# one-shot scheduler trigger (for external cron)
docker compose run --rm certman-scheduler once --force-enable
```

Kubernetes CronJob alternative manifest:

1. `k8s/certman-scheduler-cronjob.yaml`
2. apply with `kubectl apply -f k8s/certman-scheduler-cronjob.yaml`

## Links

1. [Production Cookbook](cookbook-compose.md)
2. [DNS Provider Setup](dns-providers.md)
3. [API & AI Access](api-access.md)
4. [cert-manager Local Implementation Handbook](../plans/2026-03-27-cert-manager-local-implementation.md)
