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

## MCP (certman-mcp)

1. Confirm server endpoint reachable first.
2. Start MCP server with endpoint.
3. If auth required, inject token via environment variable.
4. On tool failures, classify as transport/api/timeout/validation.
