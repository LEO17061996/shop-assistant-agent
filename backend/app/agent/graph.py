"""The agent loop, written as an explicit LangGraph state machine.

    START -> agent --(no tool calls)------------------> END
               |  --(tool calls, steps < max)--> tools --> agent
               |  --(tool calls, steps = max)--> give_up -> END

Why explicit instead of a prebuilt ReAct agent: every exit of the loop is
visible here. The step cap stops a model that keeps calling tools, tool errors
go back to the model as messages so it can correct itself, and the history is
trimmed to a token budget before each model call.
"""

import asyncio
import re
import time
from functools import lru_cache
from typing import Annotated, TypedDict

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage, AnyMessage, HumanMessage, SystemMessage, ToolMessage, trim_messages
from langchain_core.messages.utils import count_tokens_approximately
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from app.agent.llm import make_llm
from app.agent.prompts import PROMPTS
from app.agent.tools import TOOLS, TOOLS_BY_NAME
from app.config import get_settings

TOOL_TIMEOUT_S = 20
GIVE_UP_TEXT = (
    "Sorry, I couldn't finish that request. You can rephrase it, or I can pass you to our support team "
    "(Mon-Fri 9am-6pm US Eastern, support@kestrelhome.example)."
)


SHOWN_NOTE = re.compile(r"\n?\[shown:[^\]]*\]?")


class AgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    steps: int


def to_messages(history: list[dict]) -> list[AnyMessage]:
    """Client-side history -> LangChain messages.

    Assistant turns carry the ids of the products they showed, so a follow-up like
    "how big is it?" can be resolved without keeping session state on the server.
    """
    out: list[AnyMessage] = []
    for m in history:
        if m["role"] == "user":
            out.append(HumanMessage(m["content"]))
        else:
            ids = m.get("product_ids") or []
            note = f"\n[shown: {', '.join(ids)}]" if ids else ""
            # A model occasionally copies the note into its own reply; drop that copy so notes never stack up
            out.append(AIMessage(SHOWN_NOTE.sub("", m["content"]) + note))
    return out


def fit_history(messages: list[AnyMessage], budget: int) -> list[AnyMessage]:
    """Keep the current turn whole, then as many earlier turns as the token budget allows.

    Earlier turns are cut at a human message, so a tool result is never kept without
    the model message that asked for it.
    """
    last_human = max((i for i, m in enumerate(messages) if isinstance(m, HumanMessage)), default=0)
    current, earlier = messages[last_human:], messages[:last_human]
    room = budget - count_tokens_approximately(current)
    if room <= 0 or not earlier:
        return current
    kept = trim_messages(
        earlier,
        max_tokens=room,
        token_counter=count_tokens_approximately,
        strategy="last",
        start_on="human",
        allow_partial=False,
    )
    return [*kept, *current]


async def run_tool(call: dict) -> ToolMessage:
    t0 = time.perf_counter()
    tool = TOOLS_BY_NAME.get(call["name"])
    try:
        if tool is None:
            raise ValueError(f"Unknown tool '{call['name']}'. Available: {', '.join(TOOLS_BY_NAME)}")
        msg = await asyncio.wait_for(tool.ainvoke({**call, "type": "tool_call"}), TOOL_TIMEOUT_S)
        content, artifact, status = msg.content, dict(msg.artifact or {}), "success"
    except TimeoutError:
        content, artifact, status = f"Tool timed out after {TOOL_TIMEOUT_S}s.", {}, "error"
    except Exception as e:  # bad arguments from the model land here; the model gets the message and can retry
        content, artifact, status = f"Tool error: {e}", {}, "error"
    artifact["latency_ms"] = round((time.perf_counter() - t0) * 1000)
    return ToolMessage(content=content, artifact=artifact, status=status, tool_call_id=call["id"], name=call["name"])


def build_graph(llm: BaseChatModel, system_prompt: str, max_steps: int, history_budget: int):
    model = llm.bind_tools(TOOLS)

    async def agent(state: AgentState):
        history = fit_history(state["messages"], history_budget)
        response = await model.ainvoke([SystemMessage(system_prompt), *history])
        return {"messages": [response], "steps": state.get("steps", 0) + 1}

    async def tools(state: AgentState):
        calls = state["messages"][-1].tool_calls
        return {"messages": list(await asyncio.gather(*(run_tool(c) for c in calls)))}

    async def give_up(state: AgentState):
        # Answer the pending calls so the history stays valid, then stop without another model call
        skipped = [
            ToolMessage(content="Not run: step limit reached.", status="error", tool_call_id=c["id"], name=c["name"])
            for c in state["messages"][-1].tool_calls
        ]
        return {"messages": [*skipped, AIMessage(content=GIVE_UP_TEXT)]}

    def route(state: AgentState) -> str:
        last = state["messages"][-1]
        if not getattr(last, "tool_calls", None):
            return END
        return "tools" if state["steps"] < max_steps else "give_up"

    g = StateGraph(AgentState)
    g.add_node("agent", agent)
    g.add_node("tools", tools)
    g.add_node("give_up", give_up)
    g.add_edge(START, "agent")
    g.add_conditional_edges("agent", route, ["tools", "give_up", END])
    g.add_edge("tools", "agent")
    g.add_edge("give_up", END)
    return g.compile()


@lru_cache
def get_graph(provider: str | None = None, prompt_version: str = "v3", model: str | None = None):
    s = get_settings()
    return build_graph(
        make_llm(provider, model),
        PROMPTS[prompt_version],
        max_steps=s.max_agent_steps,
        history_budget=s.history_token_budget,
    )
