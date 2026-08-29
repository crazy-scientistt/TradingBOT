import { existsSync, readFileSync } from "node:fs";

const OCX_URL = "http://127.0.0.1:10100";

export const SEEDS = {
  google: {
    adapter: "google",
    baseUrl: "https://generativelanguage.googleapis.com",
    googleMode: "ai-studio" as const,
    liveModels: true,
    defaultModel: "gemini-3.7-flash",
    label: "Google Gemini",
  },
  anthropic: {
    adapter: "anthropic",
    baseUrl: "https://api.anthropic.com",
    liveModels: true,
    defaultModel: "claude-sonnet-4-5",
    label: "Anthropic",
  },
  openai: {
    adapter: "openai-chat",
    baseUrl: "https://api.openai.com/v1",
    liveModels: true,
    defaultModel: "gpt-4.1",
    label: "OpenAI",
  },
  openrouter: {
    adapter: "openai-chat",
    baseUrl: "https://openrouter.ai/api/v1",
    liveModels: true,
    defaultModel: "google/gemini-2.5-flash",
    label: "OpenRouter",
  },
  xai: {
    adapter: "openai-chat",
    baseUrl: "https://api.x.ai/v1",
    liveModels: true,
    defaultModel: "grok-3",
    label: "xAI",
  },
} as const;

export type ProviderName = keyof typeof SEEDS;

function readAdminToken(): string {
  const candidates = [
    "/workspace/.opencodex-runtime/admin-api-token",
    process.env.OPENCODEX_ADMIN_AUTH_TOKEN,
  ].filter((p): p is string => Boolean(p));
  for (const path of candidates) {
    if (path.startsWith("/")) {
      try {
        if (!existsSync(path)) continue;
        const value = readFileSync(path, "utf8").trim();
        if (value) return value;
      } catch {
        /* try next */
      }
    } else if (path.trim()) {
      return path.trim();
    }
  }
  return readDataToken();
}

function readDataToken(): string {
  const candidates = [
    "/workspace/.opencodex-runtime/token",
    process.env.OPENCODEX_TOKEN_FILE,
    process.env.OPENCODEX_API_AUTH_TOKEN,
  ].filter((p): p is string => Boolean(p));
  for (const path of candidates) {
    if (path.startsWith("/")) {
      try {
        if (!existsSync(path)) continue;
        const value = readFileSync(path, "utf8").trim();
        if (value) return value;
      } catch {
        /* try next */
      }
    } else if (path.trim()) {
      return path.trim();
    }
  }
  return "";
}

function readToken(): string {
  return readAdminToken();
}

function redact(value: string): string {
  const t = value.trim();
  if (t.length < 8) return t ? "set" : "absent";
  return `${t.slice(0, 3)}…${t.slice(-3)}`;
}

async function ocxFetch(
  path: string,
  init: RequestInit = {},
  timeoutMs = 8000,
  plane: "admin" | "data" = "admin",
): Promise<{ ok: boolean; status: number; json: unknown; text: string }> {
  const token = plane === "data" ? readDataToken() || readAdminToken() : readAdminToken();
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), timeoutMs);
  try {
    const headers = new Headers(init.headers);
    headers.set("accept", "application/json");
    if (token) {
      headers.set("x-opencodex-api-key", token);
      headers.set("authorization", `Bearer ${token}`);
    }
    if (init.body && !headers.has("content-type")) {
      headers.set("content-type", "application/json");
    }
    const res = await fetch(`${OCX_URL}${path}`, {
      ...init,
      headers,
      signal: ctrl.signal,
    });
    const text = await res.text();
    let json: unknown = null;
    try {
      json = text ? JSON.parse(text) : null;
    } catch {
      json = null;
    }
    return { ok: res.ok, status: res.status, json, text };
  } catch (err) {
    const message = err instanceof Error ? err.message : "unreachable";
    return { ok: false, status: 0, json: { error: message }, text: message };
  } finally {
    clearTimeout(timer);
  }
}

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

