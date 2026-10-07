import pytest

from app.rag.search import ProductFilter, search_policies, search_products


@pytest.mark.parametrize("mode", ["dense", "sparse", "hybrid"])
def test_filters_hold_in_every_mode(mode):
    flt = ProductFilter(category="Chairs", max_price=200, ships_to="UK", in_stock_only=True)
    hits = search_products("comfortable armchair", flt, limit=5, mode=mode)
    assert hits
    for h in hits:
        assert h["category"] == "Chairs"
        assert h["price_usd"] <= 200
        assert "UK" in h["ships_to"]
        assert h["stock"] > 0


def test_impossible_filter_returns_nothing():
    assert search_products("sofa", ProductFilter(category="Sofas", ships_to="UK")) == []


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Do I pay VAT on a UK order over 135 pounds?", "shipping#uk-customs-duties-and-vat"),
        ("Can I return a rug that was cut to size?", "returns#items-that-cannot-be-returned"),
        ("How do I clean a leather couch?", "care#leather-and-faux-leather"),
        ("What payment methods do you take?", "orders-and-support#payment-methods"),
    ],
)
def test_policy_search_finds_the_right_section(question, expected):
    assert expected in [h["id"] for h in search_policies(question, limit=3)]
