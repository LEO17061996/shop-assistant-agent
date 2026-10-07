"""Chat model factory + price table for cost reporting."""

from functools import lru_cache

from langchain_anthropic import ChatAnthropic
from langchain_core.language_models import BaseChatModel
from langchain_core.rate_limiters import InMemoryRateLimiter
from langchain_google_genai import ChatGoogleGenerativeAI

from app.config import get_settings

# USD per 1M tokens (input, output), paid tier list prices. Free-tier calls cost $0,
# but reporting the paid price shows what the same traffic would cost in production.
PRICES = {
    "gemini-3.1-flash-lite": (0.25, 1.50),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-2.5-flash-lite": (0.10, 0.40),
    "gemini-2.5-flash": (0.30, 2.50),
    "gemini-3.5-flash": (1.50, 9.00),
    "claude-haiku-4-5-20251001": (1.00, 5.00),
}


def model_name(provider: str) -> str:
    s = get_settings()
    return s.claude_model if provider == "claude" else s.gemini_model


@lru_cache
def rate_limiter(model: str) -> InMemoryRateLimiter | None:
    """One token bucket per model per process. Free-tier quotas are per model per minute, so
    callers wait their turn here instead of failing with 429.

    The bucket holds 4 tokens so one customer's turn (usually 2-3 model calls) runs without
    waiting, while sustained traffic still averages out at the per-minute cap."""
    rpm = get_settings().llm_requests_per_minute
    return InMemoryRateLimiter(requests_per_second=rpm / 60, max_bucket_size=4) if rpm else None


def make_llm(provider: str | None = None, model: str | None = None) -> BaseChatModel:
    s = get_settings()
    provider = provider or s.llm_provider
    model = model or model_name(provider)
    extra = {"temperature": s.temperature} if s.temperature is not None else {}
    if provider == "claude":
        return ChatAnthropic(
            model=model,
            api_key=s.anthropic_api_key,
            base_url=s.anthropic_base_url,
            max_tokens=1024,
            timeout=60,
            max_retries=2,
            **extra,
        )
    return ChatGoogleGenerativeAI(
        model=model,
        api_key=s.gemini_api_key,
        timeout=60,
        max_retries=2,
        rate_limiter=rate_limiter(model),
        **extra,
    )


def cost_usd(model: str, input_tokens: int, output_tokens: int) -> float | None:
    price = PRICES.get(model)
    if not price:
        return None
    return round((input_tokens * price[0] + output_tokens * price[1]) / 1_000_000, 6)
