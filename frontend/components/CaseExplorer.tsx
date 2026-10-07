"use client";

import { useEffect, useState } from "react";
import ReactMarkdown from "react-markdown";
import type { CaseResult } from "@/lib/eval";

type Filter = "all" | "failed" | "passed";

export function CaseExplorer({
  runs,
  checkLabels,
}: {
  runs: { id: string; label: string }[];
  checkLabels: Record<string, string>;
}) {
  const [runId, setRunId] = useState(runs[0]?.id);
  const [cases, setCases] = useState<CaseResult[] | null>(null);
  const [filter, setFilter] = useState<Filter>("failed");
  const [open, setOpen] = useState<string | null>(null);

  useEffect(() => {
    if (!runId) return;
    let cancelled = false;
    fetch(`/eval/${runId}.json`)
      .then((r) => r.json())
      .then((d) => !cancelled && setCases(d.cases))
      .catch(() => !cancelled && setCases([]));
    return () => {
      cancelled = true;
    };
  }, [runId]);

  const shown = (cases ?? []).filter((c) => filter === "all" || (filter === "failed") === !c.passed);

  return (
    <div className="mt-6">
      <div className="flex flex-wrap items-center gap-3">
        <select
          value={runId}
          onChange={(e) => {
            setCases(null);
            setRunId(e.target.value);
          }}
          className="rounded-[3px] border border-rule bg-card px-3 py-2 text-sm"
        >
          {runs.map((r) => (
            <option key={r.id} value={r.id}>
              {r.label}
            </option>
          ))}
        </select>
        <div className="flex overflow-hidden rounded-[3px] border border-rule text-sm">
          {(["failed", "passed", "all"] as Filter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-3 py-2 capitalize ${filter === f ? "bg-ink text-paper" : "bg-card text-ink-2 hover:bg-paper-2"}`}
            >
              {f}
            </button>
          ))}
        </div>
        {cases && (
          <span className="font-mono text-xs text-ink-3">
            {cases.filter((c) => c.passed).length}/{cases.length} passed
          </span>
        )}
      </div>

      {cases === null ? (
        <p className="mt-6 text-ink-3">Loading…</p>
      ) : shown.length === 0 ? (
        <p className="mt-6 text-ink-3">Nothing here.</p>
      ) : (
        <ul className="mt-4 divide-y divide-rule border-y border-rule">
          {shown.map((c) => {
            const failed = Object.entries(c.checks ?? {}).filter(([, v]) => !v.pass);
            const isOpen = open === c.id;
            return (
              <li key={c.id}>
                <button
                  onClick={() => setOpen(isOpen ? null : c.id)}
                  className="flex w-full items-baseline gap-4 py-3 text-left hover:bg-card/60"
                  aria-expanded={isOpen}
                >
                  <span className={`w-12 shrink-0 font-mono text-[11px] ${c.passed ? "text-olive" : "text-danger"}`}>
                    {c.passed ? "PASS" : "FAIL"}
                  </span>
                  <span className="w-24 shrink-0 font-mono text-[11px] text-ink-3">{c.id}</span>
                  <span className="flex-1 text-[15px]">{c.message}</span>
                  <span className="hidden shrink-0 font-mono text-[11px] text-ink-3 sm:inline">
                    {(c.latency_ms / 1000).toFixed(1)}s · {c.steps} calls
                  </span>
                </button>
                {isOpen && (
                  <div className="grid gap-6 pb-6 pl-0 sm:pl-16 md:grid-cols-[1fr_300px]">
                    <div>
                      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-3">Answer</p>
                      <div className="prose-answer mt-1 rounded-[3px] border border-rule bg-card p-4 text-[14.5px] leading-relaxed">
                        {c.error ? <p className="text-danger">{c.error}</p> : <ReactMarkdown>{c.answer || "_(empty)_"}</ReactMarkdown>}
                      </div>
                      {c.judge?.reason && (
                        <p className="mt-3 text-sm text-ink-2">
                          <span className="font-mono text-[11px] text-clay">
                            judge {c.judge.faithfulness}/5 faithful · {c.judge.helpfulness}/5 helpful —{" "}
                          </span>
                          {c.judge.reason}
                        </p>
                      )}
                    </div>
                    <div className="space-y-4 font-mono text-[12px]">
                      <div>
                        <p className="text-[10px] uppercase tracking-[0.2em] text-ink-3">Tool calls</p>
                        {c.tool_calls?.length ? (
                          <ol className="mt-1 space-y-1">
                            {c.tool_calls.map((t, i) => (
                              <li key={i} className="break-words">
                                <span className="text-clay">→</span> {t.name}
                                <span className="text-ink-3"> {JSON.stringify(t.args)}</span>
                              </li>
                            ))}
                          </ol>
                        ) : (
                          <p className="mt-1 text-ink-3">none</p>
                        )}
                      </div>
                      <div>
                        <p className="text-[10px] uppercase tracking-[0.2em] text-ink-3">Checks</p>
                        <ul className="mt-1 space-y-1">
                          {Object.entries(c.checks ?? {}).map(([k, v]) => (
                            <li key={k} className={v.pass ? "text-olive" : "text-danger"}>
                              {v.pass ? "✓" : "✗"} {checkLabels[k] ?? k}
                              {!v.pass && v.detail && <span className="block pl-4 text-ink-3">{v.detail}</span>}
                            </li>
                          ))}
                        </ul>
                        {failed.length === 0 && !c.error && <p className="mt-1 text-ink-3">all passed</p>}
                      </div>
                    </div>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
