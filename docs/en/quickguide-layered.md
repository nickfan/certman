# Layered Quick Guide (CLI / Agent / Service)

This guide gets the full three-layer certman flow running in about 15 minutes:

- CLI layer: direct issue, renew, check, and export
- Service layer: control plane API + worker queue execution
- Agent layer: signed node polling and result reporting

## 0. Prerequisites

1. Install dependencies and prepare data files

```bash
uv sync
cp data/conf/config.example.toml data/conf/config.toml
cp data/conf/item_example.example.toml data/conf/item_site_a.toml
```

2. Edit data/conf/config.toml (minimum)

```toml
run_mode = "local"

[global]
data_dir = "data"
acme_server = "staging"
email = "ops@example.com"
```

3. Edit data/conf/item_site_a.toml (minimum entry)

```toml
name = "site-a"
primary_domain = "example.com"
secondary_domains = ["www.example.com"]
wildcard = true
dns_provider = "route53"
account_id = "MAIN"
```

4. Put provider credentials into data/conf/.env

```dotenv
CERTMAN_AWS_MAIN_ACCESS_KEY_ID=AKIA...
CERTMAN_AWS_MAIN_SECRET_ACCESS_KEY=...
CERTMAN_AWS_MAIN_REGION=us-east-1
```

## 1. CLI Layer Quick Start

```bash
uv run certman -D data config-validate
uv run certman -D data new --name site-a --verbose
uv run certman -D data check --warn-days 30 --force-renew-days 7
uv run certman -D data export --name site-a
```

Expected outcome: fullchain.pem and privkey.pem under data/output/site-a/.

## 2. Service Layer Quick Start

1. Switch config to server mode

```toml
run_mode = "server"

[server]
db_path = "data/run/certman.db"
listen_host = "127.0.0.1"
listen_port = 8000
signing_key_path = "data/run/keys/server_ed25519.pem"
```

2. Start server and worker

```bash
uv run certman-server -D data
uv run certman-worker -D data --loop --interval-seconds 30
```

3. Open live API docs

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/redoc
http://127.0.0.1:8000/openapi.json
```

4. Submit and query jobs

```bash
curl -X POST http://127.0.0.1:8000/api/v1/certificates \
  -H "content-type: application/json" \
  -d '{"entry_name":"site-a"}'

curl http://127.0.0.1:8000/api/v1/jobs/<job_id>
```

5. Repeat the same flow with the remote CLI

```bash
uv run certmanctl --endpoint http://127.0.0.1:8000 health
uv run certmanctl --endpoint http://127.0.0.1:8000 cert create --entry-name site-a
uv run certmanctl --endpoint http://127.0.0.1:8000 job list --subject-id site-a
```

## 3. Agent Layer Quick Start

1. Configure agent mode

```toml
run_mode = "agent"

[control_plane]
endpoint = "http://127.0.0.1:8000"
poll_interval_seconds = 30

[node_identity]
node_id = "node-a"
private_key_path = "data/run/keys/node-a.pem"
public_key_path = "data/run/keys/node-a.pub"
```

2. Pre-register node-a as active in control plane DB.

3. Run one poll cycle

```bash
uv run certman-agent -D data --once
```

Sample output:

```text
node_id=node-a poll_count=1
```

## 4. One-Page Troubleshooting

- config-validate fails: check .env variable naming against account_id.
- Windows certbot permission issues: use elevated shell, Docker, or WSL.
- jobs stuck in queued: verify worker is running and shares same db_path.
- agent 401: verify node active status, public key match, and time skew.
- agent 409 replay: duplicated nonce was rejected by design.
