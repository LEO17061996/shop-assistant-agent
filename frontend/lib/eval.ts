export type RunSummary = {
  run_id: string;
  created_at: string;
  provider: string;
  model: string;
  prompt: string;
  judge: string | null;
  n_cases: number;
  errors: number;
  pass_rate: number;
  by_check: Record<string, { pass_rate: number; n: number }>;
  by_category: Record<string, { pass_rate: number; n: number }>;
  latency_ms_median: number | null;
  latency_ms_p90: number | null;
  steps_avg: number | null;
  tokens_in_avg: number | null;
  tokens_out_avg: number | null;
  cost_usd_avg: number | null;
  judge_faithfulness_avg: number | null;
  judge_helpfulness_avg: number | null;
};

export type CaseResult = {
  id: string;
  category: string;
  message: string;
  passed: boolean;
  error?: string;
  checks: Record<string, { pass: boolean; detail: string }>;
  answer: string;
  tool_calls: { name: string; args: Record<string, unknown> }[];
  steps: number;
  latency_ms: number;
  cost_usd: number | null;
  judge?: { faithfulness?: number; helpfulness?: number; reason?: string; error?: string };
};

export const CHECK_LABELS: Record<string, string> = {
  tools_called: "Called the right tool",
  tools_not_called: "Held back a tool it shouldn't use",
  search_filters: "Search filters (price, country, category)",
  policy_retrieval: "Retrieved the right policy section",
  answer_includes: "Answer has the required fact",
  answer_includes_any: "Answer states the expected outcome",
  answer_excludes: "Answer leaks nothing it shouldn't",
  asks_question: "Asks before searching a vague request",
  handoff: "Hands off to a person when it should",
  grounded_money: "Every price traceable to a tool",
};

export const MODEL_LABELS: Record<string, string> = {
  "gemini-3.1-flash-lite": "Gemini 3.1 Flash-Lite",
  "gemini-3.5-flash-lite": "Gemini 3.5 Flash-Lite",
  "claude-haiku-4-5-20251001": "Claude Haiku 4.5",
  "gemini-3.5-flash": "Gemini 3.5 Flash",
  "gemini-2.5-flash": "Gemini 2.5 Flash",
};

export const pct = (x: number | null | undefined) => (x === null || x === undefined ? "–" : `${Math.round(x * 100)}%`);
