# certman-operator iteration-2 benchmark

## Scope

新增 eval 4-6，覆盖异常路径：鉴权失败(401)、job-wait 超时、参数缺失。

## Summary

- with_skill: 9/9 assertions (100.00%)
- without_skill: 3/9 assertions (33.33%)
- delta: +66.67%

## Per eval

| eval | name | with_skill | without_skill | 主要差距 |
|------|------|-----------|--------------|---------|
| 4 | auth-failure-401 | 3/3 | 1/3 | 环境变量名约定不符 |
| 5 | job-wait-timeout | 3/3 | 0/3 | 使用 curl 而非 certmanctl，无 --max-wait |
| 6 | missing-entry-param | 3/3 | 1/3 | 工具名 certman-ctl 错、--url 非 --endpoint |

## Cumulative (two iterations)

- with_skill 总计: 18/18 (100%)
- without_skill 总计: 5/18 (27.8%)
- 累计增益: +72.2%

## Analyst notes

- without_skill 最薄弱点：命令面漂移（curl REST、错误工具名、错误参数名）。
- 当 skill 存在时，这三类偏差完全消失。
- iteration-3 建议：补充 happy-path eval（真实可用控制面），并为 eval-4 补充 CERTMAN_MCP_TOKEN 的文档说明，避免潜在的名称混淆。
