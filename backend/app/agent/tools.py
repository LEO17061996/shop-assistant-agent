"""Tools the agent can call.

Rule of thumb: anything that must be exactly right (prices, stock, shipping
cost, order status) comes from code, never from the model's memory or maths.
Each tool returns (content_for_model, artifact_for_ui): the model sees compact
JSON, the UI gets product cards and timing without spending tokens on them.
"""

import json
import uuid
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app import catalog
from app.config import get_settings
from app.rag.search import ProductFilter, search_policies, search_products

Category = Literal[
    "Beds & Headboards",
    "Chairs",
    "Lighting",
    "Mirrors",
    "Ottomans & Stools",
    "Pillows & Throws",
    "Planters",
    "Rugs",
    "Shelves & Storage",
    "Sofas",
    "Tables",
    "Wall Art",
]
Country = Literal["US", "UK"]
FREIGHT = {"Sofas", "Beds & Headboards"}

# What each category holds. Without this the model filed "bar stools" under Chairs and told the
# customer none were in stock (eval case search-05).
CATEGORY_GUIDE = (
    "Beds & Headboards: bed frames, headboards. "
    "Chairs: dining, accent, office and kids chairs, recliners. "
    "Lighting: table, floor, pendant, ceiling, vanity and outdoor lights. "
    "Mirrors: wall and floor mirrors. "
    "Ottomans & Stools: ottomans, poufs, footstools, benches, bar and counter stools. "
    "Pillows & Throws: throw pillows, cushions, blankets. "
    "Planters: planters, plant pots, vases, plant stands. "
    "Rugs: area rugs, runners. "
    "Shelves & Storage: bookcases, shelves, storage units. "
    "Sofas: sofas, loveseats, sectionals. "
    "Tables: dining, coffee, side, end and console tables, nightstands. "
    "Wall Art: prints, canvases, framed art."
)


def _card(p: dict) -> dict:
    return {k: p.get(k) for k in ("id", "name", "price_usd", "stock", "ships_to", "category", "image_url")}


