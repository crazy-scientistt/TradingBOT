import { useEffect, useState, type ReactNode } from "react";
import {
  Activity,
  BookOpen,
  Briefcase,
  Gauge,
  KeyRound,
  LayoutDashboard,
  Newspaper,
  Pause,
  Play,
  RotateCcw,
  Settings,
  ShieldAlert,
  ShieldCheck,
  Square,
  TrendingUp,
  X,
} from "lucide-react";
import { useShallow } from "zustand/react/shallow";
import { ChartDock } from "./ChartDock";
import { ProvidersView } from "./ProvidersView";
import { fmt, riskGates, signed, unrealized } from "@/lib/trading/engine";
import { runHermesResearch } from "@/lib/trading/hermes";
import { collectLiveDiagnostics } from "@/lib/trading/opencodex";
import { useDesk } from "@/lib/trading/store";
import type { Candle, EngineState, Tab } from "@/lib/trading/types";
import { UNIVERSE } from "@/lib/trading/types";

const NAV: { id: Tab; label: string; icon: typeof LayoutDashboard }[] = [
  { id: "home", label: "Overview", icon: LayoutDashboard },
  { id: "providers", label: "Providers", icon: KeyRound },
  { id: "market", label: "Market", icon: TrendingUp },
  { id: "trades", label: "Trades", icon: Briefcase },
  { id: "agent", label: "Agent", icon: Activity },
  { id: "news", label: "Evidence", icon: Newspaper },
  { id: "learning", label: "Hermes", icon: BookOpen },
  { id: "cockpit", label: "Cockpit", icon: ShieldAlert },
  { id: "qualify", label: "Qualify", icon: ShieldCheck },
];

export function Cockpit() {
  const boot = useDesk((s) => s.boot);
  useEffect(() => {
    void boot();
  }, [boot]);

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-bg text-fg">
      <TopBar />
      <MobileTicker />
      <TabStrip />
      <main className="flex min-h-0 flex-1 flex-col overflow-hidden pb-[calc(3.75rem+env(safe-area-inset-bottom))] md:pb-0">
        <Body />
      </main>
      <SettingsSheet />
      <MobileNav />
    </div>
  );
}

function Logo() {
  return (
    <div className="flex h-7 w-7 items-center justify-center rounded-sm bg-accent text-accent-fg">
      <svg width="14" height="14" viewBox="0 0 32 32" fill="none" aria-hidden>
        <path
          d="M6 22 L13 10 L17 18 L21 12 L26 22"
          stroke="currentColor"
          strokeWidth="2.6"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>
    </div>
  );
}

function TopBar() {
  const running = useDesk((s) => s.running);
  const paused = useDesk((s) => s.paused);
  const halted = useDesk((s) => s.halted);
  const start = useDesk((s) => s.start);
  const pause = useDesk((s) => s.pause);
  const resume = useDesk((s) => s.resume);
  const halt = useDesk((s) => s.halt);
  const setSettingsOpen = useDesk((s) => s.setSettingsOpen);
  const setTab = useDesk((s) => s.setTab);

  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b border-border bg-bg px-2 pt-[env(safe-area-inset-top)] md:h-11 md:gap-3 md:px-4">
      <div className="flex min-w-0 items-center gap-2">
        <Logo />
        <div className="min-w-0">
          <div className="text-sm font-semibold tracking-tight">GoldGuard</div>
        </div>
        <span className="rounded-xs bg-accent-dim px-1.5 py-0.5 text-2xs font-semibold tracking-widest text-accent uppercase">
          Paper
        </span>
      </div>
      <TickerInline />
      <div className="ml-auto flex items-center gap-1">
        <button
          onClick={() => setTab("providers")}
          className="hidden h-9 items-center gap-1.5 rounded-sm border border-border px-2.5 text-2xs font-medium text-muted transition-colors duration-150 hover:bg-bg-hover hover:text-fg sm:inline-flex"
        >
          <KeyRound size={13} />
          AI key
        </button>
        {halted ? (
          <span className="rounded-xs bg-down-dim px-2 py-1 text-2xs font-semibold tracking-wider text-down uppercase">
            Halted
          </span>
        ) : running && !paused ? (
          <button
            onClick={pause}
            className="inline-flex h-9 items-center gap-1.5 rounded-sm border border-border bg-bg-subtle px-3 text-xs font-medium text-fg transition-colors duration-150 hover:bg-bg-hover"
          >
            <Pause size={13} /> <span className="hidden xs:inline sm:inline">Pause</span>
          </button>
        ) : (
          <button
            onClick={running ? resume : start}
            className="inline-flex h-9 items-center gap-1.5 rounded-sm bg-accent px-3 text-xs font-semibold text-accent-fg transition-colors duration-150 hover:bg-accent-hover"
          >
            <Play size={13} className="ml-px" /> {paused ? "Resume" : "Start"}
          </button>
        )}
        <button
          onClick={halt}
          className="inline-flex h-9 w-9 items-center justify-center rounded-sm border border-down/40 bg-down-dim text-down transition-opacity duration-150 hover:opacity-90 md:w-auto md:gap-1.5 md:px-2.5"
          aria-label="Halt"
        >
          <Square size={12} />
          <span className="hidden md:inline text-xs font-semibold">Halt</span>
        </button>
        <button
          onClick={() => setSettingsOpen(true)}
          className="inline-flex h-9 w-9 items-center justify-center rounded-sm border border-border text-muted transition-colors duration-150 hover:bg-bg-hover hover:text-fg"
          aria-label="Settings"
        >
          <Settings size={15} />
        </button>
      </div>
    </header>
  );
}

