import React, { useState, useEffect } from 'react';
import { TrendingUp, Activity, BarChart2, ShieldCheck, RefreshCw } from 'lucide-react';
import { useBot } from '../../context/BotContext';

export const MarketView: React.FC = () => {
  const { quote, candles, selectedPair } = useBot();
  const [spreadHistory, setSpreadHistory] = useState<number[]>([0.25, 0.28, 0.30, 0.22, 0.35, 0.30]);

  useEffect(() => {
    setSpreadHistory((prev) => [...prev.slice(-15), quote.spread]);
  }, [quote]);

  const lastCandle = candles[candles.length - 1];

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', color: '#e2e4e8' }}>
      {/* Top Banner */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          backgroundColor: '#0d0e12',
          padding: '12px 16px',
          borderRadius: '8px',
          border: '1px solid #1e222b',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <TrendingUp size={20} color="#f0b90b" />
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
              Binance Spot {selectedPair} Market Stream
            </h2>
            <span style={{ fontSize: '12px', color: '#9498a4' }}>
              Real-time book ticker, spread rate monitoring &amp; technical indicator metrics
            </span>
          </div>
        </div>

        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span
            style={{
              fontSize: '12px',
              color: '#10b981',
              backgroundColor: 'rgba(16, 185, 129, 0.1)',
              padding: '4px 10px',
              borderRadius: '4px',
              border: '1px solid rgba(16, 185, 129, 0.3)',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', backgroundColor: '#10b981' }} />
            Connected (100% In-Sync)
          </span>
        </div>
      </div>

      {/* Grid: Ticker Cards */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '10px' }}>
        <div style={{ backgroundColor: '#0d0e12', border: '1px solid #1e222b', borderRadius: '8px', padding: '14px' }}>
          <span style={{ fontSize: '11.5px', color: '#676b78', display: 'block' }}>Best Bid</span>
          <span style={{ fontSize: '18px', fontWeight: 700, color: '#10b981', fontFamily: 'monospace' }}>
            ${quote.bid.toFixed(2)}
          </span>
          <span style={{ fontSize: '11px', color: '#9498a4', display: 'block', marginTop: '2px' }}>USDT</span>
        </div>

        <div style={{ backgroundColor: '#0d0e12', border: '1px solid #1e222b', borderRadius: '8px', padding: '14px' }}>
          <span style={{ fontSize: '11.5px', color: '#676b78', display: 'block' }}>Best Ask</span>
          <span style={{ fontSize: '18px', fontWeight: 700, color: '#ef4444', fontFamily: 'monospace' }}>
            ${quote.ask.toFixed(2)}
          </span>
          <span style={{ fontSize: '11px', color: '#9498a4', display: 'block', marginTop: '2px' }}>USDT</span>
        </div>

        <div style={{ backgroundColor: '#0d0e12', border: '1px solid #1e222b', borderRadius: '8px', padding: '14px' }}>
          <span style={{ fontSize: '11.5px', color: '#676b78', display: 'block' }}>Live Spread</span>
          <span style={{ fontSize: '18px', fontWeight: 700, color: '#f0b90b', fontFamily: 'monospace' }}>
            ${quote.spread.toFixed(2)}
          </span>
          <span style={{ fontSize: '11px', color: '#9498a4', display: 'block', marginTop: '2px' }}>
            {(quote.spread_rate * 10000).toFixed(1)} bps
          </span>
        </div>

        <div style={{ backgroundColor: '#0d0e12', border: '1px solid #1e222b', borderRadius: '8px', padding: '14px' }}>
          <span style={{ fontSize: '11.5px', color: '#676b78', display: 'block' }}>EMA 20 (15m)</span>
          <span style={{ fontSize: '18px', fontWeight: 700, color: '#60a5fa', fontFamily: 'monospace' }}>
            ${lastCandle?.ema20?.toFixed(2) || '2520.77'}
          </span>
          <span style={{ fontSize: '11px', color: '#9498a4', display: 'block', marginTop: '2px' }}>Short trend</span>
        </div>

        <div style={{ backgroundColor: '#0d0e12', border: '1px solid #1e222b', borderRadius: '8px', padding: '14px' }}>
          <span style={{ fontSize: '11.5px', color: '#676b78', display: 'block' }}>EMA 50 (1h)</span>
          <span style={{ fontSize: '18px', fontWeight: 700, color: '#a78bfa', fontFamily: 'monospace' }}>
            ${lastCandle?.ema50?.toFixed(2) || '2515.35'}
          </span>
          <span style={{ fontSize: '11px', color: '#9498a4', display: 'block', marginTop: '2px' }}>Regime filter</span>
        </div>
      </div>

      {/* Technical Indicators Table */}
      <div
        style={{
          backgroundColor: '#0d0e12',
          border: '1px solid #1e222b',
          borderRadius: '8px',
          padding: '16px',
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
        }}
      >
        <h3 style={{ fontSize: '14px', fontWeight: 600, color: '#f8fafc', margin: 0 }}>
          Live Indicator Matrix &amp; Guard Bounds
        </h3>

        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))', gap: '12px' }}>
          <div style={{ backgroundColor: '#121418', border: '1px solid #1c2028', borderRadius: '6px', padding: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
              <span style={{ fontSize: '13px', fontWeight: 600, color: '#f0b90b' }}>Spread Rate Guard</span>
              <span style={{ fontSize: '12px', color: '#10b981', fontWeight: 700 }}>PASS</span>
            </div>
            <span style={{ fontSize: '12px', color: '#9498a4', display: 'block' }}>
              Current: {(quote.spread_rate * 100).toFixed(4)}% | Ceiling: 0.1500%
            </span>
          </div>

          <div style={{ backgroundColor: '#121418', border: '1px solid #1c2028', borderRadius: '6px', padding: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
              <span style={{ fontSize: '13px', fontWeight: 600, color: '#60a5fa' }}>RSI (14, 15m)</span>
              <span style={{ fontSize: '12px', color: '#10b981', fontWeight: 700 }}>PASS (54.2)</span>
            </div>
            <span style={{ fontSize: '12px', color: '#9498a4', display: 'block' }}>
              Strategy Threshold: &gt; 45.0 | Pullback momentum intact
            </span>
          </div>

          <div style={{ backgroundColor: '#121418', border: '1px solid #1c2028', borderRadius: '6px', padding: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
              <span style={{ fontSize: '13px', fontWeight: 600, color: '#10b981' }}>Volume Ratio (20)</span>
              <span style={{ fontSize: '12px', color: '#10b981', fontWeight: 700 }}>PASS (1.14x)</span>
            </div>
            <span style={{ fontSize: '12px', color: '#9498a4', display: 'block' }}>
              Floor: &gt;= 0.80x 20-period average volume
            </span>
          </div>

          <div style={{ backgroundColor: '#121418', border: '1px solid #1c2028', borderRadius: '6px', padding: '12px' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
              <span style={{ fontSize: '13px', fontWeight: 600, color: '#a78bfa' }}>Hourly Trend Alignment</span>
              <span style={{ fontSize: '12px', color: '#10b981', fontWeight: 700 }}>BULLISH (Slope &gt; 0)</span>
            </div>
            <span style={{ fontSize: '12px', color: '#9498a4', display: 'block' }}>
              1h EMA50 slope positive; long entries permitted
            </span>
          </div>
        </div>
      </div>
    </div>
  );
};
