# certman

**[中文版本 (中文)/Chinese Version](README.zh-CN.md) | English**

SSL certificate management CLI (certbot + DNS plugins).

## Runtime Modes

CertMan now exposes four runtime surfaces built on the same config and service layer:

- `certman`: local operator CLI for `new`, `renew`, `check`, `export`
- `certman-server`: FastAPI control plane for `/health`, job submission, job query, webhook subscription
- `certman-worker`: background job runner for queued `issue` and `renew` jobs
- `certman-agent`: node-side polling agent scaffold for controlled execution mode

Typical local commands:

```bash
uv run certman --help
uv run certman-server --data-dir data --config-file config.toml
uv run certman-worker --data-dir data --config-file config.toml --once
uv run certman-agent --data-dir data --config-file config.toml --once
```

## Runtime Dependency Matrix

- `certman` (CLI local mode): no dependency on Kubernetes or Docker; can run directly via Python/uv.
- `certman-server` + `certman-worker`: no dependency on Kubernetes or Docker; Docker is optional for packaging/deploy.
- `certman-agent`: no hard dependency on Kubernetes or Docker, but requires reachable control-plane endpoint.
- `scripts/certman-docker.ps1` / `scripts/certman-docker.sh`: requires Docker engine because they are docker wrappers.

Direct run examples (no k8s/docker required):

```bash
uv run certman --data-dir data entries
uv run certman --data-dir data check --warn-days 30 --force-renew-days 7
```

```powershell
uv run certman --data-dir data entries
uv run certman --data-dir data check --warn-days 30 --force-renew-days 7
```

## Data layout

Default `--data-dir` is `data/` (configurable).

- `data/conf/`: ops-facing config
  - `config.example.toml`: global config template (tracked)
  - `config.toml`: global config (local, ignored)
  - `item_example.example.toml`: entry template (tracked)
  - `item_*.toml`: entry item configs (local, ignored)
  - `.env`: optional secrets (ignored)
  - `.env.example`: secrets template (tracked)
- `data/run/`: runtime data (ignored)
  - `letsencrypt/`: certbot state (recommended)
- `data/log/`: execution logs (ignored), default keep 30 days
- `data/output/`: user-facing exported artifacts (ignored)

## Docker Image

Docker Hub: `nickfan/certman`

GitHub Container Registry (GHCR): `ghcr.io/nickfan/certman`

- `edge`: built from `master`
- `latest` + `X.Y.Z`: built from git tags like `vX.Y.Z`

If GHCR images are not pullable (403) even though workflow succeeded:

- Go to GitHub repo **Packages** `certman` **Package settings** set **Visibility** to **Public**.

## Docker Compose Quick Flow

The repository includes a compose service in [docker-compose.yml](docker-compose.yml):

```yaml
services:
  certman:
    build: .
    entrypoint: ["uv", "run", "certman", "--data-dir", "/data"]
    volumes:
      - ./data:/data
  certman-server:
    build: .
    entrypoint: ["uv", "run", "certman-server", "--data-dir", "/data", "--config-file", "config.compose-server.toml"]
    volumes:
      - ./data:/data
    ports:
      - "8000:8000"
  certman-worker:
    build: .
    entrypoint: ["uv", "run", "certman-worker", "--data-dir", "/data", "--config-file", "config.compose-server.toml", "--loop", "--interval-seconds", "30"]
    volumes:
      - ./data:/data
```

Common compose commands (configuration-driven):

```bash
# 1) validate one or more explicit entries (recommended default)
docker compose run --rm certman config-validate --name <entry-name>

# 1.1) validate all merged entries explicitly
docker compose run --rm certman config-validate --all

# 2) list merged entries
docker compose run --rm certman entries

# 3) issue certificate for one entry
docker compose run --rm certman new --name <entry-name>

# 4) renew one entry or all entries
docker compose run --rm certman renew --name <entry-name>
docker compose run --rm certman renew --all

# 5) export certificate files for one entry or all entries
docker compose run --rm certman export --name <entry-name>
docker compose run --rm certman export --all

# 6) start control plane and worker
docker compose up certman-server certman-worker
```

Optional scripted e2e validation (compose/k8s):

```bash
python scripts/e2e-test.py --compose-only
python scripts/e2e-test.py --k8s-only
```

Server API quick checks:

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/api/v1/certificates \
  -H 'content-type: application/json' \
  -d '{"entry_name":"site-a"}'
