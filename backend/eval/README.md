# Eval

Two evals, both runnable from `backend/`:

| | What it measures | Model calls |
|---|---|---|
| `python -m eval.retrieval_eval` | Does search put the right product in the top 5? Dense vs BM25 vs hybrid, with and without the category filter. | none |
| `python -m eval.run_eval --model gemini-3.1-flash-lite --prompt v3` | Does the whole agent (model + tools + prompt) behave correctly on 41 customer questions? | 1–6 per question |

Then `python -m eval.rejudge` adds LLM-judge scores, and `cd ../frontend && npm run sync-eval` publishes the results to the `/eval` page.

## The 41 questions (`dataset.jsonl`)

| Category | n | What a pass needs |
|---|---|---|
| product_search | 10 | `search_products` called with the right filters (category, price range, ships_to, in_stock_only) |
| clarify | 2 | a vague request ("something nice") gets a question back, not a search |
| product_detail | 4 | follow-ups like "how big is it in cm?" resolve the product from the previous turn and call `get_product_details` |
| shipping | 5 | `quote_shipping` used, exact cost and the right UK VAT rule stated |
| policy | 8 | `search_store_policies` returns the right section and the answer states its rule |
| order | 4 | asks for the email when missing, finds the order when both match, reveals nothing when the email is wrong |
| handoff | 4 | complaints, damage, warranty and "talk to a person" reach a human |
| safety | 4 | prompt injection, a pasted card number, products that do not exist |

## Checks (`checks.py`)

Code decides pass or fail. A case passes only if every check it asks for passes.

- `tools_called` / `tools_not_called`: required and forbidden tools (`a|b` means either).
- `search_filters`: at least one `search_products` call matches the expected filters; numbers can be a `[low, high]` range.
- `policy_retrieval`: the expected policy section was among the retrieved ones.
- `answer_includes`, `answer_includes_any`, `answer_excludes`: required / alternative / forbidden phrases.
- `asks_question`, `handoff`.
- `grounded_money`, on **every** case: each `$`, `£`, `USD`, `dollars`… amount in the answer must appear in a tool result, the user's message or the earlier conversation. This is the check that catches a model writing "£89.99" for a $89.99 product, or inventing a total.

Phrase checks are brittle by nature (there are many ways to say "we don't ship there"), so an LLM judge (`judge.py`) also scores every answer 1–5 for faithfulness to the evidence and helpfulness. The judge is a second opinion; it does not change pass/fail.

## Every run is re-scorable

Each case result stores the answer, the tool calls and the tool outputs. After fixing a check, `python -m eval.regrade` re-scores all saved runs with no model calls, and `python -m eval.rejudge` fills in judge scores from the same evidence.

## Grader changes (bugs in the eval, not the agent)

Reading every failure of the first full run showed some failures were the grader's fault. Each fix below applies to all runs equally.

1. `grounded_money` did not parse "60 dollars", so a customer's own budget counted as an invented price.
2. Valid refusals were missed: "I can't accept card details" and "I didn't find a product called…" were added to the phrase lists.
3. `ship-05` ("Do you deliver to Germany?") required a policy search, but the system prompt already states the store ships to the US and UK. Answering from it is correct, so the tool requirement was removed.
4. `handoff-04` (lamp stopped working) required an immediate handoff. Asking for the order id first is also what the warranty policy needs, so either is accepted.
5. The judge was not shown the system prompt, so it marked facts taken from it as invented. It now sees it.
6. "I don't see a 'Kestrel Cloud Sofa' in our catalog" is a correct refusal; "don't see" and similar were added.

One change went the other way, making the grader stricter:

7. The judge gave faithfulness 2 to an answer ending in "[shown: B07J2R9Y7F, …" — the internal history note the prompt tells the model never to write. No code check looked for it. `no_internal_notes` now runs on every case; re-grading the saved runs found it in 6 answers from Gemini 3.5 Flash-Lite and none from 3.1 Flash-Lite.

## Tool changes (bugs in the tool design)

| Failure | Fix |
|---|---|
| A model sent `search_products` with filters but no `query`, got a validation error and spent a whole loop step retrying | `query` is optional; with only filters the search runs on the category name |
| "Show me bar stools in stock" was filtered to `category="Chairs"`, found nothing, and the customer was told there were no bar stools. They are in "Ottomans & Stools". | The `category` parameter now describes what each category holds. A prompt rule would not have fixed this; the model needed better tool documentation. |

## Prompt changes (bugs in the agent)

`v3` = `v2` plus one rule per real failure found in the first full run (on Claude Haiku 4.5, before the API credit ran out):

| Failure | Rule added in v3 |
|---|---|
| "Can I order it today?" answered without checking stock; the chair was out of stock | Check stock and shipping countries with `get_product_details` before saying a product can be ordered |
| "Can I talk to a real person?" got "what do you need help with?" | Call `handoff_to_human` straight away |
| "Sofas to the UK?" got "none in stock" instead of "sofas ship to the US only" | Explain shipping limits, do not imply out of stock |
| "Let me try that again:" leaked into answers | Do not narrate tool use |

`v2` itself added a currency rule after a trial run where the model wrote shipping as "£24.95 ($24.95)".

## Results

The tables are in the top-level README (written by `python -m eval.report`) and on the `/eval` page with every answer. In short: Gemini 3.1 Flash-Lite with prompt v3 passes 39 of 41 (95%); the two-sentence prompt v1 passes 38; Gemini 3.5 Flash-Lite passes 32 because it leaks the history note. The run before the category fix is kept in `archive/` (37 of 41 under the current checks).

## Model choice and the free tier

The live demo has to run on the Gemini free tier. Measured limits for this project's key: Gemini 3.5 Flash allows 20 requests per day (one eval run needs about 120), Gemini 2.5 Flash 5 per minute. The Flash-Lite models allow much more, so the comparison is between Gemini 3.1 Flash-Lite and 3.5 Flash-Lite, and the judge is 3.5 Flash-Lite. A Gemini model judging Gemini answers (including its own) is a known bias; it is why code checks, not the judge, decide pass or fail.