export async function getStatus() {
  const tokenPresent = Boolean(readAdminToken() || readDataToken());
  const health = await ocxFetch("/healthz", { method: "GET" }, 3000);
  const healthJson = (health.json ?? {}) as { status?: string; version?: string };
  const providers = health.ok ? await ocxFetch("/api/providers", { method: "GET" }, 4000) : null;
  const models = health.ok ? await ocxFetch("/v1/models", { method: "GET" }, 4000, "data") : null;
  const providerRows: ProviderRow[] = Array.isArray(providers?.json)
    ? (providers.json as Array<Record<string, unknown>>).map((row) => ({
        name: String(row.name ?? ""),
        adapter: typeof row.adapter === "string" ? row.adapter : undefined,
        hasApiKey: row.hasApiKey === true,
        defaultModel: typeof row.defaultModel === "string" ? row.defaultModel : undefined,
        disabled: row.disabled === true,
      }))
    : [];
  const modelIds: string[] = [];
  const modelPayload = models?.json as { data?: Array<{ id?: string }> } | null;
  if (Array.isArray(modelPayload?.data)) {
    for (const m of modelPayload.data) {
      if (typeof m.id === "string") modelIds.push(m.id);
    }
  }
  return {
    up: health.ok && healthJson.status === "ok",
    version: healthJson.version ?? null,
    tokenPresent,
    providers: providerRows,
    models: modelIds.slice(0, 40),
    modelCount: modelIds.length,
    antigravity: await readAntigravity(),
    hermesModel: "google-antigravity/gemini-3.7-flash",
    error: health.ok ? null : "OpenCodex is not answering health yet.",
  };
}

export type AntigravityStatus = {
  loggedIn: boolean;
  email?: string;
  done: boolean;
  error?: string;
  configured: boolean;
};

async function readAntigravity(): Promise<AntigravityStatus> {
  const status = await ocxFetch("/api/oauth/status?provider=google-antigravity", { method: "GET" }, 4000);
  const body = (status.json ?? {}) as {
    loggedIn?: boolean;
    email?: string;
    done?: boolean;
    error?: string;
  };
  return {
    loggedIn: status.ok && body.loggedIn === true,
    email: typeof body.email === "string" ? body.email : undefined,
    done: body.done === true,
    error: typeof body.error === "string" ? body.error : status.ok ? undefined : "OAuth status unreachable",
    configured: status.ok,
  };
}

export async function startAntigravityLogin() {
  await ocxFetch(
    "/api/providers",
    {
      method: "POST",
      body: JSON.stringify({
        name: "google-antigravity",
        setDefault: false,
        provider: {
          adapter: "google",
          baseUrl: "https://daily-cloudcode-pa.googleapis.com",
          liveModels: true,
          defaultModel: "gemini-3.7-flash",
          googleMode: "cloud-code-assist",
        },
      }),
    },
    8000,
  );
  const res = await ocxFetch(
    "/api/oauth/login",
    {
      method: "POST",
      body: JSON.stringify({
        provider: "google-antigravity",
        openBrowser: false,
      }),
    },
    20000,
  );
  const body = (res.json ?? {}) as {
    url?: string;
    instructions?: string;
    deviceCode?: string;
    error?: string;
  };
  if (!res.ok) {
    return {
      ok: false as const,
      detail: body.error || `OpenCodex refused Antigravity login (${res.status || "offline"}).`,
    };
  }
  return {
    ok: true as const,
    url: body.url ?? null,
    instructions: body.instructions ?? null,
    deviceCode: body.deviceCode ?? null,
    detail: "Google login URL ready. Complete it, then paste the redirect if the page does not close itself.",
  };
}

export async function antigravityStatus() {
  return readAntigravity();
}

export async function cancelAntigravityLogin() {
  const res = await ocxFetch(
    "/api/oauth/login/cancel",
    {
      method: "POST",
      body: JSON.stringify({ provider: "google-antigravity" }),
    },
    8000,
  );
  return { ok: res.ok };
}

