import asyncio
import csv
import io
import json

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from app import limits, main
from app.studio import pipeline, routes
from app.studio.rules import check
from app.studio.schemas import AdVariant, Copy, Listing, ProductFacts, SellerNotes
from app.studio.shopify import to_csv
from tests.conftest import ScriptedModel, tool_call

FACTS = ProductFacts(
    category="Chairs",
    product_type="accent chair",
    colors=["navy blue"],
    materials=["fabric", "wood"],
    style="mid-century modern",
    features=["tapered wooden legs", "two cushions"],
)
TAGS = [
    "accent chair",
    "navy chair",
    "blue armchair",
    "mid century chair",
    "living room chair",
    "reading chair",
    "fabric chair",
    "wood leg chair",
    "modern armchair",
    "lounge chair",
    "bedroom chair",
    "upholstered chair",
    "navy blue decor",
]
DESCRIPTION = " ".join(["A navy blue accent chair with tapered wooden legs."] * 8)


def make_copy(**listing_overrides) -> Copy:
    listing = {
        "title": "Navy Blue Accent Chair, Mid-Century Modern",
        "description": DESCRIPTION,
        "tags": TAGS,
        "seo_title": "Navy Blue Mid-Century Accent Chair",
        "seo_description": "A navy blue mid-century modern accent chair with tapered wooden legs and two cushions.",
    } | listing_overrides
    ads = [
        AdVariant(angle="benefit", primary_text="Two soft cushions.", headline="Sit back", description="Navy chair"),
        AdVariant(angle="style", primary_text="Mid-century lines.", headline="Clean lines", description="Wood legs"),
        AdVariant(
            angle="problem-solution", primary_text="Corner looks bare?", headline="Fill it", description="Accent"
        ),
    ]
    return Copy(listing=Listing(**listing), ads=ads)


def rules_broken(copy: Copy, notes: SellerNotes | None = None) -> set[str]:
    return {f"{v.field}:{v.rule}" for v in check(copy, FACTS, notes or SellerNotes())}


def test_clean_copy_passes():
    assert rules_broken(make_copy()) == set()


def test_platform_limits():
    broken = rules_broken(make_copy(title="x" * 141, tags=TAGS[:12], seo_description="too short"))
    assert {"listing.title:max_length", "listing.tags:count", "listing.seo_description:min_length"} <= broken


def test_risky_claims_unless_seller_says_so():
    copy = make_copy(title="Best handmade navy chair")
    assert {"listing.title:risky_claim"} <= rules_broken(copy)
    # "handmade" is fine when the seller says it; "best" never is
    still = check(copy, FACTS, SellerNotes(notes="Handmade in Vermont"))
    assert [v.detail for v in still if v.rule == "risky_claim"] == ["'best' cannot be backed up"]


def test_numbers_must_come_from_facts_or_notes():
    copy = make_copy(title="Navy chair, 2 cushions, 32 inches wide, $149.00")
    assert "listing.title:invented_number" in rules_broken(copy)
    ok = rules_broken(copy, SellerNotes(price_usd=149, dimensions="32 inches wide"))
    assert "listing.title:invented_number" not in ok  # "2" comes from "two cushions" in the facts


def test_prepare_image_rejects_non_images_and_shrinks_big_ones():
    with pytest.raises(pipeline.BadImage):
        pipeline.prepare_image(b"not an image")
    buf = io.BytesIO()
    Image.new("RGB", (2000, 1000), "navy").save(buf, format="PNG")
    out = Image.open(io.BytesIO(pipeline.prepare_image(buf.getvalue())))
    assert out.format == "JPEG" and max(out.size) == pipeline.MAX_SIDE


def test_repair_loop_fixes_a_broken_draft(monkeypatch):
    bad = make_copy(title="The best navy chair").model_dump()
    good = make_copy().model_dump()
    model = ScriptedModel(script=[tool_call("Copy", bad), tool_call("Copy", good)])
    monkeypatch.setattr(pipeline, "make_llm", lambda *a, **k: model)
    usage = pipeline.Usage()
    result = asyncio.run(pipeline.write_copy(FACTS, SellerNotes(), usage, claim_check=False))
    assert [len(r) for r in result.rounds] == [1, 0]
    assert result.passed and usage.calls == 2


