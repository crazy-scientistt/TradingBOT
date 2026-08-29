import { useEffect, useState, type FormEvent } from "react";
import { ExternalLink, KeyRound, RefreshCw, ShieldCheck } from "lucide-react";
import {
  PROVIDER_CATALOG,
  cancelAntigravityLogin,
  collectLiveDiagnostics,
  getAntigravityStatus,
  getOpenCodexStatus,
  saveProviderKey,
  startAntigravityLogin,
  submitAntigravityCode,
  testProvider,
  type Check,
  type ProviderRow,
} from "@/lib/trading/opencodex";

type Status = Awaited<ReturnType<typeof getOpenCodexStatus>>;
type Gravity = Awaited<ReturnType<typeof getAntigravityStatus>>;

export function ProvidersView() {
  const [status, setStatus] = useState<Status | null>(null);
  const [checks, setChecks] = useState<Check[]>([]);
  const [gravity, setGravity] = useState<Gravity | null>(null);
  const [authUrl, setAuthUrl] = useState<string | null>(null);
  const [instructions, setInstructions] = useState<string | null>(null);
  const [redirect, setRedirect] = useState("");
  const [loading, setLoading] = useState(true);
  const [name, setName] = useState<(typeof PROVIDER_CATALOG)[number]["id"]>("google");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [ok, setOk] = useState<boolean | null>(null);

  async function refresh() {
    setLoading(true);
    try {
      const [st, diag, ag] = await Promise.all([
        getOpenCodexStatus(),
        collectLiveDiagnostics(),
        getAntigravityStatus(),
      ]);
      setStatus(st);
      setChecks(diag.checks);
      setGravity(ag);
    } catch (err) {
      setMessage(err instanceof Error ? err.message : "Diagnostics failed");
      setOk(false);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  useEffect(() => {
    if (gravity?.loggedIn || !authUrl) return;
    const id = window.setInterval(() => {
      void getAntigravityStatus().then((ag) => {
        setGravity(ag);
        if (ag.loggedIn) {
          setAuthUrl(null);
          setOk(true);
          setMessage(
            `Antigravity connected${ag.email ? ` · ${ag.email}` : ""}. Hermes model google-antigravity/gemini-3.7-flash.`,
          );
          void refresh();
        }
      });
    }, 2500);
    return () => window.clearInterval(id);
  }, [authUrl, gravity?.loggedIn]);

  async function onStartAntigravity() {
    setBusy(true);
    setMessage(null);
    try {
      const res = await startAntigravityLogin();
      setOk(res.ok);
      setMessage(res.detail);
      if (res.ok) {
        setAuthUrl(res.url);
        setInstructions(res.instructions);
        if (res.url) window.open(res.url, "_blank", "noopener,noreferrer");
      }
    } catch (err) {
      setOk(false);
      setMessage(err instanceof Error ? err.message : "Login start failed");
    } finally {
      setBusy(false);
    }
  }

  async function onCancelAntigravity() {
    setBusy(true);
    try {
      await cancelAntigravityLogin();
      setAuthUrl(null);
      setInstructions(null);
      setMessage("Antigravity login cancelled.");
      setOk(null);
    } finally {
      setBusy(false);
    }
  }

  async function onSubmitRedirect(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const res = await submitAntigravityCode({ data: { input: redirect } });
      setOk(res.ok);
      setMessage(res.detail);
      if (res.ok) {
        setRedirect("");
        setAuthUrl(null);
        await refresh();
      }
    } catch (err) {
      setOk(false);
      setMessage(err instanceof Error ? err.message : "Redirect submit failed");
    } finally {
      setBusy(false);
    }
  }

  async function onSave(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setMessage(null);
    try {
      const res = await saveProviderKey({ data: { name, apiKey, setDefault: name === "google" } });
      setOk(res.ok);
      setMessage(res.detail);
      if (res.ok) {
        setApiKey("");
        await refresh();
      }
    } catch (err) {
      setOk(false);
      setMessage(err instanceof Error ? err.message : "Save failed");
    } finally {
      setBusy(false);
    }
  }

  async function onTest(providerName: string) {
    setBusy(true);
    try {
      const res = await testProvider({ data: { name: providerName } });
      setOk(res.ok);
      setMessage(res.latencyMs != null ? `${res.detail} · ${res.latencyMs}ms` : res.detail);
    } catch (err) {
      setOk(false);
      setMessage(err instanceof Error ? err.message : "Test failed");
    } finally {
      setBusy(false);
    }
  }

  const selected = PROVIDER_CATALOG.find((p) => p.id === name);
  const connected = gravity?.loggedIn === true;

  return (
    <div className="grid min-h-0 flex-1 lg:grid-cols-[minmax(0,1fr)_22rem]">
      <section className="flex min-h-0 flex-col overflow-y-auto border-b border-border lg:border-r lg:border-b-0">
        <header className="flex items-center justify-between gap-3 border-b border-border px-3 py-3 md:px-5 md:py-4">
          <div>
            <div className="flex items-center gap-2">
              <span className={status?.up ? "live-dot" : "inline-block h-1.5 w-1.5 rounded-full bg-muted"} />
              <h2 className="text-sm font-semibold tracking-tight">OpenCodex</h2>
              <span
                className={`rounded-xs px-1.5 py-0.5 text-2xs font-semibold tracking-wider uppercase ${
                  status?.up ? "bg-up-dim text-up" : "bg-bg-subtle text-muted"
                }`}
              >
                {status?.up ? "Live" : "Waiting"}
              </span>
            </div>
            <p className="mt-1 text-xs text-muted">
              Hermes target: google-antigravity/gemini-3.7-flash. Complete Google login below.
            </p>
          </div>
          <button
            onClick={() => void refresh()}
            className="inline-flex h-9 items-center gap-1.5 rounded-sm border border-border px-3 text-xs text-muted transition-colors duration-150 hover:bg-bg-hover hover:text-fg"
          >
            <RefreshCw size={13} /> Refresh
          </button>
        </header>

        <div className="border-b border-border px-3 py-4 md:px-5 md:py-5">
          <div className="flex items-center justify-between gap-3">
            <div>
              <div className="text-sm font-semibold">Google Antigravity</div>
              <p className="mt-1 text-xs leading-relaxed text-muted">
                OAuth, not an API key. This is the Hermes route. After Google, if the page
                fails to load, paste the full address bar URL below.
              </p>
            </div>
            <span
              className={`shrink-0 rounded-xs px-1.5 py-0.5 text-2xs font-semibold tracking-wider uppercase ${
                connected ? "bg-up-dim text-up" : "bg-bg-subtle text-muted"
              }`}
            >
              {connected ? "Connected" : "Waiting"}
            </span>
          </div>
          {connected ? (
            <p className="mt-3 text-xs text-up">
              Logged in{gravity?.email ? ` · ${gravity.email}` : ""}. Hermes uses gemini-3.7-flash.
            </p>
          ) : (
            <div className="mt-4 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => void onStartAntigravity()}
                disabled={busy || !status?.up}
            className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-sm bg-accent px-4 text-sm font-semibold text-accent-fg transition-colors duration-150 hover:bg-accent-hover disabled:opacity-40 sm:w-auto"
              >
                Log in with Google
              </button>
              {authUrl && (
                <>
                  <a
                    href={authUrl}
                    target="_blank"
                    rel="noreferrer"
                    className="inline-flex h-11 items-center gap-2 rounded-sm border border-border px-4 text-sm font-medium text-fg hover:bg-bg-hover"
                  >
                    <ExternalLink size={14} /> Open login
                  </a>
                  <button
                    type="button"
                    onClick={() => void onCancelAntigravity()}
                    disabled={busy}
                    className="inline-flex h-11 items-center rounded-sm border border-border px-4 text-sm text-muted hover:text-fg"
                  >
                    Cancel
                  </button>
                </>
              )}
            </div>
          )}
          {instructions && !connected && <p className="mt-3 text-xs text-muted">{instructions}</p>}
          {!connected && authUrl && (
            <form onSubmit={onSubmitRedirect} className="mt-4 space-y-2">
              <label className="block text-xs">
                <span className="font-medium text-muted">Paste redirect URL or code</span>
                <input
                  value={redirect}
                  onChange={(e) => setRedirect(e.target.value)}
                  placeholder="http://127.0.0.1:…/?code=…  or the code itself"
                  className="mt-1.5 h-11 w-full rounded-sm border border-border bg-bg-subtle px-3 font-mono text-xs text-fg outline-none transition-colors duration-150 placeholder:text-subtle focus:border-accent"
                />
              </label>
              <button
                type="submit"
                disabled={busy || redirect.trim().length < 4}
                className="inline-flex h-10 items-center rounded-sm border border-border px-4 text-xs font-semibold text-fg disabled:opacity-40"
              >
                Finish login
              </button>
            </form>
          )}
        </div>

        <form onSubmit={onSave} className="max-w-xl space-y-4 px-3 py-4 md:px-5 md:py-5">
          <div>
            <div className="text-xs font-medium">Other API keys (optional)</div>
            <p className="mt-1 text-xs leading-relaxed text-muted">
              Gemini AI Studio is already connected as fallback. Antigravity is the Hermes default
              once login completes.
            </p>
          </div>
          <label className="block text-xs">
            <span className="font-medium text-muted">Provider</span>
            <select
              value={name}
              onChange={(e) => setName(e.target.value as typeof name)}
              className="mt-1.5 h-11 w-full rounded-sm border border-border bg-bg-subtle px-3 text-sm text-fg outline-none transition-colors duration-150 focus:border-accent"
            >
              {PROVIDER_CATALOG.map((p) => (
                <option key={p.id} value={p.id}>
                  {p.label}
                </option>
              ))}
            </select>
          </label>
          <p className="text-xs text-subtle">{selected?.hint}</p>
          <label className="block text-xs">
            <span className="font-medium text-muted">API key</span>
            <input
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="Optional fallback key"
              className="mt-1.5 h-11 w-full rounded-sm border border-border bg-bg-subtle px-3 font-mono text-sm text-fg outline-none transition-colors duration-150 placeholder:text-subtle focus:border-accent"
            />
          </label>
          <button
            type="submit"
            disabled={busy || apiKey.trim().length < 8 || !status?.up}
            className="inline-flex h-11 w-full items-center justify-center gap-2 rounded-sm border border-border text-sm font-semibold text-fg transition-colors duration-150 hover:bg-bg-hover disabled:opacity-40"
          >
            <KeyRound size={14} />
            {busy ? "Saving…" : "Save fallback key"}
          </button>
          {message && <p className={`text-xs ${ok ? "text-up" : "text-down"}`}>{message}</p>}
        </form>

        <div className="border-t border-border px-5 py-4">
          <div className="text-xs font-medium">Saved providers</div>
          {loading ? (
            <p className="mt-2 text-xs text-muted">Reading gateway…</p>
          ) : !status?.providers.length ? (
            <p className="mt-2 text-xs text-muted">None yet.</p>
          ) : (
            <ul className="mt-2 divide-y divide-border">
              {status.providers.map((p: ProviderRow) => (
                <li key={p.name} className="flex items-center justify-between gap-3 py-2.5 text-xs">
                  <div>
                    <div className="font-medium">{p.name}</div>
                    <div className="text-2xs text-muted">
                      {p.name === "google-antigravity"
                        ? connected
                          ? "OAuth connected"
                          : "OAuth waiting"
                        : p.hasApiKey
                          ? "Key present"
                          : "No key"}
                      {p.defaultModel ? ` · ${p.defaultModel}` : ""}
                    </div>
                  </div>
                  <button
                    onClick={() => void onTest(p.name)}
                    disabled={busy || (p.name !== "google-antigravity" && !p.hasApiKey) || (p.name === "google-antigravity" && !connected)}
                    className="h-9 rounded-sm border border-border px-3 text-2xs font-semibold text-muted transition-colors duration-150 hover:text-fg disabled:opacity-40"
                  >
                    Test
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        {status && status.models.length > 0 && (
          <div className="border-t border-border px-5 py-4">
            <div className="text-xs font-medium">Live catalog ({status.modelCount})</div>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {status.models.map((id) => (
                <span key={id} className="rounded-xs bg-bg-subtle px-2 py-1 font-mono text-2xs text-muted">
                  {id}
                </span>
              ))}
            </div>
          </div>
        )}
      </section>

      <aside className="flex min-h-0 flex-col bg-bg-elevated">
        <header className="flex items-center gap-2 border-b border-border px-5 py-4">
          <ShieldCheck size={15} className="text-accent" />
          <div className="text-sm font-medium">Live diagnostics</div>
        </header>
        <ul className="divide-y divide-border overflow-y-auto">
          {checks.map((c) => (
            <li key={c.id} className="flex items-start justify-between gap-4 px-5 py-3">
              <div>
                <div className="text-sm">{c.label}</div>
                <div className="text-xs text-muted">{c.detail}</div>
              </div>
              <span
                className={`shrink-0 text-2xs font-semibold tracking-wider uppercase ${
                  c.ok ? "text-up" : "text-down"
                }`}
              >
                {c.ok ? "PASS" : "HOLD"}
              </span>
            </li>
          ))}
        </ul>
        <p className="mt-auto border-t border-border px-5 py-4 text-xs leading-relaxed text-muted">
          After Antigravity shows Connected, reply in chat. Live trading stays disarmed.
        </p>
      </aside>
    </div>
  );
}
