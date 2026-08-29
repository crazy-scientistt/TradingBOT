import { create } from "zustand";
import {
  close,
  emptyState,
  emergencyFlatten,
  hydrate,
  mark,
  tick,
} from "./engine";
import { fetchPublicKlines, fetchPublicTicker } from "./klines";
import type { ChartMode, EngineState, Interval, Tab } from "./types";

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
};

let loop: number | null = null;

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
    localStorage.setItem("goldguard.paper.v1", JSON.stringify(slim));
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
  tab: "providers",
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
    set({ loadingFeed: true, loadingChart: true, error: null });
    try {
      const { candles, source } = await fetchPublicKlines({
        data: { symbol: get().symbol, interval: "1m", limit: 240 },
      });
      set((s) => ({
        ...hydrate(s, candles, source),
        chartCandles: s.chartInterval === "1m" ? candles : s.chartCandles,
        chartSource: s.chartInterval === "1m" ? source : s.chartSource,
      }));
      if (get().chartInterval !== "1m") {
        const extra = await loadChartSeries(get().symbol, get().chartInterval);
        set({ chartCandles: extra.candles, chartSource: extra.source });
      }
    } catch (err) {
      set({ error: err instanceof Error ? err.message : "Feed failed" });
    } finally {
      set({ loadingFeed: false, loadingChart: false });
    }
  },
  start: () => {
    const s = get();
    if (s.halted) return;
    set(
      mark(
        { ...s, running: true, paused: false },
        "system",
        "Paper loop started",
        "Entries still fail closed on stale feed, tripped breaker, or HOLD evidence.",
      ),
    );
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
      localStorage.removeItem("goldguard.paper.v1");
    } catch {
      /* ignore */
    }
    const fresh = emptyState();
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
}));
