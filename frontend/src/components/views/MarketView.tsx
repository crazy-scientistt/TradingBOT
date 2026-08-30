import React, { useState, useEffect, useCallback } from 'react';
import { TrendingUp } from 'lucide-react';
import { useBot } from '../../context/BotContext';
import { api } from '../../api/client';

const fmt = (v: number | null | undefined, decimals = 2): string =>
  v != null && Number.isFinite(v) ? v.toFixed(decimals) : 'â€”';

export const MarketView: React.FC = () => {
  const { quote, candles, dataStatus } = useBot();
  const [interval, setInterval] = useState<'15m' | '1h'>('15m');
  const [localCandles, setLocalCandles] = useState(candles);
  const [loading, setLoading] = useState(false);

  const fetchCandles = useCallback(async (iv: '15m' | '1h') => {
    setLoading(true);
    try {
      const rows = await api.getMarketCandles('PAXGUSDT', iv, 50);
      setLocalCandles(rows);
    } catch { /* keep previous */ }
    setLoading(false);
  }, []);

  useEffect(() => { setLocalCandles(candles); }, [candles]);
  useEffect(() => { fetchCandles(interval); }, [interval, fetchCandles]);

  const last = localCandles[localCandles.length - 1];
  const rsi14 = last?.rsi14 ?? null;
  const atr14 = last?.atr14 ?? null;
  const volRatio = last?.volumeRatio ?? null;
  const ema20v = last?.ema20 ?? null;
  const ema50v = last?.ema50 ?? null;
  const trend = ema20v != null && ema50v != null
    ? (ema20v > ema50v ? 'Bullish' : ema20v < ema50v ? 'Bearish' : 'Neutral')
    : null;

  if (!quote && localCandles.length === 0) {
    return (
      <div style={{ padding: '40px', textAlign: 'center', color: '#9498a4' }}>
        <TrendingUp size={32} color="#676b78" style={{ marginBottom: '12px' }} />
        <div style={{ fontSize: '14px' }}>Market data unavailable</div>
        <div style={{ fontSize: '12px', marginTop: '6px' }}>
          This view shows real quotes and candles once the market feed connects.
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', color: '#e2e4e8' }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        backgroundColor: '#0d0e12', padding: '12px 16px', borderRadius: '8px', border: '1px solid #1e222b',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <TrendingUp size={20} color="var(--gold-primary)" />
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#f8fafc' }}>PAXG/USDT Market Data</h2>
            <span style={{ fontSize: '12px', color: '#9498a4' }}>
              {quote ? 'Last observed: ' + new Date(quote.observed_at).toLocaleTimeString() : 'Waiting for quote data'}
            </span>
          </div>
        </div>
        <div style={{ display: 'flex', gap: '6px' }}>
          {(['15m', '1h'] as const).map(iv => (
            <button key={iv} onClick={() => setInterval(iv)} style={{
              padding: '4px 10px', borderRadius: '4px', fontSize: '12px', fontWeight: 600, cursor: 'pointer',
              border: interval === iv ? '1px solid rgba(61, 126, 255,0.5)' : '1px solid #22242a',
              backgroundColor: interval === iv ? 'rgba(61, 126, 255,0.08)' : '#141518',
              color: interval === iv ? 'var(--gold-primary)' : '#9498a4',
            }}>{iv}</button>
          ))}
        </div>
      </div>

      {dataStatus.error && (
        <div style={{ padding: '8px 12px', borderRadius: '6px', fontSize: '12px', color: '#fca5a5',
          border: '1px solid rgba(239,68,68,0.3)', backgroundColor: 'rgba(239,68,68,0.06)' }}>
          {dataStatus.error}
        </div>
      )}

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: '10px' }}>
        <div style={{ backgroundColor: '#0d0e12', border: '1px solid #1e222b', borderRadius: '8px', padding: '14px' }}>
          <span style={{ fontSize: '11.5px', color: '#676b78', display: 'block' }}>Best Bid</span>
          <span style={{ fontSize: '18px', fontWeight: 700, color: '#10b981', fontFamily: 'monospace' }}>{quote ? fmt(quote.bid) : 'â€”'}</span>
        </div>
        <div style={{ backgroundColor: '#0d0e12', border: '1px solid #1e222b', borderRadius: '8px', padding: '14px' }}>
          <span style={{ fontSize: '11.5px', color: '#676b78', display: 'block' }}>Best Ask</span>
          <span style={{ fontSize: '18px', fontWeight: 700, color: '#ef4444', fontFamily: 'monospace' }}>{quote ? fmt(quote.ask) : 'â€”'}</span>
        </div>
        <div style={{ backgroundColor: '#0d0e12', border: '1px solid #1e222b', borderRadius: '8px', padding: '14px' }}>
          <span style={{ fontSize: '11.5px', color: '#676b78', display: 'block' }}>Spread</span>
          <span style={{ fontSize: '18px', fontWeight: 700, color: 'var(--gold-primary)', fontFamily: 'monospace' }}>{quote ? fmt(quote.spread) : 'â€”'}</span>
          {quote && <span style={{ fontSize: '11px', color: '#9498a4', display: 'block' }}>{(quote.spread_rate * 10000).toFixed(1)} bps</span>}
        </div>
        <div style={{ backgroundColor: '#0d0e12', border: '1px solid #1e222b', borderRadius: '8px', padding: '14px' }}>
          <span style={{ fontSize: '11.5px', color: '#676b78', display: 'block' }}>EMA 20</span>
          <span style={{ fontSize: '18px', fontWeight: 700, color: '#60a5fa', fontFamily: 'monospace' }}>{fmt(ema20v)}</span>
        </div>
        <div style={{ backgroundColor: '#0d0e12', border: '1px solid #1e222b', borderRadius: '8px', padding: '14px' }}>
          <span style={{ fontSize: '11.5px', color: '#676b78', display: 'block' }}>EMA 50</span>
          <span style={{ fontSize: '18px', fontWeight: 700, color: '#a78bfa', fontFamily: 'monospace' }}>{fmt(ema50v)}</span>
        </div>
      </div>

      <div style={{ backgroundColor: '#0d0e12', border: '1px solid #1e222b', borderRadius: '8px', padding: '16px' }}>
        <h3 style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc', margin: '0 0 12px' }}>
          Technical Indicators {loading && <span style={{ fontSize: '11px', color: '#9498a4' }}>(loading...)</span>}
        </h3>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))', gap: '12px' }}>
          <div style={{ backgroundColor: '#121418', border: '1px solid #1c2028', borderRadius: '6px', padding: '12px' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: 'var(--gold-primary)' }}>RSI (14)</span>
            <span style={{ fontSize: '14px', fontWeight: 700, color: '#e2e4e8', display: 'block', marginTop: '4px' }}>
              {rsi14 != null ? rsi14.toFixed(1) : 'warming up'}
            </span>
          </div>
          <div style={{ backgroundColor: '#121418', border: '1px solid #1c2028', borderRadius: '6px', padding: '12px' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#60a5fa' }}>ATR (14)</span>
            <span style={{ fontSize: '14px', fontWeight: 700, color: '#e2e4e8', display: 'block', marginTop: '4px' }}>
              {atr14 != null ? atr14.toFixed(4) : 'warming up'}
            </span>
          </div>
          <div style={{ backgroundColor: '#121418', border: '1px solid #1c2028', borderRadius: '6px', padding: '12px' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#10b981' }}>Volume Ratio (20)</span>
            <span style={{ fontSize: '14px', fontWeight: 700, color: '#e2e4e8', display: 'block', marginTop: '4px' }}>
              {volRatio != null ? volRatio.toFixed(2) + 'x' : 'warming up'}
            </span>
          </div>
          <div style={{ backgroundColor: '#121418', border: '1px solid #1c2028', borderRadius: '6px', padding: '12px' }}>
            <span style={{ fontSize: '13px', fontWeight: 600, color: '#a78bfa' }}>Trend (EMA20 vs EMA50)</span>
            <span style={{ fontSize: '14px', fontWeight: 700, color: '#e2e4e8', display: 'block', marginTop: '4px' }}>
              {trend || 'insufficient data'}
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};

