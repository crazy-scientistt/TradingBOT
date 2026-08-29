import { useShallow } from "zustand/react/shallow";
import { CandleChart } from "./CandleChart";
import { TradingViewWidget } from "./TradingViewWidget";
import { useDesk } from "@/lib/trading/store";
import { INTERVALS, UNIVERSE } from "@/lib/trading/types";

export function ChartDock() {
  const {
    candles,
    chartCandles,
    chartInterval,
    chartMode,
    chartSource,
    loadingChart,
    quote,
    position,
    feedSource,
    symbol,
    setChartInterval,
    setChartMode,
    setSymbol,
  } = useDesk(
    useShallow((s) => ({
      candles: s.candles,
      chartCandles: s.chartCandles,
      chartInterval: s.chartInterval,
      chartMode: s.chartMode,
      chartSource: s.chartSource,
      loadingChart: s.loadingChart,
      quote: s.quote,
      position: s.position,
      feedSource: s.feedSource,
      symbol: s.symbol,
      setChartInterval: s.setChartInterval,
      setChartMode: s.setChartMode,
      setSymbol: s.setSymbol,
    })),
  );
  const series = chartInterval === "1m" ? candles : chartCandles;
  const source = chartInterval === "1m" ? feedSource : chartSource;
  const spec = UNIVERSE.find((u) => u.id === symbol) ?? UNIVERSE[0];

  return (
    <div className="flex h-full min-h-0 flex-col bg-bg">
      <div className="flex h-9 shrink-0 items-center gap-1 overflow-x-auto border-b border-border px-2">
        <div className="flex shrink-0 items-center rounded-sm bg-bg-subtle p-0.5">
          {UNIVERSE.map((u) => {
            const on = u.id === symbol;
            return (
              <button
                key={u.id}
                onClick={() => setSymbol(u.id)}
                className={`h-6 rounded-xs px-2 text-2xs font-semibold tracking-wide ${
                  on ? "bg-accent text-accent-fg" : "text-muted hover:text-fg"
                }`}
              >
                {u.label}
              </button>
            );
          })}
        </div>
        <span className="hidden shrink-0 px-1 text-2xs text-subtle sm:inline">{spec.product}</span>
        <div className="flex items-center rounded-sm bg-bg-subtle p-0.5">
          {INTERVALS.map((iv) => {
            const on = chartInterval === iv;
            return (
              <button
                key={iv}
                onClick={() => setChartInterval(iv)}
                className={`h-6 min-w-8 rounded-xs px-2 text-2xs font-semibold tracking-wide transition-colors duration-150 ${
                  on ? "bg-bg-hover text-accent" : "text-muted hover:text-fg"
                }`}
              >
                {iv}
              </button>
            );
          })}
        </div>
        <div className="ml-auto flex items-center gap-2">
          <span className="hidden text-2xs text-subtle sm:inline">
            {chartMode === "advanced" ? "BINANCE:PAXGUSDT" : "EMA 12/26"}
            {" · "}
            {source === "synthetic" ? "Synthetic" : "Binance"}
          </span>
          <div className="flex items-center rounded-sm bg-bg-subtle p-0.5">
            <button
              onClick={() => setChartMode("lite")}
              className={`h-6 rounded-xs px-2 text-2xs font-semibold transition-colors duration-150 ${
                chartMode === "lite" ? "bg-accent text-accent-fg" : "text-muted hover:text-fg"
              }`}
            >
              Lite
            </button>
            <button
              onClick={() => setChartMode("advanced")}
              className={`h-6 rounded-xs px-2 text-2xs font-semibold transition-colors duration-150 ${
                chartMode === "advanced" ? "bg-accent text-accent-fg" : "text-muted hover:text-fg"
              }`}
            >
              TradingView
            </button>
          </div>
        </div>
      </div>
      <div className="relative min-h-0 flex-1">
        {chartMode === "advanced" ? (
          <TradingViewWidget interval={chartInterval} symbol={spec.tv} />
        ) : (
          <CandleChart candles={series} quote={quote} position={position} />
        )}
        {loadingChart && (
          <div className="absolute right-3 top-3 rounded-sm bg-bg/80 px-2 py-1 text-2xs text-muted">
            Loading {chartInterval}
          </div>
        )}
      </div>
    </div>
  );
}
