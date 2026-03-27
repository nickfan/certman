# CertMan Command Map

## Local surface: certman

Global:

- `-D, --data-dir`
- `-c, --config-file`

Commands:

- `entries`
- `config-validate`
- `config list|show|add|edit|remove|init`
- `env list|set|unset`
- `logs-clean --keep-days <n>`
- `new --name <entry> [--force] [--export|--no-export] [--verbose]`
- `renew [--all|--name <entry>] [--force] [--dry-run] [--export|--no-export] [--verbose]`
- `export [--all|--name <entry>] [--overwrite|--no-overwrite]`
- `check [--warn-days <n>] [--force-renew-days <n>] [--name <entry>] [--fix] [--json]`
- `oneshot-issue -d <domain>... -sp <provider> --email <email> -o <output> [--ak <ak> --sk <sk> | --api-token <token>]`
- `oneshot-renew -d <domain>... -sp <provider> --email <email> -o <output> [--ak <ak> --sk <sk> | --api-token <token>]`

## Scheduler surface: certman-scheduler

- `run --loop|--once [--force-enable] [--renew-before-days <n>] [--target-scope <scope>]`
- `once [--force-enable] [--renew-before-days <n>] [--target-scope <scope>]`

## Remote surface: certmanctl

Global:

- `--endpoint <url>`
- `--timeout <seconds>`
- `--output text|json`
- `--token <bearer>`

Auth notes:

- `certmanctl` env token: `CERTMAN_SERVER_TOKEN`
- server-side auth switch: `[server].token_auth_enabled`
- precedence when enabled: `entries[].token` > `global.token`

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
- `config list`
- `config show --entry-name <entry>`
- `config validate [--entry-name <entry>...] [--all]`

## MCP surface: certman-mcp

Server startup:

- `uv run certman-mcp --endpoint http://127.0.0.1:8000`

Auth notes:

- `--token <bearer>` is optional client override
- env fallback order: `CERTMAN_MCP_TOKEN`, then `CERTMAN_SERVER_TOKEN`

Tools:

- `health`
- `cert_create`, `cert_list`, `cert_get`, `cert_renew`
- `job_get`, `job_list(subject_id?, status?, target_scope?, limit=50)`, `job_wait`
- `webhook_create`, `webhook_list`, `webhook_get`, `webhook_update`, `webhook_delete`
- `config_list`, `config_get`, `config_validate`
