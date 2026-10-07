"""Listing Studio endpoints.

POST /api/studio/analyze streams Server-Sent Events:
    stage    a pipeline step started or finished (photo, copy, similar) with its duration
    facts    what the photo shows
    check    rule violations found in one draft (round 0 = first draft)
    copy     the final listing and ads, and whether every rule passed
    similar  catalog products that look alike
    done     model calls, tokens, cost, latency
    error    something failed; the message is safe to show
"""

import json
import logging
import time
from typing import Annotated

import httpx
from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field, ValidationError
from sse_starlette.sse import EventSourceResponse

from app import catalog
from app.config import get_settings
from app.limits import check_rate_limit
from app.studio.pipeline import (
    CLAIMS_MODEL,
    MAX_IMAGE_BYTES,
    BadImage,
    Usage,
    find_similar,
    prepare_image,
    read_photo,
    write_copy,
)
from app.studio.schemas import Copy, ProductFacts, SellerNotes
from app.studio.shopify import to_csv

router = APIRouter(prefix="/api/studio")
log = logging.getLogger(__name__)

# One per category with a clean product shot, for visitors who have no photo at hand
SAMPLE_IDS = [
    "B07HZ1LXVM",  # accent chair
    "B071ZJ6CK3",  # jute rug
    "B07DBHC37B",  # floor lamp
    "B07MFYTSDF",  # console table
    "B07JD7RFRN",  # sofa
    "B075HX5PQ7",  # wall vase
    "B072Y2S76T",  # bar stool
    "B0719SNKSY",  # platform bed
]
CARD_FIELDS = ("id", "name", "price_usd", "stock", "ships_to", "category", "image_url")


def sse(event: str, data: dict) -> dict:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


@router.get("/samples")
def samples():
    products = catalog.products()
    return [{k: products[i].get(k) for k in CARD_FIELDS} for i in SAMPLE_IDS if i in products]


async def _load_image(image: UploadFile | None, sample_id: str | None) -> tuple[bytes, str | None]:
    if image is not None:
        return await image.read(MAX_IMAGE_BYTES + 1), None
    if sample_id:
        p = catalog.products().get(sample_id)
        if not p:
            raise HTTPException(404, "Unknown sample.")
        # Only catalog URLs are fetched, never a URL sent by the client
        async with httpx.AsyncClient(timeout=20) as client:
            r = await client.get(p["image_url"])
            r.raise_for_status()
        return r.content, p["image_url"]
    raise HTTPException(422, "Send an image or pick a sample.")


@router.post("/analyze")
async def analyze(
    request: Request,
    image: Annotated[UploadFile | None, File()] = None,
    sample_id: Annotated[str | None, Form()] = None,
    price_usd: Annotated[float | None, Form()] = None,
    dimensions: Annotated[str | None, Form()] = None,
    notes: Annotated[str | None, Form()] = None,
    hint: Annotated[str | None, Form(max_length=60)] = None,
):
    check_rate_limit(request)
    try:
        seller = SellerNotes(price_usd=price_usd, dimensions=dimensions or None, notes=notes or None)
    except ValidationError as e:
        raise HTTPException(422, e.errors()[0]["msg"]) from e
    data, image_url = await _load_image(image, sample_id)
    try:
        jpeg = prepare_image(data)
    except BadImage as e:
        raise HTTPException(422, str(e)) from e

    model = f"{get_settings().gemini_model} + {CLAIMS_MODEL} (claim check)"

    async def events():
        t0 = time.perf_counter()
        usage = Usage()
        try:
            yield sse("stage", {"step": "photo", "status": "start"})
            t = time.perf_counter()
            facts = await read_photo(jpeg, usage, hint=hint or None)
            yield sse("stage", {"step": "photo", "status": "done", "ms": round((time.perf_counter() - t) * 1000)})
            yield sse("facts", {"facts": facts.model_dump(), "image_url": image_url})

            yield sse("stage", {"step": "copy", "status": "start"})
            t = time.perf_counter()
            result = await write_copy(facts, seller, usage)
            for i, violations in enumerate(result.rounds):
                yield sse("check", {"round": i, "violations": [v.model_dump() for v in violations]})
            yield sse("stage", {"step": "copy", "status": "done", "ms": round((time.perf_counter() - t) * 1000)})
            yield sse("copy", {"copy": result.copy.model_dump(), "passed": result.passed})

            yield sse("stage", {"step": "similar", "status": "start"})
            t = time.perf_counter()
            similar = [{k: h.get(k) for k in CARD_FIELDS} for h in find_similar(facts)]
            yield sse("stage", {"step": "similar", "status": "done", "ms": round((time.perf_counter() - t) * 1000)})
            yield sse("similar", {"products": similar})
        except Exception as e:  # provider outages, quota errors, unparseable output
            log.exception("studio pipeline failed")
            msg = (
                "The model is busy right now. Please try again in a minute."
                if "429" in str(e)
                else "Something went wrong reading this photo. Please try another one."
            )
            yield sse("error", {"message": msg})
            return
        yield sse(
            "done",
            {
                "model": model,
                "calls": usage.calls,
                "repairs": len(result.rounds) - 1,
                "input_tokens": usage.input_tokens,
                "output_tokens": usage.output_tokens,
                "cost_usd": round(usage.cost_usd, 6),
                "latency_ms": round((time.perf_counter() - t0) * 1000),
            },
        )

    return EventSourceResponse(events())


class CsvRequest(BaseModel):
    copy_: Copy = Field(alias="copy")  # "copy" would shadow BaseModel.copy
    facts: ProductFacts
    notes: SellerNotes = SellerNotes()
    image_url: str | None = None


@router.post("/shopify.csv")
def shopify_csv(req: CsvRequest):
    # Only catalog photo URLs go into the file; uploads have no public URL
    image_url = req.image_url if (req.image_url or "").startswith("https://amazon-berkeley-objects.") else None
    csv_text = to_csv(req.copy_, req.facts, req.notes, image_url)
    return Response(
        csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="shopify-product.csv"'},
    )
