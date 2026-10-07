"""Read-only access to the product catalog and mock orders."""

import json
from functools import lru_cache

from app.config import get_settings


@lru_cache
def products() -> dict[str, dict]:
    path = get_settings().data_dir / "catalog.jsonl"
    with open(path, encoding="utf-8") as fh:
        items = [json.loads(line) for line in fh if line.strip()]
    return {p["id"]: p for p in items}


@lru_cache
def orders() -> dict[str, dict]:
    path = get_settings().data_dir / "orders.json"
    with open(path, encoding="utf-8") as fh:
        return {o["order_id"].upper(): o for o in json.load(fh)}


def categories() -> list[str]:
    return sorted({p["category"] for p in products().values()})


def to_cm(inches: float) -> float:
    return round(inches * 2.54, 1)
