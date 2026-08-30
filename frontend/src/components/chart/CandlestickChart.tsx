import React, { useCallback, useEffect, useRef, useState } from 'react';
import { Maximize2, Minimize2 } from 'lucide-react';
import {
  ColorType,
  CrosshairMode,
  IChartApi,
  ISeriesApi,
  LineStyle,
  PriceScaleMode,
  UTCTimestamp,
  createChart,
} from 'lightweight-charts';
import { Candle, PositionDetails, Quote } from '../../types/dashboard';
import { api } from '../../api/client';
import { ChartControls } from './ChartControls';

interface CandlestickChartProps {
  candles: Candle[];
  quote?: Quote | null;
  position?: PositionDetails | null;
}

const TIMEFRAMES = ['1m', '5m', '15m', '1h', '4h', '1D'] as const;
type ChartTf = (typeof TIMEFRAMES)[number];

const toApiInterval = (tf: ChartTf): string => (tf === '1D' ? '1d' : tf);

const toUnix = (candle: Candle): UTCTimestamp => {
  const raw = candle.openTime || candle.fullTime || candle.closeTime;
  const ms = raw ? Date.parse(raw) : NaN;
  if (Number.isFinite(ms)) {
    return Math.floor((candle.openTime ? ms : ms) / 1000) as UTCTimestamp;
  }
  return Math.floor(Date.now() / 1000) as UTCTimestamp;
};

const toBar = (candle: Candle) => ({
  time: toUnix(candle),
  open: candle.open,
  high: candle.high,
  low: candle.low,
  close: candle.close,
});

const toVolume = (candle: Candle) => ({
  time: toUnix(candle),
  value: candle.volume,
  color: candle.close >= candle.open ? 'rgba(38, 166, 154, 0.5)' : 'rgba(239, 83, 80, 0.5)',
});

const scaleOptions = (mode: string) => {
  if (mode === 'log') {
    return { mode: PriceScaleMode.Logarithmic, autoScale: true };
  }
  if (mode === '%') {
    return { mode: PriceScaleMode.Percentage, autoScale: true };
  }
  return { mode: PriceScaleMode.Normal, autoScale: true };
};

