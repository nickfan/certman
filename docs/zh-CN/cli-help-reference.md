# CLI 帮助参考（Local + Control Plane）

本页用于命令发现和参数语义速查。
目标读者包括运维同学和 AI skill/tool 开发者。

## 1. 通过 --help 发现命令

```bash
uv run certman --help
uv run certman new --help
uv run certman renew --help

uv run certmanctl --help
uv run certmanctl cert --help
uv run certmanctl job wait --help
uv run certmanctl webhook update --help
```

## 2. 本地 CLI（`certman`）参数

全局参数：

- `-D, --data-dir`：基础数据目录（默认 `data`）
- `-c, --config-file`：`<data_dir>/conf` 下配置文件名

命令参数：

- `new`
  - `-n, --name`：配置里的 entry 名称
  - `-f, --force`：即使已有有效证书也强制重签
  - `--export/--no-export`：成功后是否导出产物
  - `-v, --verbose`：终端透传 certbot 输出
- `renew`
  - `-a, --all`：续签所有 entry
  - `-n, --name`：续签单个 entry
  - `-f, --force`：即使未到期也强制续签
  - `--dry-run`：走 staging 的续签验证
  - `--export/--no-export`：成功后是否导出
  - `-v, --verbose`：终端透传 certbot 输出
- `export`
  - `-a, --all`：导出全部 entry
  - `-n, --name`：导出单个 entry
  - `--overwrite/--no-overwrite`：是否覆盖输出文件
- `check`
  - `-w, --warn-days`：告警阈值天数
  - `-F, --force-renew-days`：强制续签阈值天数
  - `-n, --name`：仅巡检单个 entry
  - `--fix`：执行规划出的 new/renew 修复动作
  - `--json`：输出 JSON
- `logs-clean`
  - `-k, --keep-days`：保留最近 N 天日志
- `entries`
  - 无命令级参数
- `config list|show|add|edit|remove|init`
  - 条目配置与 item/global 存储管理
- `env list|set|unset`
  - 管理 `data/conf/.env` 里的 key
- `config-validate`
  - `-n, --name`：仅校验指定条目（可重复）
  - `--all`：校验全部合并条目
  - 范围规则：必须指定 `--name` 或 `--all`，且两者不可同时使用
- `oneshot-issue`
  - `-d, --domain`：可重复，支持通配符
  - `-sp, --sp, --service-provider`：`aliyun|cloudflare|route53`
  - `--email`：ACME 账户邮箱
  - `-o, --output`：证书导出目录
  - `--ak/--sk` 或 `--api-token`：provider 凭据
  - 纯参数模式，无需配置文件
- `oneshot-renew`
  - 与 `oneshot-issue` 参数基本一致
  - `--force/--no-force` 控制强制续签语义

## 3. 远程 CLI（`certmanctl`）参数

全局参数：

- `--endpoint`：控制面地址（默认 `http://127.0.0.1:8000`）
- `--timeout`：HTTP 超时秒数
- `--output`：`text` 或 `json`
- `--token`：Bearer Token

Token 说明：

- 仅当服务端配置 `[server].token_auth_enabled = true` 时，`--token` 才是必需的。
- 服务端 token 解析优先级为 `entries[].token` > `global.token`。
- `--token` 同时支持环境变量 `CERTMAN_SERVER_TOKEN`。

命令参数：

- `health`：无命令级参数
- `cert create|get|renew`
  - `-n, --entry-name`：服务端配置的 entry 名称
- `cert list`：无命令级参数
- `job get`
  - `--job-id`：任务 ID
- `job list`
  - `--subject-id`：按 subject 过滤
  - `--status`：按状态过滤
  - `--limit`：最大条数（1-200）
- `job wait`
  - `--job-id`：任务 ID
  - `--poll-interval`：轮询间隔秒数
  - `--max-wait`：最长等待秒数
- `webhook create`
  - `--topic`：事件主题（如 `job.completed`）
  - `--endpoint-url`：回调 URL
  - `--secret`：签名共享密钥
- `webhook list`
  - `--topic`：主题过滤
  - `--status`：状态过滤
- `webhook get|delete`
  - `--id`：订阅 ID
- `webhook update`
  - `--id`：订阅 ID
  - `--endpoint-url`：新回调 URL
  - `--secret`：新密钥
  - `--status`：新状态
- `config list`
  - 无命令级参数
- `config show`
  - `-n, --entry-name`：条目名
- `config validate`
  - `-n, --entry-name`：指定条目（可重复）
  - `--all`：校验全部合并条目

## 4. Skill 预备建议

推荐在 skill 里按以下顺序做参数发现：

1. 先读取本页，确认命令边界和参数名。
2. 在 CI 或 preflight 中执行 `--help` 做存在性校验。
3. 涉及 API 编排时，再读取 `api-access.md` 与 `/openapi.json`。