function TickerInline() {
  const symbol = useDesk((s) => s.symbol);
  const last = useDesk((s) => s.quote?.last);
  const spread = useDesk((s) => s.quote?.spread);
  const candles = useDesk((s) => s.candles);
  const equity = useDesk((s) => s.equity);
  const feedSource = useDesk((s) => s.feedSource);
  const loadingFeed = useDesk((s) => s.loadingFeed);
  const stats = seriesStats(candles);
  const price = last ?? stats?.last;
  const change = stats?.change ?? 0;
  const changePct = stats?.changePct ?? 0;
  const up = change >= 0;

  return (
    <div className="hidden min-w-0 items-center gap-5 overflow-hidden md:flex">
      <div className="flex items-baseline gap-2.5">
        <span className="text-xs font-semibold">{symbol.replace("USDT", "")}</span>
        {price != null && (
          <span className={`desk-num text-base font-semibold ${up ? "text-up" : "text-down"}`}>
            {price.toFixed(2)}
          </span>
        )}
        {stats && (
          <span className={`desk-num text-2xs ${up ? "text-up" : "text-down"}`}>
            {signed(change)} ({changePct >= 0 ? "+" : ""}
            {changePct.toFixed(2)}%)
          </span>
        )}
      </div>
      <Stat label="High" value={stats ? stats.high.toFixed(2) : "—"} />
      <Stat label="Low" value={stats ? stats.low.toFixed(2) : "—"} />
      <Stat label="Spread" value={spread != null ? spread.toFixed(3) : "—"} />
      <Stat label="Equity" value={fmt(equity)} />
      <div className="flex items-center gap-1.5 text-2xs uppercase tracking-wider text-muted">
        <span className={loadingFeed ? "inline-block h-1.5 w-1.5 rounded-full bg-muted" : "live-dot"} />
        <span>
          {loadingFeed ? "Connecting" : feedSource === "binance-public" ? "Binance" : "Synthetic"}
        </span>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="hidden shrink-0 lg:block">
      <div className="text-2xs uppercase tracking-wider text-subtle">{label}</div>
      <div className="desk-num text-xs text-fg">{value}</div>
    </div>
  );
}

function MobileTicker() {
  const symbol = useDesk((s) => s.symbol);
  const last = useDesk((s) => s.quote?.last);
  const candles = useDesk((s) => s.candles);
  const equity = useDesk((s) => s.equity);
  const feedSource = useDesk((s) => s.feedSource);
  const loadingFeed = useDesk((s) => s.loadingFeed);
  const stats = seriesStats(candles);
  const price = last ?? stats?.last;
  const changePct = stats?.changePct ?? 0;
  const up = (stats?.change ?? 0) >= 0;

  const spec = UNIVERSE.find((u) => u.id === symbol);
  return (
    <div className="flex h-10 shrink-0 items-center gap-2 overflow-hidden border-b border-border px-3 md:hidden">
      <span className="shrink-0 text-2xs font-semibold text-muted">{spec?.label ?? symbol}</span>
      {price != null && (
        <span className={`desk-num shrink-0 text-sm font-semibold ${up ? "text-up" : "text-down"}`}>
          {price >= 1000 ? price.toFixed(2) : price.toFixed(4)}
        </span>
      )}
      <span className={`desk-num min-w-0 truncate text-2xs ${up ? "text-up" : "text-down"}`}>
        {changePct >= 0 ? "+" : ""}
        {changePct.toFixed(2)}%
      </span>
      <span className="ml-auto shrink-0 desk-num text-xs">${fmt(equity)}</span>
      <span className="flex shrink-0 items-center gap-1 text-2xs uppercase tracking-wider text-muted">
        <span className={loadingFeed ? "inline-block h-1.5 w-1.5 rounded-full bg-muted" : "live-dot"} />
        {loadingFeed ? "…" : feedSource === "binance-public" ? "Live" : "Sim"}
      </span>
    </div>
  );
}

