# certman-operator iteration-1 benchmark

## Summary

- with_skill: 9/9 assertions (100.00%)
- without_skill: 2/9 assertions (22.22%)
- delta: +77.78%

## Per eval

- eval-1 cert-create-and-job-wait: with_skill 3/3, without_skill 0/3
- eval-2 webhook-update-and-verify: with_skill 3/3, without_skill 1/3
- eval-3 local-check-json-and-renew-decision: with_skill 3/3, without_skill 1/3

## Analyst notes

- with_skill 在三类场景都能稳定命中 certman/certmanctl 命令面，且错误分类可消费。
- without_skill 容易出现接口面漂移（例如 curl PATCH 或不存在的 CLI 参数）。
- 本 benchmark 统计的是断言通过率，不代表多次重复运行统计。
- 下一轮重点：把时间/Token 指标纳入自动采集，减少仅靠结构化质量打分带来的偏差。