export async function submitAntigravityCode(input: string) {
  const res = await ocxFetch(
    "/api/oauth/login/code",
    {
      method: "POST",
      body: JSON.stringify({ provider: "google-antigravity", input: input.trim() }),
    },
    12000,
  );
  const body = (res.json ?? {}) as { ok?: boolean; error?: string };
  if (!res.ok || body.ok === false) {
    return {
      ok: false as const,
      detail: body.error || `OpenCodex rejected the redirect (${res.status || "offline"}).`,
    };
  }
  await promoteAntigravity();
  const status = await readAntigravity();
  return {
    ok: true as const,
    detail: status.loggedIn
      ? `Antigravity connected${status.email ? ` · ${status.email}` : ""}. Hermes model google-antigravity/gemini-3.7-flash.`
      : "Code accepted. Waiting for OpenCodex to finish the login.",
    status,
  };
}

async function promoteAntigravity() {
  await ocxFetch(
    "/api/providers?name=google-antigravity",
    {
      method: "PATCH",
      body: JSON.stringify({ setDefault: true }),
    },
    8000,
  );
}

export async function promoteAntigravityDefault() {
  const status = await readAntigravity();
  if (!status.loggedIn) {
    return { ok: false as const, detail: "Antigravity is not logged in yet." };
  }
  const res = await ocxFetch(
    "/api/providers?name=google-antigravity",
    {
      method: "PATCH",
      body: JSON.stringify({ setDefault: true }),
    },
    8000,
  );
  if (!res.ok) {
    const err = (res.json ?? {}) as { error?: string };
    return { ok: false as const, detail: err.error || "Could not set Antigravity as default." };
  }
  return {
    ok: true as const,
    detail: "Default route is google-antigravity/gemini-3.7-flash.",
  };
}

export async function saveKey(data: { name: ProviderName; apiKey: string; setDefault?: boolean }) {
  const seed = SEEDS[data.name];
  const body = {
    name: data.name,
    setDefault: data.setDefault ?? data.name === "google",
    provider: {
      adapter: seed.adapter,
      baseUrl: seed.baseUrl,
      apiKey: data.apiKey.trim(),
      liveModels: seed.liveModels,
      defaultModel: seed.defaultModel,
      ...("googleMode" in seed ? { googleMode: seed.googleMode } : {}),
    },
  };
  const res = await ocxFetch("/api/providers", {
    method: "POST",
    body: JSON.stringify(body),
  }, 12000);
  if (!res.ok) {
    const err = (res.json ?? {}) as { error?: string };
    return {
      ok: false as const,
      detail: err.error || `OpenCodex refused the key (${res.status || "offline"}).`,
    };
  }
  return {
    ok: true as const,
    detail: `${seed.label} key stored in OpenCodex. GoldGuard never keeps the secret.`,
    fingerprint: redact(data.apiKey),
  };
}

export async function testKey(name: string) {
  const res = await ocxFetch(
    `/api/providers/test?name=${encodeURIComponent(name)}`,
    { method: "POST" },
    15000,
  );
  const payload = (res.json ?? {}) as {
    ok?: boolean;
    error?: string;
    message?: string;
    models?: number;
    latencyMs?: number;
  };
  return {
    ok: res.ok && payload.ok !== false,
    detail: payload.message || payload.error || (res.ok ? "Connected." : "Test failed."),
    models: payload.models ?? null,
    latencyMs: payload.latencyMs ?? null,
  };
}

