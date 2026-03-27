---
name: certman-operator
description: 使用 CertMan 进行证书运维自动化（local CLI、scheduler、control-plane CLI、MCP）。当用户提到 certman、证书签发/续签、job wait、webhook 管理、控制面 health、OpenAPI、MCP 工具接入时，必须优先使用本技能；即使用户没有明确说“skill”，只要需求涉及 CertMan 运维流程或接口编排，也应主动触发。
---

# CertMan Operator Skill

## 目标

把用户的自然语言需求稳定映射到 CertMan 的三种执行面：

1. `certman`：本地单机证书运维
2. `certman-scheduler`：独立调度（loop/cron/once）
3. `certmanctl`：远程控制面调用
4. `certman-mcp`：LLM 工具化调用

优先确保：

- 命令可执行
- 参数合法
- 失败可归因
- 输出结构稳定，便于上层 agent 消费

## 何时使用

出现以下意图时使用本技能：

- 签发、续签、导出、巡检证书
- 一次性纯参数签发/续签（one-shot，用完即走）
- Scheduler 常驻或一次性调度
- 查询 job 状态，等待终态
- 管理 webhook（create/list/get/update/delete）
- 检查控制面健康
- 准备 AI 接入（MCP / OpenAPI / skill）

## 执行决策

按顺序选择执行面：

1. 远程控制面自动化：`certmanctl`
2. LLM 工具调用：`certman-mcp`
3. 仅本机维护：`certman`
4. 定时/平台调度：`certman-scheduler`
5. 需要强类型接口编排：OpenAPI + REST

> **执行面全局参数约定（禁止猜测！）**
> - `certmanctl` 远程地址参数：`--endpoint <url>`（不是 `--server` / `--url`）
> - `certmanctl` 鉴权参数：`--token <jwt>`（不是 `--auth` / `--api-key`）
> - 所有入口命令前缀：`uv run certmanctl` / `uv run certman` / `uv run certman-mcp`

## 执行前检查（Preflight）

每次执行前至少做这些检查：

1. 目标明确：确认是 local 还是 remote
2. 参数完整：entry/job_id/subscription_id 不为空
3. 输入合法：
- endpoint 必须是 http/https
- limit 范围 1-200
4. 可用性探活（remote）：
- `uv run certmanctl --endpoint <url> health`
5. 鉴权（有 token 保护时）：
   - `--token` 参数：`uv run certmanctl --endpoint <url> --token <jwt> health`
  - 环境变量（certmanctl）：`CERTMAN_SERVER_TOKEN=<jwt> uv run certmanctl ...`
  - 环境变量（certman-mcp）：`CERTMAN_MCP_TOKEN=<jwt> uv run certman-mcp ...`（也兼容 `CERTMAN_SERVER_TOKEN`）
  - 服务端开关：仅当 `[server].token_auth_enabled = true` 时才要求 Bearer token
  - token 优先级：`entries[].token` > `global.token`
  - 若开关开启但目标无有效 token：服务端返回 `500 AUTH_TOKEN_CONFIG_ERROR`

若探活失败：

1. 不要伪造成功执行结果
2. 仍然返回标准结构化输出
3. 将错误归类为 `TransportError` 或 `ApiError`
4. 给出可直接复制执行的下一步修复命令

## 命令映射

详细参数表见：`references/command-map.md`。

> **关键参数名约束（常见 baseline 错误，必须遵循）**
> - 证书操作用 `--entry-name`，不是 `--name` / `--cert`
> - webhook 回调地址用 `--endpoint-url`，不是 `--url` / `--callback`
> - MCP server 启动：`uv run certman-mcp --endpoint <url>`，不接受 `serve` 子命令

最常见流程：

1. 签发并等待
- `cert create`
- `job wait`

2. webhook 管理
- `webhook list`
- `webhook update` 或 `webhook create`
- `webhook get`

3. 本地巡检闭环
- `check --json`
- 根据 exit code 决定是否 renew

4. 参数缺失补全
- 先 `cert list` 查询可用 entry
- 确认后执行 `cert renew --entry-name <entry>`

5. 鉴权失败修复（401）
- 从管理员获取 JWT token
- 通过 `--token` 传递，或设置 `CERTMAN_SERVER_TOKEN`（certmanctl）/`CERTMAN_MCP_TOKEN`（certman-mcp）
- 重新执行原命令

