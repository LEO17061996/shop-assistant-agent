"use client";

import { useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import { Ledger, type TraceLine } from "@/components/Ledger";
import { ProductCard } from "@/components/ProductCard";
import { streamChat, type Handoff, type HistoryItem, type Product, type Usage } from "@/lib/api";

type Turn = {
  id: number;
  role: "user" | "assistant";
  content: string;
  products: Product[];
  trace: TraceLine[];
  usage?: Usage;
  handoff?: Handoff;
  error?: string;
  streaming?: boolean;
};

const SUGGESTIONS = [
  "I'm in London and need a wooden side table under $150.",
  "Do you sell sofas that ship to the UK?",
  "I had a rug cut to fit my hallway. Can I still return it?",
  "Order KH-10407, email customer2@example.com. Where is it?",
  "Tôi ở Manchester, cần một tấm thảm dưới $300, phí ship bao nhiêu?",
];

const HISTORY_LIMIT = 12;
// The model is told never to write these notes, but strip them if it does
const SHOWN_NOTE = /\n?\[shown:[^\]]*\]/g;

function toHistory(turns: Turn[]): HistoryItem[] {
  return turns
    .filter((t) => t.content && !t.error)
    .slice(-HISTORY_LIMIT)
    .map((t) =>
      t.role === "user"
        ? { role: "user", content: t.content }
        : { role: "assistant", content: t.content, product_ids: t.products.map((p) => p.id).slice(0, 10) },
    );
}

