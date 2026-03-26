# 双 CLI 模式说明（Local + Control Plane Client）

## 1. 为什么要拆分

CertMan 面向两类用户：

1. 本地简单用户：只想完成证书申请、续签、导出与巡检
2. 平台运维用户：需要通过控制面 API 做远程查询与管理

为了降低认知负担，CLI 按职责拆分：

- `certman`：本地运维 CLI（local）
- `certmanctl`：控制面远程客户端 CLI（remote）

## 2. 组件与入口

1. `certman`

- 纯本地命令，延续现有使用习惯

1. `certmanctl`

- 类似 docker 客户端，通过 REST 调用 `certman-server`

1. `certman-server`

- 控制面 API 服务

1. `certman-worker`

- 后台任务执行器

1. `certman-agent`

- 节点代理（注册、轮询、上报）

## 3. 典型部署形态

### 单机原生

- 仅使用 `certman`

### 容器化

- `server + worker` 运行于 compose
- 运维通过 `certmanctl` 调用控制面

### 分布式

- `server + worker + agent`
- 运维与自动化通过 `certmanctl`

## 4. 命令职责边界

### certman（local）

- entries
- new
- renew
- export
- check
- config-validate
- logs-clean

### certmanctl（remote）

- health
- cert create
- job get
- webhook create

## 5. 兼容策略

1. `certman` 保持向后兼容，不破坏旧脚本
2. 远程能力全部进入 `certmanctl`
3. 通过入口拆分避免本地/远程语义冲突

## 6. 当前阶段状态

当前阶段已完成文档与方案冻结，下一阶段进入编码实现与测试核验。

相关计划文档：

- `docs/notes/plans/2026-03-26-dual-cli-program.md`
