# 三层快速指南（CLI / Agent / Service）

本指南用于 15 分钟内把 certman 跑通三层工作流：

- CLI 层：本地命令直接发证、续签、检查、导出
- Service 层：控制面 API + Worker 队列执行
- Agent 层：受控节点签名拉取任务并回传结果

## 0. 前置准备

1. 安装依赖并准备数据目录

```bash
uv sync
cp data/conf/config.example.toml data/conf/config.toml
cp data/conf/item_example.example.toml data/conf/item_site_a.toml
```

2. 编辑 data/conf/config.toml（最小可用）

```toml
run_mode = "local"

[global]
data_dir = "data"
acme_server = "staging"
email = "ops@example.com"
```

3. 编辑 data/conf/item_site_a.toml（最小条目）

```toml
name = "site-a"
primary_domain = "example.com"
secondary_domains = ["www.example.com"]
wildcard = true
dns_provider = "route53"
account_id = "MAIN"
```

4. 在 data/conf/.env 写入 provider 凭据（示例：Route53）

```dotenv
CERTMAN_AWS_MAIN_ACCESS_KEY_ID=AKIA...
CERTMAN_AWS_MAIN_SECRET_ACCESS_KEY=...
CERTMAN_AWS_MAIN_REGION=us-east-1
```

## 1. CLI 层快速上手（单机）

1. 校验配置

```bash
uv run certman -D data config-validate
```

2. 发证

```bash
uv run certman -D data new --name site-a --verbose
```

3. 证书健康检查

```bash
uv run certman -D data check --warn-days 30 --force-renew-days 7
```

4. 导出交付物

```bash
uv run certman -D data export --name site-a
```

成功后可在 data/output/site-a/ 看到 fullchain.pem 与 privkey.pem。

## 2. Service 层快速上手（控制面）

1. 切换到 server 模式配置

```toml
run_mode = "server"

[server]
db_path = "data/run/certman.db"
listen_host = "127.0.0.1"
listen_port = 8000
signing_key_path = "data/run/keys/server_ed25519.pem"
```

2. 启动 server 与 worker（两个终端）

```bash
uv run certman-server -D data
uv run certman-worker -D data --loop --interval-seconds 30
```

3. 提交发证任务 + 查询状态

```bash
curl -X POST http://127.0.0.1:8000/api/v1/certificates \
  -H "content-type: application/json" \
  -d '{"entry_name":"site-a"}'

curl http://127.0.0.1:8000/api/v1/jobs/<job_id>
```

## 3. Agent 层快速上手（受控节点）

1. agent 节点配置（run_mode=agent）

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

2. 在控制面数据库提前注册 node-a 且状态 active（当前版本要求）

3. 运行 agent 轮询

```bash
uv run certman-agent -D data --once
```

输出示例：

```text
node_id=node-a poll_count=1
```

说明签名请求、防重放 nonce、任务分配链路已打通。

## 4. 一页排障

- `config-validate` 失败：优先检查 .env 变量命名与 account_id 前缀一致。
- Windows certbot 权限错误：使用管理员终端或 Docker/WSL。
- job 长期 queued：检查 worker 是否启动，且 server/worker 的 db_path 是否同一文件。
- agent 401：检查 node 状态是否 active、公钥是否匹配、系统时间偏差是否过大。
- agent 409 replay：同一 nonce 重放，被控制面拒绝，属于预期安全行为。
