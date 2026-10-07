import { API_URL, readSse, type Product } from "@/lib/api";

export type Facts = {
  category: string;
  product_type: string;
  colors: string[];
  materials: string[];
  style: string;
  features: string[];
  photo_issues: string[];
};

export type Listing = {
  title: string;
  description: string;
  tags: string[];
  seo_title: string;
  seo_description: string;
};

export type Ad = {
  angle: "benefit" | "style" | "problem-solution";
  primary_text: string;
  headline: string;
  description: string;
};

export type Copy = { listing: Listing; ads: Ad[] };
export type Violation = { field: string; rule: string; detail: string };
export type Notes = { price_usd?: number; dimensions?: string; notes?: string };

export type StudioUsage = {
  model: string;
  calls: number;
  repairs: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  latency_ms: number;
};

export type StudioEvent =
  | { event: "stage"; data: { step: "photo" | "copy" | "similar"; status: "start" | "done"; ms?: number } }
  | { event: "facts"; data: { facts: Facts; image_url: string | null } }
  | { event: "check"; data: { round: number; violations: Violation[] } }
  | { event: "copy"; data: { copy: Copy; passed: boolean } }
  | { event: "similar"; data: { products: Product[] } }
  | { event: "done"; data: StudioUsage }
  | { event: "error"; data: { message: string } };

/** Character limits shown next to each field (same numbers the backend enforces). */
export const LIMITS = {
  title: 140,
  seo_title: 70,
  seo_description: 160,
  primary_text: 125,
  headline: 40,
  description: 30,
  tag: 20,
};

export async function getSamples(): Promise<Product[]> {
  const res = await fetch(`${API_URL}/api/studio/samples`);
  if (!res.ok) throw new Error(`samples ${res.status}`);
  return res.json();
}

export async function* analyze(
  input: { file?: File; sampleId?: string; hint?: string; notes: Notes },
  signal?: AbortSignal,
): AsyncGenerator<StudioEvent> {
  const form = new FormData();
  if (input.file) form.append("image", input.file);
  if (input.sampleId) form.append("sample_id", input.sampleId);
  if (input.hint) form.append("hint", input.hint);
  if (input.notes.price_usd !== undefined) form.append("price_usd", String(input.notes.price_usd));
  if (input.notes.dimensions) form.append("dimensions", input.notes.dimensions);
  if (input.notes.notes) form.append("notes", input.notes.notes);
  const res = await fetch(`${API_URL}/api/studio/analyze`, { method: "POST", body: form, signal });
  yield* readSse<StudioEvent>(res);
}

export async function downloadShopifyCsv(copy: Copy, facts: Facts, notes: Notes, imageUrl: string | null) {
  const res = await fetch(`${API_URL}/api/studio/shopify.csv`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ copy, facts, notes, image_url: imageUrl }),
  });
  if (!res.ok) throw new Error(`csv ${res.status}`);
  const url = URL.createObjectURL(await res.blob());
  const a = document.createElement("a");
  a.href = url;
  a.download = "shopify-product.csv";
  a.click();
  URL.revokeObjectURL(url);
}
