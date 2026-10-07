"""Listing Studio eval. Ground truth comes from the ABO catalog itself.

For a sample of products (a few per category):
1. read_photo(catalog photo) -> facts, scored against the catalog's category, colour and material.
2. write_copy(facts, price) -> rule violations in the first draft and after the repair loop.
3. An LLM judge lists claims in the final copy that the facts and notes do not support.
4. read_photo(a different photo of the same product) -> find_similar -> rank of the product.

Usage: python -m eval.studio_eval --n 40
"""

import argparse
import asyncio
import json
import random
import statistics
import time
from collections import defaultdict

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from app import catalog
from app.agent.llm import rate_limiter
from app.config import get_settings
from app.studio.pipeline import CLAIMS_MODEL, Usage, find_similar, prepare_image, read_photo, write_copy
from app.studio.schemas import ProductFacts, SellerNotes
from eval.judge import JUDGE_MODEL
from eval.run_eval import RATE_LIMIT_WAIT_S, RESULTS
from eval.studio_data import IMAGES

SEED = 11
COLOURS = {
    "black": ["black", "ebony", "onyx"],
    "white": ["white", "snow"],
    "grey": ["grey", "gray", "charcoal", "slate", "graphite", "pewter", "silver grey"],
    "brown": [
        "brown",
        "espresso",
        "walnut",
        "oak",
        "chestnut",
        "mocha",
        "cognac",
        "saddle",
        "taupe",
        "bronze",
        "teak",
        "cherry",
        "mahogany",
    ],
    "beige": [
        "beige",
        "cream",
        "ivory",
        "natural",
        "tan",
        "khaki",
        "sand",
        "oatmeal",
        "linen",
        "off-white",
        "off white",
        "taupe",
    ],
    "blue": ["blue", "navy", "teal", "indigo", "denim", "aqua", "turquoise"],
    "green": ["green", "olive", "sage", "emerald", "teal", "mint"],
    "red": ["red", "burgundy", "maroon", "rust", "terracotta", "brick"],
    "yellow": ["yellow", "mustard", "gold", "ochre"],
    "orange": ["orange", "rust", "terracotta", "copper"],
    "pink": ["pink", "blush", "rose", "coral", "mauve"],
    "purple": ["purple", "plum", "lavender", "violet", "mauve"],
    "metallic": ["gold", "silver", "brass", "chrome", "nickel", "copper", "bronze"],
}
MATERIALS = {
    "wood": [
        "wood",
        "oak",
        "walnut",
        "pine",
        "acacia",
        "mango",
        "bamboo",
        "birch",
        "mdf",
        "veneer",
        "rubberwood",
        "teak",
        "beech",
        "plywood",
        "particle",
    ],
    "metal": ["metal", "steel", "iron", "aluminum", "aluminium", "brass", "chrome", "nickel"],
    "fabric": [
        "fabric",
        "polyester",
        "linen",
        "cotton",
        "velvet",
        "upholster",
        "microfiber",
        "chenille",
        "boucle",
        "textile",
        "polypropylene",
        "olefin",
        "wool",
        "acrylic yarn",
    ],
    "leather": ["leather", "leathersoft", "faux leather", "pu "],
    "glass": ["glass", "mirror"],
    "plastic": ["plastic", "acrylic", "resin", "pvc", "abs"],
    "natural fibre": ["jute", "sisal", "rattan", "wicker", "seagrass", "cane", "rope"],
    "stone/ceramic": ["marble", "stone", "concrete", "ceramic", "porcelain", "terracotta", "earthenware"],
}


def families(text: str | None, table: dict[str, list[str]]) -> set[str]:
    low = f" {(text or '').lower()} "
    return {fam for fam, words in table.items() if any(w in low for w in words)}