export async function diagnostics() {
  const checks: Check[] = [];
  const tokenPresent = Boolean(readAdminToken() || readDataToken());

  const health = await ocxFetch("/healthz", { method: "GET" }, 3000);
  const healthJson = (health.json ?? {}) as { status?: string; version?: string };
  checks.push({
    id: "opencodex",
    label: "OpenCodex gateway",
    ok: health.ok && healthJson.status === "ok",
    detail: health.ok
      ? `Answering · ${healthJson.version ?? "version unknown"}`
      : "Not answering. Credentials cannot be stored until this is up.",
  });

  checks.push({
    id: "token",
    label: "Gateway token",
    ok: tokenPresent,
    detail: tokenPresent
      ? "Present on the server. Never shown in the desk."
      : "Missing. OpenCodex will refuse management calls.",
  });

  if (health.ok) {
    const providers = await ocxFetch("/api/providers", { method: "GET" }, 4000);
    const rows = Array.isArray(providers.json) ? (providers.json as Array<{ hasApiKey?: boolean }>) : [];
    const keyed = rows.filter((r) => r.hasApiKey).length;
    const antigravity = await readAntigravity();
    checks.push({
      id: "providers",
      label: "AI provider keys",
      ok: keyed > 0 || antigravity.loggedIn,
      detail: antigravity.loggedIn
        ? `Antigravity logged in${antigravity.email ? ` · ${antigravity.email}` : ""}`
        : providers.ok
          ? keyed > 0
            ? `${keyed} provider${keyed === 1 ? "" : "s"} with a key · Antigravity waiting for Google login`
            : "Gateway is up. Antigravity waiting for Google login."
          : `Management API ${providers.status || "offline"}`,
    });
    checks.push({
      id: "antigravity",
      label: "Google Antigravity",
      ok: antigravity.loggedIn,
      detail: antigravity.loggedIn
        ? `Connected · Hermes uses google-antigravity/gemini-3.7-flash`
        : antigravity.error || "Not logged in. Open Providers and complete Google OAuth.",
    });

    const models = await ocxFetch("/v1/models", { method: "GET" }, 4000, "data");
    const data = (models.json as { data?: unknown[] } | null)?.data;
    const count = Array.isArray(data) ? data.length : 0;
    checks.push({
      id: "models",
      label: "Model catalog",
      ok: models.ok && count > 0,
      detail: models.ok
        ? count > 0
          ? `${count} model${count === 1 ? "" : "s"} listed`
          : "Empty until a provider key is accepted"
        : "Catalog probe failed",
    });
  }

  try {
    const binance = await fetch("https://api.binance.com/api/v3/ticker/price?symbol=PAXGUSDT", {
      headers: { Accept: "application/json" },
      signal: AbortSignal.timeout(4000),
    });
    checks.push({
      id: "binance",
      label: "Binance public PAXGUSDT",
      ok: binance.ok,
      detail: binance.ok ? "Public ticker reachable. No API key used." : `HTTP ${binance.status}`,
    });
  } catch {
    checks.push({
      id: "binance",
      label: "Binance public PAXGUSDT",
      ok: false,
      detail: "Unreachable. Desk will use the labelled synthetic path.",
    });
  }

  try {
    const hermesUrl = process.env.GOLDGUARD_HERMES_BASE_URL ?? "http://127.0.0.1:8642";
    const hermes = await fetch(`${hermesUrl.replace(/\/$/, "")}/health`, {
      signal: AbortSignal.timeout(2000),
    });
    let detail = `HTTP ${hermes.status}. Paper desk still runs.`;
    if (hermes.ok) {
      try {
        const body = (await hermes.json()) as { model?: string; service?: string };
        const model = typeof body.model === "string" ? body.model : "google-antigravity/gemini-3.7-flash";
        detail = `Answering · ${body.service ?? "hermes"} · ${model}`;
      } catch {
        detail = "Health endpoint answering.";
      }
    }
    checks.push({
      id: "hermes",
      label: "Hermes researcher",
      ok: hermes.ok,
      detail,
    });
  } catch {
    checks.push({
      id: "hermes",
      label: "Hermes researcher",
      ok: false,
      detail: "Not running in this preview. Research degrades; paper trading does not.",
    });
  }

  checks.push({
    id: "paper",
    label: "Paper desk",
    ok: true,
    detail: "Armed. Live execution stays disarmed.",
  });
  checks.push({
    id: "live",
    label: "Live arm",
    ok: true,
    detail: "Disarmed. Qualification is fail-closed. No profitability claim.",
  });

  return {
    at: new Date().toISOString(),
    ready: checks
      .filter((c) => c.id !== "hermes" && c.id !== "live" && c.id !== "providers" && c.id !== "models")
      .every((c) => c.ok),
    checks,
  };
}
