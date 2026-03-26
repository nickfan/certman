# Docker Compose Cookbook - 真实场景模板集

本手册根据真实生产场景提供可直接复制的完整示例（包括配置文件）。


---

## 场景 1: 新接入一个API服务域名到Route53

**背景**: Bob 需要为新上线的 API 服务 `api.demo.com` 申请证书，该域名托管在 AWS Route53，已有 AWS 凭据。

### Step 1: 配置文件

创建 `data/conf/item_api_demo.toml`:

```toml
[entry]
name = "api-demo"
domain = "api.demo.com"
alt_names = ["api-staging.demo.com"]
provider = "route53"
challenge_type = "dns-01"
```

创建或修改 `data/conf/.env` 添加 Route53 凭据：

```bash
CERTMAN_ROUTE53_ACCESS_KEY_ID=AKIA2EXAMPLE000000000
CERTMAN_ROUTE53_SECRET_ACCESS_KEY=xxxSecretxxx...
CERTMAN_ROUTE53_REGION=us-west-2
```

### Step 2: 校验并申请

```bash
# 校验配置
docker compose run --rm certman config-validate

# 确认条目已加载
docker compose run --rm certman entries

# 申请证书（包含 api-staging.demo.com 的 SANs）
docker compose run --rm certman new --name api-demo
```

**预期结果**:

```
[INFO] Requesting certificate for api-demo (api.demo.com, api-staging.demo.com)
[INFO] DNS challenge validated
[SUCCESS] Certificate issued and exported to data/output/api-demo/
```

证书已保存到 `data/output/api-demo/fullchain.pem` 和 `data/output/api-demo/privkey.pem`，可直接用于 Nginx/HAProxy。

---

## 场景 2: 每日监控告警（纯巡检，不修复）

**背景**: Charlie 在 CI/CD 流水线中设置了每日 13:00 UTC 的定时作业，用来监控所有证书健康度。只报警，不自动修复，由人工决策是否续签。

### 配置管理系统

假设已有 5 个域名的配置：`api.demo.com`, `web.demo.com`, `admin.demo.com`, `internal.demo.com`, `static.demo.com`

### 巡检命令

```bash
#!/bin/bash
# 每日巡检脚本，输入设定告警阈值参数
docker compose run --rm certman check --warn-days 30 --force-renew-days 7
EXIT_CODE=$?

# 按 EXIT_CODE 做运维决策
case $EXIT_CODE in
  0)
    echo "✓ All certificates healthy"
    ;;
  10)
    echo "⚠ Warning: some certificates expire within 30 days"
    # 发送 Slack/Email 告警给运维
    # curl -X POST https://slack-webhook-url ...
    ;;
  20)
    echo "🔴 Critical: some certificates expire within 7 days (need renewal)"
    # 发送紧急告警
    ;;
  30)
    echo "🔴 Critical: some certificates are missing"
    # 发送紧急告警
    ;;
esac
exit $EXIT_CODE
```

### 在 Kubernetes 中的 CronJob 示例

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cert-daily-check
spec:
  # 每天 13:00 UTC 运行
  schedule: "0 13 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: certman-check
            image: nickfan/certman:edge
            command: ["/bin/sh", "-c"]
            args:
              - docker run --rm -v $(pwd)/data:/app/data nickfan/certman:edge check --warn-days 30 --force-renew-days 7
          restartPolicy: OnFailure
```

**输出示例** (全部正常):

```
[INFO] Checking 5 certificates...
[INFO] api.demo.com: Valid until 2026-08-15 (130 days remaining) ✓
[INFO] web.demo.com: Valid until 2026-07-20 (105 days remaining) ✓
[INFO] admin.demo.com: Valid until 2026-06-10 (56 days remaining) ✓
[INFO] internal.demo.com: Valid until 2026-05-20 (35 days remaining) ⚠ (will warn in 5 days)
[INFO] static.demo.com: Valid until 2026-05-09 (24 days remaining) ⚠ WARN
[EXIT CODE] 10
```

---

## 场景 3: 完全自动化续签（每周一 02:00）

**背景**: David 的整个域名组合托管在 Aliyun DNS（已有 AccessKey），希望每周一凌晨自动续签所有快过期的证书，无需人工干预。

### 配置示例

`data/conf/config.toml`:

```toml
[certman]
acme_dir = "https://acme-v02.api.letsencrypt.org/directory"
email = "ops@example.com"
provider = "aliyun"
log_level = "info"
```

假设已配置 3 个 Aliyun 托管域名：`site1.com`, `site2.com`, `site3.cn`

`data/conf/.env`:

```bash
# Aliyun 凭据（所有域名共用）
CERTMAN_ALIYUN_ACCESS_KEY_ID=LTAI5xxxxx...
CERTMAN_ALIYUN_ACCESS_KEY_SECRET=xxxSecret...
```

### 自动续签命令

```bash
#!/bin/bash
# 脚本: renew-all-and-export.sh

