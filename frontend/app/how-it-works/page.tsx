import type { Metadata } from "next";
import retrieval from "@/data/retrieval-eval.json";

export const metadata: Metadata = { title: "How it works — Kestrel Home assistant" };

type RetrievalRow = { "hit@1": number; "hit@5": number; mrr: number; ms_per_query: number };
const ret = retrieval as { n_queries: number; k: number; results: Record<string, RetrievalRow> };

const TOOLS = [
  ["search_products", "Hybrid search over 453 products with price, category, country and stock filters.", "Filters run inside Qdrant, so a $900 sofa never reaches the model when the budget is $500."],
  ["get_product_details", "Size in inches and cm, weight, materials, stock, shipping countries.", "Unit conversion in code, not in the model's head."],
  ["search_store_policies", "Top 3 policy sections (shipping, VAT, returns, warranty, care, payments).", "The answer cites the section it came from."],
  ["quote_shipping", "Exact shipping cost, delivery time and UK VAT note for a basket.", "Pricing rules are business logic. The model never adds numbers up."],
  ["lookup_order", "Order status, only when order id and email both match.", "Same reply for wrong email and unknown order, so ids can't be probed."],
  ["handoff_to_human", "Creates a ticket for complaints, damage, warranty, trade orders.", "Some decisions should not be automated."],
];

function Box({ title, children, tone = "card" }: { title: string; children: React.ReactNode; tone?: "card" | "clay" | "olive" }) {
  const toneClass = tone === "clay" ? "border-clay/50 bg-clay-soft" : tone === "olive" ? "border-olive/40 bg-olive-soft" : "border-rule bg-card";
  return (
    <div className={`rounded-[3px] border p-4 ${toneClass}`}>
      <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-2">{title}</p>
      <div className="mt-2 text-[14.5px] leading-relaxed text-ink-2">{children}</div>
    </div>
  );
}

function Arrow({ label }: { label?: string }) {
  return (
    <div className="flex items-center justify-center gap-2 py-2 font-mono text-[11px] text-ink-3">
      <span className="text-clay">↓</span>
      {label}
    </div>
  );
}

