# Iteration 1 Review

## 结论

- 当前 certman-operator skill 能显著提升执行面选择一致性与输出可消费性。
- 在三个代表性场景中，with_skill 相比 baseline 的断言通过率提升明显。

## 主要提升点

- 统一输出协议：surface/action/inputs/result/next_steps
- 统一错误枚举：TransportError/ApiError/TimeoutError/ValidationError/null
- 统一命令面：remote 用 certmanctl，local 用 certman

## 仍需优化

- 暂未采集稳定 token/duration 指标
- 真实服务联通下的端到端校验样本不足

## iteration-2 建议

1. 接入 timing 自动采集（每个 run 的 total_tokens/duration_ms）。
2. 新增异常路径 eval：认证失败、timeout、参数缺失。
3. 在可用环境中补真实执行证据（command stdout/stderr 片段）。
