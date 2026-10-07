"""Add or refresh LLM-judge scores on saved runs, from the saved answers and evidence. The agent is not re-run.

Usage:
    python -m eval.rejudge            # only cases with no judge score yet (or a failed one)
    python -m eval.rejudge --all      # re-score everything, e.g. after changing the judge
"""

import argparse
import asyncio
import json

from app.agent.prompts import PROMPTS
from eval.judge import JUDGE_MODEL, judge, make_judge
from eval.run_eval import RATE_LIMIT_WAIT_S, RESULTS, conversation_text, load_cases, save_run, summarize


async def judge_with_retry(judge_llm, *args) -> dict:
    for attempt in range(4):
        try:
            return await judge(judge_llm, *args)
        except Exception as e:
            rate_limited = "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e)
            if not rate_limited or attempt == 3:
                return {"error": str(e)[:300]}
            await asyncio.sleep(RATE_LIMIT_WAIT_S * (attempt + 1))
    return {"error": "unreachable"}


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--concurrency", type=int, default=2)
    args = ap.parse_args()

    cases = {c["id"]: c for c in load_cases(None)}
    judge_llm = make_judge()
    sem = asyncio.Semaphore(args.concurrency)

    async def one(prompt: str, r: dict) -> None:
        case = cases[r["id"]]
        async with sem:
            r["judge"] = await judge_with_retry(
                judge_llm, prompt, conversation_text(case), r["evidence"]["tool_outputs"], r["answer"]
            )

    for path in sorted(RESULTS.glob("2*.json")):
        run = json.loads(path.read_text(encoding="utf-8"))
        results = run.pop("cases")
        todo = [
            r
            for r in results
            if "error" not in r
            and "evidence" in r
            and r["id"] in cases
            and (args.all or "faithfulness" not in r.get("judge", {}))
        ]
        await asyncio.gather(*(one(PROMPTS[run["prompt"]], r) for r in todo))
        run.update(summarize(results))
        run["judge"] = JUDGE_MODEL
        save_run(run, results)
        failed = sum(1 for r in todo if "error" in r.get("judge", {}))
        print(f"{run['run_id']}: judged {len(todo) - failed}/{len(todo)}, faithfulness {run['judge_faithfulness_avg']}")


if __name__ == "__main__":
    asyncio.run(main())