export default function HowItWorks() {
  return (
    <main className="mx-auto w-full max-w-[1100px] px-4 py-8 sm:px-6">
      <p className="rise font-mono text-[11px] uppercase tracking-[0.3em] text-ink-3">Under the counter</p>
      <h1 className="rise mt-2 max-w-[22ch] font-display text-[44px] leading-[1.05] tracking-tight sm:text-[56px]">
        A small agent loop, <em className="text-clay">with every exit written down.</em>
      </h1>
      <p className="rise mt-4 max-w-[68ch] text-ink-2">
        FastAPI + LangGraph backend, Qdrant for retrieval, Gemini as the model, Next.js for this page. The model decides
        what to look up; code decides anything that has to be exactly right.
      </p>

      <section className="mt-12 grid gap-10 lg:grid-cols-[1fr_1fr]">
        <div>
          <h2 className="font-display text-2xl">1 · The loop</h2>
          <div className="mt-4">
            <Box title="POST /api/chat">
              Validates input (≤ 2,000 chars, ≤ 20 messages), rate-limits per IP, then streams Server-Sent Events. History
              lives in the browser; assistant turns carry the ids of products they showed, so “how big is it?” still
              resolves without server sessions.
            </Box>
            <Arrow label="history trimmed to a 6,000-token budget" />
            <Box title="agent node" tone="clay">
              System prompt + history → model with 6 tools bound. If the reply has no tool calls, it is the answer and
              the loop ends.
            </Box>
            <Arrow label="tool calls · step < 6" />
            <Box title="tools node">
              Runs the calls in parallel, 20 s timeout each. A bad argument or a crash becomes an error message the
              model reads on the next step, so it can correct itself instead of the request failing.
            </Box>
            <Arrow label="back to agent node" />
            <Box title="give_up node" tone="olive">
              Reached when the model still wants tools at step 6. Answers the pending calls as “not run”, returns a
              fixed apology with support contacts, and makes no further model call.
            </Box>
          </div>
        </div>

        <div>
          <h2 className="font-display text-2xl">2 · Retrieval</h2>
          <div className="mt-4 space-y-3 text-[15px] leading-relaxed text-ink-2">
            <p>
              <strong className="text-ink">Data.</strong> 453 furniture products from Amazon Berkeley Objects (real names,
              materials, sizes, photos), deduplicated across colour variants. Prices, stock and UK eligibility are
              generated deterministically from the product id. Vendor lines like “free returns” are dropped so the five
              policy files are the only source of policy.
            </p>
            <p>
              <strong className="text-ink">Chunking.</strong> One document per product (short, chunking would split facts
              that belong together). Policies split by section heading, each chunk prefixed with “Document &gt; Section”
              so it stands on its own: 30 chunks.
            </p>
            <p>
              <strong className="text-ink">Two vectors per point.</strong> Dense: bge-small-en-v1.5 (384 dimensions,
              runs locally on CPU via ONNX). Sparse: BM25, with IDF computed by Qdrant. Dense catches “cozy reading
              chair”; BM25 catches “jute” and “queen”. Both candidate lists are merged with Reciprocal Rank Fusion.
            </p>
          </div>

          <div className="mt-5 overflow-x-auto rounded-[3px] border border-rule bg-card p-4">
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-ink-3">
              Retrieval eval · {ret.n_queries} shopper queries, no model in the loop
            </p>
            <table className="mt-2 w-full min-w-[420px] text-sm">
              <thead>
                <tr className="border-b border-rule text-left font-mono text-[10px] uppercase tracking-wider text-ink-3">
                  <th className="py-1.5 font-normal">Setup</th>
                  <th className="py-1.5 text-right font-normal">hit@1</th>
                  <th className="py-1.5 text-right font-normal">hit@5</th>
                  <th className="py-1.5 text-right font-normal">MRR</th>
                  <th className="py-1.5 text-right font-normal">ms</th>
                </tr>
              </thead>
              <tbody>
                {Object.entries(ret.results).map(([k, m]) => (
                  <tr key={k} className={`border-b border-rule/60 ${k.startsWith("hybrid") ? "text-ink" : "text-ink-2"}`}>
                    <td className="py-1.5">{k}</td>
                    <td className="py-1.5 text-right font-mono tabular-nums">{Math.round(m["hit@1"] * 100)}%</td>
                    <td className="py-1.5 text-right font-mono tabular-nums">{Math.round(m["hit@5"] * 100)}%</td>
                    <td className="py-1.5 text-right font-mono tabular-nums">{m.mrr.toFixed(2)}</td>
                    <td className="py-1.5 text-right font-mono tabular-nums">{m.ms_per_query}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-2 text-xs text-ink-3">
              Each query was written by an LLM from one product’s description, without brand or name words. Hit@5 = that
              product is in the top 5. Other products can also fit a query, so these are lower bounds.
            </p>
          </div>
        </div>
      </section>

      <section className="mt-14">
        <h2 className="font-display text-2xl">3 · Tools: what the model may not do itself</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full min-w-[720px] border-collapse text-[14.5px]">
            <tbody>
              {TOOLS.map(([name, what, why]) => (
                <tr key={name} className="border-b border-rule align-top">
                  <td className="py-3 pr-4 font-mono text-[13px] text-clay">{name}</td>
                  <td className="py-3 pr-4 text-ink">{what}</td>
                  <td className="py-3 text-ink-2">{why}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="mt-14 grid gap-6 md:grid-cols-3">
        <Box title="4 · Eval">
          41 questions in 8 categories, each with expected tools, filters, policy section and answer content. Code checks
          decide pass or fail, including a rule that every $ or £ amount in an answer must appear in a tool result. An LLM
          judge adds faithfulness and helpfulness scores. Results are saved with their evidence, so a grader fix is
          re-scored offline without calling the model again.
        </Box>
        <Box title="5 · Prompt versions">
          v1 is two sentences. v2 adds grounding, search, order and safety rules. v3 adds one rule per failure the first
          eval run found: check stock before saying “you can order it”, hand off immediately when asked for a person,
          explain shipping limits instead of implying “out of stock”.
        </Box>
        <Box title="6 · Not built (yet)">
          Real auth and a database for orders, a Qdrant server instead of embedded mode, tracing (LangSmith or
          OpenTelemetry), answer caching for repeated questions, and running the eval in CI on every prompt change.
        </Box>
      </section>
    </main>
  );
}