export function ChatApp() {
  const [turns, setTurns] = useState<Turn[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [selected, setSelected] = useState<number | null>(null);
  const [ledgerOpen, setLedgerOpen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);
  const endRef = useRef<HTMLDivElement>(null);
  const nextId = useRef(1);

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [turns]);

  const assistantTurns = turns.filter((t) => t.role === "assistant");
  const ledgerTurn = turns.find((t) => t.id === selected) ?? assistantTurns.at(-1);
  const ledgerNumber = ledgerTurn ? assistantTurns.indexOf(ledgerTurn) + 1 : 0;

  function patch(id: number, fn: (t: Turn) => Turn) {
    setTurns((all) => all.map((t) => (t.id === id ? fn(t) : t)));
  }

  async function send(text: string) {
    const content = text.trim();
    if (!content || busy) return;
    const user: Turn = { id: nextId.current++, role: "user", content, products: [], trace: [] };
    const bot: Turn = { id: nextId.current++, role: "assistant", content: "", products: [], trace: [], streaming: true };
    const history = toHistory([...turns, user]);
    setTurns((all) => [...all, user, bot]);
    setSelected(null);
    setInput("");
    setBusy(true);

    const controller = new AbortController();
    abortRef.current = controller;
    try {
      for await (const ev of streamChat(history, controller.signal)) {
        switch (ev.event) {
          case "token":
            patch(bot.id, (t) => ({ ...t, content: t.content + ev.data.text }));
            break;
          case "step": {
            const s = ev.data;
            if (s.type === "tool_call") {
              patch(bot.id, (t) => ({ ...t, trace: [...t.trace, { step: s.step, name: s.name, args: s.args }] }));
            } else {
              patch(bot.id, (t) => {
                const i = t.trace.findIndex((l) => l.name === s.name && !l.status);
                if (i === -1) return t;
                const trace = [...t.trace];
                trace[i] = { ...trace[i], status: s.status, latency_ms: s.latency_ms };
                return { ...t, trace };
              });
            }
            break;
          }
          case "products":
            patch(bot.id, (t) => {
              const seen = new Set(t.products.map((p) => p.id));
              return { ...t, products: [...t.products, ...ev.data.products.filter((p) => !seen.has(p.id))] };
            });
            break;
          case "handoff":
            patch(bot.id, (t) => ({ ...t, handoff: ev.data }));
            break;
          case "done":
            patch(bot.id, (t) => ({ ...t, usage: ev.data }));
            break;
          case "error":
            patch(bot.id, (t) => ({ ...t, error: ev.data.message }));
            break;
        }
      }
    } catch (e) {
      if ((e as Error).name !== "AbortError") {
        patch(bot.id, (t) => ({ ...t, error: "Could not reach the assistant. Is the API running?" }));
      }
    } finally {
      patch(bot.id, (t) => ({ ...t, streaming: false }));
      setBusy(false);
      abortRef.current = null;
    }
  }

  const ledger = (
    <Ledger
      lines={ledgerTurn?.trace ?? []}
      usage={ledgerTurn?.usage}
      busy={Boolean(ledgerTurn?.streaming)}
      turn={ledgerNumber}
    />
  );

  return (
    <div className="mx-auto grid w-full max-w-[1240px] flex-1 gap-8 px-4 py-6 sm:px-6 lg:grid-cols-[minmax(0,1fr)_340px]">
      <section className="flex min-h-[70vh] flex-col">
        {turns.length === 0 ? (
          <Welcome onPick={send} />
        ) : (
          <div className="flex-1 space-y-7 pb-6">
            {turns.map((t) =>
              t.role === "user" ? (
                <div key={t.id} className="rise flex justify-end">
                  <p className="max-w-[85%] whitespace-pre-wrap rounded-[18px] rounded-br-[4px] bg-ink px-4 py-2.5 text-[15px] text-paper">
                    {t.content}
                  </p>
                </div>
              ) : (
                <AssistantTurn
                  key={t.id}
                  t={t}
                  active={ledgerTurn?.id === t.id}
                  onShowLedger={() => {
                    setSelected(t.id);
                    setLedgerOpen(true);
                  }}
                />
              ),
            )}
            <div ref={endRef} />
          </div>
        )}

        <form
          className="sticky bottom-0 mt-auto border-t border-rule bg-paper/95 pt-3 pb-4 backdrop-blur"
          onSubmit={(e) => {
            e.preventDefault();
            send(input);
          }}
        >
          <div className="flex items-end gap-2 rounded-[4px] border border-rule bg-card p-2 focus-within:border-clay">
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  send(input);
                }
              }}
              rows={1}
              maxLength={2000}
              placeholder="Ask about a product, delivery, returns or an order…"
              className="max-h-40 min-h-[40px] flex-1 resize-none bg-transparent px-2 py-2 text-[15px] outline-none placeholder:text-ink-3"
              style={{ fieldSizing: "content" } as React.CSSProperties}
            />
            {busy ? (
              <button
                type="button"
                onClick={() => abortRef.current?.abort()}
                className="rounded-[3px] border border-rule px-4 py-2 text-sm text-ink-2 hover:bg-paper-2"
              >
                Stop
              </button>
            ) : (
              <button
                type="submit"
                disabled={!input.trim()}
                className="rounded-[3px] bg-clay px-4 py-2 text-sm font-medium text-white transition hover:brightness-110 disabled:opacity-40"
              >
                Ask
              </button>
            )}
          </div>
          <p className="mt-2 text-[11px] text-ink-3">
            Answers come from the catalog and policy tools only. Replies in your language.
          </p>
        </form>
      </section>

      <aside className="hidden lg:block">
        <div className="sticky top-6">{ledger}</div>
      </aside>

      {/* Mobile: the "N tool calls" link under an answer opens the ledger as a bottom sheet */}
      {ledgerOpen && (
        <div className="fixed inset-0 z-30 flex items-end bg-ink/40 lg:hidden" onClick={() => setLedgerOpen(false)}>
          <div className="max-h-[80vh] w-full overflow-y-auto bg-paper p-4" onClick={(e) => e.stopPropagation()}>
            {ledger}
          </div>
        </div>
      )}
    </div>
  );
}

/** Seconds since mount, shown after 3s so a slow free-tier queue does not look like a hang. */
function Elapsed() {
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(id);
  }, []);
  if (seconds < 3) return null;
  return (
    <span className="ml-2 not-italic font-mono text-[11px]">
      {seconds}s{seconds >= 12 ? " · free-tier model queue, still working" : ""}
    </span>
  );
}

