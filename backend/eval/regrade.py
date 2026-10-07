"""Re-score saved runs with the current checks and dataset expectations. No model is called.

Use after fixing a grader bug: `python -m eval.regrade`. LLM-judge scores are kept as they were.
"""

import json

from eval.checks import Trace, run_checks
from eval.run_eval import RESULTS, conversation_text, load_cases, save_run, summarize


def main() -> None:
    cases = {c["id"]: c for c in load_cases(None)}
    for path in sorted(RESULTS.glob("2*.json")):
        if path.name == "summary.json":
            continue
        run = json.loads(path.read_text(encoding="utf-8"))
        results = run.pop("cases")
        for r in results:
            if "error" in r or "evidence" not in r or r["id"] not in cases:
                continue
            case = cases[r["id"]]
            trace = Trace(
                message=case["message"],
                history_text=conversation_text(case),
                answer=r["answer"],
                tool_calls=r["tool_calls"],
                **r["evidence"],
            )
            r["checks"] = run_checks(trace, case["expect"])
            r["passed"] = all(c["pass"] for c in r["checks"].values())
        run.update(summarize(results))
        save_run(run, results)
        print(f"{run['run_id']}: pass {run['pass_rate']:.0%}")


if __name__ == "__main__":
    main()
