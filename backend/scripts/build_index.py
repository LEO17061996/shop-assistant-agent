"""Embed the catalog and policy docs into Qdrant. Run after build_catalog.py.

Usage: python scripts/build_index.py
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import catalog  # noqa: E402
from app.config import get_settings  # noqa: E402
from app.rag import index  # noqa: E402
from app.rag.documents import policy_chunks, product_text  # noqa: E402

# Payload fields the API and agent read back; long text stays out of the payload
PRODUCT_FIELDS = ("id", "name", "brand", "category", "price_usd", "stock", "ships_to", "material", "color", "image_url")


def main() -> None:
    t0 = time.perf_counter()
    products = list(catalog.products().values())
    index.recreate(index.PRODUCTS)
    index.upsert(
        index.PRODUCTS,
        ids=list(range(len(products))),
        texts=[product_text(p) for p in products],
        payloads=[{k: p.get(k) for k in PRODUCT_FIELDS} for p in products],
    )

    chunks = policy_chunks(get_settings().data_dir / "policies")
    index.recreate(index.POLICIES)
    index.upsert(
        index.POLICIES,
        ids=list(range(len(chunks))),
        texts=[c["text"] for c in chunks],
        payloads=chunks,
    )
    index.client().close()
    print(f"Indexed {len(products)} products, {len(chunks)} policy chunks in {time.perf_counter() - t0:.1f}s")


if __name__ == "__main__":
    main()
