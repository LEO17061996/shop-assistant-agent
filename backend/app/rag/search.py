"""Hybrid retrieval: dense + BM25 candidates, merged with Reciprocal Rank Fusion.

Structured constraints (price, category, country, stock) are Qdrant payload
filters applied inside both candidate searches, so the model never has to
"remember" to drop a $900 sofa when the customer said under $500.
"""

from dataclasses import dataclass
from typing import Literal

from qdrant_client import models

from app.rag.index import DENSE, POLICIES, PRODUCTS, SPARSE, client, embed_query

Mode = Literal["dense", "sparse", "hybrid"]


@dataclass
class ProductFilter:
    category: str | None = None
    min_price: float | None = None
    max_price: float | None = None
    ships_to: str | None = None
    in_stock_only: bool = False

    def to_qdrant(self) -> models.Filter | None:
        must: list[models.Condition] = []
        if self.category:
            must.append(models.FieldCondition(key="category", match=models.MatchValue(value=self.category)))
        if self.min_price is not None or self.max_price is not None:
            must.append(
                models.FieldCondition(key="price_usd", range=models.Range(gte=self.min_price, lte=self.max_price))
            )
        if self.ships_to:
            must.append(models.FieldCondition(key="ships_to", match=models.MatchValue(value=self.ships_to.upper())))
        if self.in_stock_only:
            must.append(models.FieldCondition(key="stock", range=models.Range(gt=0)))
        return models.Filter(must=must) if must else None


def _query(collection: str, text: str, limit: int, flt: models.Filter | None, mode: Mode):
    dense, sparse = embed_query(text)
    c = client()
    if mode == "dense":
        res = c.query_points(collection, query=dense, using=DENSE, query_filter=flt, limit=limit)
    elif mode == "sparse":
        res = c.query_points(collection, query=sparse, using=SPARSE, query_filter=flt, limit=limit)
    else:
        res = c.query_points(
            collection,
            prefetch=[
                models.Prefetch(query=dense, using=DENSE, filter=flt, limit=limit * 4),
                models.Prefetch(query=sparse, using=SPARSE, filter=flt, limit=limit * 4),
            ],
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=limit,
        )
    return res.points


def search_products(text: str, flt: ProductFilter | None = None, limit: int = 5, mode: Mode = "hybrid") -> list[dict]:
    points = _query(PRODUCTS, text, limit, flt.to_qdrant() if flt else None, mode)
    return [p.payload | {"score": round(p.score, 4)} for p in points]


def search_policies(text: str, limit: int = 3, mode: Mode = "hybrid") -> list[dict]:
    points = _query(POLICIES, text, limit, None, mode)
    return [p.payload | {"score": round(p.score, 4)} for p in points]
