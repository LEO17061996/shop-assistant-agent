"""LLM-as-judge for what string checks cannot see: is every claim backed by evidence, and does it help.

One fixed judge model grades every run so scores are comparable across the configurations under test.
Known bias: the judge is a Gemini model grading Gemini answers (including its own), and models tend to
rate their own family a little higher. The code checks are the primary metric; judge scores are a
second opinion.
"""

from langchain_google_genai import ChatGoogleGenerativeAI
from pydantic import BaseModel, Field

from app.agent.llm import rate_limiter
from app.config import get_settings

JUDGE_MODEL = "gemini-3.5-flash-lite"
MAX_EVIDENCE_CHARS = 8000

PROMPT = """You grade a customer-support assistant for an online furniture store.

<conversation>
{conversation}
</conversation>

<assistant_instructions>
The assistant's system prompt. Store facts stated here are valid evidence.
{instructions}
</assistant_instructions>

<evidence>
Tool results the assistant retrieved. Together with the instructions above, the ONLY valid source of store facts.
{evidence}
</evidence>

<answer>
{answer}
</answer>

Score from 1 to 5:
- faithfulness: 5 = every store fact in the answer (price, stock, size, shipping, policy, order status) is supported by the evidence, the instructions or the conversation. 1 = it invents important facts. Friendly wording and general advice are fine.
- helpfulness: 5 = resolves what the customer asked, or correctly asks for missing information or hands off to a person. 1 = ignores the request.
Be strict about invented numbers, currencies and policies."""


class Verdict(BaseModel):
    faithfulness: int = Field(ge=1, le=5)
    helpfulness: int = Field(ge=1, le=5)
    reason: str = Field(description="One or two sentences.")


def make_judge():
    s = get_settings()
    llm = ChatGoogleGenerativeAI(
        model=JUDGE_MODEL,
        api_key=s.gemini_api_key,
        temperature=0,
        timeout=60,
        max_retries=3,
        rate_limiter=rate_limiter(JUDGE_MODEL),
    )
    return llm.with_structured_output(Verdict)


async def judge(judge_llm, instructions: str, conversation: str, evidence: list[str], answer: str) -> dict:
    ev = "\n---\n".join(evidence)[:MAX_EVIDENCE_CHARS] or "(no tools were called)"
    prompt = PROMPT.format(instructions=instructions, conversation=conversation, evidence=ev, answer=answer)
    verdict: Verdict = await judge_llm.ainvoke(prompt)
    return verdict.model_dump()