docker compose run --rm certman renew --all --auto-export

# 若续签成功，同时导出证书到 data/output/
# 输出如：
# [INFO] Renewing: site1.com (RENEWED)
# [INFO] Renewing: site2.com (SKIP - valid until 2026-08-10)
# [INFO] Renewing: site3.cn (RENEWED)
# [INFO] Auto-exporting renewed certificates...
# [SUCCESS] Export complete
```

### 在 Linux 上的 Crontab 设置

```bash
# 编辑 crontab
crontab -e

# 添加以下行：
# 每周一 02:00 运行（UTC）
0 2 * * 1 cd /path/to/certman && bash ./renew-all-and-export.sh >> /var/log/certman-renew.log 2>&1
```

### 在 Docker/Kubernetes 上的定期任务

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cert-weekly-renew
spec:
  # 周一 02:00 UTC
  schedule: "0 2 * * 1"
  jobTemplate:
    spec:
      template:
        spec:
          containers:
          - name: certman-renew
            image: nickfan/certman:edge
            volumeMounts:
            - name: data-vol
              mountPath: /app/data
            command: ["/bin/sh", "-c"]
            args:
              - certman renew --all --auto-export
          volumes:
          - name: data-vol
            persistentVolumeClaim:
              claimName: certman-data
          restartPolicy: OnFailure
```

**输出示例**:

```
[INFO] Renewing all certificates (Aliyun provider)...
[INFO] Processing: site1.com
  [INFO] Current: Valid until 2026-05-10 (14 days remaining)
  [INFO] Renewing...
  [SUCCESS] Renewed: site1.com (new cert valid until 2026-08-10)
[INFO] Processing: site2.com
  [INFO] Current: Valid until 2026-08-15 (75 days remaining)
  [SKIP] Not expired yet
[INFO] Processing: site3.cn
  [INFO] Current: Valid until 2026-05-05 (9 days remaining)
  [INFO] Renewing...
  [SUCCESS] Renewed: site3.cn (new cert valid until 2026-08-05)
[INFO] Exporting renewed certificates...
[SUCCESS] All renewed certs exported to data/output/
```

---

## 场景 4: 跨多个 Provider 的证书管理

**背景**: Eve 的公司有多个业务域，分别使用不同的 DNS provider：
- 核心 API：AWS Route53（`api.internal.com`）
- 客户门户：Cloudflare（`portal.company.com`, `portal-cn.company.com`）  
- 备用链路：Aliyun（`backup.company.cn`）

需要在一个 certman 实例中统一管理。

### 多 Provider 配置

`data/conf/config.toml`:

```toml
[certman]
acme_dir = "https://acme-v02.api.letsencrypt.org/directory"
email = "security@company.com"
log_level = "info"
# 无默认 provider，每个条目指定各自的
```

创建多个条目文件：

**`data/conf/item_api_internal.toml`** (Route53):

```toml
[entry]
name = "api-internal"
domain = "api.internal.com"
provider = "route53"
challenge_type = "dns-01"
```

**`data/conf/item_portal_company.toml`** (Cloudflare):

```toml
[entry]
name = "portal"
domain = "portal.company.com"
alt_names = ["portal-cn.company.com"]
provider = "cloudflare"
challenge_type = "dns-01"
```

**`data/conf/item_backup_cn.toml`** (Aliyun):

```toml
[entry]
name = "backup"
domain = "backup.company.cn"
provider = "aliyun"
challenge_type = "dns-01"
```

### 个性化凭据配置

`data/conf/.env`:

```bash
# Route53 (api-internal)
CERTMAN_ROUTE53_ACCESS_KEY_ID=AKIA5XXXXX...
CERTMAN_ROUTE53_SECRET_ACCESS_KEY=xxxSecret...
CERTMAN_ROUTE53_REGION=us-east-1

# Cloudflare (portal)
CERTMAN_CLOUDFLARE_API_TOKEN=zcDlxxxxx...
CERTMAN_CLOUDFLARE_ZONE_ID=xxxx1111yyyy...

# Aliyun (backup)
CERTMAN_ALIYUN_ACCESS_KEY_ID=LTAI5xxxxx...
CERTMAN_ALIYUN_ACCESS_KEY_SECRET=xxxSecret...
```

