import json
import typing

from app import catalog
from app.agent import tools


def call(tool, **args) -> dict:
    content, _ = tool.func(**args)
    return json.loads(content)


def first(category: str, *, ships_uk: bool | None = None, max_price: float | None = None) -> dict:
    for p in catalog.products().values():
        if p["category"] != category:
            continue
        if ships_uk is not None and ("UK" in p["ships_to"]) != ships_uk:
            continue
        if max_price is not None and p["price_usd"] > max_price:
            continue
        return p
    raise LookupError(category)


def test_category_enum_matches_catalog():
    assert set(typing.get_args(tools.Category)) == set(catalog.categories())


def test_us_small_order_pays_flat_rate():
    p = first("Pillows & Throws", max_price=98)
    r = call(tools.quote_shipping, product_ids=[p["id"]], country="US")
    assert r["shipping_usd"] == 9.95


def test_us_order_over_99_ships_free():
    p = next(x for x in catalog.products().values() if x["category"] == "Chairs" and x["price_usd"] >= 99)
    r = call(tools.quote_shipping, product_ids=[p["id"]], country="US")
    assert r["shipping_usd"] == 0.0


def test_freight_item_costs_149_in_us():
    sofa = first("Sofas")
    r = call(tools.quote_shipping, product_ids=[sofa["id"]], country="US")
    assert r["shipping_usd"] == 149.0
    assert "freight" in r["delivery"]


def test_sofa_cannot_ship_to_uk():
    sofa = first("Sofas")
    r = call(tools.quote_shipping, product_ids=[sofa["id"]], country="UK")
    assert r["can_ship"] is False


def test_uk_vat_note_switches_at_135_gbp():
    cheap = first("Pillows & Throws", ships_uk=True)
    r = call(tools.quote_shipping, product_ids=[cheap["id"]], country="UK")
    assert "added at checkout" in r["uk_tax_note"]
    pricey = next(p for p in catalog.products().values() if "UK" in p["ships_to"] and p["price_usd"] > 400)
    r = call(tools.quote_shipping, product_ids=[pricey["id"]], country="UK")
    assert "collected by the carrier" in r["uk_tax_note"]


def test_unknown_product_id_is_an_error_not_a_guess():
    r = call(tools.quote_shipping, product_ids=["NOPE"], country="US")
    assert "error" in r


def test_product_details_include_cm():
    p = next(x for x in catalog.products().values() if x.get("dimensions_in"))
    r = call(tools.get_product_details, product_id=p["id"])
    k = next(iter(p["dimensions_in"]))
    assert r["size_cm"][k] == round(p["dimensions_in"][k] * 2.54, 1)


def test_order_lookup_needs_matching_email():
    order = next(iter(catalog.orders().values()))
    ok = call(tools.lookup_order, order_id=order["order_id"].lower(), email=order["email"].upper())
    assert ok["found"] is True and ok["order"]["status"] == order["status"]
    wrong_email = call(tools.lookup_order, order_id=order["order_id"], email="someone@else.com")
    missing = call(tools.lookup_order, order_id="KH-00000", email=order["email"])
    # Identical answers, so a caller cannot tell which order ids exist
    assert wrong_email == missing == {"found": False, "note": "No order matches this id and email."}


def test_lookup_order_never_returns_email():
    order = next(iter(catalog.orders().values()))
    r = call(tools.lookup_order, order_id=order["order_id"], email=order["email"])
    assert "email" not in r["order"]


def test_search_works_with_filters_only():
    # Models sometimes send only filters; that must not be a validation error
    r = call(tools.search_products_tool, category="Rugs", max_price=300, ships_to="UK")
    assert r["results"] and all(x["category"] == "Rugs" and x["price_usd"] <= 300 for x in r["results"])
