import { create } from "zustand";
import {
  close,
  emptyState,
  emergencyFlatten,
  hydrate,
  mark,
  replayPaper,
  tick,
} from "./engine";
import { fetchPublicKlines, fetchPublicTicker } from "./klines";
import { runHermesResearch } from "./hermes";
import type { CanarySize, ChartMode, EngineState, Genome, Interval, Tab, UniverseId } from "./types";
import { UNIVERSE } from "./types";

type Store = EngineState & {
  tab: Tab;
  settingsOpen: boolean;
  loadingFeed: boolean;
  loadingChart: boolean;
  chartInterval: Interval;
  chartMode: ChartMode;
  chartCandles: EngineState["candles"];
  chartSource: EngineState["feedSource"];
  setTab: (tab: Tab) => void;
  setSettingsOpen: (open: boolean) => void;
  setChartInterval: (interval: Interval) => void;
  setChartMode: (mode: ChartMode) => void;
  boot: () => Promise<void>;
  start: () => void;
  pause: () => void;
  resume: () => void;
  halt: () => void;
  flatten: () => void;
  resetPaper: () => void;
  setCanary: (size: CanarySize) => void;
  setSymbol: (id: UniverseId) => void;
  applyProposal: (raw: string, model: string) => void;
  research: () => Promise<void>;
};

let loop: number | null = null;
let bootSeq = 0;

function persist(state: EngineState) {
  try {
    const slim = {
      cash: state.cash,
      realizedPnl: state.realizedPnl,
      dailyPnl: state.dailyPnl,
      fees: state.fees,
      trades: state.trades.slice(0, 20),
      peakEquity: state.peakEquity,
    };
    localStorage.setItem("goldguard.paper.v2", JSON.stringify(slim));
  } catch {
    /* ignore quota */
  }
}

async function loadChartSeries(symbol: string, interval: Interval) {
  return fetchPublicKlines({
    data: { symbol, interval, limit: interval === "1m" ? 240 : 300 },
  });
}

