# CertMan + cert-manager 本地实施手册（kind k8s 1.34）

> 日期: 2026-03-27
> 状态: 实施中（第 1 批自动化资产）
> 范围: 安装 cert-manager、执行 smoke 校验、准备 CertMan 直签/续签实测入口

## 1. 目标

1. 在 Docker Desktop + kind 上快速创建可重复的 cert-manager 本地测试环境。
2. 用最小 smoke 资源验证 cert-manager CRD 与控制器功能正常。
3. 为后续 kumaxiong.com 的 CertMan 真实直签/续签测试提供稳定底座。

## 2. 新增资产

1. 自动化脚本: scripts/cert_manager_lab.py
2. smoke 资源: k8s/cert-manager-smoke-selfsigned.yaml
3. Docker 本地续签兼容配置: docker-compose.yml 新增 certman-linuxfs profile

## 3. 前置条件

1. 已安装并可用: docker、kind、kubectl、helm。
2. 本仓库已安装 uv，并可执行 Python 3.12+。
3. Docker Desktop Kubernetes 与 kind 可同时运行。

## 4. 执行步骤

### 4.1 创建 kind + 安装 cert-manager（Helm）

```powershell
uv run scripts/cert_manager_lab.py up
```

说明:

1. 如果不存在 certman-lab 集群，脚本将按 kindest/node:v1.34.0 创建。
2. 使用 Helm 安装 cert-manager（默认 chart 版本 v1.18.2）。
3. 自动等待 cert-manager 关键 deployment 就绪。

### 4.2 运行 cert-manager smoke 验证

```powershell
uv run scripts/cert_manager_lab.py smoke
```

说明:

1. 应用 certman-lab 命名空间下的 Issuer + Certificate。
2. 等待 certificate/smoke-cert-selfsigned Ready。
3. 会创建 smoke-cert-selfsigned-tls Secret 作为成功判据。

### 4.3 查看状态

```powershell
uv run scripts/cert_manager_lab.py status
```

### 4.4 清理 smoke 与 cert-manager

```powershell
uv run scripts/cert_manager_lab.py down
```

## 5. 与 CertMan 直签/续签联动（下一步）

1. 在保持 cert-manager 已安装前提下，运行现有 k8s e2e：

```powershell
uv run scripts/e2e-test.py --k8s-only --no-cleanup
```

1. 准备 kumaxiong.com 的 data/conf/.env 与 item 配置后，执行 CertMan 直签验证：

```powershell
docker compose --profile local-linuxfs run --rm certman-linuxfs config-validate --name kumaxiong
docker compose --profile local-linuxfs run --rm certman-linuxfs new --name kumaxiong --no-export
```

1. 执行续签 dry-run 验证：

```powershell
docker compose --profile local-linuxfs run --rm certman-linuxfs renew --name kumaxiong --dry-run --no-export
```

1. 实测建议先使用 ACME staging，确认链路稳定后再切 production。

## 6. 安全要求

1. 不打印 AK/SK，不在日志中输出敏感环境变量。
2. data/conf/.env 保持本地文件，不进入版本控制。
3. 如需分享日志，先做关键字脱敏（ACCESS_KEY、SECRET、TOKEN）。

## 7. 当前限制

1. 本批仅交付 cert-manager 安装与 smoke 验证，不包含 cert-manager addon/plugin 实现。
2. certman/delivery/k8s.py 仍为未实现状态，未变更当前主干边界。
3. cert-manager 与 CertMan 深度协作（inbound events/external issuer）将在后续批次推进。

## 8. 已验证结果（2026-03-27）

1. cert-manager 已在 kind 集群 certman-lab 安装成功（Helm，chart v1.18.2）。
2. smoke 证书资源已成功 Ready，并生成 secret/smoke-cert-selfsigned-tls。
3. 现有 CertMan k8s e2e 已通过：`uv run scripts/e2e-test.py --k8s-only --no-cleanup`。
4. kumaxiong.com 直签链路已成功（容器内执行）。
5. kumaxiong.com 续签 dry-run 已成功（容器内执行）。

## 8.1 第二批：一键流水线（新增）

脚本: `scripts/certman_certmanager_pipeline.py`

1. 仅验证 cert-manager 底座：

```powershell
uv run scripts/certman_certmanager_pipeline.py baseline
```

1. 仅验证 CertMan 直签/续签：

```powershell
uv run scripts/certman_certmanager_pipeline.py certman --entry kumaxiong
```

1. 全链路（默认包含 k8s e2e）：

```powershell
uv run scripts/certman_certmanager_pipeline.py full --entry kumaxiong
```

1. 报告输出:

- JSON: `docs/notes/certman-certmanager-pipeline-report.json`
- Markdown: `docs/notes/certman-certmanager-pipeline-report.md`

## 9. Windows 实测注意事项

1. 在 Windows bind mount (`./data:/data`) 下，certbot 续签可能报 symlink 语义错误。
2. 已通过新增 `certman-linuxfs` profile 规避：
   - 将 `/data/run` 放在 Docker named volume（Linux 文件系统）
   - 保留 `/data/conf`、`/data/output`、`/data/log` 与宿主机映射
