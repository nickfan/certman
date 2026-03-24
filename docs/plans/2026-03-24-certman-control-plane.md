# CertMan Control Plane Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将当前 CLI 型 certman 演进为支持本地自治模式与中心控制平面模式的跨环境证书管理系统。

**Architecture:** 保留现有 certbot/provider/config/export/check 执行内核，向上抽取 service 层，再新增 server、agent、scheduler、security、delivery 组件。先做单进程模块化，再做多入口，再做远端节点通信与安全分发。

**Tech Stack:** Python 3.12, Typer, FastAPI, Pydantic, Uvicorn, APScheduler or equivalent, cryptography, httpx, pytest

---

## Phase 0: 边界与配置模型定稿

### Task 1: 固化运行模式配置模型

**Files:**
- Modify: certman/config.py
- Modify: certman/config_merge.py
- Test: tests/test_config_modes.py

**Step 1: Write the failing test**

覆盖以下场景：

1. 本地模式配置能正常加载
2. 节点模式配置能正常加载
3. 缺失 control plane endpoint 时节点模式报错
4. 缺失私钥路径或节点身份配置时报错

**Step 2: Run test to verify it fails**

Run: pytest tests/test_config_modes.py -q
Expected: FAIL

**Step 3: Write minimal implementation**

在 config.py 中新增：

1. run_mode: local | agent | server
2. control_plane 配置块
3. node_identity 配置块
4. hooks 配置块

**Step 4: Run test to verify it passes**

Run: pytest tests/test_config_modes.py -q
Expected: PASS

### Task 2: 定义统一领域模型

**Files:**
- Create: certman/models/__init__.py
- Create: certman/models/certificate.py
- Create: certman/models/job.py
- Create: certman/models/node.py
- Test: tests/test_models.py

**Step 1: Write the failing test**

验证 Certificate、Job、NodeIdentity 的最小构造与序列化。

**Step 2: Run test to verify it fails**

Run: pytest tests/test_models.py -q
Expected: FAIL

**Step 3: Write minimal implementation**

新增 Pydantic 模型，字段与设计文档对齐。

**Step 4: Run test to verify it passes**

Run: pytest tests/test_models.py -q
Expected: PASS

---

## Phase 1: 抽取 CLI 核心服务层

### Task 3: 抽取证书生命周期服务

**Files:**
- Create: certman/services/cert_service.py
- Modify: certman/cli.py
- Test: tests/test_cert_service.py

**Step 1: Write the failing test**

测试 issue、renew、check 对现有 runner/provider 的编排行为。

**Step 2: Run test to verify it fails**

Run: pytest tests/test_cert_service.py -q
Expected: FAIL

**Step 3: Write minimal implementation**

从 cli.py 提取：

1. new
2. renew
3. check

**Step 4: Run test to verify it passes**

Run: pytest tests/test_cert_service.py -q
Expected: PASS

### Task 4: 抽取导出与 hook 服务

**Files:**
- Create: certman/services/export_service.py
- Create: certman/hooks/runner.py
- Modify: certman/cli.py
- Test: tests/test_export_service.py
- Test: tests/test_hook_runner.py

**Step 1: Write the failing test**

验证：

1. export 到文件系统
2. hook 命令执行
3. hook 执行失败时能正确记录

**Step 2: Run test to verify it fails**

Run: pytest tests/test_export_service.py tests/test_hook_runner.py -q
Expected: FAIL

**Step 3: Write minimal implementation**

新增 export_service 与 hook runner。

**Step 4: Run test to verify it passes**

Run: pytest tests/test_export_service.py tests/test_hook_runner.py -q
Expected: PASS

---

## Phase 2: 节点模式（Agent）

### Task 5: 建立节点模式入口

**Files:**
- Create: certman/node_agent/__init__.py
- Create: certman/node_agent/agent.py
- Create: certman/node_agent/poller.py
- Modify: pyproject.toml
- Test: tests/test_agent_mode.py

**Step 1: Write the failing test**

验证 agent 能加载节点配置并启动空轮询。

**Step 2: Run test to verify it fails**

Run: pytest tests/test_agent_mode.py -q
Expected: FAIL

**Step 3: Write minimal implementation**

新增 certman-agent 入口与基础 poller。

**Step 4: Run test to verify it passes**

Run: pytest tests/test_agent_mode.py -q
Expected: PASS

### Task 6: 实现节点任务执行器

**Files:**
- Create: certman/node_agent/executor.py
- Create: certman/delivery/filesystem.py
- Create: certman/delivery/k8s.py
- Test: tests/test_node_executor.py

**Step 1: Write the failing test**

验证节点收到任务后能：

1. 落地文件
2. 执行 hook
3. 返回成功/失败结果

**Step 2: Run test to verify it fails**

Run: pytest tests/test_node_executor.py -q
Expected: FAIL

**Step 3: Write minimal implementation**

实现 delivery executor，先支持 filesystem，再预留 k8s。

**Step 4: Run test to verify it passes**

Run: pytest tests/test_node_executor.py -q
Expected: PASS

---

