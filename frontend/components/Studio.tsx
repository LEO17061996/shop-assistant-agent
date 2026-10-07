"use client";

import Image from "next/image";
import { useEffect, useRef, useState } from "react";
import { ProductCard } from "@/components/ProductCard";
import { money, type Product } from "@/lib/api";
import {
  analyze,
  downloadShopifyCsv,
  getSamples,
  LIMITS,
  type Copy,
  type Facts,
  type Notes,
  type StudioUsage,
  type Violation,
} from "@/lib/studio";

type Step = "photo" | "copy" | "similar";
type StepState = { status: "idle" | "running" | "done"; ms?: number };
type Run = {
  facts?: Facts;
  imageUrl: string | null;
  rounds: Violation[][];
  copy?: Copy;
  passed?: boolean;
  similar?: Product[];
  usage?: StudioUsage;
  error?: string;
  steps: Record<Step, StepState>;
};

const STEP_LABELS: Record<Step, string> = {
  photo: "Read the photo",
  copy: "Write, check, repair",
  similar: "Find look-alikes",
};
const ANGLE_LABELS = { benefit: "Benefit", style: "Style", "problem-solution": "Problem → solution" };
const idleSteps = (): Record<Step, StepState> => ({
  photo: { status: "idle" },
  copy: { status: "idle" },
  similar: { status: "idle" },
});

