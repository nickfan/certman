#!/usr/bin/env python3
"""
aggregate_timing.py — 从各 eval 目录的 timing.json 聚合到 benchmark.json

用法：
    uv run python docs/skills/certman-operator-workspace/aggregate_timing.py \
        --iteration 3
"""
import argparse
import json
import statistics
from pathlib import Path

WORKSPACE = Path(__file__).parent


def aggregate(iteration: int):
    iter_dir = WORKSPACE / f"iteration-{iteration}"
    benchmark_path = iter_dir / "benchmark.json"

    if not benchmark_path.exists():
        print(f"benchmark.json not found in {iter_dir}")
        return

    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))

    for mode in ("with_skill", "without_skill"):
        tokens_list = []
        durations_list = []

        for eval_dir in sorted(iter_dir.glob("eval-*")):
            timing_path = eval_dir / mode / "timing.json"
            if timing_path.exists():
                t = json.loads(timing_path.read_text(encoding="utf-8"))
                tokens_list.append(t.get("total_tokens", 0))
                durations_list.append(t.get("duration_seconds", 0.0))

        if tokens_list:
            benchmark["summary"][mode]["avg_tokens"] = round(statistics.mean(tokens_list))
            benchmark["summary"][mode]["avg_duration_seconds"] = round(statistics.mean(durations_list), 3)
            print(f"  {mode}: avg_tokens={benchmark['summary'][mode]['avg_tokens']}  "
                  f"avg_duration={benchmark['summary'][mode]['avg_duration_seconds']}s  "
                  f"({len(tokens_list)} evals)")

    benchmark_path.write_text(json.dumps(benchmark, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"benchmark.json updated → {benchmark_path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--iteration", type=int, required=True)
    args = parser.parse_args()
    aggregate(args.iteration)


if __name__ == "__main__":
    main()
