import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";

export type Check = {
  id: string;
  label: string;
  ok: boolean;
  detail: string;
};

export type ProviderRow = {
  name: string;
  adapter?: string;
  hasApiKey: boolean;
  defaultModel?: string;
  disabled?: boolean;
};

export const PROVIDER_CATALOG = [
  {
    id: "google" as const,
    label: "Google Gemini (AI Studio)",
    hint: "Gemini API key. Hermes can use gemini-3.7-flash on this path right now.",
    defaultModel: "gemini-3.7-flash",
  },
  {
    id: "anthropic" as const,
    label: "Anthropic",
    hint: "Claude API key from the Anthropic console.",
    defaultModel: "claude-sonnet-4-5",
  },
  {
    id: "openai" as const,
    label: "OpenAI",
    hint: "Platform API key. Separate from a ChatGPT login.",
    defaultModel: "gpt-4.1",
  },
  {
    id: "openrouter" as const,
    label: "OpenRouter",
    hint: "Routes many upstream models through one key.",
    defaultModel: "google/gemini-2.5-flash",
  },
  {
    id: "xai" as const,
    label: "xAI",
    hint: "xAI API key from the xAI console.",
    defaultModel: "grok-3",
  },
];

export const getOpenCodexStatus = createServerFn({ method: "GET" }).handler(async () => {
  const { getStatus } = await import("./opencodex.server");
  return getStatus();
});

export const startAntigravityLogin = createServerFn({ method: "POST" }).handler(async () => {
  const { startAntigravityLogin: start } = await import("./opencodex.server");
  return start();
});

export const getAntigravityStatus = createServerFn({ method: "GET" }).handler(async () => {
  const { antigravityStatus } = await import("./opencodex.server");
  return antigravityStatus();
});

export const cancelAntigravityLogin = createServerFn({ method: "POST" }).handler(async () => {
  const { cancelAntigravityLogin: cancel } = await import("./opencodex.server");
  return cancel();
});

const CodeInput = z.object({ input: z.string().min(4).max(4096) });

export const submitAntigravityCode = createServerFn({ method: "POST" })
  .validator(CodeInput)
  .handler(async ({ data }) => {
    const { submitAntigravityCode: submit } = await import("./opencodex.server");
    return submit(data.input);
  });

const SaveInput = z.object({
  name: z.enum(["google", "anthropic", "openai", "openrouter", "xai"]),
  apiKey: z.string().min(8).max(512),
  setDefault: z.boolean().optional(),
});

export const saveProviderKey = createServerFn({ method: "POST" })
  .validator(SaveInput)
  .handler(async ({ data }) => {
    const { saveKey } = await import("./opencodex.server");
    return saveKey(data);
  });

export const testProvider = createServerFn({ method: "POST" })
  .validator(z.object({ name: z.string().min(2).max(40) }))
  .handler(async ({ data }) => {
    const { testKey } = await import("./opencodex.server");
    return testKey(data.name);
  });

export const collectLiveDiagnostics = createServerFn({ method: "GET" }).handler(async () => {
  const { diagnostics } = await import("./opencodex.server");
  return diagnostics();
});
