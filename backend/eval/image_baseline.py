"""Visual search with real image embeddings, as a baseline for the live describe-then-search approach.

Index: the catalog photo of every product. Query: a *different* photo of the same product.
A hit means the right product comes back. No LLM involved; runs locally.

Usage: python -m eval.image_baseline
"""

import json
import multiprocessing
import os
import time

import numpy as np
from fastembed import ImageEmbedding

from app.config import get_settings
from eval.run_eval import RESULTS
from eval.studio_data import IMAGES

MODELS = [
    "Qdrant/clip-ViT-B-32-vision",
    "google/siglip2-base-patch16-224",
    "nomic-ai/nomic-embed-vision-v1.5-Q",
    "Qdrant/resnet50-onnx",
]


def rss_mb() -> float | None:
    """Resident memory of this process; RAM matters because the free host has 512 MB."""
    try:
        import psutil

        return psutil.Process(os.getpid()).memory_info().rss / 2**20
    except ImportError:
        return None


def evaluate(model_name: str, ids: list[str], query_ids: list[str]) -> dict:
    before = rss_mb()
    model = ImageEmbedding(model_name, cache_dir=str(get_settings().embed_cache_dir))
    t0 = time.perf_counter()
    index = np.array(list(model.embed([str(IMAGES / "main" / f"{i}.jpg") for i in ids], batch_size=32)))
    ms_per_image = (time.perf_counter() - t0) * 1000 / len(ids)
    queries = np.array(list(model.embed([str(IMAGES / "alt" / f"{i}.jpg") for i in query_ids], batch_size=32)))
    index /= np.linalg.norm(index, axis=1, keepdims=True)
    queries /= np.linalg.norm(queries, axis=1, keepdims=True)
    ranks = []
    for q, target in zip(queries, query_ids, strict=True):
        order = np.argsort(-(index @ q))
        ranks.append(int(np.where(np.array(ids)[order] == target)[0][0]) + 1)
    after = rss_mb()
    n = len(ranks)
    return {
        "model": model_name,
        "hit@1": round(sum(r == 1 for r in ranks) / n, 3),
        "hit@5": round(sum(r <= 5 for r in ranks) / n, 3),
        "mrr": round(sum(1 / r for r in ranks) / n, 3),
        "ms_per_image_cpu": round(ms_per_image, 1),
        "extra_ram_mb": round(after - before) if before and after else None,
        "ranks": dict(zip(query_ids, ranks, strict=True)),
    }


def main() -> None:
    ids = sorted(p.stem for p in (IMAGES / "main").glob("*.jpg"))
    query_ids = json.loads((IMAGES / "alt_index.json").read_text(encoding="utf-8"))
    out = {"n_index": len(ids), "n_queries": len(query_ids), "models": []}
    # One fresh process per model, so each RAM figure covers only that model
    ctx = multiprocessing.get_context("spawn")
    for name in MODELS:
        with ctx.Pool(1) as pool:
            r = pool.apply(evaluate, (name, ids, query_ids))
        out["models"].append(r)
        print(
            f"{name:40s} hit@1 {r['hit@1']:.2f}  hit@5 {r['hit@5']:.2f}  MRR {r['mrr']:.2f}  "
            f"{r['ms_per_image_cpu']} ms/img  +{r['extra_ram_mb']} MB"
        )
    (RESULTS / "image_baseline.json").write_text(json.dumps(out, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
