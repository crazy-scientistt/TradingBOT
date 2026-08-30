import React, { useState, useEffect, useCallback } from 'react';
import { Briefcase, RefreshCw } from 'lucide-react';
import { api } from '../../api/client';

interface TradeRow {
  client_order_id?: string;
  side?: string;
  status?: string;
  quantity?: string | null;
  price?: string | null;
  fee?: string | null;
  filled_at?: string | null;
}

const fmtNum = (v: string | null | undefined, decimals = 2): string => {
  if (v == null || v === '') return '—';
  const n = Number(v);
  return Number.isFinite(n) ? n.toFixed(decimals) : '—';
};

export const TradesView: React.FC = () => {
  const [trades, setTrades] = useState<TradeRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchTrades = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getTrades();
      setTrades(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load trade history.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void fetchTrades(); }, [fetchTrades]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', color: '#e2e4e8' }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        backgroundColor: '#0d0e12', padding: '12px 16px', borderRadius: '8px', border: '1px solid #1e222b',
      }}>
        <div>
          <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
            Paper Trade History
          </h2>
          <span style={{ fontSize: '12px', color: '#9498a4' }}>
            Filled paper orders, saved durably across restarts.
          </span>
        </div>
        <button onClick={fetchTrades} disabled={loading} style={{
          display: 'flex', alignItems: 'center', gap: '6px', padding: '6px 12px',
          backgroundColor: '#181a20', color: '#e2e4e8', border: '1px solid #2d3139',
          borderRadius: '6px', fontSize: '12px', cursor: 'pointer',
        }}>
          <RefreshCw size={13} /> Refresh
        </button>
      </div>

      {error && (
        <div style={{ padding: '8px 12px', borderRadius: '6px', fontSize: '12px', color: '#fca5a5',
          border: '1px solid rgba(239,68,68,0.3)', backgroundColor: 'rgba(239,68,68,0.06)' }}>
          {error}
        </div>
      )}

      <div style={{ backgroundColor: '#0d0e12', border: '1px solid #1e222b', borderRadius: '8px', overflow: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12.5px', minWidth: '680px' }}>
          <thead>
            <tr style={{ backgroundColor: '#121418', borderBottom: '1px solid #1e222b', color: '#9498a4' }}>
              <th style={{ padding: '10px 12px' }}>Order ID</th>
              <th style={{ padding: '10px 12px' }}>Side</th>
              <th style={{ padding: '10px 12px' }}>Status</th>
              <th style={{ padding: '10px 12px' }}>Quantity</th>
              <th style={{ padding: '10px 12px' }}>Fill Price</th>
              <th style={{ padding: '10px 12px' }}>Fee</th>
              <th style={{ padding: '10px 12px' }}>Time</th>
            </tr>
          </thead>
          <tbody>
            {loading && trades.length === 0 ? (
              <tr><td colSpan={7} style={{ padding: '24px', textAlign: 'center', color: '#676b78' }}>Loading trade history...</td></tr>
            ) : trades.length === 0 ? (
              <tr><td colSpan={7} style={{ padding: '24px', textAlign: 'center', color: '#676b78' }}>
                No paper orders have been filled yet.
              </td></tr>
            ) : trades.map((t, i) => (
              <tr key={t.client_order_id || i} style={{ borderBottom: '1px solid #181a1f', backgroundColor: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
                <td style={{ padding: '10px 12px', fontFamily: 'monospace', color: 'var(--gold-primary)', fontSize: '11px' }}>
                  {t.client_order_id || '—'}
                </td>
                <td style={{ padding: '10px 12px' }}>
                  <span style={{
                    padding: '2px 6px', borderRadius: '3px', fontSize: '11px',
                    backgroundColor: t.side === 'BUY' ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
                    color: t.side === 'BUY' ? '#10b981' : '#ef4444', fontWeight: 700,
                  }}>{t.side || '—'}</span>
                </td>
                <td style={{ padding: '10px 12px', color: '#9498a4', fontSize: '11px' }}>{t.status || '—'}</td>
                <td style={{ padding: '10px 12px', fontFamily: 'monospace', color: '#e2e4e8' }}>{fmtNum(t.quantity, 4)}</td>
                <td style={{ padding: '10px 12px', fontFamily: 'monospace', color: '#f8fafc' }}>{fmtNum(t.price)}</td>
                <td style={{ padding: '10px 12px', fontFamily: 'monospace', color: '#9498a4' }}>{fmtNum(t.fee, 4)}</td>
                <td style={{ padding: '10px 12px', color: '#676b78', fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                  {t.filled_at ? new Date(t.filled_at).toLocaleTimeString() : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
