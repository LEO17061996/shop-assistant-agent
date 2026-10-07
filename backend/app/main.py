"""HTTP API. /api/chat streams the agent's work as Server-Sent Events:

step      a tool call or tool result (name, args, latency) for the trace panel
products  product cards to render under the answer
handoff   ticket created by handoff_to_human
token     a piece of the answer text
done      usage, cost, latency, steps
error     something failed; the message is safe to show
"""

import json
import time
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from langchain_core.messages import AIMessage, ToolMessage
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from app import catalog
from app.agent.graph import get_graph, to_messages
from app.agent.llm import cost_usd, model_name
from app.config import get_settings
from app.rag.index import embed_query

settings = get_settings()


@asynccontextmanager
async def lifespan(_: FastAPI):
    # Load embedding models and catalog before the first request instead of during it
    embed_query("warm up")
    catalog.products()
    yield


app = FastAPI(title="Kestrel Home shopping assistant", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


class ChatMessage(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1)
    product_ids: list[str] = Field(default_factory=list, max_length=10)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(min_length=1, max_length=20)
    prompt_version: Literal["v1", "v2", "v3"] = "v3"


_hits: dict[str, deque] = defaultdict(deque)


def check_rate_limit(ip: str) -> None:
    now = time.monotonic()
    q = _hits[ip]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= settings.rate_limit_per_minute:
        raise HTTPException(429, "Too many messages. Please wait a minute.")
    q.append(now)


def client_ip(request: Request) -> str:
    # Behind a hosting proxy every request comes from the proxy; the real client is first in X-Forwarded-For
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def sse(event: str, data: dict) -> dict:
    return {"event": event, "data": json.dumps(data, ensure_ascii=False)}


@app.get("/api/health")
def health():
    return {"status": "ok", "provider": settings.llm_provider, "model": model_name(settings.llm_provider)}


@app.get("/api/products/{product_id}")
def product(product_id: str):
    p = catalog.products().get(product_id)
    if not p:
        raise HTTPException(404, "Product not found")
    return p


@app.post("/api/chat")
async def chat(req: ChatRequest, request: Request):
    check_rate_limit(client_ip(request))
    if req.messages[-1].role != "user":
        raise HTTPException(422, "The last message must come from the user.")
    if len(req.messages[-1].content) > settings.max_user_message_chars:
        raise HTTPException(422, f"Message is longer than {settings.max_user_message_chars} characters.")

    provider = settings.llm_provider
    model = model_name(provider)
    graph = get_graph(provider, req.prompt_version)
    state = {"messages": to_messages([m.model_dump() for m in req.messages]), "steps": 0}

    async def events():
        t0 = time.perf_counter()
        tokens_in = tokens_out = steps = 0
        try:
            async for mode, payload in graph.astream(state, stream_mode=["messages", "updates"]):
                if mode == "messages":
                    chunk, meta = payload
                    # Streaming models send chunks; non-streaming ones send the whole message once
                    if isinstance(chunk, AIMessage) and meta.get("langgraph_node") == "agent" and chunk.text:
                        yield sse("token", {"text": chunk.text})
                    continue
                for node, update in payload.items():
                    for m in (update or {}).get("messages", []):
                        if isinstance(m, AIMessage) and node == "agent":
                            steps += 1
                            usage = m.usage_metadata or {}
                            tokens_in += usage.get("input_tokens", 0)
                            tokens_out += usage.get("output_tokens", 0)
                            for c in m.tool_calls:
                                yield sse(
                                    "step", {"type": "tool_call", "step": steps, "name": c["name"], "args": c["args"]}
                                )
                        elif isinstance(m, AIMessage) and node == "give_up":
                            yield sse("token", {"text": m.text})
                        elif isinstance(m, ToolMessage):
                            art = m.artifact or {}
                            yield sse(
                                "step",
                                {
                                    "type": "tool_result",
                                    "name": m.name,
                                    "status": m.status,
                                    "latency_ms": art.get("latency_ms"),
                                },
                            )
                            if art.get("products"):
                                yield sse("products", {"products": art["products"]})
                            if art.get("handoff"):
                                yield sse("handoff", art["handoff"])
        except Exception as e:  # provider outages, quota errors
            msg = (
                "The assistant is busy right now. Please try again in a minute."
                if "429" in str(e)
                else "Something went wrong. Please try again."
            )
            yield sse("error", {"message": msg})
            return
        yield sse(
            "done",
            {
                "model": model,
                "steps": steps,
                "input_tokens": tokens_in,
                "output_tokens": tokens_out,
                "cost_usd": cost_usd(model, tokens_in, tokens_out),
                "latency_ms": round((time.perf_counter() - t0) * 1000),
            },
        )

    return EventSourceResponse(events())
