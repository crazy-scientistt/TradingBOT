import { useShallow } from "zustand/react/shallow";
import { CandleChart } from "./CandleChart";
import { TradingViewWidget } from "./TradingViewWidget";
import { useDesk } from "@/lib/trading/store";
import { INTERVALS } from "@/lib/trading/types";

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
    setChartInterval,
    setChartMode,
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
      setChartInterval: s.setChartInterval,
      setChartMode: s.setChartMode,
    })),
  );
  const series = chartInterval === "1m" ? candles : chartCandles;
  const source = chartInterval === "1m" ? feedSource : chartSource;

  return (
    <div className="flex h-full min-h-0 flex-col bg-bg">
      <div className="flex h-9 shrink-0 items-center gap-1 overflow-x-auto border-b border-border px-2">
        <span className="shrink-0 px-1.5 text-xs font-semibold tracking-tight">PAXG/USDT</span>
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
          <TradingViewWidget interval={chartInterval} />
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
