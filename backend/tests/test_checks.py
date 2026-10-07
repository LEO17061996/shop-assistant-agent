from app.agent.graph import to_messages
from eval.checks import Trace, money_in, run_checks

TOOL_OUT = (
    '{"results": [{"id": "B07MFYTSDF", "price_usd": 89.99}], "shipping_usd": 24.95, "uk_tax_note": "about £67.49"}'
)


def trace(answer: str, **kw) -> Trace:
    return Trace(message="table under $150", history_text="", answer=answer, tool_outputs=[TOOL_OUT], **kw)


def test_money_parsing():
    assert money_in("$1,299.00 or 24.95 USD or £67.49") == {("USD", 1299.0), ("USD", 24.95), ("GBP", 67.49)}


def test_grounded_prices_pass():
    r = run_checks(trace("It is $89.99, shipping $24.95, about £67.49 before VAT. Under your $150 budget."), {})
    assert r["grounded_money"]["pass"]


def test_wrong_currency_is_caught():
    # Real failure from a Claude run: a USD price shown with a pound sign
    r = run_checks(trace("The table is £89.99."), {})
    assert not r["grounded_money"]["pass"]


def test_invented_price_is_caught():
    r = run_checks(trace("It is $79.99."), {})
    assert not r["grounded_money"]["pass"]


def test_filter_ranges_and_alternative_tools():
    t = trace(
        "ok",
        tool_calls=[{"name": "search_products", "args": {"category": "Tables", "max_price": 150, "ships_to": "uk"}}],
    )
    expect = {
        "tools": ["get_product_details|search_products"],
        "filters": {"category": "Tables", "ships_to": "UK", "max_price": [140, 160]},
    }
    r = run_checks(t, expect)
    assert r["tools_called"]["pass"] and r["search_filters"]["pass"]


def test_shown_ids_survive_the_round_trip():
    msgs = to_messages(
        [
            {"role": "user", "content": "chairs?"},
            {"role": "assistant", "content": "Try the Goodwin.", "product_ids": ["B07HZ1LXVM"]},
            {"role": "user", "content": "how big is it?"},
        ]
    )
    assert msgs[1].content.endswith("[shown: B07HZ1LXVM]")


def test_copied_history_note_is_dropped_and_flagged():
    msgs = to_messages([{"role": "assistant", "content": "Try these.\n[shown: B1, B2", "product_ids": ["B1"]}])
    assert msgs[0].content == "Try these.\n[shown: B1]"
    assert not run_checks(trace("Try these. [shown: B1]"), {})["no_internal_notes"]["pass"]
