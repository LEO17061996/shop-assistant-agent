export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8077";

export type Product = {
  id: string;
  name: string;
  price_usd: number;
  stock: number;
  ships_to: string[];
  category: string;
  image_url: string;
};

export type Step =
  | { type: "tool_call"; step: number; name: string; args: Record<string, unknown> }
  | { type: "tool_result"; name: string; status: "success" | "error"; latency_ms: number | null };

export type Usage = {
  model: string;
  steps: number;
  input_tokens: number;
  output_tokens: number;
  cost_usd: number | null;
  latency_ms: number;
};

export type Handoff = { ticket: string; reason: string; summary: string };

export type ChatEvent =
  | { event: "token"; data: { text: string } }
  | { event: "step"; data: Step }
  | { event: "products"; data: { products: Product[] } }
  | { event: "handoff"; data: Handoff }
  | { event: "done"; data: Usage }
  | { event: "error"; data: { message: string } };

export type HistoryItem = { role: "user" | "assistant"; content: string; product_ids?: string[] };

/** POST /api/chat and yield Server-Sent Events as they arrive (EventSource cannot POST). */
export async function* streamChat(history: HistoryItem[], signal?: AbortSignal): AsyncGenerator<ChatEvent> {
  const res = await fetch(`${API_URL}/api/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ messages: history }),
    signal,
  });
  yield* readSse<ChatEvent>(res);
}

/** Parse an SSE response body into {event, data} objects; HTTP errors become one "error" event. */
export async function* readSse<T>(res: Response): AsyncGenerator<T> {
  if (!res.ok || !res.body) {
    const detail = await res.json().catch(() => null);
    const message =
      res.status === 429
        ? "Too many requests. Please wait a minute."
        : (detail?.detail as string) ?? `Request failed (${res.status})`;
    yield { event: "error", data: { message: typeof message === "string" ? message : "Invalid request" } } as T;
    return;
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value.replace(/\r\n/g, "\n");
    let cut: number;
    while ((cut = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, cut);
      buffer = buffer.slice(cut + 2);
      let event = "message";
      let data = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event:")) event = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trimStart();
      }
      if (data) yield { event, data: JSON.parse(data) } as T;
    }
  }
}

export function money(usd: number) {
  return usd.toLocaleString("en-US", { style: "currency", currency: "USD" });
}
