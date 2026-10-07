"""Run the agent over eval/dataset.jsonl and score every case.

Usage:
    python -m eval.run_eval --provider gemini --prompt v2 --judge
    python -m eval.run_eval --provider claude --prompt v1 --ids policy-01,order-02

Writes eval/results/<run_id>.json (every case) and updates eval/results/summary.json
(one line per run) which the /eval page and REPORT.md are built from.
"""

import argparse
import asyncio
import json
import statistics
import time
from datetime import datetime
from pathlib import Path

from langchain_core.messages import AIMessage, ToolMessage

from app.agent.graph import get_graph, to_messages
from app.agent.llm import cost_usd, model_name
from app.agent.prompts import PROMPTS
from eval.checks import Trace, run_checks
from eval.judge import JUDGE_MODEL, judge, make_judge

EVAL_DIR = Path(__file__).resolve().parent
RESULTS = EVAL_DIR / "results"
RATE_LIMIT_WAIT_S = 30


def load_cases(ids: set[str] | None) -> list[dict]:
    with open(EVAL_DIR / "dataset.jsonl", encoding="utf-8") as fh:
        cases = [json.loads(line) for line in fh if line.strip()]
    return [c for c in cases if not ids or c["id"] in ids]


def conversation_text(case: dict) -> str:
    lines = [f"{m['role']}: {m['content']}" for m in case.get("history", [])]
    return "\n".join([*lines, f"user: {case['message']}"])


async def run_case(graph, model: str, prompt: str, case: dict, judge_llm, sem: asyncio.Semaphore) -> dict:
    history = [*case.get("history", []), {"role": "user", "content": case["message"]}]
    messages = to_messages(history)
    async with sem:
        for attempt in range(4):
            t0 = time.perf_counter()
            try:
                out = await graph.ainvoke({"messages": messages, "steps": 0})
                break
            except Exception as e:  # free tiers return 429 under load: wait and retry
                rate_limited = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
                if not rate_limited or attempt == 3:
                    return {"id": case["id"], "category": case["category"], "error": str(e)[:500], "passed": False}
                await asyncio.sleep(RATE_LIMIT_WAIT_S * (attempt + 1))
        latency_ms = round((time.perf_counter() - t0) * 1000)

    turn = out["messages"][len(messages) :]
    ai = [m for m in turn if isinstance(m, AIMessage)]
    tools = [m for m in turn if isinstance(m, ToolMessage)]
    trace = Trace(
        message=case["message"],
        history_text=conversation_text(case),
        answer="\n".join(m.text for m in ai if m.text).strip(),
        tool_calls=[{"name": c["name"], "args": c["args"]} for m in ai for c in m.tool_calls],
        tool_outputs=[m.content if isinstance(m.content, str) else json.dumps(m.content) for m in tools],
        policy_ids=[pid for m in tools for pid in (m.artifact or {}).get("policy_ids", [])],
        handoff=any((m.artifact or {}).get("handoff") for m in tools),
    )
    checks = run_checks(trace, case["expect"])
    tokens_in = sum((m.usage_metadata or {}).get("input_tokens", 0) for m in ai)
    tokens_out = sum((m.usage_metadata or {}).get("output_tokens", 0) for m in ai)
    result = {
        "id": case["id"],
        "category": case["category"],
        "message": case["message"],
        "passed": all(c["pass"] for c in checks.values()),
        "checks": checks,
        "answer": trace.answer,
        "tool_calls": trace.tool_calls,
        # Saved so eval/regrade.py can re-score this run after the checks change, without calling the model again
        "evidence": {"tool_outputs": trace.tool_outputs, "policy_ids": trace.policy_ids, "handoff": trace.handoff},
        "steps": len(ai),
        "latency_ms": latency_ms,
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "cost_usd": cost_usd(model, tokens_in, tokens_out),
    }
    if judge_llm:
        try:
            result["judge"] = await judge(judge_llm, prompt, conversation_text(case), trace.tool_outputs, trace.answer)
        except Exception as e:
            result["judge"] = {"error": str(e)[:300]}
    return result


