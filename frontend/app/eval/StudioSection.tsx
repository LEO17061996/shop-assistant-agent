import Image from "next/image";
import baselineData from "@/data/image-baseline.json";
import studioData from "@/data/studio-eval.json";
import { pct } from "@/lib/eval";
import { STUDIO_FINDINGS } from "./findings";

type StudioCase = {
  id: string;
  name?: string;
  category: string;
  image_url?: string;
  truth?: { color: string | null; material: string | null };
  facts?: { category: string; colors: string[]; materials: string[]; product_type: string };
  category_ok?: boolean;
  colour_ok?: boolean | null;
  material_ok?: boolean | null;
  violations_by_round?: unknown[][];
  copy_passed?: boolean;
  unsupported_claims?: string[];
  similar_rank?: number | null;
  error?: string;
};
type Studio = {
  model: string;
  claim_check?: string | null;
  judge: string;
  n: number;
  errors: number;
  category_accuracy: number | null;
  colour_accuracy: number | null;
  colour_n: number;
  material_accuracy: number | null;
  material_n: number;
  first_draft_pass: number | null;
  final_pass: number | null;
  repairs_avg: number | null;
  no_unsupported_claims: number | null;
  unsupported_claims_avg: number | null;
  "visual_hit@1": number | null;
  "visual_hit@5": number | null;
  cost_usd_avg: number | null;
  latency_ms_median: number | null;
  cases: StudioCase[];
};
type Baseline = {
  n_queries: number;
  models: {
    model: string;
    "hit@1": number;
    "hit@5": number;
    ms_per_image_cpu: number;
    extra_ram_mb: number | null;
    ranks: Record<string, number>;
  }[];
};

const studio = studioData as unknown as Studio;
const baseline = baselineData as Baseline;

const MODEL_NAMES: Record<string, string> = {
  "Qdrant/clip-ViT-B-32-vision": "CLIP ViT-B/32",
  "google/siglip2-base-patch16-224": "SigLIP 2 base",
  "nomic-ai/nomic-embed-vision-v1.5-Q": "Nomic vision 1.5 (quantized)",
  "Qdrant/resnet50-onnx": "ResNet-50",
};

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-[3px] border border-rule bg-card p-4">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-3">{label}</p>
      <p className="mt-1 font-display text-3xl tabular-nums">{value}</p>
      {sub && <p className="mt-1 text-xs text-ink-3">{sub}</p>}
    </div>
  );
}

function Mark({ ok }: { ok: boolean | null | undefined }) {
  if (ok === null || ok === undefined) return <span className="text-ink-3">–</span>;
  return <span className={ok ? "text-olive" : "text-danger"}>{ok ? "✓" : "✗"}</span>;
}

