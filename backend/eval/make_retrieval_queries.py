"""Generate shopper-style queries for retrieval eval: one per sampled product.

The model sees the product and writes what a customer might type to find it, without the
brand or name words, so exact-name keyword matching cannot cheat. Saved once and reviewed;
retrieval_eval.py then measures whether search returns that product.

Usage: python -m eval.make_retrieval_queries
"""

import asyncio
import json
import random

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from app import catalog
from app.agent.llm import rate_limiter
from app.config import get_settings
from eval.run_eval import EVAL_DIR

N_PRODUCTS = 80
SEED = 7

PROMPT = """A customer is shopping on a furniture website. Write the search request they would type if this product is exactly what they want.

Product:
{product}

Rules:
- 6 to 16 words, natural shopper language, like "round wooden coffee table for a small living room".
- Describe it by type, look, material, size or use.
- Do NOT use the brand, the product name, model names or any distinctive word taken from the name."""


class Query(BaseModel):
    query: str = Field(description="The shopper's search request.")


async def main() -> None:
    s = get_settings()
    model = "gemini-3.5-flash-lite"
    llm = ChatGoogleGenerativeAI(
        model=model, api_key=s.gemini_api_key, temperature=0.7, max_retries=3, rate_limiter=rate_limiter(model)
    ).with_structured_output(Query)

    products = list(catalog.products().values())
    sample = random.Random(SEED).sample(products, N_PRODUCTS)
    sem = asyncio.Semaphore(3)

    async def one(p: dict) -> dict:
        view = {k: p.get(k) for k in ("name", "category", "material", "color", "style", "dimensions_in")}
        view["description"] = p["bullets"][:3]
        async with sem:
            q: Query = await llm.ainvoke(PROMPT.format(product=json.dumps(view, ensure_ascii=False)))
        return {"product_id": p["id"], "category": p["category"], "name": p["name"], "query": q.query}

    rows = await asyncio.gather(*(one(p) for p in sample))
    with open(EVAL_DIR / "retrieval_queries.jsonl", "w", encoding="utf-8") as fh:
        for r in rows:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"wrote {len(rows)} queries")


if __name__ == "__main__":
    asyncio.run(main())