export const CandlestickChart: React.FC<CandlestickChartProps> = ({
  candles: seedCandles,
  quote,
  position,
}) => {
  const shellRef = useRef<HTMLDivElement | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const candleSeries = useRef<ISeriesApi<'Candlestick'> | null>(null);
  const volumeSeries = useRef<ISeriesApi<'Histogram'> | null>(null);
  const ema20Series = useRef<ISeriesApi<'Line'> | null>(null);
  const ema50Series = useRef<ISeriesApi<'Line'> | null>(null);
  const stickToLive = useRef(true);
  const replacingData = useRef(false);
  const lastIndexRef = useRef(0);
  const [activeTf, setActiveTf] = useState<ChartTf>('15m');
  const [scaleMode, setScaleMode] = useState('auto');
  const [rows, setRows] = useState<Candle[]>(seedCandles);
  const [liveQuote, setLiveQuote] = useState<Quote | null>(quote ?? null);
  const [hover, setHover] = useState<Candle | null>(null);
  const [status, setStatus] = useState('Connecting live feed…');
  const [fullscreen, setFullscreen] = useState(false);
  const [tvMode, setTvMode] = useState(false);

  const applyBars = useCallback((nextRows: Candle[], fit = false) => {
    if (!candleSeries.current || !chartRef.current) return;
    const unique = new Map<number, Candle>();
    for (const row of nextRows) unique.set(toUnix(row), row);
    const ordered = [...unique.values()].sort((a, b) => toUnix(a) - toUnix(b));
    lastIndexRef.current = Math.max(ordered.length - 1, 0);
    const scale = chartRef.current.timeScale();
    const previous = scale.getVisibleLogicalRange();
    const pinned = stickToLive.current;
    replacingData.current = true;
    candleSeries.current.setData(ordered.map(toBar));
    volumeSeries.current?.setData(ordered.map(toVolume));
    ema20Series.current?.setData(
      ordered
        .filter((row) => row.ema20 != null)
        .map((row) => ({ time: toUnix(row), value: row.ema20 as number })),
    );
    ema50Series.current?.setData(
      ordered
        .filter((row) => row.ema50 != null)
        .map((row) => ({ time: toUnix(row), value: row.ema50 as number })),
    );
    if (fit || !previous) {
      scale.fitContent();
      stickToLive.current = true;
    } else if (pinned) {
      scale.scrollToRealTime();
    } else {
      scale.setVisibleLogicalRange(previous);
    }
    replacingData.current = false;
  }, []);

  const load = useCallback(async (tf: ChartTf) => {
    try {
      const data = await api.getMarketCandles('PAXGUSDT', toApiInterval(tf), 500);
      const next = Array.isArray(data) ? data : [];
      setRows(next);
      applyBars(next, true);
    } catch {
      /* keep previous bars */
    }
  }, [applyBars]);

  useEffect(() => {
    if (activeTf === '15m' && seedCandles.length && rows.length === 0) {
      setRows(seedCandles);
      applyBars(seedCandles, true);
    }
  }, [activeTf, seedCandles, rows.length, applyBars]);

  useEffect(() => {
    void load(activeTf);
  }, [activeTf, load]);

  useEffect(() => {
    if (quote) setLiveQuote(quote);
  }, [quote]);

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const chart = createChart(el, {
      width: el.clientWidth,
      height: el.clientHeight || 460,
      layout: {
        background: { type: ColorType.Solid, color: '#0b0c0e' },
        textColor: '#9498a4',
        fontFamily: 'IBM Plex Mono, ui-monospace, monospace',
      },
      grid: {
        vertLines: { color: '#151619' },
        horzLines: { color: '#17181c' },
      },
      crosshair: { mode: CrosshairMode.Normal },
      rightPriceScale: { borderColor: '#22242a', ...scaleOptions('auto') },
      timeScale: {
        borderColor: '#22242a',
        timeVisible: true,
        secondsVisible: false,
        rightOffset: 4,
        barSpacing: 8,
        minBarSpacing: 3,
        lockVisibleTimeRangeOnResize: true,
      },
      handleScroll: {
        mouseWheel: true,
        pressedMouseMove: true,
        horzTouchDrag: true,
        vertTouchDrag: true,
      },
      handleScale: {
        axisPressedMouseMove: true,
        mouseWheel: true,
        pinch: true,
        axisDoubleClickReset: true,
      },
    });
    const candles = chart.addCandlestickSeries({
      upColor: '#26a69a',
      downColor: '#ef5350',
      wickUpColor: '#26a69a',
      wickDownColor: '#ef5350',
      borderVisible: false,
    });
    const volume = chart.addHistogramSeries({
      priceFormat: { type: 'volume' },
      priceScaleId: 'volume',
    });
    chart.priceScale('volume').applyOptions({
      scaleMargins: { top: 0.78, bottom: 0 },
    });
    const ema20 = chart.addLineSeries({
      color: '#38bdf8',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    const ema50 = chart.addLineSeries({
      color: '#f59e0b',
      lineWidth: 2,
      priceLineVisible: false,
      lastValueVisible: false,
    });
    chartRef.current = chart;
    candleSeries.current = candles;
    volumeSeries.current = volume;
    ema20Series.current = ema20;
    ema50Series.current = ema50;

    chart.timeScale().subscribeVisibleLogicalRangeChange((range) => {
      if (replacingData.current || !range) return;
      stickToLive.current = range.to >= lastIndexRef.current - 2;
    });

    chart.subscribeCrosshairMove((param) => {
      if (!param.time) {
        setHover(null);
        return;
      }
      const bar = param.seriesData.get(candles) as
        | { open: number; high: number; low: number; close: number }
        | undefined;
      if (!bar) return;
      setHover({
        time: String(param.time),
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
        volume: 0,
        ema20: null,
        ema50: null,
        rsi14: null,
        atr14: null,
        volumeRatio: null,
      });
    });

    const resize = () => {
      if (!containerRef.current || !chartRef.current) return;
      chartRef.current.applyOptions({
        width: containerRef.current.clientWidth,
        height: containerRef.current.clientHeight || 460,
      });
    };
    const observer = new ResizeObserver(resize);
    observer.observe(el);
    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
    };
    // Chart is created once; timeframe changes only swap data.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    const onChange = () => {
      setFullscreen(document.fullscreenElement === shellRef.current);
    };
    document.addEventListener('fullscreenchange', onChange);
    return () => document.removeEventListener('fullscreenchange', onChange);
  }, []);

  useEffect(() => {
    const series = candleSeries.current;
    if (!series) return;
    const lines: ReturnType<ISeriesApi<'Candlestick'>['createPriceLine']>[] = [];
    if (position) {
      lines.push(series.createPriceLine({
        price: position.entry, color: '#38bdf8', lineWidth: 1,
        lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: 'entry',
      }));
      if (position.stop != null) {
        lines.push(series.createPriceLine({
          price: position.stop, color: '#ef5350', lineWidth: 1,
          lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: 'stop',
        }));
      }
      if (position.target != null) {
        lines.push(series.createPriceLine({
          price: position.target, color: '#22c55e', lineWidth: 1,
          lineStyle: LineStyle.Dashed, axisLabelVisible: true, title: 'target',
        }));
      }
    }
    return () => {
      lines.forEach((line) => series.removePriceLine(line));
    };
  }, [position]);

  useEffect(() => {
    const interval = toApiInterval(activeTf);
    const dispose = api.streamMarket({
      onSnapshot: (payload) => {
        if (payload.quote) setLiveQuote(payload.quote);
        const forming = payload.forming?.[interval];
        if (forming) {
          setRows((previous) => {
            const next = upsertCandle(previous, forming);
            lastIndexRef.current = Math.max(next.length - 1, 0);
            candleSeries.current?.update(toBar(forming));
            volumeSeries.current?.update(toVolume(forming));
            if (forming.ema20 != null) {
              ema20Series.current?.update({ time: toUnix(forming), value: forming.ema20 });
            }
            if (forming.ema50 != null) {
              ema50Series.current?.update({ time: toUnix(forming), value: forming.ema50 });
            }
            if (stickToLive.current) chartRef.current?.timeScale().scrollToRealTime();
            return next;
          });
        }
        setStatus('Live Binance feed');
      },
      onQuote: (next) => {
        setLiveQuote(next);
        setStatus('Live Binance feed');
      },
      onKline: (bar) => {
        if ((bar.interval || interval) !== interval) return;
        setRows((previous) => {
          const next = upsertCandle(previous, bar);
          lastIndexRef.current = Math.max(next.length - 1, 0);
          candleSeries.current?.update(toBar(bar));
          volumeSeries.current?.update(toVolume(bar));
          if (stickToLive.current) chartRef.current?.timeScale().scrollToRealTime();
          return next;
        });
      },
      onError: (error) => setStatus(error.message),
    });
    return dispose;
  }, [activeTf]);

  useEffect(() => {
    chartRef.current?.priceScale('right').applyOptions(scaleOptions(scaleMode));
  }, [scaleMode]);

  useEffect(() => {
    chartRef.current?.timeScale().applyOptions({
      secondsVisible: activeTf === '1m',
    });
  }, [activeTf]);

  const toggleFullscreen = async () => {
    const shell = shellRef.current;
    if (!shell) return;
    try {
      if (document.fullscreenElement === shell) {
        await document.exitFullscreen();
      } else {
        await shell.requestFullscreen();
      }
    } catch {
      setFullscreen((value) => !value);
    }
  };

  const last = hover || rows[rows.length - 1];
  const lastClose = liveQuote ? (liveQuote.bid + liveQuote.ask) / 2 : last?.close;
  const bull = last != null && last.close >= last.open;
  const chartHeight = fullscreen ? 'calc(100vh - 96px)' : '460px';

  return (
    <div
      ref={shellRef}
      className="dashboard-card"
      style={{
        flex: 1,
        display: 'flex',
        flexDirection: 'column',
        minWidth: 0,
        backgroundColor: '#0b0c0e',
        height: fullscreen ? '100vh' : undefined,
        zIndex: fullscreen ? 1000 : undefined,
      }}
    >
      <div style={{
        padding: '10px 16px 6px 16px',
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'flex-start',
        borderBottom: '1px solid rgba(255, 255, 255, 0.04)',
      }}>
        <div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '3px' }}>
            <span style={{ fontSize: '14.5px', fontWeight: 700, color: '#f8fafc' }}>
              PAXG / USDT · {activeTf}
            </span>
            <span style={{ fontSize: '11px', color: '#676b78' }}>{status}</span>
          </div>
          {last && (
            <div style={{
              display: 'flex',
              alignItems: 'center',
              gap: '10px',
              fontSize: '11px',
              fontFamily: 'var(--font-mono)',
              color: '#9498a4',
            }}>
              <span>O <span style={{ color: '#d1d5db' }}>{last.open.toFixed(2)}</span></span>
              <span>H <span style={{ color: '#d1d5db' }}>{last.high.toFixed(2)}</span></span>
              <span>L <span style={{ color: '#d1d5db' }}>{last.low.toFixed(2)}</span></span>
              <span>C <span style={{ color: bull ? '#22c55e' : '#ef5350', fontWeight: 600 }}>{last.close.toFixed(2)}</span></span>
            </div>
          )}
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <span style={{
            fontSize: '17px',
            fontWeight: 700,
            color: '#f8fafc',
            fontFamily: 'var(--font-mono)',
          }}>
            {lastClose != null
              ? lastClose.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
              : '—'}
          </span>
          <button
            onClick={() => setTvMode((value) => !value)}
            style={{
              background: tvMode ? 'rgba(61,126,255,0.15)' : 'transparent',
              border: '1px solid #1c2330',
              color: tvMode ? 'var(--gold-primary)' : '#9498a4',
              cursor: 'pointer',
              padding: '3px 8px',
              fontSize: '10px',
              fontWeight: 700,
              borderRadius: '4px',
            }}
            title="TradingView"
          >
            TV
          </button>
          <button
            onClick={() => void toggleFullscreen()}
            style={{ background: 'transparent', border: 'none', color: '#9498a4', cursor: 'pointer', padding: '4px' }}
            title={fullscreen ? 'Exit fullscreen' : 'Fullscreen'}
          >
            {fullscreen ? <Minimize2 size={15} /> : <Maximize2 size={15} />}
          </button>
        </div>
      </div>
      {tvMode ? (
        <iframe
          title="TradingView PAXGUSDT"
          src={`https://s.tradingview.com/widgetembed/?symbol=BINANCE%3APAXGUSDT&interval=${activeTf === '1D' ? 'D' : activeTf === '4h' ? '240' : activeTf === '1h' ? '60' : activeTf === '5m' ? '5' : activeTf === '1m' ? '1' : '15'}&theme=dark&style=1&locale=en&hideideas=1`}
          style={{ width: '100%', height: chartHeight, border: 0, backgroundColor: '#0b0c0e' }}
        />
      ) : (
        <div
          ref={containerRef}
          style={{ width: '100%', height: chartHeight, flex: fullscreen ? 1 : undefined, backgroundColor: '#0b0c0e' }}
        />
      )}
      <ChartControls
        activeTimeframe={activeTf}
        onSelectTimeframe={(tf) => setActiveTf(tf as ChartTf)}
        activeScaleMode={scaleMode}
        onSelectScaleMode={setScaleMode}
      />
    </div>
  );
};

function upsertCandle(rows: Candle[], incoming: Candle): Candle[] {
  if (!incoming.openTime && !incoming.fullTime) return rows;
  const key = toUnix(incoming);
  const next = [...rows];
  const index = next.findIndex((row) => toUnix(row) === key);
  if (index >= 0) next[index] = { ...next[index], ...incoming };
  else next.push(incoming);
  return next;
}
