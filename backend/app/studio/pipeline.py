"""Listing Studio: photo -> facts -> copy -> check/repair loop -> similar products.

Each step is a separate model call with a structured output, so every intermediate
result can be shown, checked and evaluated on its own.
"""

import base64
import io
from dataclasses import dataclass, field

from langchain_core.messages import HumanMessage
from PIL import Image, UnidentifiedImageError
from pydantic import BaseModel, Field

from app.agent.llm import cost_usd, fallback_model, make_llm
from app.agent.tools import CATEGORY_GUIDE
from app.config import get_settings
from app.rag.search import ProductFilter, search_products
from app.studio.rules import check
from app.studio.schemas import Copy, ProductFacts, SellerNotes, Violation

MAX_IMAGE_BYTES = 5 * 1024 * 1024
MAX_SIDE = 768  # enough detail for furniture; fewer image tokens than a full-size photo
MAX_REPAIRS = 2
# Checks claims in each draft. It is the same model the eval uses as judge, because Gemini 2.5 is closed
# to new API projects; the eval therefore also reports a run without this check (eval/README.md).
CLAIMS_MODEL = "gemini-3.5-flash-lite"

FACTS_PROMPT = f"""You catalogue product photos for an online home furnishing store.
Describe only what is visible in the photo. Do not guess hidden materials, sizes, brands or prices.
If the photo is a dimension diagram, a lifestyle scene or shows several products, say so in photo_issues and describe the main product.
Categories: {CATEGORY_GUIDE} Use "Other" if none fits."""

HINT_PROMPT = "The seller says the product for sale is: {hint}. Describe that product, not the room around it."

COPY_PROMPT = """You write product listings and Meta ads for an online home furnishing store selling to the US and UK.

Facts from the photo (the only product facts you may use):
{facts}

Seller notes (also true; may add price, size, origin or offers):
{notes}

Rules:
- State only what the facts or seller notes say. Never invent sizes, weights, prices, numbers, brands, certifications, "handmade", "eco-friendly", "free shipping" or discounts.
- A photo cannot show assembly, durability, comfort, weight capacity, warranty or care instructions. Leave these out unless the seller notes cover them.
- No superlatives or promises: avoid "best", "#1", "cheapest", "guaranteed", "lifetime", health claims.
- Ads must not assume things about the reader's personal life or attributes.
- US English. Title: most searched words first. Tags: lowercase, 1-3 words, no "#".
- Write prices as $343.99, at most once per text, and only if the seller gave one.
- Respect every length limit in the field descriptions; count characters."""

REPAIR_PROMPT = """Your draft broke these rules:
{violations}

Draft:
{draft}

Return the corrected version. Change only what is needed to fix the listed problems."""

CLAIMS_PROMPT = """You check product copy before it goes live.

Facts read from the product photo:
{facts}

Seller notes:
{notes}

Copy:
{copy}

List each specific claim in the copy that the facts and notes do not support: materials, finishes, sizes,
features, assembly, durability, comfort, indoor/outdoor use, origin, offers.
General marketing tone ("adds warmth to the room", "a versatile piece") is fine and must not be listed."""


class BadImage(ValueError):
    pass


def prepare_image(data: bytes) -> bytes:
    """Validate an upload and re-encode it as a small JPEG. Anything Pillow cannot open is rejected."""
    if len(data) > MAX_IMAGE_BYTES:
        raise BadImage("Image is larger than 5 MB.")
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except (UnidentifiedImageError, OSError) as e:
        raise BadImage("File is not a readable image.") from e
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=85)
    return out.getvalue()


@dataclass
class Usage:
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0  # summed per call, since the pipeline uses two models

    def add(self, raw, model: str) -> None:
        meta = getattr(raw, "usage_metadata", None) or {}
        self.calls += 1
        self.input_tokens += meta.get("input_tokens", 0)
        self.output_tokens += meta.get("output_tokens", 0)
        self.cost_usd += cost_usd(model, meta.get("input_tokens", 0), meta.get("output_tokens", 0)) or 0.0


