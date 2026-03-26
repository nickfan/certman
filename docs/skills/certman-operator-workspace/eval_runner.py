#!/usr/bin/env python3
"""
certman-operator eval runner（计时 + token 统计模板）

用法：
    uv run python docs/skills/certman-operator-workspace/eval_runner.py \
        --eval-id 7 \
        --mode with_skill \
        --iteration 3

运行前需设置环境变量（任选其一接入真实模型 API）：
    export OPENAI_API_KEY=...
    export ANTHROPIC_API_KEY=...

输出：
    timing.json → 写入对应 eval 目录
    并更新 benchmark.json 中 avg_tokens / avg_duration_seconds
"""
import argparse
import json
import time
from pathlib import Path

WORKSPACE = Path(__file__).parent
SKILL_DIR = WORKSPACE.parent / "certman-operator"


def load_eval(eval_id: int) -> dict:
    evals_path = SKILL_DIR / "evals" / "evals.json"
    data = json.loads(evals_path.read_text(encoding="utf-8"))
    for ev in data["evals"]:
        if ev["id"] == eval_id:
            return ev
    raise ValueError(f"eval_id={eval_id} not found")


def load_skill_md() -> str:
    return (SKILL_DIR / "SKILL.md").read_text(encoding="utf-8")


def build_system_prompt(mode: str) -> str:
    if mode == "with_skill":
        skill_content = load_skill_md()
        return f"你是已加载 certman-operator SKILL 的 AI 助手。\n\n---SKILL---\n{skill_content}\n---END SKILL---"
    else:
        return (
            "你是一个通用 AI 助手（baseline 模式，没有任何 certman 专项知识）。"
            "背景：CertMan 是证书管理工具，有 certman(local)、certmanctl(remote)、certman-mcp(MCP) 三种 CLI。"
        )


def run_with_openai(system: str, user_prompt: str) -> tuple[str, int, int]:
    """返回 (response_text, input_tokens, output_tokens)"""
    import openai  # type: ignore

    client = openai.OpenAI()
    t0 = time.perf_counter()
    resp = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user_prompt},
        ],
        temperature=0,
    )
    elapsed = time.perf_counter() - t0
    text = resp.choices[0].message.content
    usage = resp.usage
    return text, usage.prompt_tokens, usage.completion_tokens, elapsed


def run_with_anthropic(system: str, user_prompt: str) -> tuple[str, int, int, float]:
    """返回 (response_text, input_tokens, output_tokens, elapsed_seconds)"""
    import anthropic  # type: ignore

    client = anthropic.Anthropic()
    t0 = time.perf_counter()
    resp = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=4096,
        system=system,
        messages=[{"role": "user", "content": user_prompt}],
    )
    elapsed = time.perf_counter() - t0
    text = resp.content[0].text
    return text, resp.usage.input_tokens, resp.usage.output_tokens, elapsed


def grade(output_text: str, assertions: list[str]) -> list[dict]:
    """
    简单关键词匹配评分（可替换为 LLM-as-judge）。
    真实部署时建议用一个独立 LLM 调用做断言判断。
    """
    results = []
    for i, assertion in enumerate(assertions, start=1):
        # 启发式：断言文本中包含的关键词是否出现在输出
        keywords = [w for w in assertion.replace("，", " ").split() if len(w) > 2]
        passed = any(kw.lower() in output_text.lower() for kw in keywords)
        results.append({
            "id": i,
            "text": assertion,
            "pass": passed,
            "reason": "keyword match (heuristic)" if passed else "keyword not found (heuristic)",
        })
    return results


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--eval-id", type=int, required=True)
    parser.add_argument("--mode", choices=["with_skill", "without_skill"], required=True)
    parser.add_argument("--iteration", type=int, required=True)
    parser.add_argument("--provider", choices=["openai", "anthropic"], default="anthropic")
    args = parser.parse_args()

    ev = load_eval(args.eval_id)
    system = build_system_prompt(args.mode)
    user_prompt = ev["prompt"]

    print(f"Running eval-{args.eval_id} [{args.mode}] via {args.provider} ...")

    if args.provider == "openai":
        text, inp_tok, out_tok, elapsed = run_with_openai(system, user_prompt)
    else:
        text, inp_tok, out_tok, elapsed = run_with_anthropic(system, user_prompt)

    total_tokens = inp_tok + out_tok

    grading_results = grade(text, ev["assertions"])
    passed = sum(1 for r in grading_results if r["pass"])

    # Output files
    iter_dir = WORKSPACE / f"iteration-{args.iteration}" / f"eval-{args.eval_id}" / args.mode
    iter_dir.mkdir(parents=True, exist_ok=True)

    output = {
        "surface": "certmanctl",
        "action": f"eval-{args.eval_id}",
        "inputs": {"prompt": user_prompt},
        "result": {"status": "success", "data": {"response": text}, "error": {"type": None, "message": None, "raw": None}},
        "commands": [],
        "next_steps": [],
    }
    (iter_dir / "output.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    grading = {
        "eval_id": args.eval_id,
        "mode": args.mode,
        "assertions": grading_results,
        "passed": passed,
        "total": len(ev["assertions"]),
    }
    (iter_dir / "grading.json").write_text(json.dumps(grading, ensure_ascii=False, indent=2), encoding="utf-8")

    timing = {
        "eval_id": args.eval_id,
        "mode": args.mode,
        "provider": args.provider,
        "input_tokens": inp_tok,
        "output_tokens": out_tok,
        "total_tokens": total_tokens,
        "duration_seconds": round(elapsed, 3),
    }
    (iter_dir / "timing.json").write_text(json.dumps(timing, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"  passed={passed}/{len(ev['assertions'])}  tokens={total_tokens}  duration={elapsed:.2f}s")
    print(f"  output  → {iter_dir}/output.json")
    print(f"  grading → {iter_dir}/grading.json")
    print(f"  timing  → {iter_dir}/timing.json")


if __name__ == "__main__":
    main()