def test_repair_loop_gives_up_after_two_rewrites(monkeypatch):
    bad = make_copy(title="The best navy chair").model_dump()
    model = ScriptedModel(script=[tool_call("Copy", bad)])
    monkeypatch.setattr(pipeline, "make_llm", lambda *a, **k: model)
    result = asyncio.run(pipeline.write_copy(FACTS, SellerNotes(), pipeline.Usage(), claim_check=False))
    assert len(result.rounds) == 1 + pipeline.MAX_REPAIRS and not result.passed


def test_claim_check_sends_unsupported_claims_back(monkeypatch):
    good = make_copy().model_dump()
    model = ScriptedModel(
        script=[
            tool_call("Copy", good),
            tool_call("Claims", {"unsupported": ["requires assembly"]}),
            tool_call("Copy", good),
            tool_call("Claims", {"unsupported": []}),
        ]
    )
    monkeypatch.setattr(pipeline, "make_llm", lambda *a, **k: model)
    usage = pipeline.Usage()
    result = asyncio.run(pipeline.write_copy(FACTS, SellerNotes(), usage))
    assert [[v.rule for v in r] for r in result.rounds] == [["unsupported_claim"], []]
    assert usage.calls == 4


def test_shopify_csv_is_a_draft_with_escaped_html():
    copy = make_copy(description=DESCRIPTION + "\n\nFits <small> rooms & corners.")
    rows = list(csv.DictReader(io.StringIO(to_csv(copy, FACTS, SellerNotes(price_usd=137.99)))))
    assert len(rows) == 1
    row = rows[0]
    assert row["Status"] == "draft" and row["Published"] == "FALSE" and row["Variant Price"] == "137.99"
    assert "&lt;small&gt; rooms &amp; corners" in row["Body (HTML)"]
    assert row["Handle"] == "navy-blue-accent-chair-mid-century-modern"


@pytest.fixture
def api(monkeypatch):
    async def fake_read_photo(jpeg, usage, model=None, hint=None):
        usage.calls += 1
        return FACTS

    async def fake_write_copy(facts, notes, usage, model=None):
        usage.calls += 1
        return pipeline.CopyResult(copy=make_copy(), rounds=[[]])

    monkeypatch.setattr(routes, "read_photo", fake_read_photo)
    monkeypatch.setattr(routes, "write_copy", fake_write_copy)
    limits._hits.clear()
    with TestClient(main.app) as c:
        yield c


def png_bytes() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (64, 64), "white").save(buf, format="PNG")
    return buf.getvalue()


def test_samples(api):
    samples = api.get("/api/studio/samples").json()
    assert len(samples) == len(routes.SAMPLE_IDS) and all(s["image_url"] for s in samples)


def test_analyze_streams_facts_copy_and_similar(api):
    r = api.post("/api/studio/analyze", files={"image": ("chair.png", png_bytes(), "image/png")})
    events = [
        (block.split("\n")[0].removeprefix("event: "), json.loads(block.split("data: ", 1)[1]))
        for block in r.text.replace("\r\n", "\n").strip().split("\n\n")
    ]
    kinds = [e for e, _ in events]
    assert kinds[0] == "stage" and kinds[-1] == "done"
    assert {"facts", "check", "copy", "similar"} <= set(kinds)
    similar = next(d for e, d in events if e == "similar")["products"]
    assert similar and all(p["category"] == "Chairs" for p in similar)


def test_analyze_rejects_files_that_are_not_images(api):
    r = api.post("/api/studio/analyze", files={"image": ("x.png", b"<?php echo 1; ?>", "image/png")})
    assert r.status_code == 422


def test_analyze_needs_an_image_or_sample(api):
    assert api.post("/api/studio/analyze", data={"price_usd": "10"}).status_code == 422


def test_csv_endpoint_drops_foreign_image_urls(api):
    body = {"copy": make_copy().model_dump(), "facts": FACTS.model_dump(), "image_url": "https://evil.example/x.jpg"}
    r = api.post("/api/studio/shopify.csv", json=body)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert next(csv.DictReader(io.StringIO(r.text)))["Image Src"] == ""