@dataclass
class CopyResult:
    copy: Copy
    rounds: list[list[Violation]] = field(default_factory=list)  # violations found in each draft

    @property
    def passed(self) -> bool:
        return not self.rounds[-1]


async def _structured(schema, messages, usage: Usage, model: str | None):
    model = model or get_settings().gemini_model
    llm = make_llm("gemini", model).with_structured_output(schema, include_raw=True)
    fallback = fallback_model("gemini", model)
    if fallback:
        llm = llm.with_fallbacks([make_llm("gemini", fallback).with_structured_output(schema, include_raw=True)])
    out = await llm.ainvoke(messages)
    # Price the call by the model that actually answered, which may be the fallback
    usage.add(out["raw"], (out["raw"].response_metadata or {}).get("model_name") or model)
    if out["parsed"] is None:
        raise ValueError(f"Model output did not match {schema.__name__}: {out['parsing_error']}")
    return out["parsed"]


async def read_photo(jpeg: bytes, usage: Usage, model: str | None = None, hint: str | None = None) -> ProductFacts:
    # A hint matters for room shots: a rug photographed under a sofa is otherwise read as the sofa
    prompt = f"{FACTS_PROMPT}\n{HINT_PROMPT.format(hint=hint)}" if hint else FACTS_PROMPT
    msg = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {"type": "image", "base64": base64.b64encode(jpeg).decode(), "mime_type": "image/jpeg"},
        ]
    )
    return await _structured(ProductFacts, [msg], usage, model)


class Claims(BaseModel):
    unsupported: list[str] = Field(description="Unsupported claims, quoted or paraphrased. Empty if none.")


async def check_claims(copy: Copy, facts: ProductFacts, notes_json: str, usage: Usage) -> list[Violation]:
    """What the rule checks cannot see: statements the photo and notes do not back up."""
    prompt = CLAIMS_PROMPT.format(facts=facts.model_dump_json(), notes=notes_json, copy=copy.model_dump_json())
    claims: Claims = await _structured(Claims, [HumanMessage(prompt)], usage, CLAIMS_MODEL)
    return [Violation(field="copy", rule="unsupported_claim", detail=c) for c in claims.unsupported[:6]]


async def write_copy(
    facts: ProductFacts,
    notes: SellerNotes,
    usage: Usage,
    model: str | None = None,
    claim_check: bool = True,
) -> CopyResult:
    """Draft, check, and send violations back for a rewrite, at most MAX_REPAIRS times.

    Every draft gets the deterministic rule checks and, with claim_check, an LLM claim check.
    """
    notes_json = notes.model_dump_json(exclude_none=True) if notes.model_dump(exclude_none=True) else "(none)"
    prompt = COPY_PROMPT.format(facts=facts.model_dump_json(indent=1), notes=notes_json)

    async def all_checks(copy: Copy) -> list[Violation]:
        found = check(copy, facts, notes)
        if claim_check:
            found += await check_claims(copy, facts, notes_json, usage)
        return found

    draft: Copy = await _structured(Copy, [HumanMessage(prompt)], usage, model)
    result = CopyResult(copy=draft, rounds=[await all_checks(draft)])
    while result.rounds[-1] and len(result.rounds) <= MAX_REPAIRS:
        violations = "\n".join(f"- {v.field}: {v.rule} ({v.detail})" for v in result.rounds[-1])
        repair = REPAIR_PROMPT.format(violations=violations, draft=result.copy.model_dump_json(indent=1))
        result.copy = await _structured(Copy, [HumanMessage(f"{prompt}\n\n{repair}")], usage, model)
        result.rounds.append(await all_checks(result.copy))
    return result


def facts_query(facts: ProductFacts) -> str:
    return " ".join([facts.style, *facts.colors[:2], *facts.materials[:2], facts.product_type, *facts.features[:3]])


def find_similar(facts: ProductFacts, limit: int = 5) -> list[dict]:
    """Visual search without an image model: search the catalog with the photo's description."""
    flt = ProductFilter(category=facts.category) if facts.category != "Other" else None
    hits = search_products(facts_query(facts), flt, limit=limit)
    if not hits and flt:
        hits = search_products(facts_query(facts), None, limit=limit)
    return hits