### 管理命令

列出所有条目（验证配置）:

```bash
docker compose run --rm certman entries
```

**输出**:

```
[INFO] Registered entries:
  - api-internal: api.internal.com (provider: route53, dns-01)
  - portal: portal.company.com, portal-cn.company.com (provider: cloudflare, dns-01)
  - backup: backup.company.cn (provider: aliyun, dns-01)
```

为某个特定 Provider 的域名申请：

```bash
# 申请 Cloudflare 托管的门户证书
docker compose run --rm certman new --name portal

# 输出示例
[INFO] Requesting certificate for portal
[INFO] Using provider: cloudflare
[INFO] Creating DNS challenge in Cloudflare...
[SUCCESS] Certificate issued
```

统一续签所有域名（跨 Provider）:

```bash
docker compose run --rm certman renew --all

# 会自动按不同 provider 处理：
[INFO] Renewing api-internal (Route53)...
[INFO] Renewing portal (Cloudflare)...
[INFO] Renewing backup (Aliyun)...
```

---

## 场景 5: 证书导出给 Kubernetes Secret

**背景**: Frank 的 K8s 集群中部署了多个应用，需要定期从 certman 导出证书，更新到 K8s Secret 中。

### 导出证书到文件

```bash
# 导出所有域名的证书
docker compose run --rm certman export --all

# 或仅导出特定域名
docker compose run --rm certman export --name api-internal
```

输出位置: `data/output/<entry-name>/`

### K8s Secret 创建脚本

创建 `scripts/update-k8s-secrets.sh`:

```bash
#!/bin/bash
set -e

NAMESPACE="production"
DOMAIN="portal.company.com"

# 1. 导出最新证书
docker compose run --rm certman export --name portal

# 2. 从文件创建 Secret（覆盖旧的）
kubectl delete secret -n $NAMESPACE tls-portal --ignore-not-found
kubectl create secret tls tls-portal \
  --cert=data/output/portal/fullchain.pem \
  --key=data/output/portal/privkey.pem \
  -n $NAMESPACE

# 3. 验证
kubectl get secret -n $NAMESPACE tls-portal -o jsonpath='{.data.tls\.crt}' | base64 -d | openssl x509 -noout -text | grep "Not After"

echo "✓ K8s Secret updated successfully"
```

### 在 CronJob 中定期更新

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: cert-export-to-k8s
  namespace: certman