export function StudioSection() {
  const cases = studio.cases.filter((c) => !c.error);
  const sampleIds = cases.map((c) => c.id);
  const onSample = (ranks: Record<string, number>) => {
    const r = sampleIds.map((id) => ranks[id]).filter((x) => x !== undefined);
    return { hit1: r.filter((x) => x === 1).length / r.length, hit5: r.filter((x) => x <= 5).length / r.length };
  };

  return (
    <section className="mt-16 border-t border-ink pt-10">
      <p className="font-mono text-[11px] uppercase tracking-[0.3em] text-ink-3">Project B · Listing Studio</p>
      <h2 className="mt-2 max-w-[24ch] font-display text-[36px] leading-[1.05] tracking-tight">
        Photo in, listing out, <em className="text-clay">checked against the catalog.</em>
      </h2>
      <p className="mt-3 max-w-[70ch] text-ink-2">
        {studio.n} products, a few per category. The catalog already knows each product&apos;s category, colour and
        material, so the vision step is scored against that. Visual search uses a <em>different</em> photo of the same
        product as the query and counts how often the product comes back.
      </p>
      {(studio.errors > 0 || !studio.claim_check) && (
        <p className="mt-3 max-w-[70ch] border-l-2 border-clay pl-3 text-sm text-clay">
          Preliminary: {studio.n - studio.errors} of {studio.n} products finished before the free-tier daily quota ran
          out{studio.claim_check ? "" : ", and this run predates the LLM claim check now in the pipeline"}. A full
          re-run is pending.
        </p>
      )}

      <div className="mt-6 grid grid-cols-2 gap-3 md:grid-cols-4">
        <Tile label="Category read" value={pct(studio.category_accuracy)} sub={`${cases.length} photos`} />
        <Tile label="Colour read" value={pct(studio.colour_accuracy)} sub={`${studio.colour_n} with a usable catalog colour`} />
        <Tile label="Material read" value={pct(studio.material_accuracy)} sub={`${studio.material_n} with a usable catalog material`} />
        <Tile
          label="Rules: first draft → final"
          value={`${pct(studio.first_draft_pass)} → ${pct(studio.final_pass)}`}
          sub={`${studio.repairs_avg} rewrites per listing on average`}
        />
        <Tile
          label="No unsupported claims"
          value={pct(studio.no_unsupported_claims)}
          sub={`${studio.unsupported_claims_avg} per listing, judged by ${studio.judge}`}
        />
        <Tile label="Visual search hit@5" value={pct(studio["visual_hit@5"])} sub={`hit@1 ${pct(studio["visual_hit@1"])}`} />
        <Tile
          label="Cost per listing"
          value={studio.cost_usd_avg !== null ? `$${studio.cost_usd_avg.toFixed(4)}` : "–"}
          sub="paid-tier list price, all calls"
        />
        <Tile
          label="Median time"
          value={studio.latency_ms_median ? `${(studio.latency_ms_median / 1000).toFixed(0)}s` : "–"}
          sub="free-tier queueing included"
        />
      </div>

      {STUDIO_FINDINGS.length > 0 && (
        <ol className="mt-8 space-y-4 border-y border-rule py-6">
          {STUDIO_FINDINGS.map((f, i) => (
            <li key={i} className="flex gap-4">
              <span className="font-mono text-sm text-clay">{String(i + 1).padStart(2, "0")}</span>
              <div>
                <p className="font-medium">{f.title}</p>
                <p className="mt-1 text-[15px] text-ink-2">{f.body}</p>
              </div>
            </li>
          ))}
        </ol>
      )}

      <h3 className="mt-10 font-display text-2xl">Visual search: describe-then-search vs image embeddings</h3>
      <p className="mt-1 max-w-[70ch] text-sm text-ink-2">
        Same {cases.length} query photos for every row. Image models were also run on all {baseline.n_queries} products
        with a second photo (last column). RAM is what the model adds to the process; the free API host has 512 MB in
        total and the app already uses about 380 MB.
      </p>
      <div className="mt-4 overflow-x-auto">
        <table className="w-full min-w-[720px] border-collapse text-sm">
          <thead>
            <tr className="border-b border-ink text-left font-mono text-[10px] uppercase tracking-wider text-ink-3">
              <th className="py-2 font-normal">Approach</th>
              <th className="py-2 text-right font-normal">hit@1</th>
              <th className="py-2 text-right font-normal">hit@5</th>
              <th className="py-2 text-right font-normal">Extra RAM</th>
              <th className="py-2 text-right font-normal">CPU / image</th>
              <th className="py-2 text-right font-normal">hit@5, all {baseline.n_queries}</th>
            </tr>
          </thead>
          <tbody>
            <tr className="border-b border-rule bg-olive-soft/40">
              <td className="py-2.5">
                Gemini describes the photo → hybrid text search <span className="ml-1 font-mono text-[10px] uppercase text-olive">live</span>
              </td>
              <td className="py-2.5 text-right font-mono">{pct(studio["visual_hit@1"])}</td>
              <td className="py-2.5 text-right font-mono">{pct(studio["visual_hit@5"])}</td>
              <td className="py-2.5 text-right font-mono">0 MB</td>
              <td className="py-2.5 text-right font-mono">1 API call</td>
              <td className="py-2.5 text-right font-mono text-ink-3">–</td>
            </tr>
            {baseline.models.map((m) => {
              const s = onSample(m.ranks);
              return (
                <tr key={m.model} className="border-b border-rule">
                  <td className="py-2.5">{MODEL_NAMES[m.model] ?? m.model} embeddings</td>
                  <td className="py-2.5 text-right font-mono">{pct(s.hit1)}</td>
                  <td className="py-2.5 text-right font-mono">{pct(s.hit5)}</td>
                  <td className="py-2.5 text-right font-mono">{m.extra_ram_mb !== null ? `${m.extra_ram_mb} MB` : "–"}</td>
                  <td className="py-2.5 text-right font-mono">{Math.round(m.ms_per_image_cpu)} ms</td>
                  <td className="py-2.5 text-right font-mono text-ink-3">{pct(m["hit@5"])}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <h3 className="mt-10 font-display text-2xl">What the model read vs what the catalog says</h3>
      <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {cases.map((c) => (
          <article key={c.id} className="flex gap-3 rounded-[3px] border border-rule bg-card p-3 text-[12px]">
            <div className="relative h-16 w-16 shrink-0 bg-paper-2">
              {c.image_url && <Image src={c.image_url} alt="" fill unoptimized className="object-contain p-1" />}
            </div>
            <div className="min-w-0 space-y-0.5 font-mono">
              <p className="truncate font-sans text-[13px] text-ink">{c.facts?.product_type}</p>
              <p className="truncate">
                <Mark ok={c.category_ok} /> {c.facts?.category}
              </p>
              <p className="truncate" title={`catalog: ${c.truth?.color ?? "–"}`}>
                <Mark ok={c.colour_ok} /> {c.facts?.colors.join(", ")}{" "}
                <span className="text-ink-3">/ {c.truth?.color ?? "–"}</span>
              </p>
              <p className="truncate" title={`catalog: ${c.truth?.material ?? "–"}`}>
                <Mark ok={c.material_ok} /> {c.facts?.materials.join(", ") || "–"}{" "}
                <span className="text-ink-3">/ {c.truth?.material ?? "–"}</span>
              </p>
              <p className="truncate text-ink-3">
                look-alike rank {c.similar_rank ?? ">10"} · {c.unsupported_claims?.length ?? 0} unsupported
              </p>
            </div>
          </article>
        ))}
      </div>
    </section>
  );
}
