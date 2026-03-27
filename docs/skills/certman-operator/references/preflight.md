# Preflight Checklist

## Universal

1. Confirm target surface: local / remote / mcp.
2. Validate required identifiers are non-empty.
3. Validate URLs use http/https.
4. Ensure secrets are not echoed in logs.

## Local (certman)

1. `data/conf/config.toml` exists.
2. `data/run` and `data/output` are writable.
3. Run `uv run certman --help` for command availability when in doubt.

## Remote (certmanctl)

1. Probe health:
- `uv run certmanctl --endpoint <url> health`
2. Check command availability:
- `uv run certmanctl --help`
- `uv run certmanctl job wait --help`
3. Keep `--limit` within 1-200.
4. Auth check:
- if `[server].token_auth_enabled = false`, token is optional
- if `[server].token_auth_enabled = true`, provide `--token` or `CERTMAN_SERVER_TOKEN`
- if server returns `AUTH_TOKEN_CONFIG_ERROR`, report server-side token config issue (`entries[].token` > `global.token`)

## MCP (certman-mcp)

1. Confirm server endpoint reachable first.
2. Start MCP server with endpoint.
3. If auth required, inject token via `--token` or env var (`CERTMAN_MCP_TOKEN`, fallback `CERTMAN_SERVER_TOKEN`).
4. On tool failures, classify as transport/api/timeout/validation.