export const useDesk = create<Store>((set, get) => ({
  ...emptyState(),
  tab: "home",
  settingsOpen: false,
  loadingFeed: false,
  loadingChart: false,
  chartInterval: "1m",
  chartMode: "lite",
  chartCandles: [],
  chartSource: "synthetic",
  setTab: (tab) => set({ tab, settingsOpen: false }),
  setSettingsOpen: (open) => set({ settingsOpen: open }),
  setChartMode: (mode) => set({ chartMode: mode }),
  setChartInterval: (interval) => {
    set({ chartInterval: interval, loadingChart: true });
    const { symbol, candles, feedSource } = get();
    if (interval === "1m" && candles.length > 0) {
      set({ chartCandles: candles, chartSource: feedSource, loadingChart: false });
      return;
    }
    void loadChartSeries(symbol, interval)
      .then(({ candles: series, source }) => {
        set({ chartCandles: series, chartSource: source, loadingChart: false });
      })
      .catch((err: unknown) => {
        set({
          loadingChart: false,
          error: err instanceof Error ? err.message : "Chart feed failed",
        });
      });
  },
  boot: async () => {
    const seq = ++bootSeq;
    set({ loadingFeed: true, loadingChart: true, error: null });
    try {
      const { candles, source } = await fetchPublicKlines({
        data: { symbol: get().symbol, interval: "1m", limit: 240 },
      });
      if (seq !== bootSeq) return;
      set((s) => ({
        ...hydrate(s, candles, source),
        chartCandles: s.chartInterval === "1m" ? candles : s.chartCandles,
        chartSource: s.chartInterval === "1m" ? source : s.chartSource,
      }));
      if (get().chartInterval !== "1m") {
        const extra = await loadChartSeries(get().symbol, get().chartInterval);
        if (seq !== bootSeq) return;
        set({ chartCandles: extra.candles, chartSource: extra.source });
      }
    } catch (err) {
      if (seq !== bootSeq) return;
      set({ error: err instanceof Error ? err.message : "Feed failed" });
    } finally {
      if (seq !== bootSeq) return;
      set({ loadingFeed: false, loadingChart: false });
      if (!get().halted && !get().running) {
        get().start();
        void get().research();
      }
    }
  },
  start: () => {
    const s = get();
    if (s.halted) return;
    if (loop && s.running) return;
    const replayed = replayPaper({ ...s, running: true, paused: false }, s.candles);
    set(
      mark(
        replayed,
        "system",
        "Paper loop started",
        "Public feed on the selected pair. HOLD is a valid autonomous decision. Live stays disarmed.",
      ),
    );
    persist(replayed);
    if (loop) window.clearInterval(loop);
    loop = window.setInterval(() => {
      void (async () => {
        const prev = get();
        if (!prev.running || prev.paused || prev.halted) return;
        let incoming: (typeof prev.candles)[number] | undefined;
        let source = prev.feedSource;
        try {
          const t = await fetchPublicTicker({ data: { symbol: prev.symbol } });
          if (t.last != null) {
            const lastC = prev.candles[prev.candles.length - 1];
            const px = t.last;
            incoming = {
              t: Date.now(),
              o: lastC?.c ?? px,
              h: Math.max(lastC?.c ?? px, px),
              l: Math.min(lastC?.c ?? px, px),
              c: px,
              v: lastC?.v ?? 1,
            };
            source = t.source;
          }
        } catch {
          /* local tick */
        }
        const next = tick({ ...prev, feedSource: source }, Date.now(), incoming);
        next.feedSource = source;
        if (incoming) next.lastTickAt = Date.now();
        const chartLive = get().chartInterval === "1m";
        set(chartLive ? { ...next, chartCandles: next.candles, chartSource: next.feedSource } : next);
        persist(next);
      })();
    }, 1600);
  },
  pause: () => {
    set((s) => mark({ ...s, paused: true }, "system", "Paused", "Open protection stays active. New entries are blocked."));
  },
  resume: () => {
    const s = get();
    if (s.halted) return;
    set(mark({ ...s, paused: false, running: true }, "system", "Resumed", "Paper loop is live again."));
  },
  halt: () => {
    if (loop) window.clearInterval(loop);
    loop = null;
    set((s) => emergencyFlatten(s));
  },
  flatten: () => {
    set((s) => {
      if (!s.position || !s.quote) return s;
      return close(s, s.quote.last, "EMERGENCY", Date.now());
    });
  },
  resetPaper: () => {
    if (loop) window.clearInterval(loop);
    loop = null;
    try {
      localStorage.removeItem("goldguard.paper.v2");
      localStorage.removeItem("goldguard.paper.v1");
    } catch {
      /* ignore */
    }
    const fresh = emptyState(get().startingCash);
    set({
      ...fresh,
      tab: get().tab,
      settingsOpen: false,
      loadingFeed: false,
      loadingChart: false,
      chartInterval: get().chartInterval,
      chartMode: get().chartMode,
      chartCandles: [],
      chartSource: "synthetic",
    });
    void get().boot();
  },
  setCanary: (size) => {
    if (loop) window.clearInterval(loop);
    loop = null;
    const tab = get().tab;
    const chartInterval = get().chartInterval;
    const chartMode = get().chartMode;
    set({
      ...emptyState(size),
      tab,
      settingsOpen: true,
      loadingFeed: false,
      loadingChart: false,
      chartInterval,
      chartMode,
      chartCandles: [],
      chartSource: "synthetic",
    });
    void get().boot();
  },
  setSymbol: (id) => {
    const spec = UNIVERSE.find((u) => u.id === id);
    if (!spec) return;
    if (loop) window.clearInterval(loop);
    loop = null;
    const startingCash = get().startingCash;
    set({
      ...emptyState(startingCash),
      symbol: spec.id,
      product: spec.product,
      tab: get().tab,
      settingsOpen: false,
      loadingFeed: true,
      loadingChart: true,
      chartInterval: get().chartInterval,
      chartMode: get().chartMode,
      chartCandles: [],
      chartSource: "synthetic",
    });
    void get().boot();
  },
  applyProposal: (raw, model) => {
    let parsed: Record<string, unknown> | null = null;
    try {
      const match = raw.match(/\{[\s\S]*\}/);
      parsed = match ? (JSON.parse(match[0]) as Record<string, unknown>) : null;
    } catch {
      parsed = null;
    }
    const id = String(parsed?.proposal_id ?? `hermes-${Date.now()}`);
    const change = String(parsed?.change ?? parsed?.rationale ?? "bounded paper tweak");
    const genome: Genome = {
      id,
      name: `Hermes ${String(id).slice(0, 28)}`,
      status: "candidate",
      sharpe: "unqualified",
      trades: 0,
      maxDd: "n/a",
      note: `${change} · ${model}. Untrusted until schema and holdout pass.`,
    };
    set((s) =>
      mark(
        { ...s, genomes: [genome, ...s.genomes.filter((g) => g.id !== id)].slice(0, 8) },
        "hermes",
        "Hermes proposal landed",
        genome.note,
      ),
    );
  },
  research: async () => {
    const res = await runHermesResearch();
    if (res.ok) get().applyProposal(res.raw, res.model);
    else set((s) => mark(s, "hermes", "Hermes HOLD", res.detail));
  },
}));
