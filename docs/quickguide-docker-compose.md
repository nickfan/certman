# Docker Compose 快速指南 - 完整例子演练

**场景**: 用户Alice在AWS Route53上解析 `mydemo1.com`，获得了 AWS Access Key 和 Secret Key，现在需要申请、续签、导出该域名的证书。

本指南展示真实的配置文件和命令执行过程。
---

## 1. 前置条件

1. ✅ 已安装 Docker / Docker Compose（检查：`docker --version && docker-compose --version`）
2. ✅ 当前目录为项目根目录（包含 `docker-compose.yml` 和 `data/` 文件夹）
3. ✅ Route53 凭据准备就绪（AWS Access Key ID 和 Secret Access Key）

参考详细信息：[dns-providers.md](dns-providers.md)

---

## 2. 第一步：准备配置文件

### a) 主配置 `data/conf/config.toml`

```toml
# 基础配置
[certman]
# Let's Encrypt 测试环境（推荐新手），生产改为 https://acme-v02.api.letsencrypt.org/directory
acme_dir = "https://acme-staging-v02.api.letsencrypt.org/directory"

# 邮件（必填，用于证书过期提醒）
email = "alice@mydemo1.com"

# 默认 provider（可选，单个条目可覆盖）
provider = "route53"

# 日志级别
log_level = "info"
```

### b) 域名条目配置 `data/conf/item_mydemo1.toml`

```toml
# mydemo1.com 证书配置
[entry]
name = "mydemo1"  # 条目标识符
domain = "mydemo1.com"  # 主域名
alt_names = ["www.mydemo1.com"]  # 替代域名（可选）
provider = "route53"  # DNS provider，必须与 dns-providers.md 中的支持列表一致

# 证书验证方式（推荐 "dns-01" 以支持泛域名）
challenge_type = "dns-01"

# Route53 凭据配置
# 方式1（推荐）：通过 .env 文件管理凭据（详见下方）
# 方式2：直接在此处指定（DEMO ONLY，生产环境应使用方式1）
# [credentials]
# aws_access_key_id = "AKIAIOSFODNN7EXAMPLE"
# aws_secret_access_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
# region = "us-east-1"
```

### c) 环境变量 `data/conf/.env`（推荐方式）

```bash
# Route53 凭据 - mydemo1 条目
CERTMAN_ROUTE53_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE
CERTMAN_ROUTE53_SECRET_ACCESS_KEY=wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY
CERTMAN_ROUTE53_REGION=us-east-1
```

⚠️ **安全提示**: 
- `.env` 文件已在 `.gitignore` 中，不会上传到 Git
- 生产环境建议使用 AWS IAM Role 或 AWS credentials file（参考 [dns-providers.md](dns-providers.md)）

---

## 3. 第二步：校验配置

执行校验命令：

```bash
docker compose run --rm certman config-validate --name mydemo1

# 如需全量校验，显式加 --all
docker compose run --rm certman config-validate --all
```

**预期输出**（成功时）:

```
[INFO] Loading config from data/conf/config.toml
[INFO] Loaded entry: mydemo1 (mydemo1.com, www.mydemo1.com)
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
- 凭据缺失：检查 `data/conf/.env` 中的 `CERTMAN_ROUTE53_ACCESS_KEY_ID` 和 `CERTMAN_ROUTE53_SECRET_ACCESS_KEY`
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