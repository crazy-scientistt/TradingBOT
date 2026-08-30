import React, { useEffect, useState } from 'react';
import { TrendingUp } from 'lucide-react';
import { useBot } from '../../context/BotContext';
import { toBinanceSymbol } from '../../api/client';

const fmt = (v: number | null | undefined, decimals = 2): string =>
  v != null && Number.isFinite(v) ? v.toFixed(decimals) : '—';

export const MarketView: React.FC = () => {
  const { quote, selectedPair } = useBot();
  const [symbol, setSymbol] = useState(`BINANCE:${toBinanceSymbol(selectedPair)}`);
  const [draft, setDraft] = useState(`BINANCE:${toBinanceSymbol(selectedPair)}`);

  useEffect(() => {
    const next = `BINANCE:${toBinanceSymbol(selectedPair)}`;
    setSymbol(next);
    setDraft(next);
  }, [selectedPair]);

  const src =
    `https://s.tradingview.com/widgetembed/?symbol=${encodeURIComponent(symbol)}` +
    `&interval=15&theme=dark&style=1&locale=en&symboledit=1` +
    `&hideideas=1&hidesidetoolbar=0&withdateranges=1&toolbarbg=0b0c0e`;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', color: '#e2e4e8', minHeight: 0 }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center', flexWrap: 'wrap', gap: '10px',
        backgroundColor: '#0d0e12', padding: '12px 16px', borderRadius: '8px', border: '1px solid #1e222b',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <TrendingUp size={20} color="var(--gold-primary)" />
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
              TradingView · {symbol}
            </h2>
            <span style={{ fontSize: '12px', color: '#9498a4' }}>
              Search any Binance pair, NASDAQ, NYSE, or FX ticker. Use the chart toolbar for timeframe.
            </span>
          </div>
        </div>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            const next = draft.trim().toUpperCase();
            if (next) setSymbol(next.includes(':') ? next : `BINANCE:${next}`);
          }}
          style={{ display: 'flex', gap: '6px', alignItems: 'center' }}
        >
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            placeholder="BINANCE:ETHUSDT or NASDAQ:AAPL"
            style={{
              width: '220px',
              backgroundColor: '#121418',
              color: '#f8fafc',
              border: '1px solid #2d3139',
              borderRadius: '4px',
              padding: '6px 8px',
              fontSize: '12px',
              fontFamily: 'var(--font-mono)',
            }}
          />
          <button
            type="submit"
            style={{
              padding: '6px 10px',
              borderRadius: '4px',
              border: '1px solid rgba(61,126,255,0.45)',
              backgroundColor: 'rgba(61,126,255,0.12)',
              color: 'var(--gold-primary)',
              fontWeight: 700,
              fontSize: '12px',
              cursor: 'pointer',
            }}
          >
            Load
          </button>
        </form>
      </div>

      {quote && symbol.endsWith(toBinanceSymbol(selectedPair)) && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, minmax(0, 1fr))', gap: '10px' }}>
          <QuoteTile label="Best Bid" value={fmt(quote.bid)} color="#10b981" />
          <QuoteTile label="Best Ask" value={fmt(quote.ask)} color="#ef4444" />
          <QuoteTile label="Spread" value={fmt(quote.spread)} color="var(--gold-primary)" />
        </div>
      )}

      <iframe
        title={`TradingView ${symbol}`}
        src={src}
        style={{
          width: '100%',
          height: 'min(68vh, 640px)',
          border: '1px solid #1e222b',
          borderRadius: '8px',
          backgroundColor: '#0b0c0e',
        }}
      />
    </div>
  );
};

const QuoteTile: React.FC<{ label: string; value: string; color: string }> = ({ label, value, color }) => (
  <div style={{ backgroundColor: '#0d0e12', border: '1px solid #1e222b', borderRadius: '8px', padding: '12px 14px' }}>
    <span style={{ fontSize: '11.5px', color: '#676b78', display: 'block' }}>{label}</span>
    <span style={{ fontSize: '18px', fontWeight: 700, color, fontFamily: 'monospace' }}>{value}</span>
  </div>
);
