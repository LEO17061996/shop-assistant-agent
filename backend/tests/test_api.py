import json

import pytest
from fastapi.testclient import TestClient

from app import limits, main
from app.agent.graph import build_graph
from tests.conftest import ScriptedModel, answer, tool_call


@pytest.fixture
def api(monkeypatch):
    model = ScriptedModel(
        script=[
            tool_call("search_products", {"query": "oak chair", "category": "Chairs", "max_price": 300}),
            answer("Here is a chair."),
        ]
    )
    graph = build_graph(model, "system", max_steps=6, history_budget=6000)
    monkeypatch.setattr(main, "get_graph", lambda *a, **k: graph)
    limits._hits.clear()
    with TestClient(main.app) as c:
        yield c


def parse_sse(text: str) -> list[tuple[str, dict]]:
    events = []
    for block in text.replace("\r\n", "\n").strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.split("\n") if ": " in line)
        events.append((lines["event"], json.loads(lines["data"])))
    return events


def test_chat_streams_trace_products_answer_and_usage(api):
    r = api.post("/api/chat", json={"messages": [{"role": "user", "content": "oak chair under 300"}]})
    assert r.status_code == 200
    events = parse_sse(r.text)
    kinds = [e for e, _ in events]
    assert kinds[0] == "step" and events[0][1]["name"] == "search_products"
    assert "products" in kinds
    assert all(p["price_usd"] <= 300 for p in next(d for e, d in events if e == "products")["products"])
    assert "".join(d["text"] for e, d in events if e == "token") == "Here is a chair."
    done = events[-1]
    assert done[0] == "done" and done[1]["steps"] == 2 and done[1]["input_tokens"] == 100


def test_last_message_must_be_from_user(api):
    r = api.post("/api/chat", json={"messages": [{"role": "assistant", "content": "hi"}]})
    assert r.status_code == 422


def test_long_message_rejected(api):
    r = api.post("/api/chat", json={"messages": [{"role": "user", "content": "x" * 5000}]})
    assert r.status_code == 422


def test_rate_limit(api):
    body = {"messages": [{"role": "user", "content": "hi"}]}
    codes = [api.post("/api/chat", json=body, headers={"x-forwarded-for": "1.2.3.4"}).status_code for _ in range(12)]
    assert codes[:10] == [200] * 10 and codes[10] == 429


def test_product_endpoint(api):
    from app import catalog

    pid = next(iter(catalog.products()))
    assert api.get(f"/api/products/{pid}").json()["id"] == pid
    assert api.get("/api/products/nope").status_code == 404
