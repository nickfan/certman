# CertMan Command Map

## Local surface: certman

Global:

- `-D, --data-dir`
- `-c, --config-file`

Commands:

- `entries`
- `config-validate`
- `logs-clean --keep-days <n>`
- `new --name <entry> [--force] [--export|--no-export] [--verbose]`
- `renew [--all|--name <entry>] [--force] [--dry-run] [--export|--no-export] [--verbose]`
- `export [--all|--name <entry>] [--overwrite|--no-overwrite]`
- `check [--warn-days <n>] [--force-renew-days <n>] [--name <entry>] [--fix] [--json]`

## Remote surface: certmanctl

Global:

- `--endpoint <url>`
- `--timeout <seconds>`
- `--output text|json`
- `--token <bearer>`

Commands:

- `health`
- `cert create --entry-name <entry>`
- `cert list`
- `cert get --entry-name <entry>`
- `cert renew --entry-name <entry>`
- `job get --job-id <id>`
- `job list [--subject-id <value>] [--status <value>] [--limit <1-200>]`
- `job wait --job-id <id> [--poll-interval <seconds>] [--max-wait <seconds>]`
- `webhook create --topic <topic> --endpoint-url <url> --secret <secret>`
- `webhook list [--topic <topic>] [--status <status>]`
- `webhook get --id <id>`
- `webhook update --id <id> [--endpoint-url <url>] [--secret <value>] [--status <value>]`
- `webhook delete --id <id>`

## MCP surface: certman-mcp

Server startup:

- `uv run certman-mcp --endpoint http://127.0.0.1:8000`

Tools:

- `health`
- `cert_create`, `cert_list`, `cert_get`, `cert_renew`
- `job_get`, `job_list`, `job_wait`
- `webhook_create`, `webhook_list`, `webhook_get`, `webhook_update`, `webhook_delete`