def summarize(results: list[dict]) -> dict:
    ok = [r for r in results if "error" not in r]
    check_names = sorted({k for r in ok for k in r["checks"]})
    by_check = {}
    for name in check_names:
        scored = [r["checks"][name]["pass"] for r in ok if name in r["checks"]]
        by_check[name] = {"pass_rate": round(sum(scored) / len(scored), 3), "n": len(scored)}
    by_category = {}
    for cat in sorted({r["category"] for r in results}):
        rs = [r for r in results if r["category"] == cat]
        by_category[cat] = {"pass_rate": round(sum(r["passed"] for r in rs) / len(rs), 3), "n": len(rs)}
    judged = [r["judge"] for r in ok if "faithfulness" in r.get("judge", {})]
    costs = [r["cost_usd"] for r in ok if r["cost_usd"] is not None]
    return {
        "n_cases": len(results),
        "errors": len(results) - len(ok),
        "pass_rate": round(sum(r["passed"] for r in results) / len(results), 3),
        "by_check": by_check,
        "by_category": by_category,
        "latency_ms_median": round(statistics.median(r["latency_ms"] for r in ok)) if ok else None,
        "latency_ms_p90": round(statistics.quantiles([r["latency_ms"] for r in ok], n=10)[-1]) if len(ok) > 1 else None,
        "steps_avg": round(statistics.mean(r["steps"] for r in ok), 2) if ok else None,
        "tokens_in_avg": round(statistics.mean(r["input_tokens"] for r in ok)) if ok else None,
        "tokens_out_avg": round(statistics.mean(r["output_tokens"] for r in ok)) if ok else None,
        "cost_usd_avg": round(statistics.mean(costs), 5) if costs else None,
        "judge_faithfulness_avg": round(statistics.mean(j["faithfulness"] for j in judged), 2) if judged else None,
        "judge_helpfulness_avg": round(statistics.mean(j["helpfulness"] for j in judged), 2) if judged else None,
    }


def save_run(summary: dict, results: list[dict]) -> None:
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / f"{summary['run_id']}.json").write_text(
        json.dumps({**summary, "cases": results}, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    if summary["partial"]:
        return
    index_path = RESULTS / "summary.json"
    runs = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else []
    key = (summary["model"], summary["prompt"])
    runs = [r for r in runs if (r["model"], r["prompt"]) != key] + [summary]
    index_path.write_text(json.dumps(runs, indent=2, ensure_ascii=False), encoding="utf-8")


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--provider", choices=["gemini", "claude"], default="gemini")
    ap.add_argument("--model", help="override the model name from settings")
    ap.add_argument("--prompt", choices=sorted(PROMPTS), default="v3")
    ap.add_argument("--judge", action="store_true", help=f"score answers with {JUDGE_MODEL}")
    ap.add_argument("--ids", help="comma-separated case ids")
    ap.add_argument("--concurrency", type=int, default=2)
    args = ap.parse_args()

    model = args.model or model_name(args.provider)
    graph = get_graph(args.provider, args.prompt, args.model)
    cases = load_cases(set(args.ids.split(",")) if args.ids else None)
    judge_llm = make_judge() if args.judge else None
    sem = asyncio.Semaphore(args.concurrency)

    t0 = time.perf_counter()
    results = await asyncio.gather(*(run_case(graph, model, PROMPTS[args.prompt], c, judge_llm, sem) for c in cases))
    run_id = f"{datetime.now():%Y%m%d-%H%M}_{model}_{args.prompt}"
    summary = {
        "run_id": run_id,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "provider": args.provider,
        "model": model,
        "prompt": args.prompt,
        "judge": JUDGE_MODEL if args.judge else None,
        "partial": bool(args.ids),
        "wall_time_s": round(time.perf_counter() - t0),
        **summarize(results),
    }

    save_run(summary, results)
    print(f"\n{run_id}: pass {summary['pass_rate']:.0%} of {summary['n_cases']} ({summary['errors']} errors)")
    for name, c in summary["by_check"].items():
        print(f"  {name:22s} {c['pass_rate']:.0%} (n={c['n']})")
    for r in results:
        if not r["passed"]:
            failed = {k: v["detail"] for k, v in r.get("checks", {}).items() if not v["pass"]}
            print(f"  FAIL {r['id']}: {r.get('error') or failed}")


if __name__ == "__main__":
    asyncio.run(main())
