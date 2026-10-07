import asyncio

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from app.agent.graph import GIVE_UP_TEXT, build_graph, fit_history
from tests.conftest import FailingModel, ScriptedModel, answer, tool_call


def run(model, text="hi", max_steps=6):
    graph = build_graph(model, "system", max_steps=max_steps, history_budget=6000)
    return asyncio.run(graph.ainvoke({"messages": [HumanMessage(text)], "steps": 0}))["messages"]


def test_answer_without_tools_ends_loop():
    msgs = run(ScriptedModel(script=[answer("Hello!")]))
    assert [type(m) for m in msgs] == [HumanMessage, AIMessage]
    assert msgs[-1].content == "Hello!"


def test_tool_result_goes_back_to_model():
    model = ScriptedModel(
        script=[tool_call("search_store_policies", {"question": "return window"}), answer("30 days.")]
    )
    msgs = run(model)
    tool_msg = next(m for m in msgs if isinstance(m, ToolMessage))
    assert tool_msg.status == "success" and "returns#return-window" in tool_msg.content
    assert msgs[-1].content == "30 days."
    assert model.calls == 2


def test_bad_arguments_become_an_error_the_model_can_fix():
    model = ScriptedModel(
        script=[
            tool_call("quote_shipping", {"product_ids": ["X"], "country": "France"}),  # not an allowed value
            answer("Sorry, we only ship to the US and UK."),
        ]
    )
    msgs = run(model)
    tool_msg = next(m for m in msgs if isinstance(m, ToolMessage))
    assert tool_msg.status == "error" and "Tool error" in tool_msg.content
    assert msgs[-1].content.startswith("Sorry")


def test_unknown_tool_is_reported_not_raised():
    msgs = run(ScriptedModel(script=[tool_call("delete_database", {}), answer("ok")]))
    tool_msg = next(m for m in msgs if isinstance(m, ToolMessage))
    assert tool_msg.status == "error" and "Unknown tool" in tool_msg.content


def test_step_limit_stops_a_model_that_never_answers():
    model = ScriptedModel(script=[tool_call("search_store_policies", {"question": "x"})])
    msgs = run(model, max_steps=3)
    assert model.calls == 3
    assert msgs[-1].content == GIVE_UP_TEXT
    # Every tool call still has a matching result, so the history stays valid
    call_ids = {c["id"] for m in msgs if isinstance(m, AIMessage) for c in m.tool_calls}
    result_ids = {m.tool_call_id for m in msgs if isinstance(m, ToolMessage)}
    assert call_ids == result_ids


def test_fit_history_keeps_current_turn_and_drops_oldest():
    old = []
    for i in range(30):
        old += [HumanMessage(f"question {i} " + "word " * 100), AIMessage(f"answer {i} " + "word " * 100)]
    current = [
        HumanMessage("latest question"),
        AIMessage("", tool_calls=[{"name": "t", "args": {}, "id": "c1"}]),
        ToolMessage("result", tool_call_id="c1"),
    ]
    kept = fit_history(old + current, budget=1500)
    assert kept[-3:] == current
    assert len(kept) < len(old) + 3
    assert isinstance(kept[0], HumanMessage)


def test_fallback_model_answers_when_the_main_one_is_down():
    primary, backup = FailingModel(), ScriptedModel(script=[answer("Answered by the fallback.")])
    graph = build_graph(primary, "system", max_steps=6, history_budget=6000, fallback=backup)
    msgs = asyncio.run(graph.ainvoke({"messages": [HumanMessage("hi")], "steps": 0}))["messages"]
    assert msgs[-1].content == "Answered by the fallback." and primary.calls >= 1
