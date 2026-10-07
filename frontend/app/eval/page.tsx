import type { Metadata } from "next";
import summaryData from "@/data/eval-summary.json";
import { CaseExplorer } from "@/components/CaseExplorer";
import { CHECK_LABELS, MODEL_LABELS, pct, type RunSummary } from "@/lib/eval";
import { FINDINGS, LIVE_CONFIG } from "./findings";

export const metadata: Metadata = { title: "Eval report — Kestrel Home assistant" };

const runs = (summaryData as RunSummary[]).toSorted((a, b) => b.pass_rate - a.pass_rate);

function heat(value: number | undefined) {
  if (value === undefined) return {};
  // Low scores lean clay, high scores lean olive
  const tone = value >= 0.8 ? "var(--olive)" : value >= 0.6 ? "var(--ink-3)" : "var(--clay)";
  const strength = value >= 0.8 ? Math.round((value - 0.6) * 90) : Math.round((1 - value) * 45);
  return { background: `color-mix(in oklab, ${tone} ${strength}%, transparent)` };
}

function label(r: RunSummary) {
  return `${MODEL_LABELS[r.model] ?? r.model} · ${r.prompt}`;
}

function Matrix({ title, rows, get }: { title: string; rows: [string, string][]; get: (r: RunSummary, key: string) => { pass_rate: number; n: number } | undefined }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-sm">
        <thead>
          <tr className="border-b border-ink">
            <th className="py-2 pr-4 text-left font-normal text-ink-3">{title}</th>
            {runs.map((r) => (
              <th key={r.run_id} className="px-2 py-2 text-right align-bottom font-mono text-[10px] font-normal uppercase leading-tight tracking-wider text-ink-2">
                {MODEL_LABELS[r.model] ?? r.model}
                <br />
                <span className="text-clay">{r.prompt}</span>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(([key, text]) => (
            <tr key={key} className="border-b border-rule">
              <td className="py-2 pr-4 text-ink-2">
                {text}
                <span className="ml-2 font-mono text-[10px] text-ink-3">n={runs.map((r) => get(r, key)?.n).find(Boolean) ?? 0}</span>
              </td>
              {runs.map((r) => {
                const v = get(r, key);
                return (
                  <td key={r.run_id} className="px-2 py-2 text-right font-mono tabular-nums" style={heat(v?.pass_rate)}>
                    {pct(v?.pass_rate)}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export default function EvalPage() {
  const checkKeys = Object.keys(CHECK_LABELS).filter((k) => runs.some((r) => r.by_check[k]));
  const categories = [...new Set(runs.flatMap((r) => Object.keys(r.by_category)))];
  const nCases = runs[0]?.n_cases ?? 0;

  return (
    <main className="mx-auto w-full max-w-[1240px] px-4 py-8 sm:px-6">
      <p className="rise font-mono text-[11px] uppercase tracking-[0.3em] text-ink-3">Report card</p>
      <h1 className="rise mt-2 max-w-[20ch] font-display text-[44px] leading-[1.05] tracking-tight sm:text-[56px]">
        Same {nCases} questions, <em className="text-clay">every model, every prompt.</em>
      </h1>
      <p className="rise mt-4 max-w-[68ch] text-ink-2">
        Each question has an expected outcome: which tool should run, which filters it should use, which policy section
        it should find, what the answer must say. Those are checked by code. On top, Claude Haiku 4.5 grades every answer
        for faithfulness to the retrieved evidence and helpfulness (1–5). A case passes only if every code check passes.
      </p>

      <section className="mt-10">
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] border-collapse">
            <thead>
              <tr className="border-b border-ink text-left font-mono text-[10px] uppercase tracking-wider text-ink-3">
                <th className="py-2 font-normal">Configuration</th>
                <th className="py-2 text-right font-normal">Pass</th>
                <th className="py-2 text-right font-normal">Faithful</th>
                <th className="py-2 text-right font-normal">Helpful</th>
                <th className="py-2 text-right font-normal">Median time</th>
                <th className="py-2 text-right font-normal">Model calls</th>
                <th className="py-2 text-right font-normal">Cost / chat*</th>
              </tr>
            </thead>
            <tbody>
              {runs.map((r, i) => {
                const live = r.model === LIVE_CONFIG.model && r.prompt === LIVE_CONFIG.prompt;
                return (
                  <tr key={r.run_id} className="rise border-b border-rule" style={{ animationDelay: `${i * 50}ms` }}>
                    <td className="py-3">
                      <span className="font-display text-lg">{MODEL_LABELS[r.model] ?? r.model}</span>
                      <span className="ml-2 rounded-sm bg-paper-2 px-1.5 py-0.5 font-mono text-[11px] text-clay">prompt {r.prompt}</span>
                      {live && <span className="ml-2 rounded-sm bg-olive-soft px-1.5 py-0.5 font-mono text-[10px] uppercase text-olive">live demo</span>}
                      {r.errors > 0 && <span className="ml-2 font-mono text-[10px] text-danger">{r.errors} errored</span>}
                    </td>
                    <td className="py-3 text-right font-display text-3xl tabular-nums">{pct(r.pass_rate)}</td>
                    <td className="py-3 text-right font-mono tabular-nums">{r.judge_faithfulness_avg?.toFixed(2) ?? "–"}</td>
                    <td className="py-3 text-right font-mono tabular-nums">{r.judge_helpfulness_avg?.toFixed(2) ?? "–"}</td>
                    <td className="py-3 text-right font-mono tabular-nums">
                      {r.latency_ms_median ? `${(r.latency_ms_median / 1000).toFixed(1)}s` : "–"}
                    </td>
                    <td className="py-3 text-right font-mono tabular-nums">{r.steps_avg?.toFixed(1) ?? "–"}</td>
                    <td className="py-3 text-right font-mono tabular-nums">
                      {r.cost_usd_avg !== null ? `$${r.cost_usd_avg.toFixed(4)}` : "–"}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="mt-2 text-xs text-ink-3">
          *Paid-tier list price for the tokens used, averaged per question. The live demo runs on the Gemini free tier.
          Times include every model call and tool call in the loop.
        </p>
      </section>

      {FINDINGS.length > 0 && (
        <section className="mt-12 grid gap-6 border-y border-rule py-8 md:grid-cols-[220px_1fr]">
          <h2 className="font-display text-2xl italic">What the numbers say</h2>
          <ol className="space-y-4">
            {FINDINGS.map((f, i) => (
              <li key={i} className="flex gap-4">
                <span className="font-mono text-sm text-clay">{String(i + 1).padStart(2, "0")}</span>
                <div>
                  <p className="font-medium">{f.title}</p>
                  <p className="mt-1 text-[15px] text-ink-2">{f.body}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}

      <section className="mt-12 space-y-10">
        <Matrix title="Code check" rows={checkKeys.map((k) => [k, CHECK_LABELS[k]])} get={(r, k) => r.by_check[k]} />
        <Matrix title="Question type" rows={categories.map((c) => [c, c.replace("_", " ")])} get={(r, k) => r.by_category[k]} />
      </section>

      <section className="mt-14">
        <h2 className="font-display text-3xl tracking-tight">Every answer, with its trace</h2>
        <p className="mt-2 max-w-[65ch] text-ink-2">
          Pick a run to read what the assistant actually said, which tools it called, which check failed and why the
          judge scored it the way it did.
        </p>
        <CaseExplorer runs={runs.map((r) => ({ id: r.run_id, label: label(r) }))} checkLabels={CHECK_LABELS} />
      </section>
    </main>
  );
}