function TabStrip() {
  const tab = useDesk((s) => s.tab);
  const setTab = useDesk((s) => s.setTab);
  return (
    <nav className="hidden h-9 shrink-0 items-stretch overflow-x-auto border-b border-border bg-bg-elevated px-1 md:flex">
      {NAV.map((item) => {
        const active = tab === item.id;
        return (
          <button
            key={item.id}
            onClick={() => setTab(item.id)}
            className={`relative flex shrink-0 items-center px-3 text-xs font-medium transition-colors duration-150 ${
              active ? "text-fg" : "text-muted hover:text-fg"
            }`}
          >
            {item.label}
            {active && <span className="absolute inset-x-2 bottom-0 h-0.5 bg-accent" />}
          </button>
        );
      })}
    </nav>
  );
}

function Body() {
  const tab = useDesk((s) => s.tab);
  if (tab === "home") {
    return (
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <Overview />
      </div>
    );
  }
  if (tab === "providers") {
    return (
      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        <ProvidersView />
      </div>
    );
  }
  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      {tab === "agent" && <AgentView />}
      {tab === "news" && <EvidenceView />}
      {tab === "learning" && <HermesView />}
      {tab === "market" && <MarketView />}
      {tab === "trades" && <TradesView />}
      {tab === "cockpit" && <EmergencyView />}
      {tab === "qualify" && <QualifyView />}
    </div>
  );
}

function Overview() {
  const equity = useDesk((s) => s.equity);
  const cash = useDesk((s) => s.cash);
  const realizedPnl = useDesk((s) => s.realizedPnl);
  const peakEquity = useDesk((s) => s.peakEquity);
  const quote = useDesk((s) => s.quote);
  const position = useDesk((s) => s.position);
  const u = unrealized({ position, quote } as EngineState);
  const dd = peakEquity > 0 ? ((peakEquity - equity) / peakEquity) * 100 : 0;
  const cards = [
    { label: "Equity", value: `${fmt(equity)}`, tone: "fg" as const },
    { label: "Unrealized", value: signed(u), tone: toneOf(u) },
    { label: "Realized", value: signed(realizedPnl), tone: toneOf(realizedPnl) },
    { label: "Drawdown", value: `${dd.toFixed(2)}%`, tone: dd > 6 ? ("down" as const) : ("muted" as const) },
    { label: "Cash", value: fmt(cash), tone: "muted" as const },
  ];

  return (
    <div className="grid min-h-0 flex-1 grid-rows-[minmax(11rem,1fr)_auto_auto] lg:grid-cols-[minmax(0,1fr)_18rem] lg:grid-rows-[minmax(0,1fr)_auto]">
      <div className="min-h-0 min-w-0 overflow-hidden">
        <ChartDock />
      </div>
      <aside className="hidden min-h-0 flex-col overflow-y-auto border-l border-border bg-bg-elevated lg:flex">
        <PositionPanel />
        <EvidenceMini />
        <RiskMini />
      </aside>
      <div className="col-span-full grid grid-cols-2 overflow-x-auto border-t border-border sm:grid-cols-5">
        {cards.map((c) => (
          <div key={c.label} className="min-w-0 border-r border-border px-3 py-2 last:border-r-0">
            <div className="text-2xs uppercase tracking-wider text-subtle">{c.label}</div>
            <div
              className={`desk-num mt-0.5 truncate text-sm ${
                c.tone === "up"
                  ? "text-up"
                  : c.tone === "down"
                    ? "text-down"
                    : c.tone === "muted"
                      ? "text-muted"
                      : "text-fg"
              }`}
            >
              {c.value}
            </div>
          </div>
        ))}
      </div>
      <div className="col-span-full max-h-44 overflow-y-auto border-t border-border lg:hidden">
        <PositionPanel />
      </div>
    </div>
  );
}

