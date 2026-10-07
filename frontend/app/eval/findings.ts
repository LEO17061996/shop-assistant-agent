// Written by hand after reading the eval runs; numbers here must match data/eval-summary.json.
export const LIVE_CONFIG = { model: "gemini-3.1-flash-lite", prompt: "v3" };

export const FINDINGS: { title: string; body: string }[] = [
  {
    title: "Tool design moved the score more than prompt wording.",
    body: "Describing what each category holds in the search tool's schema took prompt v3 from 37 to 39 of 41 (90% → 95%): the model had filed “bar stools” under Chairs and told the customer there were none. The two-sentence prompt v1 scores 93%, one question behind v3. With 41 questions that gap is within noise; I would not claim v3 is better without repeated runs.",
  },
  {
    title: "Gemini 3.1 Flash-Lite runs the live demo.",
    body: "95% against 78% for Gemini 3.5 Flash-Lite, which copied the internal “[shown: …]” history note into 6 of its 10 product answers, apparently imitating the format described in the prompt, and costs about 50% more per question. Gemini 3.5 Flash was not an option: its free tier allows 20 requests a day.",
  },
  {
    title: "Two questions fail in every configuration.",
    body: "ship-04: asked about charges on delivery, the model answers from the VAT policy instead of calling quote_shipping, which is the tool that knows the basket's value in pounds. order-01: it tries lookup_order before it has the email; the tool's schema rejects the call so nothing leaks, but the rule says to ask first. Both point to tool-level fixes, not more prompt text.",
  },
  {
    title: "The LLM judge is a detector, not a score.",
    body: "It rated faithfulness 4.85–5.0 for every run, so it cannot rank configurations. But its low scores found two real problems the code checks missed: the leaked history note and centimetre sizes the model converted itself. The note leak is now a code check, applied to every saved run without calling the model again.",
  },
  {
    title: "Retrieval is not the bottleneck on this catalog.",
    body: "Hybrid search puts the target product in the top 5 for 80 of 80 queries (dense 98%, BM25 99%). The generated queries often reuse catalog words, which flatters keyword search; paraphrases, typos and Vietnamese queries would be a harder and more useful test.",
  },
];

export const STUDIO_FINDINGS: { title: string; body: string }[] = [];
