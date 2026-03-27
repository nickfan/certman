# Docker Compose 快速指南 - 完整例子演练

**场景**: 用户Alice在AWS Route53上解析 `mydemo1.com`，获得了 AWS Access Key 和 Secret Key，现在需要申请、续签、导出该域名的证书。

本指南展示真实的配置文件和命令执行过程。

---

## 1. 前置条件

1. ✅ 已安装 Docker / Docker Compose（检查：`docker --version && docker-compose --version`）
2. ✅ 当前目录为项目根目录（包含 `docker-compose.yml` 和 `data/` 文件夹）
3. ✅ Route53 凭据准备就绪（AWS Access Key ID 和 Secret Access Key）

参考详细信息：[dns-providers.md](../dns-providers.md) | [英文版本](../../docs/en/quickguide-docker-compose.md)

---

## 2. 第一步：准备配置文件

### a) 主配置 `data/conf/config.toml`

```toml
run_mode = "local"

[global]
email = "alice@mydemo1.com"
acme_server = "staging"
scan_items_glob = "item_*.toml"
```

### b) 域名条目配置 `data/conf/item_mydemo1.toml`

```toml
description = "mydemo1.com via route53"
primary_domain = "mydemo1.com"
secondary_domains = ["www.mydemo1.com"]
dns_provider = "route53"
account_id = "demo_route53"
```

### c) 环境变量 `data/conf/.env`（推荐方式）

```bash
# Route53 凭据 - mydemo1 条目
CERTMAN_AWS_DEMO_ROUTE53_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
CERTMAN_AWS_DEMO_ROUTE53_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
CERTMAN_AWS_DEMO_ROUTE53_REGION=us-east-1
```

说明：`account_id = "demo_route53"` 会在环境变量查找时归一化为 `DEMO_ROUTE53`。

⚠️ **安全提示**: 
- `.env` 文件已在 `.gitignore` 中，不会上传到 Git
- 生产环境建议使用 AWS IAM Role 或 AWS credentials file（参考 [dns-providers.md](../dns-providers.md)）

---

## 3. 第二步：校验配置

执行校验命令（推荐先按条目校验）：

```bash
docker compose run --rm certman config-validate --name mydemo1

# 如需全量校验，显式加 --all
docker compose run --rm certman config-validate --all
```

**预期输出**（成功时）:

```
[INFO] Loading config from data/conf/config.toml
[INFO] Loaded entry: mydemo1 (...)
[INFO] Config validation passed ✓
```

列出所有已配置的条目：

```bash
docker compose run --rm certman entries
```

**预期输出**:

```
[INFO] Registered entries:
  - mydemo1: mydemo1.com, www.mydemo1.com (provider: route53, challenge: dns-01)
```

如果这一步失败，常见原因：
- 凭据缺失：检查 `data/conf/.env` 中的 `CERTMAN_AWS_DEMO_ROUTE53_ACCESS_KEY_ID` 和 `CERTMAN_AWS_DEMO_ROUTE53_SECRET_ACCESS_KEY`
- 配置文件路径错误：确保 `item_mydemo1.toml` 在 `data/conf/` 目录下
- TOML 语法错误：用 TOML 在线验证器检查文件格式

---

## 4. 第三步：申请证书

首次为 `mydemo1.com` 申请证书：

```bash
docker compose run --rm certman new --name mydemo1
```

**执行过程**（大约 30-60 秒）：

```
[INFO] Requesting certificate for mydemo1 (mydemo1.com, www.mydemo1.com)
[INFO] Using ACME directory: https://acme-staging-v02.api.letsencrypt.org/directory
[INFO] Creating DNS challenge record in Route53...
[INFO] Waiting for DNS propagation...
[INFO] DNS validation passed ✓
[INFO] Certificate issued successfully
[INFO] Exporting certificate to data/output/mydemo1/
[INFO] Export complete:
  - fullchain.pem (证书链)
  - privkey.pem (私钥)
  - cert.pem (证书)
[SUCCESS] Certificate for mydemo1.com issued and exported
```

**输出文件结构**:

```
data/output/mydemo1/
├── cert.pem           # 证书（仅证书，不含中间证书）
├── privkey.pem        # 私钥（保密！）
├── fullchain.pem      # 完整链（包含中间证书，用于 Nginx/Apache）
└── metadata.json      # 证书元数据（发行日期、过期日期等）
```

---

## 5. 第四步：续签证书

在证书即将过期时（Let's Encrypt 证书有效期 90 天），续签单个条目：

```bash
docker compose run --rm certman renew --name mydemo1
```

或一键续签所有条目：

```bash
docker compose run --rm certman renew --all
```

**输出示例**:

```
[INFO] Renewing certificate for mydemo1 (mydemo1.com)
[INFO] Current certificate valid until: 2026-06-24
[INFO] Renewal not yet required (30 days remaining)
[INFO] Skipping renewal
```

如果需要强制续签（测试用）：

