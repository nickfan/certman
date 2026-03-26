# CLI Help Reference (Local + Control Plane)

This page is a quick reference for command discovery and parameter semantics.
It is designed for operators and for AI skill/tool builders.

## 1. Discover commands with --help

```bash
uv run certman --help
uv run certman new --help
uv run certman renew --help

uv run certmanctl --help
uv run certmanctl cert --help
uv run certmanctl job wait --help
uv run certmanctl webhook update --help
```

## 2. Local CLI (`certman`) parameters

Global options:

- `-D, --data-dir`: Base data directory (default: `data`)
- `-c, --config-file`: Config filename under `<data_dir>/conf`

Command options:

- `new`
  - `-n, --name`: Entry name from config
  - `-f, --force`: Re-issue even if cert exists
  - `--export/--no-export`: Export artifacts after success
  - `-v, --verbose`: Stream certbot output
- `renew`
  - `-a, --all`: Renew all entries
  - `-n, --name`: Renew one entry
  - `-f, --force`: Force renew even if not due
  - `--dry-run`: Staging renew validation
  - `--export/--no-export`: Export after success
  - `-v, --verbose`: Stream certbot output
- `export`
  - `-a, --all`: Export all entries
  - `-n, --name`: Export one entry
  - `--overwrite/--no-overwrite`: Overwrite output files
- `check`
  - `-w, --warn-days`: warning threshold days
  - `-F, --force-renew-days`: force-renew threshold days
  - `-n, --name`: Check one entry
  - `--fix`: Execute planned new/renew fixes
  - `--json`: Print JSON result
- `logs-clean`
  - `-k, --keep-days`: Keep latest N days logs
- `entries`
  - no command-specific options
- `config-validate`
  - `-n, --name`: validate only specified entry (repeatable)
  - `--all`: validate all merged entries
  - scope rule: must provide `--name` or `--all`; cannot combine both

## 3. Remote CLI (`certmanctl`) parameters

Global options:

- `--endpoint`: Control-plane endpoint (default: `http://127.0.0.1:8000`)
- `--timeout`: HTTP timeout seconds
- `--output`: `text` or `json`
- `--token`: Bearer token

Command options:

- `health`: no command-specific options
- `cert create|get|renew`
  - `-n, --entry-name`: server-side entry name
- `cert list`: no command-specific options
- `job get`
  - `--job-id`: job id
- `job list`
  - `--subject-id`: subject filter
  - `--status`: status filter
  - `--limit`: max rows (1-200)
- `job wait`
  - `--job-id`: job id
  - `--poll-interval`: polling interval seconds
  - `--max-wait`: timeout seconds
- `webhook create`
  - `--topic`: event topic (for example `job.completed`)
  - `--endpoint-url`: callback URL
  - `--secret`: shared secret
- `webhook list`
  - `--topic`: topic filter
  - `--status`: status filter
- `webhook get|delete`
  - `--id`: subscription id
- `webhook update`
  - `--id`: subscription id
  - `--endpoint-url`: new callback URL
  - `--secret`: new secret
  - `--status`: new status

## 4. Skill preparation notes

Recommended discovery flow in skill implementation:

1. Read this page for option names and command boundaries.
2. Confirm runtime behavior via `--help` in CI or preflight checks.
3. For API-level orchestration, also read `api-access.md` and `/openapi.json`.
