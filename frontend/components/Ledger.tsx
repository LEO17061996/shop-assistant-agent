import type { Usage } from "@/lib/api";

export type TraceLine = {
  step: number;
  name: string;
  args: Record<string, unknown>;
  status?: "success" | "error";
  latency_ms?: number | null;
};

function formatArgs(args: Record<string, unknown>) {
  return Object.entries(args)
    .filter(([, v]) => v !== null && v !== undefined && v !== false)
    .map(([k, v]) => `${k}=${JSON.stringify(v)}`)
    .join(" ");
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-baseline gap-2">
      <span>{label}</span>
      <span className="leader h-[1em] flex-1" />
      <span className="tabular-nums">{value}</span>
    </div>
  );
}

export function Ledger({
  lines,
  usage,
  busy,
  turn,
}: {
  lines: TraceLine[];
  usage?: Usage;
  busy: boolean;
  turn: number;
}) {
  const steps = [...new Set(lines.map((l) => l.step))];
  return (
    <div className="receipt-edge bg-card px-5 pt-5 pb-8 font-mono text-[12px] leading-relaxed text-ink-2 shadow-[0_10px_30px_-18px_rgba(60,40,20,0.45)]">
      <div className="text-center">
        <p className="text-[10px] uppercase tracking-[0.3em] text-ink-3">Agent ledger</p>
        <p className="font-display text-lg italic text-ink">Turn {turn || "—"}</p>
      </div>
      <div className="my-3 border-t border-dashed border-rule" />

      {lines.length === 0 && !busy && (
        <p className="py-4 text-center text-ink-3">
          Each model call, tool call and its latency
          <br />
          is itemised here as the agent works.
        </p>
      )}

      <ol className="space-y-3">
        {steps.map((s) => (
          <li key={s} className="rise">
            <p className="text-[10px] uppercase tracking-[0.2em] text-ink-3">Loop {s} · model → tools</p>
            {lines
              .filter((l) => l.step === s)
              .map((l, i) => (
                <div key={i} className="mt-1">
                  <div className="flex items-baseline gap-2 text-ink">
                    <span className="text-clay">→</span>
                    <span className="font-medium">{l.name}</span>
                    <span className="leader h-[1em] flex-1" />
                    <span
                      className={`tabular-nums ${
                        l.status === "error" ? "text-danger" : l.status ? "text-olive" : "text-ink-3"
                      }`}
                    >
                      {l.status ? `${l.status === "error" ? "ERR" : "ok"} ${l.latency_ms ?? "?"}ms` : "…"}
                    </span>
                  </div>
                  <p className="break-words pl-4 text-[11px] text-ink-3">{formatArgs(l.args) || "(no args)"}</p>
                </div>
              ))}
          </li>
        ))}
        {busy && (
          <li className="flex items-center gap-2 text-ink-3">
            <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-clay" />
            model thinking…
          </li>
        )}
      </ol>

      {usage && (
        <>
          <div className="my-3 border-t border-dashed border-rule" />
          <div className="space-y-0.5">
            <Row label="Model" value={usage.model} />
            <Row label="Model calls" value={String(usage.steps)} />
            <Row label="Tokens in" value={usage.input_tokens.toLocaleString()} />
            <Row label="Tokens out" value={usage.output_tokens.toLocaleString()} />
            <Row label="Wall time" value={`${(usage.latency_ms / 1000).toFixed(1)}s`} />
          </div>
          <div className="my-3 border-t border-double border-rule" />
          <div className="flex items-baseline justify-between text-ink">
            <span className="uppercase tracking-[0.2em]">Total</span>
            <span className="font-display text-xl not-italic tabular-nums">
              {usage.cost_usd === null ? "n/a" : `$${usage.cost_usd.toFixed(4)}`}
            </span>
          </div>
          <p className="mt-1 text-right text-[10px] text-ink-3">at paid-tier list price</p>
        </>
      )}
    </div>
  );
}