```bash
docker compose run --rm certman renew --name mydemo1 --force
```

---

## 6. 第五步：导出证书

如果仅需重新导出某个已存在的证书（不重新申请/续签）：

```bash
# 导出单个条目
docker compose run --rm certman export --name mydemo1
```

或导出所有条目：

```bash
docker compose run --rm certman export --all
```

**输出示例**:

```
[INFO] Exporting certificate for mydemo1
[INFO] Checking local certificate cache at data/run/letsencrypt/
[INFO] Found valid certificate for mydemo1.com
[INFO] Exporting to data/output/mydemo1/
[SUCCESS] Export complete: cert.pem, privkey.pem, fullchain.pem, metadata.json
```

此时可以在 `data/output/mydemo1/` 中找到最新的证书文件。

---

## 7. 第六步：周期巡检（推荐用于自动化）

通常以 cron 任务或 CI/CD 流水线运行：

```bash
docker compose run --rm certman check --warn-days 30 --force-renew-days 7
```

**参数说明**:
- `--warn-days 30`: 剩余有效期 < 30 天时告警（退出码 10）
- `--force-renew-days 7`: 剩余有效期 < 7 天时触发自动续签（退出码 20）

**不同时期的输出示例**:

*情况1 - 证书健康（剩余 60 天）*:
```
[INFO] Checking certificate for mydemo1.com
[INFO] Valid until: 2026-06-24 (60 days remaining)
[INFO] Status: OK
[EXIT CODE] 0
```

*情况2 - 即将过期（剩余 15 天）*:
```
[INFO] Checking certificate for mydemo1.com
[INFO] Valid until: 2026-05-15 (15 days remaining)
[WARN] Certificate expires within 30 days
[EXIT CODE] 10
```

*情况3 - 需要续签（剩余 5 天）*:
```
[INFO] Checking certificate for mydemo1.com
[INFO] Valid until: 2026-04-01 (5 days remaining)
[ERROR] Certificate expires within 7 days - renewal required
[EXIT CODE] 20
```

**可选：自动修复模式**

如果希望在检查时发现过期就自动续签：

```bash
docker compose run --rm certman check --warn-days 30 --force-renew-days 7 --fix
```

此时：
- 若发现需续签，将自动执行 `renew --name mydemo1`
- 续签成功后自动导出新证书
- 导出完成后才返回

---

## 8. 最终输出目录结构

完整流程后，项目目录如下：

```
certman/
├── docker-compose.yml            # 不变
├── data/
│   ├── conf/
│   │   ├── config.toml           # 主配置
│   │   ├── item_mydemo1.toml     # mydemo1.com 条目配置
│   │   └── .env                  # 凭据（.gitignore）
│   ├── output/
│   │   └── mydemo1/              # ⭐ 最终证书文件
│   │       ├── fullchain.pem     # 用于 Nginx/Apache
│   │       ├── privkey.pem       # 私钥（保密）
│   │       ├── cert.pem
│   │       └── metadata.json
│   ├── run/
│   │   └── letsencrypt/          # Let's Encrypt 内部状态（自动管理，无需手工修改）
│   └── log/
│       └── letsencrypt.log.*     # 详细日志
```

---

## 9. 纯参数 one-shot 模式（无配置文件）

面向自动化/Skill 调用，可完全不依赖 `config.toml` / `item_*.toml`：

```bash
# 一次性签发
uv run certman --data-dir data oneshot-issue \
  -d mydemo1.com -d *.mydemo1.com \
  -sp route53 \
  --email alice@mydemo1.com \
  --ak <aws-ak> --sk <aws-sk> \
  --aws-region us-east-1 \
  -o /tmp/mydemo1

# 一次性续签
uv run certman --data-dir data oneshot-renew \
  -d mydemo1.com -d *.mydemo1.com \
  -sp route53 \
  --email alice@mydemo1.com \
  --ak <aws-ak> --sk <aws-sk> \
  --aws-region us-east-1 \
  -o /tmp/mydemo1
```

---

## 10. 独立 Scheduler 用法（常驻 + 一次性）

Scheduler 独立于 `certman-server` 进程，推荐与 worker 搭配运行：

```bash
# 常驻调度
docker compose up certman-server certman-worker certman-scheduler

# 一次性触发（供外部 Cron/Task Scheduler 调用）
docker compose run --rm certman-scheduler once --force-enable
```

Kubernetes 也可使用 CronJob 一次性调度：`k8s/certman-scheduler-cronjob.yaml`。

---

## 下一步

- 多域名？在 `data/conf/` 中添加 `item_otherdomain.toml`，重复步骤 2-7
- 更换 Provider？参考 [dns-providers.md](../dns-providers.md) 修改 `provider` 字段和凭据
- 定时任务？参考 [cookbook-compose.md](cookbook-compose.md) 的"场景3: 每日自动续签"
- 生产环境？将 `acme_dir` 改为 Let's Encrypt 正式服务器（测试完成后）
