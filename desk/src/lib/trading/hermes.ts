import { createServerFn } from "@tanstack/react-start";

export type HermesProposal = {
  ok: boolean;
  model: string;
  raw: string;
  detail: string;
};

export const runHermesResearch = createServerFn({ method: "POST" }).handler(async (): Promise<HermesProposal> => {
  const model = "google-antigravity/gemini-3.7-flash";
  const packet = {
    role: "research",
    symbol: "PAXGUSDT",
    product: "SPOT",
    partition: "development",
    instruction:
      "Propose exactly one bounded paper-only genome tweak as JSON: {proposal_id, parent_version, change, rationale, evidence_refs}. No orders. No secrets. Holdout stays sealed.",
  };
  try {
    const res = await fetch("http://127.0.0.1:8642/v1/chat/completions", {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify({
        model,
        temperature: 0,
        max_tokens: 800,
        reasoning_effort: "high",
        messages: [
          {
            role: "user",
            content: JSON.stringify(packet),
          },
        ],
      }),
      signal: AbortSignal.timeout(45000),
    });
    const json = (await res.json()) as {
      model?: string;
      choices?: Array<{ message?: { content?: string } }>;
      error?: { message?: string };
    };
    if (!res.ok) {
      return {
        ok: false,
        model,
        raw: "",
        detail: json.error?.message || `Hermes HTTP ${res.status}`,
      };
    }
    const raw = json.choices?.[0]?.message?.content?.trim() ?? "";
    if (!raw) {
      return { ok: false, model: json.model || model, raw: "", detail: "Empty proposal — fail closed." };
    }
    return {
      ok: true,
      model: json.model || model,
      raw,
      detail: "Proposal received. Untrusted until GoldGuard validates schema, evidence, and holdout freeze.",
    };
  } catch (err) {
    return {
      ok: false,
      model,
      raw: "",
      detail: err instanceof Error ? err.message : "Hermes unreachable",
    };
  }
});
