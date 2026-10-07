"""Deterministic checks on generated copy: platform limits, risky ad claims, invented numbers.

The model is asked to follow these rules, but asking is not enough; every draft is checked
here and the violations are sent back for a rewrite.
"""

import re

from app.studio.schemas import Copy, ProductFacts, SellerNotes, Violation

LIMITS = {
    "listing.title": 140,
    "listing.seo_title": 70,
    "listing.seo_description": 160,
    "ads.primary_text": 125,
    "ads.headline": 40,
    "ads.description": 30,
}
TAG_COUNT = 13
TAG_MAX = 20
SEO_DESCRIPTION_MIN = 50
DESCRIPTION_WORDS = (60, 220)

# Claims a furniture shop cannot back up from a photo, or that ad platforms reject.
# Some are allowed when the seller's notes say so (e.g. "free shipping").
RISKY_CLAIMS = {
    r"\bbest\b": None,
    r"#\s?1\b|\bnumber one\b": None,
    r"\bcheapest\b|\blowest price\b": None,
    r"\bguarantee[ds]?\b": None,
    r"\b100\s?%": None,
    r"\blifetime\b": None,
    r"\bcures?\b|\bheal(s|ing)?\b|\btherapeutic\b": None,
    r"\bfree shipping\b": "free shipping",
    r"\bhandmade\b|\bhand-?made\b|\bhandcrafted\b": "hand",
    r"\b(sale|discount|% off)\b": "sale",
    r"\beco-?friendly\b|\bsustainable\b|\bnon-?toxic\b": "eco",
}
NUMBER = re.compile(r"(?<![\w.])\d+(?:[.,]\d+)?")


def _numbers(text: str) -> set[str]:
    return {n.replace(",", ".") for n in NUMBER.findall(text)}


NUMBER_WORDS = {
    w: str(i) for i, w in enumerate("zero one two three four five six seven eight nine ten eleven twelve".split())
}


def _allowed_text(facts: ProductFacts, notes: SellerNotes) -> str:
    parts = [facts.model_dump_json()]
    if notes.price_usd is not None:
        parts.append(f"{notes.price_usd:.2f} {notes.price_usd:g}")
    parts += [notes.dimensions or "", notes.notes or ""]
    text = " ".join(parts).lower()
    # "two drawers" in the facts allows "2 drawers" in the copy
    return text + " " + " ".join(d for w, d in NUMBER_WORDS.items() if re.search(rf"\b{w}\b", text))


def check(copy: Copy, facts: ProductFacts, notes: SellerNotes) -> list[Violation]:
    v: list[Violation] = []
    listing = copy.listing

    def too_long(field: str, text: str, limit_key: str) -> None:
        limit = LIMITS[limit_key]
        if len(text) > limit:
            v.append(Violation(field=field, rule="max_length", detail=f"{len(text)} characters, limit {limit}"))

    too_long("listing.title", listing.title, "listing.title")
    too_long("listing.seo_title", listing.seo_title, "listing.seo_title")
    too_long("listing.seo_description", listing.seo_description, "listing.seo_description")
    if len(listing.seo_description) < SEO_DESCRIPTION_MIN:
        v.append(Violation(field="listing.seo_description", rule="min_length", detail="shorter than 50 characters"))
    words = len(listing.description.split())
    if not DESCRIPTION_WORDS[0] <= words <= DESCRIPTION_WORDS[1]:
        v.append(Violation(field="listing.description", rule="word_count", detail=f"{words} words, want 60-220"))

    tags = [t.strip() for t in listing.tags]
    if len(tags) != TAG_COUNT:
        v.append(Violation(field="listing.tags", rule="count", detail=f"{len(tags)} tags, need exactly 13"))
    if len({t.lower() for t in tags}) != len(tags):
        v.append(Violation(field="listing.tags", rule="unique", detail="duplicate tags"))
    for t in tags:
        if len(t) > TAG_MAX:
            v.append(
                Violation(field="listing.tags", rule="max_length", detail=f"'{t}' is {len(t)} characters, limit 20")
            )

    if len(copy.ads) != 3 or {a.angle for a in copy.ads} != {"benefit", "style", "problem-solution"}:
        v.append(Violation(field="ads", rule="angles", detail="need exactly 3 ads: benefit, style, problem-solution"))
    for i, ad in enumerate(copy.ads):
        too_long(f"ads[{i}].primary_text", ad.primary_text, "ads.primary_text")
        too_long(f"ads[{i}].headline", ad.headline, "ads.headline")
        too_long(f"ads[{i}].description", ad.description, "ads.description")

    allowed = _allowed_text(facts, notes)
    texts = {
        "listing.title": listing.title,
        "listing.description": listing.description,
        "listing.seo_title": listing.seo_title,
        "listing.seo_description": listing.seo_description,
        "listing.tags": " ".join(tags),
        **{f"ads[{i}]": f"{a.primary_text} {a.headline} {a.description}" for i, a in enumerate(copy.ads)},
    }
    allowed_numbers = _numbers(allowed)
    for field, text in texts.items():
        low = text.lower()
        for pattern, unlock in RISKY_CLAIMS.items():
            m = re.search(pattern, low)
            if m and not (unlock and unlock in allowed):
                v.append(Violation(field=field, rule="risky_claim", detail=f"'{m.group(0)}' cannot be backed up"))
        invented = sorted(_numbers(text) - allowed_numbers)
        if invented:
            v.append(
                Violation(field=field, rule="invented_number", detail=f"{invented} not in the photo facts or notes")
            )
    return v
