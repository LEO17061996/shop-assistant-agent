"""Shopify product import CSV (classic column names, which Shopify's importer still accepts).

Products are created as drafts so nothing goes live before a person reviews it.
"""

import csv
import html
import io
import re

from app.studio.schemas import Copy, ProductFacts, SellerNotes

COLUMNS = [
    "Handle",
    "Title",
    "Body (HTML)",
    "Vendor",
    "Type",
    "Tags",
    "Published",
    "Variant Price",
    "Variant Requires Shipping",
    "Image Src",
    "Image Alt Text",
    "SEO Title",
    "SEO Description",
    "Status",
]


def handle(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:80]


def body_html(description: str) -> str:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", description) if p.strip()]
    return "".join(f"<p>{html.escape(p)}</p>" for p in paragraphs)


def to_csv(copy: Copy, facts: ProductFacts, notes: SellerNotes, image_url: str | None = None) -> str:
    listing = copy.listing
    row = {
        "Handle": handle(listing.title),
        "Title": listing.title,
        "Body (HTML)": body_html(listing.description),
        "Vendor": "Kestrel Home",
        "Type": facts.product_type,
        "Tags": ", ".join(listing.tags),
        "Published": "FALSE",
        "Variant Price": f"{notes.price_usd:.2f}" if notes.price_usd is not None else "",
        "Variant Requires Shipping": "TRUE",
        "Image Src": image_url or "",
        "Image Alt Text": f"{', '.join(facts.colors[:1])} {facts.product_type}".strip(),
        "SEO Title": listing.seo_title,
        "SEO Description": listing.seo_description,
        "Status": "draft",
    }
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=COLUMNS, lineterminator="\n")
    writer.writeheader()
    writer.writerow(row)
    return out.getvalue()