function AssistantTurn({ t, active, onShowLedger }: { t: Turn; active: boolean; onShowLedger: () => void }) {
  const text = t.content.replace(SHOWN_NOTE, "");
  return (
    <div className="rise">
      <div className="mb-1.5 flex items-center gap-3">
        <span className="font-mono text-[10px] uppercase tracking-[0.25em] text-clay">Kestrel</span>
        {t.trace.length > 0 && (
          <button
            onClick={onShowLedger}
            className={`font-mono text-[10px] text-ink-3 underline-offset-4 hover:text-ink hover:underline ${active ? "text-ink" : ""}`}
          >
            {t.trace.length} tool call{t.trace.length > 1 ? "s" : ""}
            {t.usage ? ` · ${(t.usage.latency_ms / 1000).toFixed(1)}s` : ""}
          </button>
        )}
      </div>
      {text ? (
        <div className={`prose-answer max-w-[62ch] text-[15.5px] leading-relaxed ${t.streaming ? "caret" : ""}`}>
          <ReactMarkdown>{text}</ReactMarkdown>
        </div>
      ) : (
        t.streaming &&
        !t.error && (
          <p className="text-[15px] italic text-ink-3">
            {t.trace.length ? `Checking ${t.trace.at(-1)?.name.replaceAll("_", " ")}…` : "Thinking…"}
            <Elapsed />
          </p>
        )
      )}
      {t.error && <p className="mt-2 border-l-2 border-danger pl-3 text-sm text-danger">{t.error}</p>}
      {t.handoff && (
        <div className="mt-3 inline-flex items-stretch overflow-hidden rounded-[3px] border border-dashed border-clay/60 bg-clay-soft text-sm">
          <span className="border-r border-dashed border-clay/60 px-3 py-2 font-mono text-clay">{t.handoff.ticket}</span>
          <span className="px-3 py-2 text-ink-2">Passed to a person · {t.handoff.reason}</span>
        </div>
      )}
      {t.products.length > 0 && (
        <div className="-mx-1 mt-4 flex gap-3 overflow-x-auto px-1 pb-2">
          {t.products.map((p, i) => (
            <ProductCard key={p.id} p={p} index={i} />
          ))}
        </div>
      )}
    </div>
  );
}

function Welcome({ onPick }: { onPick: (q: string) => void }) {
  return (
    <div className="flex-1 pt-6 pb-10">
      <p className="rise font-mono text-[11px] uppercase tracking-[0.3em] text-ink-3">The shopping desk</p>
      <h1
        className="rise mt-3 max-w-[16ch] font-display text-[44px] leading-[1.02] tracking-tight sm:text-[60px]"
        style={{ animationDelay: "60ms", fontVariationSettings: '"SOFT" 100' }}
      >
        Ask the shop floor <em className="text-clay">anything.</em>
      </h1>
      <p className="rise mt-4 max-w-[52ch] text-ink-2" style={{ animationDelay: "120ms" }}>
        453 real furniture products, five store policies and a few test orders. The assistant searches, checks
        shipping and looks up orders with tools, and every step is itemised in the agent ledger.
      </p>
      <ol className="mt-8 grid gap-2 sm:grid-cols-2">
        {SUGGESTIONS.map((q, i) => (
          <li key={q} className="rise" style={{ animationDelay: `${180 + i * 60}ms` }}>
            <button
              onClick={() => onPick(q)}
              className="group flex h-full w-full items-start gap-3 rounded-[3px] border border-rule bg-card/70 p-3 text-left text-[14px] transition hover:border-clay hover:bg-card"
            >
              <span className="font-mono text-[11px] text-clay">{String(i + 1).padStart(2, "0")}</span>
              <span className="text-ink-2 group-hover:text-ink">{q}</span>
            </button>
          </li>
        ))}
      </ol>
    </div>
  );
}
