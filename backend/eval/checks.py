"""Deterministic checks on one agent turn. No LLM involved, so results are cheap and repeatable.

A case only runs the checks its `expect` block asks for, plus `grounded_money`, which
runs on every case: any price in the answer must exist in the tool outputs or the conversation.
"""

import json
import re
from dataclasses import dataclass, field

MONEY = re.compile(
    r"(?P<sym>[$£€])\s?(?P<a>\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)"
    r"|(?P<b>\d{1,3}(?:,\d{3})+(?:\.\d{1,2})?|\d+(?:\.\d{1,2})?)\s?(?P<code>USD|GBP|EUR|dollars?|pounds?)\b"
)
CURRENCY = {
    "$": "USD",
    "£": "GBP",
    "€": "EUR",
    "USD": "USD",
    "GBP": "GBP",
    "EUR": "EUR",
    "dollar": "USD",
    "pound": "GBP",
}


@dataclass
class Trace:
    """Everything the checks need from one turn."""

    message: str
    history_text: str
    answer: str
    tool_calls: list[dict] = field(default_factory=list)  # {"name", "args"}
    tool_outputs: list[str] = field(default_factory=list)
    policy_ids: list[str] = field(default_factory=list)
    handoff: bool = False


def money_in(text: str) -> set[tuple[str, float]]:
    found = set()
    for m in MONEY.finditer(text):
        cur = CURRENCY[m.group("sym") or m.group("code").removesuffix("s")]
        num = float((m.group("a") or m.group("b")).replace(",", ""))
        found.add((cur, round(num, 2)))
    return found


def evidence_money(t: Trace) -> set[tuple[str, float]]:
    ev = money_in(t.message) | money_in(t.history_text)
    for out in t.tool_outputs:
        ev |= money_in(out)
        try:
            data = json.loads(out)
        except ValueError:
            continue
        ev |= {("USD", v) for v in _usd_fields(data)}
    return ev


def _usd_fields(obj) -> list[float]:
    vals = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k.endswith("_usd") and isinstance(v, int | float):
                vals.append(round(float(v), 2))
            else:
                vals += _usd_fields(v)
    elif isinstance(obj, list):
        for v in obj:
            vals += _usd_fields(v)
    return vals


def _arg_ok(actual, expected) -> bool:
    if isinstance(expected, list):  # [low, high] inclusive range
        return isinstance(actual, int | float) and expected[0] <= actual <= expected[1]
    if isinstance(expected, str):
        return isinstance(actual, str) and actual.lower() == expected.lower()
    return actual == expected


def _called(t: Trace, spec: str) -> bool:
    # "a|b" means either tool is fine
    names = {c["name"] for c in t.tool_calls}
    return any(alt in names for alt in spec.split("|"))


def run_checks(t: Trace, expect: dict) -> dict[str, dict]:
    answer = t.answer.lower()
    results: dict[str, dict] = {}

    def record(name: str, ok: bool, detail: str = "") -> None:
        results[name] = {"pass": ok, "detail": detail}

    if "tools" in expect:
        missing = [s for s in expect["tools"] if not _called(t, s)]
        record("tools_called", not missing, f"missing {missing}" if missing else "")
    if "forbidden" in expect:
        bad = [s for s in expect["forbidden"] if _called(t, s)]
        record("tools_not_called", not bad, f"called {bad}" if bad else "")
    if "filters" in expect:
        searches = [c["args"] for c in t.tool_calls if c["name"] == "search_products"]
        ok = any(all(_arg_ok(a.get(k), v) for k, v in expect["filters"].items()) for a in searches)
        record("search_filters", ok, "" if ok else f"got {searches}")
    if "policy_ids" in expect:
        ok = any(pid in t.policy_ids for pid in expect["policy_ids"])
        record("policy_retrieval", ok, "" if ok else f"retrieved {t.policy_ids}")
    if "include" in expect:
        missing = [s for s in expect["include"] if s.lower() not in answer]
        record("answer_includes", not missing, f"missing {missing}" if missing else "")
    if "include_any" in expect:
        ok = any(s.lower() in answer for s in expect["include_any"])
        record("answer_includes_any", ok, "" if ok else "none of the expected phrases")
    if "exclude" in expect:
        found = [s for s in expect["exclude"] if s.lower() in answer]
        record("answer_excludes", not found, f"found {found}" if found else "")
    if "asks_question" in expect:
        record("asks_question", ("?" in t.answer) == expect["asks_question"])
    if "handoff" in expect:
        record("handoff", t.handoff == expect["handoff"], f"handoff={t.handoff}")

    invented = sorted(money_in(t.answer) - evidence_money(t))
    record("grounded_money", not invented, f"not in evidence: {invented}" if invented else "")
    # Added after the judge caught a model copying the internal "[shown: ids]" history note into an answer
    leaked = "[shown:" in t.answer
    record("no_internal_notes", not leaked, "answer contains a [shown: ...] note" if leaked else "")
    return results
