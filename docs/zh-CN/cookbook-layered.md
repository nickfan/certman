# 三层场景手册（CLI / Agent / Service）

本手册以真实运维场景编排，统一采用：场景目标 -> 操作步骤 -> 验证结果 -> 常见坑。

## 场景 1：新域名首次接入（CLI）

目标：给 site-a 首次签发证书并落地到交付目录。

操作：

1. 准备条目文件 data/conf/item_site_a.toml（primary_domain + dns_provider）。
2. 运行配置校验。
3. 执行 new。
4. 执行 export。

```bash
uv run certman -D data config-validate
uv run certman -D data new --name site-a --verbose
uv run certman -D data export --name site-a
```

验证：

- data/output/site-a/fullchain.pem 存在
- data/output/site-a/privkey.pem 存在

常见坑：

- 忘记在 .env 写 account_id 对应变量。
- `acme_server=prod` 时会触发真实频控，调试阶段建议 staging。

## 场景 2：每天巡检，不自动修复（CLI）

目标：仅通过退出码驱动监控告警。

操作：

```bash
uv run certman -D data check --warn-days 30 --force-renew-days 7
```

退出码含义：

- 0：正常
- 10：进入告警窗口
- 20：进入强制续签窗口或已过期
- 30：证书文件缺失或条目缺失

验证：

- data/log/check-*.json 存在并包含 results。

常见坑：

- 只看终端输出不看退出码，导致监控漏报。

## 场景 3：控制面统一提交任务（Service）

目标：业务系统仅调 API，不直接碰证书执行细节。

操作：

1. 启动 server + worker。
2. API 提交 issue 任务。
3. 轮询 job 状态。

```bash
uv run certman-server -D data
uv run certman-worker -D data --loop --interval-seconds 15

curl -X POST http://127.0.0.1:8000/api/v1/certificates \
  -H "content-type: application/json" \
  -d '{"entry_name":"site-a"}'

curl http://127.0.0.1:8000/api/v1/jobs/<job_id>
```

验证：

- job 状态从 queued -> running -> completed/failed。

常见坑：

- server 与 worker 使用不同 db_path，导致 worker 看不到任务。

## 场景 4：防止重复续签任务堆积（Service）

目标：定时调度高频触发时，避免同一 entry 产生重复 queued 任务。

操作建议：

- 统一通过服务层 unique enqueue 入口提交 renew 任务。
- 保持 job 唯一索引迁移已执行（003 migration）。

验证：

- 同一 subject_id 的 renew 在 queued/running 阶段最多一条。

常见坑：

- 直接绕过 service 自写 SQL 插入，破坏唯一性约束策略。

## 场景 5：受控节点拉取任务（Agent）

目标：在边缘节点上以签名方式领取任务。

操作：

1. 预注册 node-a（active + 公钥）。
2. 节点执行：

```bash
uv run certman-agent -D data --once
```

验证：

- poll 返回 assignments。
- 控制面将任务绑定给 node-a（node_id 被写入 job）。

常见坑：

- 节点私钥与控制面登记公钥不匹配，导致 401。

## 场景 6：节点回传任务结果（Agent -> Service）

目标：节点执行后回写 completed/failed，且具备防重放。

操作要点：

- result 签名覆盖 job_id/status/output/error。
- 使用一次性 nonce，重复提交会返回 409。
- 仅 running 状态任务可更新结果。

验证：

- job 最终状态可被 /api/v1/jobs/{job_id} 查询到。

常见坑：

- 节点重复上报同一请求体（同 nonce），被拒绝属正常安全行为。

## 场景 7：Webhooks 通知外部系统（Service）

目标：任务完成后自动通知外部平台。

操作：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/webhooks \
  -H "content-type: application/json" \
  -d '{"topic":"job.completed","endpoint":"https://ops.example.com/hook","secret":"topsecret"}'
```

验证：

- 外部系统收到签名回调。
- 失败投递可在服务日志中追踪。

常见坑：

- endpoint 不可达或证书校验失败，需先做连通性演练。