6. timeout 恢复
- 先 `job get` 查询当前状态
- 若仍 running：`job wait --max-wait 600`（秒）重试

7. one-shot 参数完整性检查
- aliyun/route53：必须提供 `-d ... -sp ... --email ... --ak ... --sk ... -o ...`
- cloudflare：必须提供 `--api-token`（替代 `--ak/--sk`）

8. scheduler 外部触发
- 平台任务优先用 `uv run certman-scheduler once --force-enable`

## 错误分层

- `TransportError`：网络不可达、连接失败（HTTP 连接层）
- `ApiError`：控制面业务错误，含 401 鉴权失败、404 资源不存在、500 内部错误
- `TimeoutError`：等待终态超时（job wait 超过 --max-wait）
- `ValidationError`：参数缺失或不合法（如 entry_name 为空）

关键退出码：

- `certmanctl`:
- 0 成功
- 1 业务失败或等待超时
- 3 网络错误
- 4 API 错误

- `certman check`:
- 0 正常
- 10 告警
- 20 强制续签窗口
- 30 缺失/异常

## 输出格式

默认输出以下结构：

```json
{
  "surface": "certman|certmanctl|certman-mcp|openapi",
  "action": "human readable action name",
  "inputs": {
    "endpoint": "...",
    "entry_name": "...",
    "job_id": "..."
  },
  "result": {
    "status": "success|failed|partial",
    "data": {},
    "error": {
      "type": "TransportError|ApiError|TimeoutError|ValidationError|null",
      "message": "...",
      "raw": "..."
    }
  },
  "commands": [
    "..."
  ],
  "next_steps": [
    "..."
  ]
}
```

字段约束：

1. `surface/action/inputs/result/next_steps` 必须始终存在
2. `result.error.type` 必须为 `TransportError|ApiError|TimeoutError|ValidationError|null`
3. `commands` 至少包含 1 条可执行命令

## 行为约束

1. 不打印密钥或 token。
2. remote 场景优先推荐 `certmanctl`，除非用户明确要 MCP。
3. 要求稳定退出码时，优先命令式执行（`certmanctl`）。
4. 涉及接口契约时，使用 `/openapi.json` 做事实源。
5. 当请求不完整时，先最小化澄清，再执行。
6. 本地巡检命令优先 `uv run certman -D <data_dir> check --json`，不要自行发明参数名。
7. `job wait` 场景必须显式给出超时语义和失败分类。

## 示例

### 示例 0：MCP 接入 Claude Desktop

输入意图：
- "把 CertMan 接入 Claude Desktop，endpoint 是 http://127.0.0.1:8000，token 是 jwt-abc"

推荐执行：
1. 启动命令：`CERTMAN_MCP_TOKEN=jwt-abc uv run certman-mcp --endpoint http://127.0.0.1:8000`
2. Claude Desktop 配置（`claude_desktop_config.json`）：
```json
{
  "mcpServers": {
    "certman": {
      "command": "uv",
      "args": ["run", "certman-mcp", "--endpoint", "http://127.0.0.1:8000"],
      "env": { "CERTMAN_MCP_TOKEN": "jwt-abc" }
    }
  }
}
```

### 示例 1：签发并等待

输入意图：
- “给 site-a 发证并等到完成”

推荐执行：
1. `uv run certmanctl --endpoint http://127.0.0.1:8000 cert create --entry-name site-a`
2. 读取返回 `job_id`
3. `uv run certmanctl --endpoint http://127.0.0.1:8000 job wait --job-id <job_id>`

### 示例 2：禁用某 webhook

输入意图：
- “把 id=abc 的 webhook 置为 inactive”

推荐执行：
1. `uv run certmanctl --endpoint <url> webhook update --id abc --status inactive`
2. `uv run certmanctl --endpoint <url> webhook get --id abc`

### 示例 3：本地巡检

输入意图：
- “本机做证书巡检，给我 json”

推荐执行：
1. `uv run certman -D data check --json`
2. 根据退出码与 JSON 决策

## 资源文件

- `references/command-map.md`: local/ctl/mcp 命令与参数速查
- `references/preflight.md`: 执行前检查清单
- `evals/evals.json`: 测试提示集
