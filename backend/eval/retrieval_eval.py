"""Retrieval-only eval: does search put the target product near the top? No LLM involved.

For each query in retrieval_queries.jsonl, compare dense, sparse (BM25) and hybrid (RRF)
search, with and without the category filter the agent would normally add.
Metrics: hit@1, hit@5 (target in top 1 / top 5) and MRR (mean of 1/rank, 0 if not in top 10).
Note: other products may also fit a query, so these are lower bounds on real quality.

Usage: python -m eval.retrieval_eval
"""

import json
import time

from app.rag.search import ProductFilter, search_products
from eval.run_eval import EVAL_DIR

MODES = ("dense", "sparse", "hybrid")
K = 10


def main() -> None:
    with open(EVAL_DIR / "retrieval_queries.jsonl", encoding="utf-8") as fh:
        queries = [json.loads(line) for line in fh if line.strip()]

    results = {}
    for with_filter in (False, True):
        for mode in MODES:
            ranks, t0 = [], time.perf_counter()
            for q in queries:
                flt = ProductFilter(category=q["category"]) if with_filter else None
                ids = [h["id"] for h in search_products(q["query"], flt, limit=K, mode=mode)]
                ranks.append(ids.index(q["product_id"]) + 1 if q["product_id"] in ids else None)
            n = len(ranks)
            key = f"{mode}{' + category filter' if with_filter else ''}"
            results[key] = {
                "hit@1": round(sum(r == 1 for r in ranks) / n, 3),
                "hit@5": round(sum(r is not None and r <= 5 for r in ranks) / n, 3),
                "mrr": round(sum(1 / r for r in ranks if r) / n, 3),
                "ms_per_query": round((time.perf_counter() - t0) * 1000 / n, 1),
            }
    out = {"n_queries": len(queries), "k": K, "results": results}
    (EVAL_DIR / "results" / "retrieval.json").write_text(json.dumps(out, indent=2), encoding="utf-8")

    print(f"{'setup':32s} hit@1  hit@5  MRR   ms/q")
    for key, m in results.items():
        print(f"{key:32s} {m['hit@1']:.2f}   {m['hit@5']:.2f}   {m['mrr']:.2f}  {m['ms_per_query']}")


if __name__ == "__main__":
    main()
