"""Per-IP request limit shared by the chat and studio endpoints."""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import get_settings

_hits: dict[str, deque] = defaultdict(deque)


def client_ip(request: Request) -> str:
    # Behind a hosting proxy every request comes from the proxy; the real client is first in X-Forwarded-For
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def check_rate_limit(request: Request) -> None:
    now = time.monotonic()
    q = _hits[client_ip(request)]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= get_settings().rate_limit_per_minute:
        raise HTTPException(429, "Too many requests. Please wait a minute.")
    q.append(now)
