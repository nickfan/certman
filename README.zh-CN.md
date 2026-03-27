# certman

**中文 | [英文版本/English Version](README.md)**

基于 certbot 和 DNS 插件的 SSL 证书管理 CLI。

## 运行模式

CertMan 现在基于同一套配置和 service 层提供四个运行入口：

- `certman`：本地运维 CLI，负责 `new`、`renew`、`check`、`export`
- `certman-server`：控制面 FastAPI 服务，提供健康检查、任务提交、任务查询、webhook 订阅
- `certman-worker`：后台任务执行器，消费 `issue` / `renew` 队列任务
- `certman-agent`：受控节点 agent 入口，当前提供最小 polling 骨架
- `certman-scheduler`：独立续签调度器（loop/cron/once）

常用本地命令：

```bash
uv run certman --help
uv run certman-server --data-dir data --config-file config.toml
uv run certman-worker --data-dir data --config-file config.toml --once
uv run certman-agent --data-dir data --config-file config.toml --once
uv run certman-scheduler run --data-dir data --config-file config.toml --loop
uv run certman-scheduler once --data-dir data --config-file config.toml --force-enable
```

## 运行依赖矩阵

- `certman`（CLI 本地模式）：不依赖 Kubernetes 或 Docker，可直接通过 Python/uv 运行。
- `certman-server` + `certman-worker`：不依赖 Kubernetes 或 Docker；Docker 仅用于打包/部署。
- `certman-scheduler`：不依赖 Kubernetes 或 Docker，可独立常驻或一次性运行。
- `certman-agent`：不强依赖 Kubernetes 或 Docker，但需要可访问的控制面 endpoint。
- `scripts/certman-docker.ps1` / `scripts/certman-docker.sh`：本质是 docker 包装脚本，必须依赖 Docker 引擎。

无 k8s/docker 的直接运行示例：

```bash
uv run certman --data-dir data entries
uv run certman --data-dir data check --warn-days 30 --force-renew-days 7
uv run certman --data-dir data oneshot-issue -d example.com -d *.example.com -sp aliyun --email ops@example.com --ak <ak> --sk <sk> -o /tmp/example.com
```

```powershell
uv run certman --data-dir data entries
uv run certman --data-dir data check --warn-days 30 --force-renew-days 7
```

## 数据目录约定

默认 `--data-dir` 为 `data/`（可覆盖）。

- `data/conf/`: 配置目录
  - `config.example.toml`: 全局配置模板（受版本控制）
  - `config.toml`: 全局配置（本地文件，忽略）
  - `item_example.example.toml`: 条目模板（受版本控制）
  - `item_*.toml`: 证书条目配置（本地文件，忽略）
  - `.env`: 可选密钥文件（忽略）
  - `.env.example`: 密钥模板（受版本控制）
- `data/run/`: 运行时目录（忽略）
  - `letsencrypt/`: certbot 状态目录（建议）
- `data/log/`: 日志目录（忽略）
- `data/output/`: 导出证书目录（忽略）

## 镜像仓库

- Docker Hub: `nickfan/certman`
- GHCR: `ghcr.io/nickfan/certman`

标签策略：

- `edge`: 来自 master
- `latest` + `X.Y.Z`: 来自 `vX.Y.Z` 标签

## Docker Compose 模式（推荐）

项目内置 compose 服务定义：[docker-compose.yml](docker-compose.yml)

控制面场景下包含三类服务：

- `certman`：一次性运维命令
- `certman-server`：HTTP 控制面
- `certman-worker`：后台消费任务

```bash
# 1) 校验单个或多个指定条目（推荐默认）
docker compose run --rm certman config-validate --name <entry-name>

# 1.1) 显式校验全部条目
docker compose run --rm certman config-validate --all

# 2) 查看条目
docker compose run --rm certman entries

# 3) 申请单个条目证书
docker compose run --rm certman new --name <entry-name>

# 4) 续签
docker compose run --rm certman renew --name <entry-name>
docker compose run --rm certman renew --all

# 5) 导出
docker compose run --rm certman export --name <entry-name>
docker compose run --rm certman export --all

# 6) 启动控制面与 worker
docker compose up certman-server certman-worker

# 7) 启动独立 scheduler
docker compose up certman-server certman-worker certman-scheduler
```

控制面接口快速验证：

```bash
curl http://127.0.0.1:8000/health
curl -X POST http://127.0.0.1:8000/api/v1/certificates \
  -H 'content-type: application/json' \
  -d '{"entry_name":"site-a"}'
curl -X POST http://127.0.0.1:8000/api/v1/webhooks \
  -H 'content-type: application/json' \
  -d '{"topic":"job.completed","endpoint":"https://example.test/hook","secret":"topsecret"}'
```

若配置 `[server].token_auth_enabled = true`，受保护的 REST 接口需要携带 `Authorization: Bearer <token>`。

控制面 API 文档地址：

```text
http://127.0.0.1:8000/docs
http://127.0.0.1:8000/redoc
http://127.0.0.1:8000/openapi.json
```