function PositionPanel() {
  const position = useDesk((s) => s.position);
  const quote = useDesk((s) => s.quote);
  const flatten = useDesk((s) => s.flatten);
  if (!position || !quote) {
    return (
      <div className="border-b border-border px-4 py-4">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium">Position</span>
          <span className="rounded-xs bg-bg-subtle px-1.5 py-0.5 text-2xs font-semibold tracking-wider text-muted uppercase">
            Flat
          </span>
        </div>
        <p className="mt-2 text-xs leading-relaxed text-muted">
          No open paper position. Entries wait for EMA pullback, open risk gates, and ALLOW evidence.
        </p>
      </div>
    );
  }
  const u = unrealized({ position, quote } as EngineState);
  return (
    <div className="flex flex-col border-b border-border px-4 py-4">
      <div className="flex items-center justify-between">
        <span className="text-xs font-medium">Position</span>
        <span className="rounded-xs bg-up-dim px-1.5 py-0.5 text-2xs font-semibold tracking-wider text-up uppercase">
          {position.side}
        </span>
      </div>
      <div className="mt-2 desk-num text-lg">{position.symbol}</div>
      <dl className="mt-3 space-y-1.5 text-xs">
        <Row k="Qty" v={String(position.qty)} />
        <Row k="Entry" v={fmt(position.entry)} />
        <Row k="Mark" v={fmt(quote.last)} />
        <Row k="Leverage" v={`${position.leverage}x`} />
        <Row k="Isolated margin" v={fmt(position.margin ?? 0)} />
        <Row k="Liquidation" v={fmt(position.liquidation ?? 0)} />
        <Row k="Stop" v={fmt(position.stop)} />
        <Row k="Take" v={fmt(position.take)} />
        <Row k="Unrealized" v={signed(u)} up={u >= 0} />
      </dl>
      <button
        onClick={flatten}
        className="mt-4 h-9 rounded-sm border border-down/40 bg-down-dim text-xs font-semibold text-down"
      >
        Flatten at mark
      </button>
    </div>
  );
}

function EvidenceMini() {
  const evidence = useDesk((s) => s.evidence);
  return (
    <div className="border-b border-border px-4 py-4">
      <div className="text-xs font-medium">Context</div>
      <ul className="mt-3 space-y-2">
        {evidence.map((e) => (
          <li key={e.id} className="flex items-start justify-between gap-3 text-xs">
            <span className="min-w-0 leading-snug text-muted">{e.title}</span>
            <Tag tone={e.disposition === "ALLOW" ? "up" : e.disposition === "REDUCE" ? "accent" : "down"}>
              {e.disposition}
            </Tag>
          </li>
        ))}
      </ul>
    </div>
  );
}

