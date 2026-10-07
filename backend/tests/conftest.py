from collections.abc import Callable

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from app.rag.index import PRODUCTS, client


@pytest.fixture(scope="session", autouse=True)
def require_index():
    if not client().collection_exists(PRODUCTS):
        pytest.exit("Qdrant index missing: run `python scripts/build_index.py` first", returncode=1)


class ScriptedModel(BaseChatModel):
    """Stands in for an LLM: returns the next scripted message on every call."""

    script: list[Callable[[int], AIMessage]]
    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "scripted"

    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        make = self.script[min(self.calls, len(self.script) - 1)]
        self.calls += 1
        return ChatResult(generations=[ChatGeneration(message=make(self.calls))])


def tool_call(name: str, args: dict) -> Callable[[int], AIMessage]:
    return lambda n: AIMessage(content="", tool_calls=[{"name": name, "args": args, "id": f"call_{n}"}])


def answer(text: str) -> Callable[[int], AIMessage]:
    return lambda n: AIMessage(
        content=text, usage_metadata={"input_tokens": 100, "output_tokens": 20, "total_tokens": 120}
    )
