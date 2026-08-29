import { useEffect, useRef } from "react";
import { ema } from "@/lib/trading/indicators";
import type { Candle, Position, Quote } from "@/lib/trading/types";
import type { UTCTimestamp } from "lightweight-charts";

type Props = {
  candles: Candle[];
  quote: Quote | null;
  position: Position | null;
};

type Theme = {
  bg: string;
  grid: string;
  muted: string;
  up: string;
  down: string;
  accent: string;
  fg: string;
  volumeUp: string;
  volumeDown: string;
};

function readTheme(): Theme {
  const s = getComputedStyle(document.documentElement);
  const v = (name: string, fallback: string) => s.getPropertyValue(name).trim() || fallback;
  return {
    bg: v("--color-bg-elevated", "#0b1018"),
    grid: v("--color-border", "#1c2436"),
    muted: v("--color-muted", "#8b93a7"),
    up: v("--color-up", "#0ecb81"),
    down: v("--color-down", "#f6465d"),
    accent: v("--color-accent", "#3d7eff"),
    fg: v("--color-fg", "#ffffff"),
    volumeUp: "rgba(14, 203, 129, 0.28)",
    volumeDown: "rgba(246, 70, 93, 0.28)",
  };
}

function asTime(t: number): UTCTimestamp {
  return Math.floor(t / 1000) as UTCTimestamp;
}

function toBar(c: Candle) {
  return {
    time: asTime(c.t),
    open: c.o,
    high: c.h,
    low: c.l,
    close: c.c,
  };
}

function toVol(c: Candle) {
  return {
    time: asTime(c.t),
    value: c.v,
    color: c.c >= c.o ? "rgba(14, 203, 129, 0.28)" : "rgba(246, 70, 93, 0.28)",
  };
}

function emaLine(candles: Candle[], period: number) {
  const values = ema(
    candles.map((c) => c.c),
    period,
  );
  return candles.map((c, i) => ({
    time: asTime(c.t),
    value: values[i] ?? c.c,
  }));
}

export function CandleChart({ candles, quote, position }: Props) {
  const hostRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<{
    chart: import("lightweight-charts").IChartApi;
    candle: import("lightweight-charts").ISeriesApi<"Candlestick">;
    volume: import("lightweight-charts").ISeriesApi<"Histogram">;
    emaFast: import("lightweight-charts").ISeriesApi<"Line">;
    emaSlow: import("lightweight-charts").ISeriesApi<"Line">;
    lines: import("lightweight-charts").IPriceLine[];
    lastT: number;
    len: number;
  } | null>(null);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let disposed = false;
    let ro: ResizeObserver | null = null;

    void import("lightweight-charts").then((lwc) => {
      if (disposed || !hostRef.current) return;
      const el = hostRef.current;
      const theme = readTheme();
      const chart = lwc.createChart(el, {
        width: Math.max(1, el.clientWidth),
        height: Math.max(1, el.clientHeight),
        layout: {
          background: { color: theme.bg },
          textColor: theme.muted,
          fontFamily: "JetBrains Mono, ui-monospace, monospace",
          fontSize: 11,
          attributionLogo: false,
        },
        grid: {
          vertLines: { color: theme.grid },
          horzLines: { color: theme.grid },
        },
        crosshair: { mode: lwc.CrosshairMode.Normal },
        rightPriceScale: {
          borderColor: theme.grid,
          scaleMargins: { top: 0.08, bottom: 0.22 },
        },
        timeScale: {
          borderColor: theme.grid,
          timeVisible: true,
          secondsVisible: false,
        },
        localization: { priceFormatter: (p: number) => p.toFixed(2) },
      });
      const candle = chart.addSeries(lwc.CandlestickSeries, {
        upColor: theme.up,
        downColor: theme.down,
        borderUpColor: theme.up,
        borderDownColor: theme.down,
        wickUpColor: theme.up,
        wickDownColor: theme.down,
      });
      const volume = chart.addSeries(lwc.HistogramSeries, {
        priceFormat: { type: "volume" },
        priceScaleId: "vol",
      });
      chart.priceScale("vol").applyOptions({
        scaleMargins: { top: 0.82, bottom: 0 },
      });
      const emaFast = chart.addSeries(lwc.LineSeries, {
        color: theme.accent,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      const emaSlow = chart.addSeries(lwc.LineSeries, {
        color: theme.muted,
        lineWidth: 1,
        priceLineVisible: false,
        lastValueVisible: false,
        crosshairMarkerVisible: false,
      });
      chartRef.current = { chart, candle, volume, emaFast, emaSlow, lines: [], lastT: 0, len: 0 };
      const resize = () => {
        const w = el.clientWidth;
        const h = el.clientHeight;
        if (w > 8 && h > 8) chart.resize(w, h, true);
      };
      resize();
      requestAnimationFrame(resize);
      ro = new ResizeObserver(resize);
      ro.observe(el);
    });

    return () => {
      disposed = true;
      ro?.disconnect();
      chartRef.current?.chart.remove();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    const api = chartRef.current;
    if (!api || candles.length < 2) return;
    const last = candles[candles.length - 1];
    const incremental =
      api.len > 0 &&
      (candles.length === api.len || candles.length === api.len + 1) &&
      last.t >= api.lastT;
    if (incremental) {
      api.candle.update(toBar(last));
      api.volume.update(toVol(last));
    } else {
      api.candle.setData(candles.map(toBar));
      api.volume.setData(candles.map(toVol));
      api.chart.timeScale().fitContent();
    }
    api.emaFast.setData(emaLine(candles, 12));
    api.emaSlow.setData(emaLine(candles, 26));
    api.lastT = last.t;
    api.len = candles.length;
  }, [candles]);

  useEffect(() => {
    const api = chartRef.current;
    if (!api) return;
    for (const line of api.lines) api.candle.removePriceLine(line);
    api.lines = [];
    const theme = readTheme();
    if (position) {
      api.lines.push(
        api.candle.createPriceLine({
          price: position.entry,
          color: theme.accent,
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: "ENTRY",
        }),
        api.candle.createPriceLine({
          price: position.stop,
          color: theme.down,
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: "STOP",
        }),
        api.candle.createPriceLine({
          price: position.take,
          color: theme.up,
          lineWidth: 1,
          lineStyle: 2,
          axisLabelVisible: true,
          title: "TAKE",
        }),
      );
    }
  }, [position]);

  useEffect(() => {
    const api = chartRef.current;
    if (!api || !quote || candles.length === 0) return;
    const last = candles[candles.length - 1];
    api.candle.update({
      time: asTime(last.t),
      open: last.o,
      high: Math.max(last.h, quote.last),
      low: Math.min(last.l, quote.last),
      close: quote.last,
    });
  }, [quote, candles]);

  return (
    <div className="relative h-full w-full bg-bg-elevated">
      <div ref={hostRef} className="absolute inset-0" />
      {candles.length < 2 && (
        <div className="absolute inset-0 flex items-center justify-center text-xs text-muted">
          Waiting for a verified candle series.
        </div>
      )}
    </div>
  );
}