## Phase 3: 控制平面 API

### Task 7: 建立 server 入口与基础 API

**Files:**
- Create: certman/api/app.py
- Create: certman/api/routes/health.py
- Create: certman/api/routes/certificates.py
- Create: certman/server.py
- Modify: pyproject.toml
- Test: tests/test_api_health.py

**Step 1: Write the failing test**

验证 /health 与基础 certificate list 接口。

**Step 2: Run test to verify it fails**

Run: pytest tests/test_api_health.py -q
Expected: FAIL

**Step 3: Write minimal implementation**

新增 FastAPI app 与 certman-server 入口。

**Step 4: Run test to verify it passes**

Run: pytest tests/test_api_health.py -q
Expected: PASS

### Task 8: 增加任务模型与异步执行语义

**Files:**
- Create: certman/services/job_service.py
- Create: certman/api/routes/jobs.py
- Test: tests/test_job_service.py

**Step 1: Write the failing test**

验证长任务统一返回 job_id 且可查询状态。

**Step 2: Run test to verify it fails**

Run: pytest tests/test_job_service.py -q
Expected: FAIL

**Step 3: Write minimal implementation**

先用内存 job store 实现最小闭环。

**Step 4: Run test to verify it passes**

Run: pytest tests/test_job_service.py -q
Expected: PASS

---

## Phase 4: 安全分发

### Task 9: 增加节点身份与消息签名

**Files:**
- Create: certman/security/identity.py
- Create: certman/security/signing.py
- Test: tests/test_signing.py

**Step 1: Write the failing test**

验证：

1. 节点身份加载
2. 消息签名
3. 验签失败分支

**Step 2: Run test to verify it fails**

Run: pytest tests/test_signing.py -q
Expected: FAIL

**Step 3: Write minimal implementation**

加入 detached signature 机制。

**Step 4: Run test to verify it passes**

Run: pytest tests/test_signing.py -q
Expected: PASS

### Task 10: 增加证书包内容加密

**Files:**
- Create: certman/security/envelope.py
- Test: tests/test_envelope.py

**Step 1: Write the failing test**

验证信封加密、解密、错误密钥分支。

**Step 2: Run test to verify it fails**

Run: pytest tests/test_envelope.py -q
Expected: FAIL

**Step 3: Write minimal implementation**

实现 bundle 内容加密与解密。

**Step 4: Run test to verify it passes**

Run: pytest tests/test_envelope.py -q
Expected: PASS

---

## Phase 5: Scheduler 与 Webhook

### Task 11: 统一计划任务调度入口

**Files:**
- Create: certman/scheduler/jobs.py
- Create: certman/worker.py
- Test: tests/test_scheduler_jobs.py

**Step 1: Write the failing test**

验证：

1. 到期扫描
2. 自动续签任务生成
3. 分发补偿任务生成

**Step 2: Run test to verify it fails**

Run: pytest tests/test_scheduler_jobs.py -q
Expected: FAIL

**Step 3: Write minimal implementation**

先实现单进程 scheduler，后续再抽离外部队列。

**Step 4: Run test to verify it passes**

Run: pytest tests/test_scheduler_jobs.py -q
Expected: PASS

### Task 12: 实现 webhook 服务

**Files:**
- Create: certman/services/webhook_service.py
- Create: certman/api/routes/webhooks.py
- Test: tests/test_webhook_service.py

**Step 1: Write the failing test**

验证：

1. 订阅创建
2. 事件签名
3. 重试策略

**Step 2: Run test to verify it fails**

Run: pytest tests/test_webhook_service.py -q
Expected: FAIL

**Step 3: Write minimal implementation**

加入最小 webhook 发布与重试逻辑。

**Step 4: Run test to verify it passes**

Run: pytest tests/test_webhook_service.py -q
Expected: PASS

---

## Phase 6: 文档与部署

### Task 13: 更新 README 与运行示例

**Files:**
- Modify: README.md
- Modify: Dockerfile
- Modify: docker-compose.yml

**Step 1: 增加三种入口说明**

说明：

1. certman 本地模式
2. certman-agent 节点模式
3. certman-server 控制面模式

**Step 2: 增加运行示例**

覆盖：

1. 本地签发
2. 节点绑定控制面
3. webhook 本地 hook 示例

**Step 3: 校验示例命令**

Run: uv run certman --help
Run: uv run certman-agent --help
Run: uv run certman-server --help

Expected: 所有入口可显示帮助信息

---

## 验收标准

1. 现有 CLI 本地模式不回归
2. 新增 agent 模式可以拉取任务、落地证书、执行 hook
3. 新增 server 模式可以提交证书任务与查询 job
4. 证书分发链路带签名与内容加密
5. 本地与中心模式共用同一执行内核
6. scheduler、webhook、hook runner 均具备可测试最小闭环

---

## 推荐执行顺序

1. Phase 0
2. Phase 1
3. Phase 2
4. Phase 3
5. Phase 4
6. Phase 5
7. Phase 6

控制风险的关键是先把“统一内核”与“agent 模式”打稳，再向外扩展控制平面与安全分发。