3. 若使用原 `certman` profile 执行 renew，可能出现解析 lineage 失败。

## 10. 独立 Scheduler 运维手册（native / docker / k8s）

### 10.1 设计原则（本轮已落地）

1. 定时调度与 API 服务进程解耦：`certman-server` 不内嵌任何定时任务。
2. `certman-scheduler` 仅负责按策略扫描并入队 renew job。
3. `certman-worker` 仅负责消费并执行 job。
4. 支持双触发形态：
   - 常驻调度进程（主）
   - 外部 Cron/CronJob 定时调用 `--once`（备）

### 10.2 配置项（全局开关 + 计划策略）

在 `data/conf/config.toml` 增加：

```toml
[scheduler]
enabled = true
mode = "loop"              # loop | cron
scan_interval_seconds = 300 # loop 模式生效
cron_expr = "0 * * * *"    # cron 模式生效（5段表达式）
cron_poll_seconds = 15      # cron 轮询时钟间隔
renew_before_days = 30      # 提前 N 天入队 renew
```

环境变量兜底（配置文件优先）：

1. `CERTMAN_SCHEDULER_ENABLED`
2. `CERTMAN_SCHEDULER_MODE`
3. `CERTMAN_SCHEDULER_SCAN_INTERVAL_SECONDS`
4. `CERTMAN_SCHEDULER_CRON_EXPR`
5. `CERTMAN_SCHEDULER_CRON_POLL_SECONDS`
6. `CERTMAN_SCHEDULER_RENEW_BEFORE_DAYS`

### 10.3 Native 运行

1. 常驻 loop（推荐）

```powershell
uv run certman-scheduler --data-dir data --config-file config.toml --loop
```

1. 单次触发（给系统 Cron/Task Scheduler 调用）

```powershell
uv run certman-scheduler --data-dir data --config-file config.toml --once --force-enable
```

等价短命令（更适合平台级任务调度器）：

```powershell
uv run certman-scheduler once --data-dir data --config-file config.toml --force-enable
```

说明：

1. `--force-enable` 允许外部定时系统无视 `enabled=false` 做强制一次触发。
2. 未入队时输出 `scheduled=0` 为正常行为（表示当前无到期证书）。

### 10.4 Docker Compose 运行

本轮已接入独立服务：`certman-scheduler`

```powershell
docker compose up certman-server certman-worker certman-scheduler
```

仅触发一次（适合作业式调度）：

```powershell
docker compose run --rm certman-scheduler --once --force-enable
```

### 10.5 Kubernetes 运行

`k8s-e2e-test.yaml` 已新增 `certman-scheduler` Deployment（独立于 server/worker）。

```powershell
kubectl apply -f k8s-e2e-test.yaml
kubectl -n certman-lab get deploy certman-scheduler
kubectl -n certman-lab logs deploy/certman-scheduler --tail=50
```

生产建议：

1. scheduler 副本建议 `replicas=1`（避免重复扫描并发复杂度）。
2. 若偏好平台级调度，可改为 CronJob 调 `certman-scheduler once --force-enable`。
3. 示例清单：`k8s/certman-scheduler-cronjob.yaml`（替代常驻 Deployment 方案）。

### 10.6 快速排障

1. 日志出现 `scheduler disabled`：检查 `[scheduler].enabled` 或是否需要 `--force-enable`。
2. 日志长期 `scheduled=0`：检查证书 `not_after` 与 `renew_before_days` 窗口是否命中。
3. 任务已入队但未执行：检查 `certman-worker` 是否在 loop 运行、DB 路径是否与 scheduler 一致。

## 11. Local/CLI 纯参数一锤子模式（无配置文件）

适用场景：被外部自动化/skill 直接调用，不依赖 `config.toml` / `item_*.toml`。

### 11.1 一次性签发（阻塞式）

```powershell
uv run certman --data-dir data oneshot-issue \
   -d xxx.com \
   -d *.xxx.com \
   --sp aliyun \
   --email ops@example.com \
   --ak <aliyun-ak> \
   --sk <aliyun-sk> \
   -o /tmp/xxx.com
```

### 11.2 一次性续签（阻塞式）

```powershell
uv run certman --data-dir data oneshot-renew \
   -d xxx.com \
   -d *.xxx.com \
   --sp aliyun \
   --email ops@example.com \
   --ak <aliyun-ak> \
   --sk <aliyun-sk> \
   -o /tmp/xxx.com
```

### 11.3 参数说明

1. `--sp`：`aliyun` | `cloudflare` | `route53`
2. `-d/--domain`：可重复，支持通配符域名
3. `-o/--output`：签发成功后导出目录（阻塞命令返回前完成导出）
4. `--acme-server`：`prod`（默认）或 `staging`
5. `--force`：强制续签语义（`oneshot-renew` 默认开启，可 `--no-force` 关闭）