def _dump(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


class SearchProductsArgs(BaseModel):
    query: str = Field("", description="What the customer wants, in plain words (style, material, use, room).")
    category: Category | None = Field(
        None, description=f"Set when the request clearly fits one category. {CATEGORY_GUIDE}"
    )
    min_price: float | None = Field(None, description="Minimum price in USD.")
    max_price: float | None = Field(None, description="Maximum price in USD.")
    ships_to: Country | None = Field(None, description="Set when the customer said where they live.")
    in_stock_only: bool = Field(False, description="True when the customer needs it now.")


@tool("search_products", args_schema=SearchProductsArgs, response_format="content_and_artifact")
def search_products_tool(
    query: str = "",
    category: str | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    ships_to: str | None = None,
    in_stock_only: bool = False,
):
    """Search the store catalog. Returns up to 5 matching products with id, price, stock and shipping countries."""
    flt = ProductFilter(category, min_price, max_price, ships_to, in_stock_only)
    # Models sometimes put everything in filters and leave the query empty; search on the category then
    hits = search_products(query.strip() or category or "home furniture", flt, limit=5)
    rows = [
        {
            "id": h["id"],
            "name": h["name"],
            "category": h["category"],
            "price_usd": h["price_usd"],
            "in_stock": h["stock"] > 0,
            "ships_to": h["ships_to"],
            "material": h.get("material"),
            "color": h.get("color"),
        }
        for h in hits
    ]
    content = _dump({"results": rows}) if rows else _dump({"results": [], "note": "No product matches these filters."})
    return content, {"products": [_card(h) for h in hits]}


@tool(response_format="content_and_artifact")
def get_product_details(product_id: str):
    """Full details for one product id: description, materials, size in inches and cm, weight, stock, shipping countries."""
    p = catalog.products().get(product_id.strip())
    if not p:
        return _dump({"error": f"No product with id {product_id}."}), {"products": []}
    dims = p.get("dimensions_in") or {}
    detail = {
        "id": p["id"],
        "name": p["name"],
        "brand": p.get("brand"),
        "category": p["category"],
        "price_usd": p["price_usd"],
        "stock": p["stock"],
        "ships_to": p["ships_to"],
        "material": p.get("material"),
        "fabric": p.get("fabric"),
        "color": p.get("color"),
        "style": p.get("style"),
        "size_in": dims or None,
        "size_cm": {k: catalog.to_cm(v) for k, v in dims.items()} or None,
        "weight_lb": p.get("weight_lb"),
        "weight_kg": round(p["weight_lb"] * 0.4536, 1) if p.get("weight_lb") else None,
        "description": p.get("bullets", []),
    }
    return _dump(detail), {"products": [_card(p)]}


@tool(response_format="content_and_artifact")
def search_store_policies(question: str):
    """Search store policies (shipping, UK customs/VAT, returns, warranty, care, payments, support hours). Returns the 3 most relevant sections with their ids."""
    hits = search_policies(question, limit=3)
    sections = [{"id": h["id"], "text": h["text"]} for h in hits]
    return _dump({"sections": sections}), {"policy_ids": [h["id"] for h in hits]}


@tool(response_format="content_and_artifact")
def quote_shipping(product_ids: list[str], country: Country):
    """Exact shipping cost and delivery time for a basket of product ids to US or UK. Use this instead of calculating shipping yourself."""
    s = get_settings()
    items = [catalog.products().get(pid.strip()) for pid in product_ids]
    missing = [pid for pid, p in zip(product_ids, items, strict=True) if p is None]
    if missing:
        return _dump({"error": f"Unknown product ids: {missing}"}), {}
    blocked = [p["name"] for p in items if country not in p["ships_to"]]
    if blocked:
        return _dump({"can_ship": False, "country": country, "not_shippable": blocked}), {}

    subtotal = round(sum(p["price_usd"] for p in items), 2)
    has_freight = any(p["category"] in FREIGHT for p in items)
    if country == "US":
        if has_freight:
            cost, eta = 149.0, "7-14 business days, white-glove freight (carrier calls to schedule)"
        else:
            cost, eta = (0.0 if subtotal >= 99 else 9.95), "3-7 business days after dispatch (dispatch in 1-2 days)"
        tax_note = None
    else:
        cost, eta = (0.0 if subtotal >= 250 else 24.95), "7-14 business days after dispatch via Royal Mail or DHL"
        gbp = round(subtotal * s.gbp_per_usd, 2)
        tax_note = (
            f"Goods value about £{gbp}: UK VAT 20% is added at checkout."
            if gbp <= 135
            else f"Goods value about £{gbp} (over £135): VAT and import duty are collected by the carrier on delivery."
        )
    result = {
        "can_ship": True,
        "country": country,
        "subtotal_usd": subtotal,
        "shipping_usd": cost,
        "total_before_tax_usd": round(subtotal + cost, 2),
        "delivery": eta,
        "uk_tax_note": tax_note,
        "out_of_stock": [p["name"] for p in items if p["stock"] == 0],
    }
    return _dump(result), {}


@tool(response_format="content_and_artifact")
def lookup_order(order_id: str, email: str):
    """Order status. Needs BOTH the order id (KH-12345) and the checkout email; never guess either."""
    o = catalog.orders().get(order_id.strip().upper())
    if not o or o["email"].lower() != email.strip().lower():
        # Same answer for "no such order" and "wrong email" so ids cannot be probed
        return _dump({"found": False, "note": "No order matches this id and email."}), {}
    public = {k: o[k] for k in ("order_id", "status", "carrier", "tracking", "eta", "placed_at", "country", "items")}
    return _dump({"found": True, "order": public}), {}


@tool(response_format="content_and_artifact")
def handoff_to_human(reason: str, summary: str):
    """Pass the conversation to a human agent. Use for complaints, refund disputes, damage or warranty claims, trade orders, or when you cannot help. Give a one-line reason and a short summary for the agent."""
    ticket = "T-" + uuid.uuid4().hex[:6].upper()
    result = {
        "ticket": ticket,
        "hours": "Mon-Fri 9am-6pm US Eastern",
        "reply_within": "1 business day",
        "email": "support@kestrelhome.example",
    }
    return _dump(result), {"handoff": {"ticket": ticket, "reason": reason, "summary": summary}}


TOOLS = [
    search_products_tool,
    get_product_details,
    search_store_policies,
    quote_shipping,
    lookup_order,
    handoff_to_human,
]
TOOLS_BY_NAME = {t.name: t for t in TOOLS}
