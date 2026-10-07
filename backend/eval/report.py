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

    text = replace_block(README.read_text(encoding="utf-8"), "RESULTS", lines)
    studio_lines = studio_tables()
    if studio_lines:
        text = replace_block(text, "STUDIO", studio_lines)
    README.write_text(text, encoding="utf-8")
    print("\n".join(lines + [""] + studio_lines))


def replace_block(text: str, marker: str, lines: list[str]) -> str:
    block = f"<!-- {marker}:START -->\n" + "\n".join(lines) + f"\n<!-- {marker}:END -->"
    return re.sub(rf"<!-- {marker}:START -->.*<!-- {marker}:END -->", lambda _: block, text, flags=re.S)


def studio_tables() -> list[str]:
    studio_path, baseline_path = RESULTS / "studio.json", RESULTS / "image_baseline.json"
    if not studio_path.exists():
        return []
    s = json.loads(studio_path.read_text(encoding="utf-8"))
    lines = [
        f"Listing Studio eval: {s['n']} products, scored against the catalog's own metadata.",
        "",
        "| Metric | Result |",
        "|---|---:|",
        f"| Category read from photo | {pct(s['category_accuracy'])} |",
        f"| Colour read from photo | {pct(s['colour_accuracy'])} (n={s['colour_n']}) |",
        f"| Material read from photo | {pct(s['material_accuracy'])} (n={s['material_n']}) |",
        f"| Copy passes all rules: first draft → after repair loop | {pct(s['first_draft_pass'])} → {pct(s['final_pass'])} |",
        f"| Copy with no unsupported claims (LLM judge) | {pct(s['no_unsupported_claims'])} |",
        f"| Visual search, other photo of same product: hit@1 / hit@5 | {pct(s['visual_hit@1'])} / {pct(s['visual_hit@5'])} |",
        f"| Cost per listing* | ${s['cost_usd_avg']:.4f} |",
    ]
    if baseline_path.exists():
        b = json.loads(baseline_path.read_text(encoding="utf-8"))
        ids = [c["id"] for c in s["cases"] if "error" not in c]
        lines += [
            "",
            f"Visual search on the same {len(ids)} query photos (image models also on all {b['n_queries']}):",
            "",
            "| Approach | hit@1 | hit@5 | Extra RAM | hit@5, all |",
            "|---|---:|---:|---:|---:|",
            f"| Gemini describes photo → hybrid text search (live) | {pct(s['visual_hit@1'])} | {pct(s['visual_hit@5'])} | 0 MB | – |",
        ]
        for m in b["models"]:
            ranks = [m["ranks"][i] for i in ids if i in m["ranks"]]
            hit1 = sum(r == 1 for r in ranks) / len(ranks)
            hit5 = sum(r <= 5 for r in ranks) / len(ranks)
            ram = f"{m['extra_ram_mb']} MB" if m["extra_ram_mb"] is not None else "–"
            lines.append(f"| {m['model']} embeddings | {pct(hit1)} | {pct(hit5)} | {ram} | {pct(m['hit@5'])} |")
    return lines


if __name__ == "__main__":
    main()
