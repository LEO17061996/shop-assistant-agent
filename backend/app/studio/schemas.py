"""Structured outputs for Listing Studio. Field descriptions double as instructions to the model."""

from typing import Literal

from pydantic import BaseModel, Field

from app.agent.tools import Category

Angle = Literal["benefit", "style", "problem-solution"]


class ProductFacts(BaseModel):
    """What the photo shows. Nothing here may be guessed."""

    category: Category | Literal["Other"]
    product_type: str = Field(description="Short noun phrase, e.g. 'accent chair', 'round jute rug'.")
    colors: list[str] = Field(description="1-3 main colours, most dominant first, plain names like 'navy blue'.")
    materials: list[str] = Field(
        description="Materials you can actually see, e.g. 'wood', 'metal', 'velvet'. Empty if unclear."
    )
    style: str = Field(description="One style label, e.g. 'mid-century modern', 'farmhouse', 'industrial'.")
    features: list[str] = Field(description="2-6 visible features, e.g. 'tapered wooden legs', 'two drawers'.")
    photo_issues: list[str] = Field(
        default_factory=list,
        description="Problems for a listing photo: 'dimension diagram', 'several products', 'cropped', 'lifestyle scene'.",
    )


class SellerNotes(BaseModel):
    """What only the seller knows. Copy may state these as facts."""

    price_usd: float | None = Field(None, ge=0, le=100_000)
    dimensions: str | None = Field(None, max_length=120)
    notes: str | None = Field(None, max_length=400)


class Listing(BaseModel):
    title: str = Field(description="Marketplace title, at most 140 characters, most important words first.")
    description: str = Field(description="80-180 words, short paragraphs, plain text, no markdown.")
    tags: list[str] = Field(description="Exactly 13 search tags, lowercase, each at most 20 characters.")
    seo_title: str = Field(description="Web page title, at most 70 characters.")
    seo_description: str = Field(description="Meta description, 50-160 characters.")


class AdVariant(BaseModel):
    angle: Angle
    primary_text: str = Field(description="At most 125 characters.")
    headline: str = Field(description="At most 40 characters.")
    description: str = Field(description="At most 30 characters.")


class Copy(BaseModel):
    listing: Listing
    ads: list[AdVariant] = Field(description="Exactly 3 ads, one per angle: benefit, style, problem-solution.")


class Violation(BaseModel):
    field: str
    rule: str
    detail: str