export function Studio() {
  const [samples, setSamples] = useState<Product[] | null>(null);
  const [samplesError, setSamplesError] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [sample, setSample] = useState<Product | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [price, setPrice] = useState("");
  const [dimensions, setDimensions] = useState("");
  const [notes, setNotes] = useState("");
  const [hint, setHint] = useState("");
  const [run, setRun] = useState<Run | null>(null);
  const [busy, setBusy] = useState(false);
  const [dragOver, setDragOver] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const objectUrl = useRef<string | null>(null);

  useEffect(() => {
    // Also wakes a sleeping free-tier API before the visitor presses the button
    getSamples()
      .then(setSamples)
      .catch(() => setSamplesError(true));
  }, []);

  // Free the last preview URL when the page goes away
  useEffect(
    () => () => {
      if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    },
    [],
  );

  function pickFile(f: File | undefined) {
    if (!f || !f.type.startsWith("image/")) return;
    if (objectUrl.current) URL.revokeObjectURL(objectUrl.current);
    objectUrl.current = URL.createObjectURL(f);
    setFile(f);
    setSample(null);
    setPreview(objectUrl.current);
  }

  function pickSample(p: Product) {
    setSample(p);
    setFile(null);
    setPreview(p.image_url);
    if (!price) setPrice(String(p.price_usd));
  }

  const sellerNotes = (): Notes => ({
    price_usd: price ? Number(price) : undefined,
    dimensions: dimensions || undefined,
    notes: notes || undefined,
  });

  async function start() {
    if (busy || (!file && !sample)) return;
    setBusy(true);
    const next: Run = { imageUrl: sample?.image_url ?? null, rounds: [], steps: idleSteps() };
    setRun(next);
    const update = (fn: (r: Run) => Run) => setRun((r) => (r ? fn(r) : r));
    try {
      for await (const ev of analyze({
        file: file ?? undefined,
        sampleId: sample?.id,
        hint: hint || undefined,
        notes: sellerNotes(),
      })) {
        switch (ev.event) {
          case "stage":
            update((r) => ({
              ...r,
              steps: {
                ...r.steps,
                [ev.data.step]: { status: ev.data.status === "start" ? "running" : "done", ms: ev.data.ms },
              },
            }));
            break;
          case "facts":
            update((r) => ({ ...r, facts: ev.data.facts, imageUrl: ev.data.image_url ?? r.imageUrl }));
            break;
          case "check":
            update((r) => ({ ...r, rounds: [...r.rounds, ev.data.violations] }));
            break;
          case "copy":
            update((r) => ({ ...r, copy: ev.data.copy, passed: ev.data.passed }));
            break;
          case "similar":
            update((r) => ({ ...r, similar: ev.data.products }));
            break;
          case "done":
            update((r) => ({ ...r, usage: ev.data }));
            break;
          case "error":
            update((r) => ({ ...r, error: ev.data.message }));
            break;
        }
      }
    } catch {
      update((r) => ({ ...r, error: "Could not reach the API. It may be waking up; try again in a minute." }));
    } finally {
      setBusy(false);
    }
  }

  const adImage = preview;

  return (
    <div className="mx-auto grid w-full max-w-[1240px] gap-10 px-4 py-8 sm:px-6 lg:grid-cols-[380px_minmax(0,1fr)]">
      <section className="space-y-6 lg:sticky lg:top-6 lg:self-start">
        <div>
          <p className="rise font-mono text-[11px] uppercase tracking-[0.3em] text-ink-3">Listing studio</p>
          <h1 className="rise mt-2 font-display text-[40px] leading-[1.02] tracking-tight">
            Photo in, <em className="text-clay">listing out.</em>
          </h1>
          <p className="rise mt-3 text-[15px] text-ink-2">
            A vision model reads the product, a second call writes the listing and three Meta ads, and code checks every
            character limit and claim before anything is shown.
          </p>
        </div>

        <div
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={(e) => {
            e.preventDefault();
            setDragOver(false);
            pickFile(e.dataTransfer.files[0]);
          }}
          onClick={() => inputRef.current?.click()}
          className={`relative flex aspect-[4/3] cursor-pointer items-center justify-center overflow-hidden rounded-[3px] border border-dashed bg-card transition ${
            dragOver ? "border-clay bg-clay-soft" : "border-rule hover:border-clay"
          }`}
        >
          {preview ? (
            <Image src={preview} alt="Product photo" fill unoptimized className="object-contain p-4" />
          ) : (
            <div className="px-6 text-center text-sm text-ink-3">
              <p className="font-display text-xl text-ink-2">Drop a product photo</p>
              <p className="mt-1">or click to choose · JPG, PNG, WebP up to 5 MB</p>
            </div>
          )}
          <input
            ref={inputRef}
            type="file"
            accept="image/*"
            className="hidden"
            onChange={(e) => pickFile(e.target.files?.[0])}
          />
        </div>

        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-3">Or try a catalog photo</p>
          {samplesError ? (
            <p className="mt-2 text-sm text-ink-3">The API is waking up. Reload in a minute to see samples.</p>
          ) : (
            <div className="mt-2 grid grid-cols-4 gap-2">
              {(samples ?? Array.from({ length: 8 }, () => null)).map((p, i) =>
                p ? (
                  <button
                    key={p.id}
                    onClick={() => pickSample(p)}
                    title={p.name}
                    className={`relative aspect-square overflow-hidden rounded-[3px] border bg-card transition ${
                      sample?.id === p.id ? "border-clay ring-2 ring-clay/30" : "border-rule hover:border-clay"
                    }`}
                  >
                    <Image src={p.image_url} alt={p.name} fill unoptimized sizes="90px" className="object-contain p-1.5" />
                  </button>
                ) : (
                  <div key={i} className="aspect-square animate-pulse rounded-[3px] bg-paper-2" />
                ),
              )}
            </div>
          )}
        </div>

        <fieldset className="space-y-3">
          <legend className="font-mono text-[10px] uppercase tracking-[0.2em] text-ink-3">
            Seller notes · the only facts the photo can&apos;t give
          </legend>
          <input
            value={hint}
            onChange={(e) => setHint(e.target.value)}
            maxLength={60}
            placeholder="What's for sale? e.g. the rug (helps with room shots)"
            className="w-full rounded-[3px] border border-rule bg-card px-3 py-2 text-sm outline-none focus:border-clay"
          />
          <div className="grid grid-cols-2 gap-2">
            <input
              value={price}
              onChange={(e) => setPrice(e.target.value.replace(/[^0-9.]/g, ""))}
              inputMode="decimal"
              placeholder="Price, USD"
              className="rounded-[3px] border border-rule bg-card px-3 py-2 text-sm outline-none focus:border-clay"
            />
            <input
              value={dimensions}
              onChange={(e) => setDimensions(e.target.value)}
              maxLength={120}
              placeholder='Size, e.g. 32"W x 36"H'
              className="rounded-[3px] border border-rule bg-card px-3 py-2 text-sm outline-none focus:border-clay"
            />
          </div>
          <textarea
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            maxLength={400}
            rows={2}
            placeholder="Anything else that's true: handmade in Vermont, free UK shipping…"
            className="w-full resize-none rounded-[3px] border border-rule bg-card px-3 py-2 text-sm outline-none focus:border-clay"
          />
        </fieldset>

        <button
          onClick={start}
          disabled={busy || (!file && !sample)}
          className="w-full rounded-[3px] bg-clay px-4 py-3 font-medium text-white transition hover:brightness-110 disabled:opacity-40"
        >
          {busy ? "Working…" : "Write the listing"}
        </button>

        {run && <Tracker run={run} />}
      </section>

      <section className="min-w-0 space-y-10">
        {!run && <Placeholder />}
        {run?.error && <p className="border-l-2 border-danger pl-3 text-danger">{run.error}</p>}
        {run?.facts && <FactsPanel facts={run.facts} />}
        {run && run.rounds.length > 0 && <Checks rounds={run.rounds} passed={run.passed} />}
        {run?.copy && run.facts && (
          <>
            <ListingPreview copy={run.copy} price={price ? Number(price) : undefined} />
            <SearchPreview copy={run.copy} />
            <Ads copy={run.copy} image={adImage} />
            <div className="flex flex-wrap gap-3">
              <button
                onClick={() => downloadShopifyCsv(run.copy!, run.facts!, sellerNotes(), run.imageUrl)}
                className="rounded-[3px] bg-ink px-4 py-2 text-sm text-paper hover:opacity-90"
              >
                Download Shopify CSV (draft product)
              </button>
              <button
                onClick={() => navigator.clipboard.writeText(JSON.stringify(run.copy, null, 2))}
                className="rounded-[3px] border border-rule px-4 py-2 text-sm text-ink-2 hover:bg-card"
              >
                Copy as JSON
              </button>
            </div>
          </>
        )}
        {run?.similar && (
          <div>
            <SectionTitle n="06" title="Look-alikes in the catalog" note="photo → description → hybrid search" />
            <div className="mt-3 flex gap-3 overflow-x-auto pb-2">
              {run.similar.map((p, i) => (
                <ProductCard key={p.id} p={p} index={i} />
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  );
}

function SectionTitle({ n, title, note }: { n: string; title: string; note?: string }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-3 border-b border-rule pb-2">
      <span className="font-mono text-[11px] text-clay">{n}</span>
      <h2 className="font-display text-2xl tracking-tight">{title}</h2>
      {note && <span className="font-mono text-[11px] text-ink-3">{note}</span>}
    </div>
  );
}

function Counter({ text, limit }: { text: string; limit: number }) {
  const over = text.length > limit;
  return (
    <span className={`font-mono text-[10px] tabular-nums ${over ? "text-danger" : "text-ink-3"}`}>
      {text.length}/{limit}
    </span>
  );
}

function Tracker({ run }: { run: Run }) {
  return (
    <div className="receipt-edge bg-card px-5 pt-4 pb-8 font-mono text-[12px] text-ink-2 shadow-[0_10px_30px_-18px_rgba(60,40,20,0.45)]">
      <p className="text-center text-[10px] uppercase tracking-[0.3em] text-ink-3">Pipeline</p>
      <div className="my-3 border-t border-dashed border-rule" />
      {(Object.keys(STEP_LABELS) as Step[]).map((s, i) => {
        const st = run.steps[s];
        return (
          <div key={s} className="flex items-baseline gap-2 py-0.5">
            <span className="text-clay">{i + 1}</span>
            <span className={st.status === "idle" ? "text-ink-3" : "text-ink"}>{STEP_LABELS[s]}</span>
            <span className="leader h-[1em] flex-1" />
            <span className="tabular-nums">
              {st.status === "running" ? (
                <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-clay" />
              ) : st.status === "done" ? (
                `${((st.ms ?? 0) / 1000).toFixed(1)}s`
              ) : (
                "·"
              )}
            </span>
          </div>
        );
      })}
      {run.rounds.length > 0 && (
        <p className="mt-2 pl-4 text-[11px] text-ink-3">
          drafts: {run.rounds.map((r) => (r.length ? `${r.length} issue${r.length > 1 ? "s" : ""}` : "clean")).join(" → ")}
        </p>
      )}
      {run.usage && (
        <>
          <div className="my-3 border-t border-dashed border-rule" />
          <div className="flex justify-between">
            <span>Model calls</span>
            <span>{run.usage.calls}</span>
          </div>
          <div className="flex justify-between">
            <span>Tokens</span>
            <span>
              {run.usage.input_tokens.toLocaleString()} in · {run.usage.output_tokens.toLocaleString()} out
            </span>
          </div>
          <div className="mt-2 flex items-baseline justify-between text-ink">
            <span className="uppercase tracking-[0.2em]">Total</span>
            <span className="font-display text-xl">
              {run.usage.cost_usd === null ? "n/a" : `$${run.usage.cost_usd.toFixed(4)}`}
            </span>
          </div>
        </>
      )}
    </div>
  );
}

function Placeholder() {
  return (
    <div className="grid h-full min-h-[50vh] place-items-center rounded-[3px] border border-dashed border-rule p-10 text-center">
      <div className="max-w-[44ch] text-ink-3">
        <p className="font-display text-2xl text-ink-2">Nothing written yet.</p>
        <p className="mt-2 text-[15px]">
          Pick a photo on the left. You will see what the model reads from it, every rule it broke in the first draft,
          the repaired listing, three ads and similar products from the store.
        </p>
      </div>
    </div>
  );
}

function FactsPanel({ facts }: { facts: Facts }) {
  const rows: [string, string][] = [
    ["Category", facts.category],
    ["Type", facts.product_type],
    ["Colours", facts.colors.join(", ")],
    ["Materials", facts.materials.join(", ") || "not visible"],
    ["Style", facts.style],
  ];
  return (
    <div className="rise">
      <SectionTitle n="01" title="What the photo shows" note="structured output from the vision call" />
      <dl className="mt-3 grid gap-x-8 gap-y-1 sm:grid-cols-2">
        {rows.map(([k, v]) => (
          <div key={k} className="flex gap-3 border-b border-rule/60 py-1.5 text-[15px]">
            <dt className="w-24 shrink-0 text-ink-3">{k}</dt>
            <dd>{v}</dd>
          </div>
        ))}
      </dl>
      <ul className="mt-3 flex flex-wrap gap-1.5">
        {facts.features.map((f) => (
          <li key={f} className="rounded-full border border-rule bg-card px-2.5 py-0.5 text-[13px] text-ink-2">
            {f}
          </li>
        ))}
      </ul>
      {facts.photo_issues.length > 0 && (
        <p className="mt-3 text-sm text-clay">Photo note: {facts.photo_issues.join(", ")}</p>
      )}
    </div>
  );
}

function Checks({ rounds, passed }: { rounds: Violation[][]; passed?: boolean }) {
  return (
    <div className="rise">
      <SectionTitle n="02" title="Checks" note="limits, risky claims, invented numbers, unsupported claims" />
      <ol className="mt-3 space-y-3">
        {rounds.map((r, i) => (
          <li key={i} className="font-mono text-[12px]">
            <p className={r.length ? "text-clay" : "text-olive"}>
              {i === 0 ? "First draft" : `Rewrite ${i}`}: {r.length ? `${r.length} problem${r.length > 1 ? "s" : ""}` : "all checks pass"}
            </p>
            {r.length > 0 && (
              <ul className="mt-1 space-y-0.5 pl-4 text-ink-2">
                {r.map((v, j) => (
                  <li key={j}>
                    {v.field} · {v.rule.replaceAll("_", " ")} — {v.detail}
                  </li>
                ))}
              </ul>
            )}
          </li>
        ))}
      </ol>
      {passed === false && (
        <p className="mt-3 text-sm text-danger">
          Still breaking a rule after two rewrites. In a real shop this listing would go to a person, not live.
        </p>
      )}
    </div>
  );
}

function ListingPreview({ copy, price }: { copy: Copy; price?: number }) {
  const l = copy.listing;
  return (
    <div className="rise">
      <SectionTitle n="03" title="Marketplace listing" note="Etsy / Shopify" />
      <div className="mt-3 rounded-[3px] border border-rule bg-card p-5">
        <div className="flex items-start justify-between gap-4">
          <h3 className="font-display text-xl leading-snug">{l.title}</h3>
          <Counter text={l.title} limit={LIMITS.title} />
        </div>
        {price !== undefined && <p className="mt-2 font-mono text-lg">{money(price)}</p>}
        <div className="mt-4 space-y-3 whitespace-pre-line text-[15px] leading-relaxed text-ink-2">{l.description}</div>
        <ul className="mt-4 flex flex-wrap gap-1.5">
          {l.tags.map((t) => (
            <li
              key={t}
              className={`rounded-sm px-2 py-0.5 font-mono text-[11px] ${
                t.length > LIMITS.tag ? "bg-clay-soft text-danger" : "bg-paper-2 text-ink-2"
              }`}
            >
              {t}
            </li>
          ))}
        </ul>
        <p className="mt-2 font-mono text-[10px] text-ink-3">{l.tags.length}/13 tags, each ≤ 20 characters</p>
      </div>
    </div>
  );
}

function SearchPreview({ copy }: { copy: Copy }) {
  const l = copy.listing;
  const slug = l.title.toLowerCase().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "").slice(0, 60);
  return (
    <div className="rise">
      <SectionTitle n="04" title="Search result" note="SEO title + meta description" />
      <div className="mt-3 max-w-[600px] rounded-[3px] border border-rule bg-card p-4 font-sans">
        <p className="truncate text-[12px] text-ink-3">kestrelhome.example › products › {slug}</p>
        <p className="mt-1 text-[19px] leading-snug text-[#1a4fb3] dark:text-[#8ab4f8]">{l.seo_title}</p>
        <p className="mt-1 text-[14px] leading-snug text-ink-2">{l.seo_description}</p>
        <div className="mt-2 flex gap-4">
          <Counter text={l.seo_title} limit={LIMITS.seo_title} />
          <Counter text={l.seo_description} limit={LIMITS.seo_description} />
        </div>
      </div>
    </div>
  );
}

function Ads({ copy, image }: { copy: Copy; image: string | null }) {
  return (
    <div className="rise">
      <SectionTitle n="05" title="Meta ads" note="one angle each" />
      <div className="mt-3 grid gap-4 md:grid-cols-3">
        {copy.ads.map((ad) => (
          <article key={ad.angle} className="overflow-hidden rounded-[6px] border border-rule bg-card text-[13px]">
            <div className="flex items-center gap-2 px-3 pt-3">
              <span className="grid h-7 w-7 place-items-center rounded-full bg-ink font-display text-xs text-paper">K</span>
              <div>
                <p className="font-medium leading-none">Kestrel Home</p>
                <p className="text-[11px] text-ink-3">Sponsored · {ANGLE_LABELS[ad.angle]}</p>
              </div>
            </div>
            <p className="px-3 py-2 leading-snug">{ad.primary_text}</p>
            <div className="relative aspect-square bg-paper-2">
              {image && <Image src={image} alt="" fill unoptimized className="object-contain p-4" />}
            </div>
            <div className="flex items-center gap-2 bg-paper-2/60 px-3 py-2">
              <div className="min-w-0 flex-1">
                <p className="truncate text-[11px] uppercase text-ink-3">kestrelhome.example</p>
                <p className="font-medium leading-tight">{ad.headline}</p>
                <p className="truncate text-[12px] text-ink-3">{ad.description}</p>
              </div>
              <span className="rounded-[4px] bg-ink/10 px-2.5 py-1.5 text-[12px] font-medium">Shop now</span>
            </div>
            <div className="flex gap-3 px-3 py-2">
              <Counter text={ad.primary_text} limit={LIMITS.primary_text} />
              <Counter text={ad.headline} limit={LIMITS.headline} />
              <Counter text={ad.description} limit={LIMITS.description} />
            </div>
          </article>
        ))}
      </div>
    </div>
  );
}