通过 `certmanctl` 远程操作示例：

```bash
uv run certmanctl --endpoint http://127.0.0.1:8000 health
uv run certmanctl --endpoint http://127.0.0.1:8000 cert create --entry-name site-a
uv run certmanctl --endpoint http://127.0.0.1:8000 job list --subject-id site-a
uv run certmanctl --endpoint http://127.0.0.1:8000 webhook list
```

可选脚本化 e2e 验证（compose/k8s）：

```bash
python scripts/e2e-test.py --compose-only
python scripts/e2e-test.py --k8s-only
```

更多文档：

- [📖 中文文档导航](docs/zh-CN/) - 完整导航和所有指南
- 快速指南: [docs/zh-CN/quickguide-docker-compose.md](docs/zh-CN/quickguide-docker-compose.md)
- 场景手册: [docs/zh-CN/cookbook-compose.md](docs/zh-CN/cookbook-compose.md)
- 三层快速指南: [docs/zh-CN/quickguide-layered.md](docs/zh-CN/quickguide-layered.md)
- 三层场景手册: [docs/zh-CN/cookbook-layered.md](docs/zh-CN/cookbook-layered.md)
- 三层运维手册: [docs/zh-CN/manual-layered.md](docs/zh-CN/manual-layered.md)
- API 与 AI 接入: [docs/zh-CN/api-access.md](docs/zh-CN/api-access.md)
- DNS Provider 配置: [docs/zh-CN/dns-providers.md](docs/zh-CN/dns-providers.md)
- 📖 [English Documentation](docs/en/) - Complete guides in English

## Docker Run 示例

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

## 脚本封装（Windows/Linux）

为了避免重复输入镜像、挂载和环境变量，可使用脚本封装，业务参数从外部透传：

- Linux/macOS: `scripts/certman-docker.sh`
- Windows: `scripts/certman-docker.ps1`

```bash
bash scripts/certman-docker.sh check --warn-days 30 --force-renew-days 7
bash scripts/certman-docker.sh renew --all
```

```powershell
.\scripts\certman-docker.ps1 check --warn-days 30 --force-renew-days 7
.\scripts\certman-docker.ps1 renew --all
```

可选环境变量：

- `CERTMAN_IMAGE`: 覆盖镜像（默认 `nickfan/certman:edge`）
- `CERTMAN_DATA_DIR_HOST`: 覆盖主机侧数据目录（默认 `<project>/data`，挂载到容器 `/data`）

## 镜像 Build/Push 脚本

如果需要统一执行本地构建并推送到 Docker Hub 与 GHCR，可使用：

- PowerShell：`scripts/docker-image-release.ps1`
- Shell：`scripts/docker-image-release.sh`

示例：

```powershell
./scripts/docker-image-release.ps1 -Tag edge
./scripts/docker-image-release.ps1 -Tag edge -Push
```

```bash
bash scripts/docker-image-release.sh --tag edge
bash scripts/docker-image-release.sh --tag edge --push
```

说明：

- 执行 push 前请先完成 Docker Hub 与 GHCR 的 `docker login`。
- 默认会同时处理 `nickfan/certman:<tag>` 与 `ghcr.io/nickfan/certman:<tag>`。

## DNS Provider 支持

当前支持：

- Aliyun DNS
- Cloudflare DNS
- AWS Route53

详细配置示例见：[docs/dns-providers.md](docs/dns-providers.md)

## 定时检查建议

```bash
docker compose run --rm certman check --warn-days 30 --force-renew-days 7
```

可选自动修复：

```bash
docker compose run --rm certman check --warn-days 30 --force-renew-days 7 --fix
```

## 控制面说明

- `run_mode = "server"` 时必须配置 `[server]`，至少包含 `db_path`、`listen_host`、`listen_port`
- REST 鉴权总开关：`[server].token_auth_enabled`（默认 `false`）
- 开启鉴权后，证书/job 接口 token 优先级：`entries[].token` > `global.token`
- 若已开启鉴权，但当前请求目标既无 item token 也无 global token，返回 `500 AUTH_TOKEN_CONFIG_ERROR`
- 若已开启鉴权且需要 token：缺少 token 返回 `401 AUTH_MISSING_TOKEN`，token 错误返回 `401 AUTH_INVALID_TOKEN`
- webhook 订阅和投递记录持久化在控制面数据库中
- `certman-worker` 与 `certman-server` 共享同一份 SQLite 数据库
- `certman-agent` 仍是受控节点入口，Phase 4 的签名/加密原语已就绪，后续可继续扩展远程通信链路
- 当前面向 AI 的正式接入面包含 REST + OpenAPI，以及通过 `certman-mcp` 提供的 stdio MCP Server（封装控制面 API）。

## check 命令退出码

- `0`: 正常
- `10`: 告警（<= warn_days）
- `20`: 需要强制续签（<= force_renew_days 或已过期）
- `30`: 证书文件缺失 / 条目缺失
