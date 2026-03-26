# Iteration-3 Benchmark Report

**Skill**: certman-operator  
**Iteration**: 3  
**Scope**: 新执行面 — MCP 接入 / 证书查询流 / webhook 创建  
**Date**: 2026-03-26

---

## 本轮结果

| 模式 | 通过断言 | 总断言 | 通过率 |
|------|----------|--------|--------|
| with_skill | 9 | 9 | **100%** |
| without_skill | 4 | 9 | **44.4%** |
| **delta** | | | **+55.6%** |

---

## 逐评测明细

| eval_id | 场景 | with_skill | without_skill | baseline 失分原因 |
|---------|------|-----------|---------------|------------------|
| 7 | mcp-server-setup | 3/3 ✅ | 1/3 ❌ | `certman-mcp serve` 子命令不存在；环境变量名猜错 `CERTMAN_TOKEN` |
| 8 | cert-list-and-get | 3/3 ✅ | 1/3 ❌ | `--name` 而非 `--entry-name`；缺少 `result.data` envelope |
| 9 | webhook-create-verify | 3/3 ✅ | 2/3 ❌ | `--url` 而非 `--endpoint-url` |

---

## 三轮累计汇总

| 轮次 | 场景数 | with_skill 通过率 | without_skill 通过率 | delta |
|------|--------|-----------------|---------------------|-------|
| iteration-1 | 3 | 100% (9/9) | 22.2% (2/9) | +77.8% |
| iteration-2 | 3 | 100% (9/9) | 33.3% (3/9) | +66.7% |
| iteration-3 | 3 | 100% (9/9) | 44.4% (4/9) | +55.6% |
| **累计** | **9** | **100% (27/27)** | **33.3% (9/27)** | **+66.7%** |

---

## Baseline 失分模式归因

| 失分模式 | 出现次数（3轮18条baseline断言） | 示例 |
|---------|-------------------------------|------|
| 工具面参数名漂移 | 6 | `--url` / `--name` / `--server` 等非规范名 |
| 工具名/命令错误 | 4 | `certman-ctl` / `certman-mcp serve` / `curl` |
| 环境变量名猜错 | 3 | `CERTMAN_TOKEN` / `CERTMAN_API_TOKEN` |
| 缺少 `uv run` 前缀 | 2 | 直接 `certmanctl` 而非 `uv run certmanctl` |
| 缺少输出 envelope | 2 | `result.data` 字段缺失 |
| 其他 | 1 | `--max-wait` 参数缺失 |

---

## 结论

- **SKILL 对所有已测场景（9 evals / 27 断言）稳定 100% 通过**，经 3 轮迭代无退化。
- baseline 核心问题：**参数名无法从通用知识推断**，需要 SKILL 提供精确命令映射。
- SKILL v3 已覆盖参数规范，v4 考虑针对 `--endpoint` 全局标志做更显式的约束说明。
