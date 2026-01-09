# certman

SSL certificate management CLI (certbot + DNS plugins).

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

Run (example):

```sh
docker run --rm \
  -v "$(pwd)/data:/data" \
  -e CERTMAN_DATA_DIR=/data \
  nickfan/certman:edge --help
```

## Quickstart (Windows)

On Windows, `certbot` may require an elevated shell.

- Recommended (most reliable): `gsudo uv run certman new -n <name>`
- Alternative: run the terminal as Administrator

To see certbot progress in the terminal, add `-v/--verbose`.

Credentials priority (Aliyun):
- If an entry has `credentials.access_key_id` + `credentials.access_key_secret`, certman uses them (supports `${ENV_VAR}` references).
- Otherwise, if an entry has `account_id`, certman reads `CERTMAN_ALIYUN_<account_id>_ACCESS_KEY_ID` and `..._ACCESS_KEY_SECRET` from environment (optionally loaded via `data/conf/.env`).
- Certbot is always invoked with an INI file under `data/run/credentials/` (runtime artifact). certman refreshes it before `new` and `renew`.

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