spec:
  # 每天 03:00 UTC 执行
  schedule: "0 3 * * *"
  jobTemplate:
    spec:
      template:
        spec:
          serviceAccountName: certman-updater
          containers:
          - name: export
            image: nickfan/certman:edge
            volumeMounts:
            - name: data-vol
              mountPath: /app/data
            - name: kubectl-config
              mountPath: /root/.kube
            command: ["/bin/sh", "-c"]
            args:
              - |
                # 导出所有证书
                certman export --all
                
                # 遍历所有导出目录，更新 K8s Secret
                for entry_dir in data/output/*/; do
                  entry_name=$(basename $entry_dir)
                  kubectl delete secret tls-$entry_name -n production --ignore-not-found
                  kubectl create secret tls tls-$entry_name \
                    --cert=$entry_dir/fullchain.pem \
                    --key=$entry_dir/privkey.pem \
                    -n production
                done
                echo "✓ All K8s Secrets updated"
          volumes:
          - name: data-vol
            persistentVolumeClaim:
              claimName: certman-data
          - name: kubectl-config
            secret:
              secretName: kubeconfig
          restartPolicy: OnFailure
```

### 使用导出的证书

K8s Ingress 资源示例：

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: portal-ingress
spec:
  ingressClassName: nginx
  tls:
  - hosts:
    - portal.company.com
    - portal-cn.company.com
    secretName: tls-portal  # 由上述 CronJob 管理
  rules:
  - host: portal.company.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: portal-svc
            port:
              number: 8080
```

---

## 场景 6: 使用 Docker Hub 镜像而非本地 Build

**背景**: Grace 是运维，不想维护本地 Dockerfile，直接使用 Docker Hub 上的预编译镜像 `nickfan/certman:edge`。

### 修改 docker-compose.yml

原配置（本地 build）:

```yaml
services:
  certman:
    build: .
    volumes:
      - ./data:/app/data
    env_file: data/conf/.env
```

新配置（Docker Hub 镜像）:

```yaml
services:
  certman:
    image: nickfan/certman:edge  # 改这行
    pull_policy: always          # 每次运行时拉取最新
    volumes:
      - ./data:/app/data
    env_file: data/conf/.env
```

### 执行命令

之后的所有命令完全相同，只是会从 Docker Hub 拉取镜像：

```bash
# 首次运行会拉取（~200MB）
docker compose run --rm certman config-validate

# 之后的运行会使用本地缓存（秒级启动）
docker compose run --rm certman entries

# 申请证书
docker compose run --rm certman new --name api-demo
```

**优势**:
- 无需维护 Dockerfile
- 自动获得上游最新修复和功能
- CI/CD 环境中镜像统一，降低维护成本

---

## 场景 7: Windows 环境 + Task Scheduler 自动化

**背景**: Henry 在 Windows Server 2022 上部署 certman，希望通过 Windows Task Scheduler 实现每周自动续签。

### 前置准备

1. 安装 Docker Desktop for Windows（带 WSL 或 Hyper-V）
2. 在项目根目录创建 PowerShell 脚本 `renew-certs.ps1`

### 脚本内容

`renew-certs.ps1`:

```powershell
# ============================================
# certman 自动续签脚本 (Windows PowerShell)
# 运行环境: Windows Task Scheduler
# ============================================

# 设置项目路径
$ProjectPath = "C:\Certman"
Set-Location $ProjectPath

# 记录日志
$LogFile = ".\data\log\renew-$(Get-Date -Format 'yyyy-MM-dd_HH-mm-ss').log"

# 日志记录函数
function Log-Message {
    param([string]$Message)
    $Timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    "$Timestamp - $Message" | Tee-Object -FilePath $LogFile -Append
}

Log-Message "=== Certman Auto Renewal Started ==="

try {
    # Step 1: 配置校验
    Log-Message "Step 1: Validating configuration..."
    docker compose run --rm certman config-validate
    if ($LASTEXITCODE -ne 0) {
        Log-Message "ERROR: Config validation failed (exit code $LASTEXITCODE)"
        exit 1
    }
    Log-Message "✓ Configuration valid"

    # Step 2: 检查证书健康
    Log-Message "Step 2: Checking certificate status..."
    docker compose run --rm certman check --warn-days 30 --force-renew-days 7 --fix
    $CheckExitCode = $LASTEXITCODE

    # Step 3: 导出更新的证书
    Log-Message "Step 3: Exporting certificates..."
    docker compose run --rm certman export --all
    if ($LASTEXITCODE -ne 0) {
        Log-Message "ERROR: Export failed"
        exit 1
    }
    Log-Message "✓ Certificates exported"

    # 根据退出码处理
    switch ($CheckExitCode) {
        0 {
            Log-Message "✓ All certificates healthy"
        }
        10 {
            Log-Message "⚠ Warning: Some certificates expire within 30 days"
            # 可选：发送告警邮件
            # Send-MailMessage -From "certman@company.local" -To "ops@company.local" ...
        }
        20 {
            Log-Message "🔴 Some certificates renewed (check output)"
        }
        30 {
            Log-Message "🔴 ERROR: Some certificates are missing"
            exit 1
        }
    }

    Log-Message "=== Certman Auto Renewal Completed Successfully ==="
    exit 0

} catch {
    Log-Message "ERROR: $_"
    exit 1
}
```

### Task Scheduler 配置

1. **打开 Task Scheduler**（Win+R → `taskschd.msc`）

2. **Create Basic Task**:
   - **Name**: `CertMan Auto Renewal`
   - **Description**: `Automatic certificate renewal for HTTPS domains`

3. **Trigger** 选项卡:
   - **Begin the task**: Weekly
   - **Days**: Monday
   - **Time**: 02:00 AM

4. **Action** 选项卡:
   - **Program/script**: `powershell.exe`
   - **Arguments**: `-NoProfile -ExecutionPolicy Bypass -File "C:\Certman\renew-certs.ps1"`
   - **Start in**: `C:\Certman`

5. **Conditions** 选项卡:
   - ✓ Start the task only if the computer is on AC power （可选）
   - ✓ Wake the computer to run this task

6. **Settings** 选项卡:
   - ✓ Run the task as soon as possible after a scheduled start is missed
   - Run time limit: 30 minutes

### 手动测试

```powershell
# PowerShell 中直接运行一次
Set-ExecutionPolicy -ExecutionPolicy Bypass -Scope Process
.\renew-certs.ps1

# 或用 Task Scheduler 的 "Run" 按钮立即执行
```

### 查看日志

```powershell
# 查看最新的日志文件
Get-ChildItem .\data\log\renew-*.log | Sort-Object -Descending | Select-Object -First 1 | Get-Content -Tail 30

# 或追在后面实时查看
Get-Content -Path ".\data\log\renew-latest.log" -Wait
```

### 监控告警集成（可选）

修改脚本加入告警：

```powershell
# 在脚本中添加告警函数
function Send-AlertEmail {
    param([string]$Subject, [string]$Body)
    
    $EmailParams = @{
        From       = "certman@company.local"
        To         = "ops-alert@company.local"
        Subject    = $Subject
        Body       = $Body
        SmtpServer = "mail.company.local"
        Port       = 587
        UseSsl     = $true
        Credential = (New-Object System.Management.Automation.PSCredential(
            "serviceaccount@company.local",
            (ConvertTo-SecureString "svc-password" -AsPlainText -Force)
        ))
    }
    Send-MailMessage @EmailParams
}

# 在错误处理中调用
if ($CheckExitCode -eq 20) {
    Send-AlertEmail -Subject "🔴 Certificates Renewed - Please Verify" `
                    -Body "Some certificates were renewed. Please verify deployment."
}
```

---

## 故障排查指南

### 问题 1: Config validation 失败

**症状**: `docker compose run --rm certman config-validate` 返回错误

**排查步骤**:

```bash
# 1. 检查 TOML 文件是否存在
ls -la data/conf/item_*.toml

# 2. 检查 TOML 语法（在线 TOML 验证器或本地工具）
# 常见错误：缺少引号、括号不匹配、缩进错误

# 3. 检查必填字段
grep -n "name\|domain\|provider" data/conf/item_*.toml

# 4. 查看详细错误日志
docker compose run --rm certman config-validate 2>&1 | head -20
```

**常见原因和解决**:

| 错误信息 | 原因 | 解决方案 |
|--------|------|--------|
| `Entry 'xyz' not found` | 条目文件不存在或命名错误 | 检查 `item_xyz.toml` 是否在 `data/conf/` |
| `Missing field 'domain'` | TOML 中缺少必填字段 | 检查 `[entry]` 字段完整性 |
| `Unknown provider: xxx` | provider 名称拼写错误 | 确保是 `route53`, `cloudflare`, 或 `aliyun` |
| `TOML decode error` | TOML 语法错误 | 用在线验证器检查括号/引号 |

### 问题 2: Provider 凭据错误

**症状**: 申请证书时报错 `Authentication failed` 或 `Access denied`

**排查步骤**:

```bash
# 1. 检查 .env 文件是否存在且有内容
cat data/conf/.env

# 2. 检查环境变量名是否正确（大小写敏感）
grep -i "route53\|cloudflare\|aliyun" data/conf/.env

# 3. 用单条目测试凭据
docker compose run --rm certman new --name api-demo --verbose

# 4. 查看 Let's Encrypt 日志
tail -50 data/log/letsencrypt.log
```

**常见原因和解决**:

| Provider | 变量名检查清单 | 常见错误 |
|---------|---------------|--------|
| **Route53** | `CERTMAN_ROUTE53_ACCESS_KEY_ID`, `CERTMAN_ROUTE53_SECRET_ACCESS_KEY`, `CERTMAN_ROUTE53_REGION` | AK/SK 过期、IAM 权限不足 |
| **Cloudflare** | `CERTMAN_CLOUDFLARE_API_TOKEN`, `CERTMAN_CLOUDFLARE_ZONE_ID` | Token 权限不包含 DNS 修改 |
| **Aliyun** | `CERTMAN_ALIYUN_ACCESS_KEY_ID`, `CERTMAN_ALIYUN_ACCESS_KEY_SECRET` | AK/SK 禁用、RAM 权限缺失 |

**操作示例 - Cloudflare Token 检查**:

```bash
# 验证 Cloudflare Token 有效性
curl -X GET "https://api.cloudflare.com/client/v4/user/tokens/verify" \
  -H "Authorization: Bearer CERTMAN_CLOUDFLARE_API_TOKEN_VALUE" \
  -H "Content-Type: application/json"

# 返回应该是
# {"result": {"id": "...", "status": "active", ...}, "success": true}
```

### 问题 3: 证书文件未出现在预期目录

**症状**: `docker compose run --rm certman new --name api-demo` 成功，但 `data/output/api-demo/` 目录为空或不存在

**排查**:

```bash
# 1. 检查导出目录是否被创建
ls -la data/output/

# 2. 检查证书是否在 Let's Encrypt 缓存目录
ls -la data/run/letsencrypt/live/

# 3. 检查是否有导出错误
docker compose run --rm certman export --name api-demo --verbose

# 4. 检查权限问题
stat data/output/
```

**常见原因**:

- ❌ **导出未触发**: 检查 `new` 命令是否有 `--auto-export` 或 `export` 命令是否单独运行
- ❌ **权限问题**: Docker 容器内的文件所有者可能与主机不同（常见于 Linux）
  ```bash
  # 修复文件权限
  sudo chown -R $(whoami) data/output/
  ```
- ❌ **磁盘满**: 检查 `data/` 分区空间
  ```bash
  df -h data/
  ```

### 问题 4: 续签失败（need renewal）

**症状**: `docker compose run --rm certman renew --all` 返回 exit code 1

**排查步骤**:

```bash
# 1. 检查单条目续签状态
docker compose run --rm certman renew --name api-demo --verbose

# 2. 检查证书有效期
# (预期: 剩余天数 < force-renew-days)
docker compose run --rm certman check --warn-days 30 --force-renew-days 7

# 3. 检查 DNS 验证能否进行
nslookup _acme-challenge.api.demo.com
dig _acme-challenge.api.demo.com +short

# 4. 查看完整日志
tail -100 data/log/letsencrypt.log | grep -i "error\|failed"
```

**常见原因**:

- ❌ **DNS 未更新**: Provider 凭据配置不正确，certman 无法创建 DNS 记录
  - 解决: 检查凭据、IAM 权限、API Token 有效期
- ❌ **DNS 传播延迟**: Let's Encrypt 验证前，DNS 记录未在全球生效
  - 解决: 等待 30-60 秒，或在命令中加 `--delay 60` 参数
- ❌ **Rate Limit**: Let's Encrypt 速率限制（新账户有限额）
  - 解决: 切换到测试环境(`acme_dir = "https://acme-staging-v02..."`)重试

**DNS 验证手动测试**:

```bash
# 以 Cloudflare 为例，检查 TXT 记录是否能被查到
# certman 会自动创建 _acme-challenge.example.com TXT 记录

# 查询 Cloudflare API
curl -X GET "https://api.cloudflare.com/client/v4/zones/ZONE_ID/dns_records?name=_acme-challenge.example.com" \
  -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json"
```

### 问题 5: Windows PowerShell 命令执行权限拒绝

**症状**: `powershell: cannot be loaded because running scripts is disabled on this system`

**解决**:

```powershell
# 临时允许本次 Session 执行脚本
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process

# 然后重新运行脚本
.\renew-certs.ps1

# 永久设置（需要管理员权限）
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser
```

### 问题 6: Docker Compose 找不到容器或镜像

**症状**: `docker compose: command not found` 或 `image not found`

**检查**:

```bash
# 1. 确认 Docker 和 Docker Compose 已安装
docker --version
docker compose version  # 新版本（集成命令）
# 或 docker-compose --version  # 旧版本（独立 CLI）

# 2. 确认在正确目录（包含 docker-compose.yml）
pwd
ls docker-compose.yml

# 3. 如果使用 Docker Hub 镜像，检查是否可拉取
docker pull nickfan/certman:edge
```

### 快速诊断脚本

保存为 `diagnose.sh`:

```bash
#!/bin/bash
echo "=== Certman Diagnostics ==="
echo ""
echo "1. Docker Info:"
docker --version
docker compose version
echo ""
echo "2. Config Files:"
ls -la data/conf/
echo ""
echo "3. Environment Variables:"
grep -i "CERTMAN_" data/conf/.env | sed 's/=.*/=***masked***/g'
echo ""
echo "4. Entries:"
docker compose run --rm certman entries
echo ""
echo "5. Certificate Status:"
docker compose run --rm certman check --warn-days 30 --force-renew-days 7
```

运行诊断:

```bash
bash diagnose.sh 2>&1 | tee diagnostic-report.txt
# 上传 diagnostic-report.txt 给技术支持
```