def sample(n: int) -> list[dict]:
    with_alt = set(json.loads((IMAGES / "alt_index.json").read_text(encoding="utf-8")))
    by_cat = defaultdict(list)
    for p in catalog.products().values():
        if p["id"] in with_alt:
            by_cat[p["category"]].append(p)
    rng = random.Random(SEED)
    for items in by_cat.values():
        rng.shuffle(items)
    picked, i = [], 0
    while len(picked) < n and any(i < len(v) for v in by_cat.values()):
        for cat in sorted(by_cat):
            if i < len(by_cat[cat]) and len(picked) < n:
                picked.append(by_cat[cat][i])
        i += 1
    return picked


class Unsupported(BaseModel):
    claims: list[str] = Field(
        description="Each statement in the copy that the facts and seller notes do not support. Empty if none."
    )


JUDGE_PROMPT = """You check product copy for claims that are not backed by the available facts.

Facts read from the product photo:
{facts}

Seller notes:
{notes}

Copy:
{copy}

List every specific claim in the copy that the facts or notes do not support: sizes, materials, features,
assembly, durability, comfort, care, origin, offers. Ordinary marketing tone ("adds warmth to any room") is fine."""


def judge_llm():
    s = get_settings()
    llm = ChatGoogleGenerativeAI(
        model=JUDGE_MODEL,
        api_key=s.gemini_api_key,
        temperature=0,
        max_retries=3,
        rate_limiter=rate_limiter(JUDGE_MODEL),
    )
    return llm.with_structured_output(Unsupported)


async def retry(fn, *args):
    for attempt in range(4):
        try:
            return await fn(*args)
        except Exception as e:
            if ("429" not in str(e) and "RESOURCE_EXHAUSTED" not in str(e)) or attempt == 3:
                raise
            await asyncio.sleep(RATE_LIMIT_WAIT_S * (attempt + 1))


def jpeg(kind: str, pid: str) -> bytes:
    return prepare_image((IMAGES / kind / f"{pid}.jpg").read_bytes())


async def run_product(p: dict, judge, sem: asyncio.Semaphore, claim_check: bool) -> dict:
    usage = Usage()
    notes = SellerNotes(price_usd=p["price_usd"])
    async with sem:
        t0 = time.perf_counter()
        try:
            facts: ProductFacts = await retry(read_photo, jpeg("main", p["id"]), usage)
            copy = await retry(write_copy, facts, notes, usage, None, claim_check)
            unsupported = await retry(
                judge.ainvoke,
                JUDGE_PROMPT.format(
                    facts=facts.model_dump_json(), notes=notes.model_dump_json(), copy=copy.copy.model_dump_json()
                ),
            )
            alt_facts: ProductFacts = await retry(read_photo, jpeg("alt", p["id"]), usage)
        except Exception as e:
            return {"id": p["id"], "category": p["category"], "error": str(e)[:300]}
        latency_ms = round((time.perf_counter() - t0) * 1000)

    similar = [h["id"] for h in find_similar(alt_facts, limit=10)]
    gt_colours = families(p.get("color"), COLOURS)
    gt_materials = families(p.get("material"), MATERIALS)
    got_colours = families(" ".join(facts.colors), COLOURS)
    got_materials = families(" ".join(facts.materials), MATERIALS)
    return {
        "id": p["id"],
        "name": p["name"],
        "category": p["category"],
        "image_url": p["image_url"],
        "truth": {"color": p.get("color"), "material": p.get("material")},
        "facts": facts.model_dump(),
        "category_ok": facts.category == p["category"],
        # Scored only when the catalog value maps to a known family ("Multi" and odd values are skipped)
        "colour_ok": bool(gt_colours & got_colours) if gt_colours and p.get("color") != "Multi" else None,
        "material_ok": bool(gt_materials & got_materials) if gt_materials else None,
        "violations_by_round": [[v.model_dump() for v in r] for r in copy.rounds],
        "copy_passed": copy.passed,
        "copy": copy.copy.model_dump(),
        "unsupported_claims": unsupported.claims,
        "alt_facts": alt_facts.model_dump(),
        "similar_rank": similar.index(p["id"]) + 1 if p["id"] in similar else None,
        "calls": usage.calls,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cost_usd": round(usage.cost_usd, 6),
        "latency_ms": latency_ms,
    }


