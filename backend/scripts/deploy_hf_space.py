"""Create or update the Hugging Face Docker Space that hosts the API.

Needs a Hugging Face write token: run `huggingface-cli login` once (or set HF_TOKEN).
The Gemini key is read from backend/.env and stored as a Space secret, never committed.

Usage:
    python scripts/deploy_hf_space.py --space <hf-username>/kestrel-home-api \
        --origin https://kestrel-home.vercel.app
"""

import argparse
import json
import sys
from pathlib import Path

from huggingface_hub import HfApi

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import BACKEND_DIR, get_settings  # noqa: E402

SPACE_README = """---
title: Kestrel Home API
emoji: 🪑
colorFrom: yellow
colorTo: red
sdk: docker
app_port: 7860
pinned: false
---

API for the Kestrel Home shopping assistant (FastAPI + LangGraph + Qdrant).
Source and docs: https://github.com/LEO17061996/shop-assistant-agent
"""

FILES = [
    "Dockerfile",
    ".dockerignore",
    "requirements.txt",
    "app/**",
    "scripts/build_index.py",
    "data/catalog.jsonl",
    "data/orders.json",
    "data/policies/**",
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--space", required=True, help="<username>/<space-name>")
    ap.add_argument("--origin", action="append", default=[], help="frontend origin allowed by CORS (repeatable)")
    args = ap.parse_args()

    s = get_settings()
    if not s.gemini_api_key:
        sys.exit("GEMINI_API_KEY missing in backend/.env")

    api = HfApi()
    api.create_repo(args.space, repo_type="space", space_sdk="docker", exist_ok=True)
    api.add_space_secret(args.space, "GEMINI_API_KEY", s.gemini_api_key)
    origins = args.origin or ["http://localhost:3210"]
    api.add_space_variable(args.space, "CORS_ORIGINS", json.dumps(origins))
    api.upload_file(
        path_or_fileobj=SPACE_README.encode(), path_in_repo="README.md", repo_id=args.space, repo_type="space"
    )
    api.upload_folder(
        folder_path=BACKEND_DIR,
        repo_id=args.space,
        repo_type="space",
        allow_patterns=FILES,
        ignore_patterns=["**/__pycache__/**"],
        commit_message="Deploy API",
    )
    user, name = args.space.split("/")
    print(f"Space: https://huggingface.co/spaces/{args.space}")
    print(f"API:   https://{user}-{name}.hf.space/api/health  (first build takes a few minutes)")


if __name__ == "__main__":
    main()