function RiskMini() {
  const slice = useDesk(
    useShallow((s) => ({
      running: s.running,
      paused: s.paused,
      halted: s.halted,
      mode: s.mode,
      candles: s.candles,
      lastTickAt: s.lastTickAt,
      breakerTripped: s.breakerTripped,
      dailyPnl: s.dailyPnl,
      peakEquity: s.peakEquity,
      equity: s.equity,
      product: s.product,
      position: s.position,
      evidence: s.evidence,
      trades: s.trades,
      feedSource: s.feedSource,
    })),
  );
  const gates = riskGates(slice as EngineState);
  const failed = gates.filter((g) => !g.ok).length;
  return (
    <div className="px-4 py-4">
      <div className="flex items-center justify-between">
        <div className="text-xs font-medium">Risk</div>
        <span className={`text-2xs font-semibold ${failed ? "text-down" : "text-up"}`}>
          {failed ? `${failed} hold` : "Clear"}
        </span>
      </div>
      <ul className="mt-3 space-y-1.5">
        {gates.slice(0, 6).map((g) => (
          <li key={g.id} className="flex items-center justify-between text-2xs">
            <span className="text-muted">{g.label}</span>
            <span className={`font-semibold ${g.ok ? "text-up" : "text-down"}`}>{g.ok ? "PASS" : "HOLD"}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function AgentView() {
  const events = useDesk((s) => s.events);
  return (
    <section>
      <div className="border-b border-border px-4 py-3 text-sm font-medium">Agent activity</div>
      <ul className="divide-y divide-border">
        {events.map((e) => (
          <li key={e.id} className="grid gap-1 px-4 py-3 md:grid-cols-[110px_90px_1fr]">
            <span className="desk-num text-2xs text-subtle">{new Date(e.ts).toISOString().slice(11, 19)} UTC</span>
            <Tag tone={kindTone(e.kind)}>{e.kind}</Tag>
            <div>
              <div className="text-sm">{e.title}</div>
              <div className="text-xs text-muted">{e.detail}</div>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

function EvidenceView() {
  const evidence = useDesk((s) => s.evidence);
  return (
    <div>
      <div className="border-b border-border px-5 py-4">
        <div className="text-sm font-medium">Evidence policy</div>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
          Binance is authoritative for price. Forum posts never independently authorize a trade. Missing or
          conflicting evidence HOLDs new entries. Rows below are labelled policy samples.
        </p>
      </div>
      {evidence.map((e) => (
        <div key={e.id} className="border-b border-border px-5 py-4 last:border-b-0">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-medium">{e.title}</div>
            <Tag tone={e.disposition === "ALLOW" ? "up" : e.disposition === "REDUCE" ? "accent" : "down"}>
              {e.disposition}
            </Tag>
          </div>
          <div className="mt-1 text-2xs uppercase tracking-wider text-subtle">{e.source}</div>
          <p className="mt-2 text-sm text-muted">{e.when}</p>
          <div className="mt-2 desk-num text-2xs text-subtle">score {e.score.toFixed(2)}</div>
        </div>
      ))}
    </div>
  );
}

function HermesView() {
  const genomes = useDesk((s) => s.genomes);
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [ok, setOk] = useState<boolean | null>(null);

  async function run() {
    setBusy(true);
    setResult(null);
    try {
      const res = await runHermesResearch();
      setOk(res.ok);
      setResult(`${res.detail}\n\n${res.raw}`.trim());
      if (res.ok) useDesk.getState().applyProposal(res.raw, res.model);
    } catch (err) {
      setOk(false);
      setResult(err instanceof Error ? err.message : "Research failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div>
      <div className="border-b border-border px-5 py-4">
        <div className="text-sm font-medium">Hermes is untrusted</div>
        <p className="mt-2 max-w-3xl text-sm leading-relaxed text-muted">
          Hermes proposes genomes only. GoldGuard sizes, validates, and mutates state. Target model is
          google-antigravity/gemini-3.7-flash. Holdout stays sealed. Live stays disarmed.
        </p>
        <button
          onClick={() => void run()}
          disabled={busy}
          className="mt-4 inline-flex h-10 items-center rounded-sm bg-accent px-4 text-xs font-semibold text-accent-fg disabled:opacity-40"
        >
          {busy ? "Requesting proposal…" : "Run research now"}
        </button>
        {result && (
          <pre className={`mt-4 max-h-64 overflow-auto whitespace-pre-wrap rounded-sm bg-bg-subtle p-3 text-2xs ${ok ? "text-fg" : "text-down"}`}>
            {result}
          </pre>
        )}
      </div>
      {genomes.map((g) => (
        <div key={g.id} className="border-b border-border px-5 py-4 last:border-b-0">
          <div className="flex items-center justify-between">
            <div className="text-base font-medium">{g.name}</div>
            <Tag tone={g.status === "active" ? "accent" : "muted"}>{g.status}</Tag>
          </div>
          <dl className="mt-3 grid grid-cols-3 gap-3 text-xs">
            <div>
              <div className="text-subtle">Sharpe</div>
              <div className="desk-num">{g.sharpe}</div>
            </div>
            <div>
              <div className="text-subtle">Paper trades</div>
              <div className="desk-num">{g.trades}</div>
            </div>
            <div>
              <div className="text-subtle">Max DD</div>
              <div className="desk-num">{g.maxDd}</div>
            </div>
          </dl>
          <p className="mt-3 text-xs text-muted">{g.note}</p>
        </div>
      ))}
    </div>
  );
}

function MarketView() {
  return (
    <div className="grid h-full min-h-96 lg:grid-cols-[minmax(0,1fr)_16rem]">
      <div className="min-h-96 overflow-hidden border-b border-border lg:border-r lg:border-b-0">
        <div className="h-96 md:h-full">
          <ChartDock />
        </div>
      </div>
      <LastCandlePanel />
    </div>
  );
}

function LastCandlePanel() {
  const candles = useDesk((s) => s.candles);
  const patterns = useDesk((s) => s.patterns);
  const last = candles[candles.length - 1];
  return (
    <div className="px-5 py-4">
      <div className="text-sm font-medium">Last engine candle</div>
      {last ? (
        <dl className="mt-4 space-y-2 text-sm">
          <Row k="Open" v={fmt(last.o)} />
          <Row k="High" v={fmt(last.h)} />
          <Row k="Low" v={fmt(last.l)} />
          <Row k="Close" v={fmt(last.c)} />
          <Row k="Volume" v={last.v.toFixed(2)} />
        </dl>
      ) : (
        <p className="mt-3 text-sm text-muted">No candle has been observed yet.</p>
      )}
      <div className="mt-5 text-sm font-medium">Detected patterns</div>
      <p className="mt-1 text-2xs text-subtle">OHLC rules (ChartSchool / BabyPips). Not image vision.</p>
      {patterns.length === 0 ? (
        <p className="mt-2 text-xs text-muted">Waiting for 15m structure.</p>
      ) : (
        <ul className="mt-2 space-y-2">
          {patterns.map((p) => (
            <li key={p.id} className="rounded-sm bg-bg-subtle px-2 py-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium">{p.name}</span>
                <span className="text-2xs uppercase tracking-wider text-muted">{p.side}</span>
              </div>
              <p className="mt-1 text-2xs leading-relaxed text-muted">{p.detail}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TradesView() {
  const trades = useDesk((s) => s.trades);
  const orders = useDesk((s) => s.orders);
  return (
    <div>
      <div className="overflow-x-auto border-b border-border">
        <div className="border-b border-border px-4 py-3 text-sm font-medium">Closed paper trades</div>
        {trades.length === 0 ? (
          <Empty text="No paper order has been filled yet." />
        ) : (
          <table className="w-full text-left text-xs whitespace-nowrap">
            <thead className="text-2xs uppercase tracking-wider text-subtle">
              <tr>
                {["Symbol", "Side", "Qty", "Entry", "Exit", "Net", "Reason"].map((h) => (
                  <th key={h} className="px-4 py-2 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {trades.map((t) => (
                <tr key={t.id} className="border-t border-border hover:bg-bg-hover">
                  <td className="px-4 py-2 font-mono">{t.symbol}</td>
                  <td className="px-4 py-2">{t.side}</td>
                  <td className="desk-num px-4 py-2">{t.qty.toFixed(4)}</td>
                  <td className="desk-num px-4 py-2">{fmt(t.entry)}</td>
                  <td className="desk-num px-4 py-2">{fmt(t.exit)}</td>
                  <td className={`desk-num px-4 py-2 ${t.net >= 0 ? "text-up" : "text-down"}`}>{signed(t.net)}</td>
                  <td className="px-4 py-2 text-muted">{t.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <div className="overflow-x-auto">
        <div className="border-b border-border px-4 py-3 text-sm font-medium">Orders</div>
        {orders.length === 0 ? (
          <Empty text="The order ledger is empty — not seeded." />
        ) : (
          <table className="w-full text-left text-xs whitespace-nowrap">
            <thead className="text-2xs uppercase tracking-wider text-subtle">
              <tr>
                {["Client id", "Type", "Qty", "Entry", "Status"].map((h) => (
                  <th key={h} className="px-4 py-2 font-medium">
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {orders.map((o) => (
                <tr key={o.id} className="border-t border-border hover:bg-bg-hover">
                  <td className="px-4 py-2 font-mono text-2xs">{o.clientId}</td>
                  <td className="px-4 py-2">{o.type}</td>
                  <td className="desk-num px-4 py-2">{o.qty.toFixed(4)}</td>
                  <td className="desk-num px-4 py-2">{fmt(o.price)}</td>
                  <td className="px-4 py-2">{o.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  );
}

function EmergencyView() {
  const halt = useDesk((s) => s.halt);
  const flatten = useDesk((s) => s.flatten);
  const resetPaper = useDesk((s) => s.resetPaper);
  const halted = useDesk((s) => s.halted);
  const position = useDesk((s) => s.position);
  return (
    <div className="grid lg:grid-cols-2">
      <div className="border-b border-border px-5 py-5 lg:border-r lg:border-b-0">
        <div className="flex items-center gap-2 text-base font-medium">
          <Gauge size={16} className="text-down" /> Emergency cockpit
        </div>
        <p className="mt-3 text-sm leading-relaxed text-muted">
          Halt blocks new entries immediately. Flatten closes the open paper position at the last mark. Reset
          wipes this browser's paper ledger only — it does not touch Binance.
        </p>
        <div className="mt-5 flex flex-col gap-2">
          <button onClick={halt} className="h-11 rounded-sm bg-down text-sm font-semibold text-fg hover:opacity-90">
            Emergency halt
          </button>
          <button
            onClick={flatten}
            disabled={!position}
            className="h-11 rounded-sm border border-border text-sm font-medium text-fg disabled:opacity-40"
          >
            Flatten open position
          </button>
          <button
            onClick={resetPaper}
            className="inline-flex h-11 items-center justify-center gap-2 rounded-sm border border-border text-sm font-medium text-fg"
          >
            <RotateCcw size={14} /> Reset paper account
          </button>
        </div>
        {halted && <p className="mt-4 text-xs text-down">Desk is halted. Start is disabled until you reset paper.</p>}
      </div>
      <RiskMini />
    </div>
  );
}

function QualifyView() {
  const trades = useDesk((s) => s.trades);
  const feedSource = useDesk((s) => s.feedSource);
  const [remote, setRemote] = useState<{ id: string; ok: boolean; label: string; detail: string }[]>([]);

  useEffect(() => {
    void collectLiveDiagnostics().then((d) => setRemote(d.checks));
  }, []);

  const gates = [
    { name: "Paper desk", pass: true, note: "Preview is paper-only" },
    { name: "Public PAXGUSDT feed", pass: feedSource === "binance-public" || remote.some((c) => c.id === "binance" && c.ok), note: feedSource === "binance-public" ? "Binance public / vision mirror" : "Synthetic path until public klines attach" },
    { name: "OpenCodex + Antigravity", pass: remote.some((c) => c.id === "antigravity" && c.ok), note: remote.find((c) => c.id === "antigravity")?.detail ?? "Checking…" },
    { name: "Hermes researcher", pass: remote.some((c) => c.id === "hermes" && c.ok), note: remote.find((c) => c.id === "hermes")?.detail ?? "Checking…" },
    { name: "Paper evidence", pass: trades.length >= 200, note: `${trades.length} / 200 closed 15m cycles (1m micro is retired)` },
    { name: "Strategy statistics", pass: false, note: "15m walk-forward was green on one 10-day window (21 trades). Sealed holdout still closed. Not live." },
    { name: "Binance trade keys", pass: false, note: "Not present — live cannot arm. Do not paste keys in chat." },
    { name: "Telegram", pass: false, note: "Requires a bot token you control" },
    { name: "TOTP / live arm", pass: false, note: "Arming phrase is operator-owned. Code will not auto-arm." },
    { name: "Live canary", pass: false, note: "Fail-closed. ready_for_live_canary remains false." },
  ];
  const ready = gates.every((g) => g.pass);
  return (
    <section>
      <div className="flex items-center justify-between border-b border-border px-4 py-3">
        <div className="text-sm font-medium">System qualification</div>
        <Tag tone={ready ? "up" : "down"}>{ready ? "Ready for live canary" : "Not ready for live"}</Tag>
      </div>
      <ul>
        {gates.map((g) => (
          <li key={g.name} className="flex items-start justify-between gap-4 border-b border-border px-4 py-3 text-sm last:border-b-0">
            <div>
              <div>{g.name}</div>
              <div className="text-xs text-muted">{g.note}</div>
            </div>
            <span className={g.pass ? "text-up" : "text-down"}>{g.pass ? "PASS" : "HOLD"}</span>
          </li>
        ))}
      </ul>
    </section>
  );
}

function SettingsSheet() {
  const open = useDesk((s) => s.settingsOpen);
  const setOpen = useDesk((s) => s.setSettingsOpen);
  const startingCash = useDesk((s) => s.startingCash);
  const setCanary = useDesk((s) => s.setCanary);
  if (!open) return null;
  const risk = startingCash * 0.01;
  const exposure = startingCash * 0.2;
  const breaker = startingCash * 0.05;
  return (
    <div className="fixed inset-0 z-40 flex justify-end bg-overlay" onClick={() => setOpen(false)}>
      <aside
        className="flex h-full w-full max-w-md flex-col border-l border-border bg-bg-elevated p-5 pb-[calc(1.25rem+env(safe-area-inset-bottom))] shadow-[var(--shadow-sheet)]"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between">
          <div className="text-lg font-semibold">Autonomous settings</div>
          <button
            onClick={() => setOpen(false)}
            className="inline-flex h-10 w-10 items-center justify-center rounded-sm text-muted hover:bg-bg-hover hover:text-fg"
            aria-label="Close settings"
          >
            <X size={16} />
          </button>
        </div>
        <p className="mt-2 text-sm leading-relaxed text-muted">
          Paper canary only. Live stays disarmed. Size the book at 10 or 100 USDT — both are realistic
          micro sizes against PAXG/USDT.
        </p>
        <div className="mt-4 flex gap-2">
          {([10, 100] as const).map((n) => (
            <button
              key={n}
              onClick={() => setCanary(n)}
              className={`h-11 flex-1 rounded-sm text-sm font-semibold ${
                startingCash === n ? "bg-accent text-accent-fg" : "border border-border text-muted"
              }`}
            >
              ${n} canary
            </button>
          ))}
        </div>
        <div className="mt-5 space-y-2">
          <Setting label="Max capital per trade" value="1.00%" hint={`${risk.toFixed(2)} USDT risk per trade`} />
          <Setting label="Max total exposure" value="20.00%" hint={`${exposure.toFixed(2)} USDT maximum total exposure`} />
          <Setting label="Rolling 24h loss limit" value="5.00%" hint={`${breaker.toFixed(2)} USDT breaker trip`} />
          <Setting label="Engine timeframe" value="15m closed bars" hint="1m is chart-only. Entries fire on a closed 15m bar." />
          <Setting label="Cost gate" value="35% of stop" hint="Skip if round-trip fees+slip eat the stop." />
          <Setting label="Max futures leverage" value="2x used / 5x ceiling" hint="Core never treats 5x as the default." />
          <Setting label="Spot pairs" value="PAXGUSDT" hint="Cash-only. No borrowing." />
          <Setting label="Futures entries" value="BTC SOL on · ETH off" hint="ETH new entries HOLD after the paper sample." />
        </div>
      </aside>
    </div>
  );
}

function Setting({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <div className="rounded-sm bg-bg-subtle px-3 py-3 shadow-[var(--shadow-panel)]">
      <div className="flex items-center justify-between text-sm">
        <span className="text-muted">{label}</span>
        <span className="font-mono">{value}</span>
      </div>
      <div className="mt-1 text-xs text-subtle">{hint}</div>
    </div>
  );
}

function MobileNav() {
  const tab = useDesk((s) => s.tab);
  const setTab = useDesk((s) => s.setTab);
  const [more, setMore] = useState(false);
  const primary = [NAV[0], NAV[2], NAV[3], NAV[1]];
  const extra = [NAV[4], NAV[5], NAV[6], NAV[7], NAV[8]];
  const extraActive = extra.some((i) => i.id === tab);

  return (
    <>
      {more && (
        <div className="fixed inset-0 z-40 bg-overlay md:hidden" onClick={() => setMore(false)}>
          <div
            className="absolute inset-x-0 bottom-[calc(3.75rem+env(safe-area-inset-bottom))] rounded-t-lg border-t border-border bg-bg-elevated p-3"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="mb-2 text-2xs font-semibold tracking-wider text-subtle uppercase">More</div>
            <div className="grid grid-cols-3 gap-2">
              {extra.map((item) => {
                const Icon = item.icon;
                const active = tab === item.id;
                return (
                  <button
                    key={item.id}
                    onClick={() => {
                      setTab(item.id);
                      setMore(false);
                    }}
                    className={`flex min-h-14 flex-col items-center justify-center gap-1 rounded-sm border text-2xs ${
                      active ? "border-accent/40 bg-accent-dim text-accent" : "border-border text-muted"
                    }`}
                  >
                    <Icon size={16} />
                    {item.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>
      )}
      <nav className="fixed inset-x-0 bottom-0 z-30 flex justify-around border-t border-border bg-bg-elevated px-1 pt-1 pb-[max(0.4rem,env(safe-area-inset-bottom))] md:hidden">
        {primary.map((item) => {
          const Icon = item.icon;
          const active = tab === item.id;
          return (
            <button
              key={item.id}
              onClick={() => {
                setMore(false);
                setTab(item.id);
              }}
              className={`flex min-h-11 min-w-11 flex-1 flex-col items-center justify-center gap-0.5 text-2xs ${
                active ? "text-accent" : "text-muted"
              }`}
            >
              <Icon size={16} />
              {item.label}
            </button>
          );
        })}
        <button
          onClick={() => setMore((v) => !v)}
          className={`flex min-h-11 min-w-11 flex-1 flex-col items-center justify-center gap-0.5 text-2xs ${
            more || extraActive ? "text-accent" : "text-muted"
          }`}
        >
          <Gauge size={16} />
          More
        </button>
      </nav>
    </>
  );
}

function Row({ k, v, up }: { k: string; v: string; up?: boolean }) {
  return (
    <div className="flex items-center justify-between">
      <dt className="text-muted">{k}</dt>
      <dd className={`desk-num ${up === undefined ? "text-fg" : up ? "text-up" : "text-down"}`}>{v}</dd>
    </div>
  );
}

function Tag({
  children,
  tone,
}: {
  children: ReactNode;
  tone: "up" | "down" | "accent" | "muted";
}) {
  const cls =
    tone === "up"
      ? "bg-up-dim text-up"
      : tone === "down"
        ? "bg-down-dim text-down"
        : tone === "accent"
          ? "bg-accent-dim text-accent"
          : "bg-bg-subtle text-muted";
  return (
    <span className={`shrink-0 rounded-xs px-1.5 py-0.5 text-2xs font-semibold tracking-wider uppercase ${cls}`}>
      {children}
    </span>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="px-4 py-10 text-center text-sm text-muted">{text}</div>;
}

function toneOf(n: number): "up" | "down" | "fg" {
  if (n > 0) return "up";
  if (n < 0) return "down";
  return "fg";
}

function kindTone(kind: string): "up" | "down" | "accent" | "muted" {
  if (kind === "entry" || kind === "exit") return "accent";
  if (kind === "risk") return "down";
  return "muted";
}

function seriesStats(candles: Candle[]) {
  if (candles.length < 2) return null;
  const last = candles[candles.length - 1];
  const first = candles[0];
  let high = -Infinity;
  let low = Infinity;
  for (const c of candles) {
    high = Math.max(high, c.h);
    low = Math.min(low, c.l);
  }
  const change = last.c - first.o;
  const changePct = first.o !== 0 ? (change / first.o) * 100 : 0;
  return { last: last.c, high, low, change, changePct };
}