def rate(values: list) -> float | None:
    vals = [v for v in values if v is not None]
    return round(sum(vals) / len(vals), 3) if vals else None


def summarize(cases: list[dict]) -> dict:
    ok = [c for c in cases if "error" not in c]
    ranks = [c["similar_rank"] for c in ok]
    first_draft = [not c["violations_by_round"][0] for c in ok]
    rules = defaultdict(int)
    for c in ok:
        for v in c["violations_by_round"][0]:
            rules[v["rule"]] += 1
    return {
        "n": len(cases),
        "errors": len(cases) - len(ok),
        "category_accuracy": rate([c["category_ok"] for c in ok]),
        "colour_accuracy": rate([c["colour_ok"] for c in ok]),
        "colour_n": sum(c["colour_ok"] is not None for c in ok),
        "material_accuracy": rate([c["material_ok"] for c in ok]),
        "material_n": sum(c["material_ok"] is not None for c in ok),
        "first_draft_pass": rate(first_draft),
        "final_pass": rate([c["copy_passed"] for c in ok]),
        "repairs_avg": round(statistics.mean(len(c["violations_by_round"]) - 1 for c in ok), 2) if ok else None,
        "first_draft_violations_by_rule": dict(rules),
        "no_unsupported_claims": rate([not c["unsupported_claims"] for c in ok]),
        "unsupported_claims_avg": round(statistics.mean(len(c["unsupported_claims"]) for c in ok), 2) if ok else None,
        "visual_hit@1": rate([r == 1 for r in ranks]),
        "visual_hit@5": rate([r is not None and r <= 5 for r in ranks]),
        "visual_mrr": round(sum(1 / r for r in ranks if r) / len(ranks), 3) if ranks else None,
        "calls_avg": round(statistics.mean(c["calls"] for c in ok), 2) if ok else None,
        "cost_usd_avg": round(statistics.mean(c["cost_usd"] for c in ok if c["cost_usd"] is not None), 5)
        if ok
        else None,
        "latency_ms_median": round(statistics.median(c["latency_ms"] for c in ok)) if ok else None,
    }


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=40)
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--retry-errors", action="store_true", help="re-run only the cases that errored last time")
    ap.add_argument("--no-claim-check", action="store_true", help="ablation: rule checks only, no LLM claim check")
    args = ap.parse_args()

    products = sample(args.n)
    judge = judge_llm()
    sem = asyncio.Semaphore(args.concurrency)
    claim_check = not args.no_claim_check
    path = RESULTS / ("studio.json" if claim_check else "studio_no_claim_check.json")
    if args.retry_errors and path.exists():
        # Free-tier quotas run out mid-run; keep finished cases and only redo the failures
        previous = {c["id"]: c for c in json.loads(path.read_text(encoding="utf-8"))["cases"]}
        todo = [p for p in products if "error" in previous.get(p["id"], {"error": "missing"})]
        redone = {c["id"]: c for c in await asyncio.gather(*(run_product(p, judge, sem, claim_check) for p in todo))}
        cases = [redone.get(p["id"], previous.get(p["id"])) for p in products]
    else:
        cases = await asyncio.gather(*(run_product(p, judge, sem, claim_check) for p in products))
    out = {
        "model": get_settings().gemini_model,
        "claim_check": CLAIMS_MODEL if claim_check else None,
        "judge": JUDGE_MODEL,
        **summarize(cases),
        "cases": cases,
    }
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items() if k != "cases"}, indent=1))
    for c in cases:
        if "error" in c:
            print("ERROR", c["id"], c["error"])


if __name__ == "__main__":
    asyncio.run(main())
