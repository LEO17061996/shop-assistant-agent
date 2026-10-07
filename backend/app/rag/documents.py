"""Turn products and policy files into the text that gets embedded.

Products: one document per product (they are short, chunking would only split
facts that belong together). Policies: one chunk per "##" section, prefixed
with the document title so a chunk still makes sense on its own.
"""

import re
from pathlib import Path


def product_text(p: dict) -> str:
    attrs = [
        ("Category", p.get("category")),
        ("Brand", p.get("brand")),
        ("Material", p.get("material")),
        ("Fabric", p.get("fabric")),
        ("Color", p.get("color")),
        ("Style", p.get("style")),
        ("Finish", p.get("finish")),
        ("Pattern", p.get("pattern")),
        ("Shape", p.get("shape")),
    ]
    lines = [p["name"], ". ".join(f"{k}: {v}" for k, v in attrs if v) + "."]
    dims = p.get("dimensions_in")
    if dims:
        lines.append("Size (inches): " + " x ".join(f"{k} {v}" for k, v in dims.items()))
    lines.extend(p.get("bullets", []))
    if p.get("keywords"):
        lines.append("Keywords: " + ", ".join(p["keywords"]))
    return "\n".join(lines)


def policy_chunks(policies_dir: Path) -> list[dict]:
    chunks = []
    for path in sorted(policies_dir.glob("*.md")):
        title, section, body = path.stem, None, []
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
            elif line.startswith("## "):
                if section and body:
                    chunks.append(_chunk(path.stem, title, section, body))
                section, body = line[3:].strip(), []
            elif line.strip():
                body.append(line.strip())
        if section and body:
            chunks.append(_chunk(path.stem, title, section, body))
    return chunks


def _chunk(doc: str, title: str, section: str, body: list[str]) -> dict:
    return {
        "id": f"{doc}#{re.sub(r'[^a-z0-9]+', '-', section.lower()).strip('-')}",
        "doc": doc,
        "section": section,
        "text": f"{title} > {section}\n" + "\n".join(body),
    }
