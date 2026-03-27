# Preflight Checklist

## Universal

1. Confirm target surface: local / remote / mcp.
2. Validate required identifiers are non-empty.
3. Validate URLs use http/https.
4. Ensure secrets are not echoed in logs.

## Local (certman)

1. 配置驱动模式下确认 `data/conf/config.toml` 存在；若是 one-shot 纯参数模式可跳过。
2. `data/run` and `data/output` are writable.
3. Run `uv run certman --help` for command availability when in doubt.

4. one-shot 模式必须检查 provider 参数完整：

aliyun/route53 需要 `--ak` + `--sk`。
cloudflare 需要 `--api-token`。

## Scheduler (certman-scheduler)

1. 验证 server 配置存在且可访问同一数据库路径。
2. 平台调度器触发时优先使用 `uv run certman-scheduler once --force-enable`。
3. 若常驻模式，确认仅单副本运行，避免重复入队。

## Remote (certmanctl)

1. Probe health:

`uv run certmanctl --endpoint <url> health`

1. Check command availability:

`uv run certmanctl --help`
`uv run certmanctl job wait --help`

1. Keep `--limit` within 1-200.

1. Auth check:

if `[server].token_auth_enabled = false`, token is optional.
if `[server].token_auth_enabled = true`, provide `--token` or `CERTMAN_SERVER_TOKEN`.
if server returns `AUTH_TOKEN_CONFIG_ERROR`, report server-side token config issue (`entries[].token` > `global.token`).

## MCP (certman-mcp)

1. Confirm server endpoint reachable first.
2. Start MCP server with endpoint.
3. If auth required, inject token via `--token` or env var (`CERTMAN_MCP_TOKEN`, fallback `CERTMAN_SERVER_TOKEN`).
4. On tool failures, classify as transport/api/timeout/validation.
