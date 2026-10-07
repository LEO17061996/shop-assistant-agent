from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_DIR / ".env", extra="ignore")

    data_dir: Path = BACKEND_DIR / "data"
    qdrant_path: Path = BACKEND_DIR / ".qdrant"
    qdrant_url: str | None = None  # set to use a Qdrant server instead of local mode

    dense_model: str = "BAAI/bge-small-en-v1.5"
    sparse_model: str = "Qdrant/bm25"
    embed_cache_dir: Path = BACKEND_DIR / ".cache" / "fastembed"

    # "gemini" or "claude"
    llm_provider: str = "gemini"
    gemini_api_key: str | None = None
    # Flash-Lite: the free tier allows enough requests per day for a public demo (3.5 Flash allows 20)
    gemini_model: str = "gemini-3.1-flash-lite"
    # Used when the main model fails (overload, timeout, quota). None disables the fallback.
    # Gemini 2.5 models are closed to API projects created after mid-2026, so the fallback is 3.5.
    gemini_fallback_model: str | None = "gemini-3.5-flash-lite"
    anthropic_api_key: str | None = None
    # Explicit so a shell-level ANTHROPIC_BASE_URL (proxies, tooling) is never picked up by accident
    anthropic_base_url: str = "https://api.anthropic.com"
    claude_model: str = "claude-haiku-4-5-20251001"
    # None = provider default (Google recommends the default for Gemini 3 models)
    temperature: float | None = None
    # Client-side cap per model, below the free tier's 15 requests/minute. None = no cap.
    llm_requests_per_minute: float | None = 12
    gbp_per_usd: float = 0.75  # demo rate for the UK VAT threshold note

    max_agent_steps: int = 6
    history_token_budget: int = 6000
    max_user_message_chars: int = 2000

    cors_origins: list[str] = ["http://localhost:3000", "http://localhost:3210"]
    rate_limit_per_minute: int = 10


@lru_cache
def get_settings() -> Settings:
    return Settings()