curl -X POST http://127.0.0.1:8000/api/v1/webhooks \
  -H 'content-type: application/json' \
  -d '{"topic":"job.completed","endpoint":"https://example.test/hook","secret":"topsecret"}'
```

If `[server].token_auth_enabled = true`, add `Authorization: Bearer <token>` for protected REST endpoints.

Control-plane API documentation endpoints:

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/redoc
http://127.0.0.1:8000/openapi.json
```

Remote operator examples via `certmanctl`:

```bash
uv run certmanctl --endpoint http://127.0.0.1:8000 health
uv run certmanctl --endpoint http://127.0.0.1:8000 cert create --entry-name site-a
uv run certmanctl --endpoint http://127.0.0.1:8000 job list --subject-id site-a
uv run certmanctl --endpoint http://127.0.0.1:8000 webhook list
```

More detailed docs:

- [📖 Documentation Guide (English)](docs/en/) - Full navigation and all guides
- Quick guide: [docs/en/quickguide-docker-compose.md](docs/en/quickguide-docker-compose.md)
- Cookbook: [docs/en/cookbook-compose.md](docs/en/cookbook-compose.md)
- Layered quick guide: [docs/en/quickguide-layered.md](docs/en/quickguide-layered.md)
- Layered cookbook: [docs/en/cookbook-layered.md](docs/en/cookbook-layered.md)
- Layered manual: [docs/en/manual-layered.md](docs/en/manual-layered.md)
- API & AI access: [docs/en/api-access.md](docs/en/api-access.md)
- DNS Providers: [docs/en/dns-providers.md](docs/en/dns-providers.md)
- 📖 [中文文档导航 (Chinese Guide)](docs/zh-CN/) - 完整导航和所有指南

Run (example):

```sh
docker run --rm \
  -v "$(pwd)/data:/data" \
  -e CERTMAN_DATA_DIR=/data \
  nickfan/certman:edge --help
```

Common command examples:

```bash
docker run --rm \
  -v "$(pwd)/data:/data" \
  -e CERTMAN_DATA_DIR=/data \
  nickfan/certman:edge check --warn-days 30 --force-renew-days 7
```

```powershell
docker run --rm `
  -v "${PWD}/data:/data" `
  -e CERTMAN_DATA_DIR=/data `
  nickfan/certman:edge check --warn-days 30 --force-renew-days 7
```

## Script wrappers (Windows/Linux)

To avoid repeatedly typing mount/env/image options, use wrapper scripts and keep certman subcommand arguments outside.

- Linux/macOS (bash): `scripts/certman-docker.sh`
- Windows (PowerShell): `scripts/certman-docker.ps1`

Examples (arguments stay external):

```bash
bash scripts/certman-docker.sh check --warn-days 30 --force-renew-days 7
bash scripts/certman-docker.sh renew --all
```

```powershell
.\scripts\certman-docker.ps1 check --warn-days 30 --force-renew-days 7
.\scripts\certman-docker.ps1 renew --all
```

Optional environment overrides for wrapper scripts:

- `CERTMAN_IMAGE`: override image tag (default: `nickfan/certman:edge`)
- `CERTMAN_DATA_DIR_HOST`: override host data dir mounted to `/data` (default: `<project>/data`)

## Image Build/Push Scripts

Use release scripts when you need a consistent local build + publish flow for both Docker Hub and GHCR.

- PowerShell: `scripts/docker-image-release.ps1`
- Shell: `scripts/docker-image-release.sh`

Examples:

```powershell
./scripts/docker-image-release.ps1 -Tag edge
./scripts/docker-image-release.ps1 -Tag edge -Push
```

```bash
bash scripts/docker-image-release.sh --tag edge
bash scripts/docker-image-release.sh --tag edge --push
```

Notes:

- Ensure `docker login` is done for both Docker Hub and GHCR before `-Push`/`--push`.
- Default tags are published to both `nickfan/certman:<tag>` and `ghcr.io/nickfan/certman:<tag>`.

## Quickstart (Windows)

On Windows, `certbot` may require an elevated shell.

- Recommended (most reliable): `gsudo uv run certman new -n <name>`
- Alternative: run the terminal as Administrator

To see certbot progress in the terminal, add `-v/--verbose`.

For server mode, keep one terminal for `certman-server` and another for `certman-worker --loop`.

Credentials priority (all providers):

- If an entry has provider-specific `credentials.*` fields, certman uses them directly (supports `${ENV_VAR}` references).
- Otherwise, if an entry has `account_id`, certman reads provider-specific environment variables from `data/conf/.env` or the process environment.
  - account_id is normalized for env lookup: trim, uppercase, and replace `-` with `_`.
  - Aliyun: `CERTMAN_ALIYUN_<account_id>_ACCESS_KEY_ID` and `CERTMAN_ALIYUN_<account_id>_ACCESS_KEY_SECRET`
  - Cloudflare: `CERTMAN_CLOUDFLARE_<account_id>_API_TOKEN`
  - Route53: `CERTMAN_AWS_<account_id>_ACCESS_KEY_ID`, `CERTMAN_AWS_<account_id>_SECRET_ACCESS_KEY`, `CERTMAN_AWS_<account_id>_REGION`
- Certbot is always invoked with a runtime credential/config file under `data/run/credentials/`. certman refreshes it before `new` and `renew`.

## DNS Providers

Currently supported DNS providers:

- Aliyun DNS
- Cloudflare DNS
- AWS Route53

Installed certbot DNS plugins are managed by `uv` through [pyproject.toml](pyproject.toml).

Provider-specific setup examples, `.env` naming conventions, and command examples are documented in [docs/dns-providers.md](docs/dns-providers.md).

## Cron usage (recommended)

Default config behavior:

- Global config defaults to `data/conf/config.toml`
- It scans `data/conf/item_*.toml` (configurable via `scan_items_glob`) and merges them into entries
- `.env` is optional; entries can either reference `account_id` (ops mode) or embed credentials directly (portable mode)

Only check and return exit code (no auto-renew by default):

```sh
# warn when <=30d, fail when <=7d or expired
uv run python -m certman.cli --data-dir data --config-file your.toml check --warn-days 30 --force-renew-days 7

