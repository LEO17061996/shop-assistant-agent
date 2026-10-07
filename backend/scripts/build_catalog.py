"""Build the demo catalog from Amazon Berkeley Objects (ABO) listings.

Real fields (CC BY 4.0, ABO): name, brand, bullets, material, color, style,
dimensions, weight, image.
Synthetic fields (deterministic, seeded by item_id): price, stock, UK shipping
eligibility. ABO has no prices, so these are generated and labelled as such.

Usage: python scripts/build_catalog.py
Input:  data/raw/listings/*.json.gz, data/raw/images.csv.gz
Output: data/catalog.jsonl, data/orders.json
"""

from __future__ import annotations

import csv
import gzip
import hashlib
import html
import json
from collections import Counter
from pathlib import Path

DATA = Path(__file__).resolve().parents[1] / "data"
RAW = DATA / "raw"
IMAGE_BASE = "https://amazon-berkeley-objects.s3.amazonaws.com/images/small/"

CATEGORIES = {
    "CHAIR": "Chairs",
    "SOFA": "Sofas",
    "TABLE": "Tables",
    "RUG": "Rugs",
    "LAMP": "Lighting",
    "LIGHT_FIXTURE": "Lighting",
    "OTTOMAN": "Ottomans & Stools",
    "STOOL_SEATING": "Ottomans & Stools",
    "BED": "Beds & Headboards",
    "HEADBOARD": "Beds & Headboards",
    "HOME_MIRROR": "Mirrors",
    "SHELF": "Shelves & Storage",
    "PILLOW": "Pillows & Throws",
    "PLANTER": "Planters",
    "WALL_ART": "Wall Art",
}
PER_CATEGORY = 45

# USD price band per category: (min, max)
PRICE_BANDS = {
    "Chairs": (60, 450),
    "Sofas": (450, 1800),
    "Tables": (70, 700),
    "Rugs": (40, 600),
    "Lighting": (30, 250),
    "Ottomans & Stools": (40, 300),
    "Beds & Headboards": (150, 1200),
    "Mirrors": (40, 350),
    "Shelves & Storage": (50, 400),
    "Pillows & Throws": (15, 70),
    "Planters": (15, 120),
    "Wall Art": (25, 250),
}
# Too bulky for international freight in this demo store
US_ONLY = {"Sofas", "Beds & Headboards"}


def seeded(item_id: str, salt: str) -> float:
    """Deterministic 0..1 value so rebuilding gives the same catalog."""
    h = hashlib.sha256(f"{item_id}:{salt}".encode()).hexdigest()
    return int(h[:8], 16) / 0xFFFFFFFF


def en_values(field: list | None) -> list[str]:
    out = []
    for x in field or []:
        if x.get("language_tag", "en_US") == "en_US":
            v = html.unescape(x.get("value") or "").strip()  # some ABO text has HTML entities (&eacute;)
            if v and v not in out:
                out.append(v)
    return out


def dims_inches(d: dict) -> dict | None:
    dims = d.get("item_dimensions")
    if not dims:
        return None
    out = {}
    for k in ("length", "width", "height"):
        nv = (dims.get(k) or {}).get("normalized_value") or {}
        if nv.get("unit") == "inches" and nv.get("value"):
            out[k] = round(float(nv["value"]), 1)
    return out or None


def weight_lb(d: dict) -> float | None:
    for w in d.get("item_weight") or []:
        nv = w.get("normalized_value") or {}
        if nv.get("unit") == "pounds" and nv.get("value"):
            return round(float(nv["value"]), 1)
    return None


def price_for(item_id: str, category: str, dims: dict | None) -> float:
    lo, hi = PRICE_BANDS[category]
    raw = lo + (hi - lo) * seeded(item_id, "price")
    if category == "Rugs" and dims and dims.get("length") and dims.get("width"):
        # Rugs are priced by area ($3-8 per sq ft) so an 8'x10' never costs less than a doormat
        sq_ft = dims["length"] * dims["width"] / 144
        raw = min(max(sq_ft * (3 + 5 * seeded(item_id, "price")), lo), 900)
    return round(raw) - 0.01 if raw > 20 else round(raw, 2)


def load_image_paths() -> dict[str, str]:
    with gzip.open(RAW / "images.csv.gz", "rt", encoding="utf-8") as fh:
        return {row["image_id"]: row["path"] for row in csv.DictReader(fh)}


