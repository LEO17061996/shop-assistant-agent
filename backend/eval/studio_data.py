"""Images for the Listing Studio eval, downloaded once from the ABO bucket into data/images/.

main/<product_id>.jpg   the catalog photo of every product (CLIP baseline index)
alt/<product_id>.jpg    a different photo of the same product (visual search queries)

Usage: python -m eval.studio_data
"""

import asyncio
import csv
import gzip
import json
from pathlib import Path

import httpx

from app import catalog
from app.config import get_settings

DATA = get_settings().data_dir
IMAGES = DATA / "images"
BASE_URL = "https://amazon-berkeley-objects.s3.amazonaws.com/images/small/"


def alt_image_paths() -> dict[str, str]:
    """First alternate photo of each catalog product, from the raw listings."""
    with gzip.open(DATA / "raw" / "images.csv.gz", "rt", encoding="utf-8") as fh:
        paths = {row["image_id"]: row["path"] for row in csv.DictReader(fh)}
    ids = set(catalog.products())
    out = {}
    for f in sorted((DATA / "raw" / "listings").glob("*.json.gz")):
        with gzip.open(f, "rt", encoding="utf-8") as fh:
            for line in fh:
                d = json.loads(line)
                if d["item_id"] in ids and d.get("other_image_id"):
                    path = paths.get(d["other_image_id"][0])
                    if path:
                        out[d["item_id"]] = path
    return out


async def download(urls: dict[Path, str]) -> None:
    sem = asyncio.Semaphore(8)
    async with httpx.AsyncClient(timeout=30) as client:

        async def one(dest: Path, url: str) -> None:
            if dest.exists():
                return
            async with sem:
                r = await client.get(url)
                r.raise_for_status()
            dest.write_bytes(r.content)

        await asyncio.gather(*(one(d, u) for d, u in urls.items()))


def main() -> None:
    (IMAGES / "main").mkdir(parents=True, exist_ok=True)
    (IMAGES / "alt").mkdir(parents=True, exist_ok=True)
    urls = {IMAGES / "main" / f"{p['id']}.jpg": p["image_url"] for p in catalog.products().values()}
    alts = alt_image_paths()
    urls |= {IMAGES / "alt" / f"{pid}.jpg": BASE_URL + path for pid, path in alts.items()}
    asyncio.run(download(urls))
    (IMAGES / "alt_index.json").write_text(json.dumps(sorted(alts)), encoding="utf-8")
    print(f"{len(list((IMAGES / 'main').glob('*.jpg')))} main, {len(list((IMAGES / 'alt').glob('*.jpg')))} alt images")


if __name__ == "__main__":
    main()