# optional: check and auto-fix (runs new/renew + export)
uv run python -m certman.cli --data-dir data --config-file your.toml check --warn-days 30 --force-renew-days 7 --fix
```

Recommended flow:

- Scheduled `check` (cron) to alert / decide action.
- Scheduled `renew` or manual `new --force` when needed.
- `new`/`renew` default自动 `export` 到 `data/output/<entry_name>/`（可用 `--no-export` 关闭）。
- Run `export` anytime to sync cert/key to `data/output/<entry_name>/`.

## Control Plane Notes

- `run_mode = "server"` requires a `[server]` block with `db_path`, `listen_host`, and `listen_port`.
- Optional REST auth switch: `[server].token_auth_enabled` (default `false`).
- Token precedence for certificate/job APIs when auth is enabled: `entries[].token` > `global.token`.
- If auth is enabled but no effective token exists for the current target, API returns `500 AUTH_TOKEN_CONFIG_ERROR`.
- If auth is enabled and token is required: missing token returns `401 AUTH_MISSING_TOKEN`, wrong token returns `401 AUTH_INVALID_TOKEN`.
- Webhook subscriptions are stored in the control-plane database and receive signed HTTP POST callbacks.
- `certman-worker` processes queued jobs from the same SQLite database used by `certman-server`.
- `certman-agent` remains the controlled-node entrypoint; Phase 4 security primitives are now available for its next control-plane integration step.
- The current AI integration surface includes REST + OpenAPI and a stdio MCP server (`certman-mcp`) that wraps control-plane APIs.

## Certificate file formats

- Certbot outputs PEM files by default: `cert.pem`, `chain.pem`, `fullchain.pem`, `privkey.pem`.
- `*.pem`, `*.crt`, `*.cer` are often the same *PEM-encoded* data with different extensions.
  - `crt/cer` can also be DER (binary) in some ecosystems, but certbot's files here are PEM text.
- Nginx commonly uses PEM content regardless of extension:
  - `ssl_certificate` usually points to a full chain PEM (e.g. `fullchain.pem`)
  - `ssl_certificate_key` points to `privkey.pem`

If you need specific extensions for tooling, it is typically safe to copy/rename PEM files, as long as the consuming tool expects PEM (text) not DER (binary).

## Exit codes for `check`

- `0`: OK
- `10`: warning (<= warn_days)
- `20`: force-renew needed (<= force_renew_days or expired)
- `30`: missing cert files / entry missing
