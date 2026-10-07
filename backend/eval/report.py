"""Write the results tables into the top-level README between the RESULTS markers.

Usage: python -m eval.report
"""

import json
import re

from eval.run_eval import EVAL_DIR, RESULTS

README = EVAL_DIR.parents[1] / "README.md"
LABELS = {
    "gemini-3.1-flash-lite": "Gemini 3.1 Flash-Lite",
    "gemini-3.5-flash-lite": "Gemini 3.5 Flash-Lite",
}


def pct(x: float | None) -> str:
    return "–" if x is None else f"{round(x * 100)}%"


def main() -> None:
    runs = json.loads((RESULTS / "summary.json").read_text(encoding="utf-8"))
    runs.sort(key=lambda r: (-r["pass_rate"], r["model"], r["prompt"]))
    lines = [
        f"Agent eval: {runs[0]['n_cases']} questions, code checks decide pass/fail, judge = {runs[0].get('judge') or 'none'} (1–5).",
        "",
        "| Model | Prompt | Pass | Faithful | Helpful | Median time | Model calls | Cost / question* |",
        "|---|---|---:|---:|---:|---:|---:|---:|",
    ]
    for r in runs:
        lines.append(
            f"| {LABELS.get(r['model'], r['model'])} | {r['prompt']} | **{pct(r['pass_rate'])}** "
            f"| {r['judge_faithfulness_avg'] or '–'} | {r['judge_helpfulness_avg'] or '–'} "
            f"| {r['latency_ms_median'] / 1000:.1f}s | {r['steps_avg']} | ${r['cost_usd_avg']:.4f} |"
        )
    lines += [
        "",
        "*Paid-tier list price for the tokens used; the demo itself runs on the free tier. Times include free-tier queueing (12 requests/minute per model).",
    ]

    retrieval_path = RESULTS / "retrieval.json"
    if retrieval_path.exists():
        ret = json.loads(retrieval_path.read_text(encoding="utf-8"))
        lines += [
            "",
            f"Retrieval eval: {ret['n_queries']} shopper-style queries, no model in the loop.",
            "",
            "| Search | hit@1 | hit@5 | MRR |",
            "|---|---:|---:|---:|",
        ]
        for name, m in ret["results"].items():
            lines.append(f"| {name} | {pct(m['hit@1'])} | {pct(m['hit@5'])} | {m['mrr']:.2f} |")

    block = "<!-- RESULTS:START -->\n" + "\n".join(lines) + "\n<!-- RESULTS:END -->"
    text = README.read_text(encoding="utf-8")
    README.write_text(
        re.sub(r"<!-- RESULTS:START -->.*<!-- RESULTS:END -->", block, text, flags=re.S), encoding="utf-8"
    )
    print("\n".join(lines))


if __name__ == "__main__":
    main()