def load_candidates() -> list[dict]:
    rows = []
    for f in sorted((RAW / "listings").glob("*.json.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                d = json.loads(line)
                ptype = (d.get("product_type") or [{}])[0].get("value")
                if ptype not in CATEGORIES or not d.get("main_image_id"):
                    continue
                names = en_values(d.get("item_name"))
                bullets = en_values(d.get("bullet_point"))
                if not names or len(bullets) < 3 or sum(map(len, bullets)) < 150:
                    continue
                rows.append(d | {"_ptype": ptype, "_name": names[0], "_bullets": bullets})
    return rows


POLICY_WORDS = ("free returns", "warranty", "return policy")


def product_bullets(bullets: list[str]) -> list[str]:
    # Store policies live in data/policies; drop vendor boilerplate that could contradict them
    return [b for b in bullets if not any(w in b.lower() for w in POLICY_WORDS)][:8]


def dedupe_key(d: dict) -> str:
    # Colour/size variants share brand + leading words of the name
    brand = (en_values(d.get("brand")) or [""])[0].lower()
    words = d["_name"].lower().replace(",", " ").split()[:5]
    return brand + "|" + " ".join(words)


def to_product(d: dict, image_path: str) -> dict:
    item_id = d["item_id"]
    category = CATEGORIES[d["_ptype"]]
    stock = 0 if seeded(item_id, "oos") < 0.08 else 1 + int(seeded(item_id, "stock") * 40)
    ships_to = ["US"]
    if category not in US_ONLY and seeded(item_id, "uk") < 0.7:
        ships_to.append("UK")
    keywords = [k for k in en_values(d.get("item_keywords")) if len(k) > 2][:15]
    dims = dims_inches(d)
    first = lambda key: (en_values(d.get(key)) or [None])[0]  # noqa: E731
    return {
        "id": item_id,
        "name": d["_name"],
        "brand": first("brand"),
        "category": category,
        "price_usd": price_for(item_id, category, dims),
        "stock": stock,
        "ships_to": ships_to,
        "color": first("color"),
        "material": first("material"),
        "style": first("style"),
        "fabric": first("fabric_type"),
        "pattern": first("pattern"),
        "finish": first("finish_type"),
        "shape": first("item_shape"),
        "dimensions_in": dims,
        "weight_lb": weight_lb(d),
        "bullets": product_bullets(d["_bullets"]),
        "keywords": keywords,
        "image_url": IMAGE_BASE + image_path,
    }


def build_orders(products: list[dict]) -> list[dict]:
    """Mock orders so the agent has something to look up."""
    statuses = [
        ("processing", None, None),
        ("shipped", "UPS", "2026-10-12"),
        ("shipped", "Royal Mail", "2026-10-15"),
        ("delivered", "FedEx", "2026-09-28"),
        ("held_at_customs", "DHL", None),
        ("cancelled", None, None),
    ]
    orders = []
    for i in range(18):
        p = products[(i * 37) % len(products)]
        status, carrier, eta = statuses[i % len(statuses)]
        country = "UK" if carrier in ("Royal Mail", "DHL") else "US"
        orders.append(
            {
                "order_id": f"KH-{10400 + i * 7}",
                "email": f"customer{i + 1}@example.com",
                "country": country,
                "status": status,
                "carrier": carrier,
                "tracking": f"TRK{(i + 3) * 918273 % 10**9:09d}" if carrier else None,
                "eta": eta,
                "placed_at": f"2026-09-{(i % 27) + 1:02d}",
                "items": [{"product_id": p["id"], "name": p["name"], "qty": 1, "price_usd": p["price_usd"]}],
            }
        )
    return orders


def main() -> None:
    images = load_image_paths()
    candidates = load_candidates()
    candidates.sort(key=lambda d: seeded(d["item_id"], "order"))

    taken: Counter = Counter()
    seen: set[str] = set()
    products = []
    for d in candidates:
        category = CATEGORIES[d["_ptype"]]
        key = dedupe_key(d)
        path = images.get(d["main_image_id"])
        if taken[category] >= PER_CATEGORY or key in seen or not path:
            continue
        seen.add(key)
        taken[category] += 1
        products.append(to_product(d, path))

    products.sort(key=lambda p: (p["category"], p["id"]))
    with open(DATA / "catalog.jsonl", "w", encoding="utf-8") as fh:
        for p in products:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    with open(DATA / "orders.json", "w", encoding="utf-8") as fh:
        json.dump(build_orders(products), fh, indent=2, ensure_ascii=False)

    print(f"{len(products)} products from {len(candidates)} candidates")
    for cat, n in sorted(taken.items()):
        print(f"  {cat:20s} {n}")


if __name__ == "__main__":
    main()
