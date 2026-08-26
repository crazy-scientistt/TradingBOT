import React, { useState, useEffect } from 'react';
import { Briefcase, TrendingUp, TrendingDown, RefreshCw } from 'lucide-react';
import { api } from '../../api/client';

export const TradesView: React.FC = () => {
  const [trades, setTrades] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchTrades = async () => {
    setLoading(true);
    try {
      const res = await api.getTrades();
      setTrades(res);
    } catch {
      // fallback
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTrades();
  }, []);

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
          <Briefcase size={20} color="#f0b90b" />
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
              Paper Trade Execution &amp; Fill History
            </h2>
            <span style={{ fontSize: '12px', color: '#9498a4' }}>
              Conservative execution records with 10bps fee drag &amp; 2bps simulated slippage
            </span>
          </div>
        </div>

        <button
          onClick={fetchTrades}
          disabled={loading}
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            padding: '6px 12px',
            backgroundColor: '#181a20',
            color: '#e2e4e8',
            border: '1px solid #2d3139',
            borderRadius: '6px',
            fontSize: '12px',
            cursor: 'pointer',
          }}
        >
          <RefreshCw size={13} className={loading ? 'spin' : ''} /> Refresh Trades
        </button>
      </div>

      {/* Trades Table */}
      <div
        style={{
          backgroundColor: '#0d0e12',
          border: '1px solid #1e222b',
          borderRadius: '8px',
          overflow: 'hidden',
        }}
      >
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12.5px' }}>
          <thead>
            <tr style={{ backgroundColor: '#121418', borderBottom: '1px solid #1e222b', color: '#9498a4' }}>
              <th style={{ padding: '12px 16px' }}>Order ID</th>
              <th style={{ padding: '12px 16px' }}>Side</th>
              <th style={{ padding: '12px 16px' }}>Quantity</th>
              <th style={{ padding: '12px 16px' }}>Fill Price</th>
              <th style={{ padding: '12px 16px' }}>Fee Paid</th>
              <th style={{ padding: '12px 16px' }}>Filled At</th>
            </tr>
          </thead>
          <tbody>
            {trades.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ padding: '24px', textAlign: 'center', color: '#676b78' }}>
                  No fills recorded in this paper session yet. Positions will open upon valid 15m signal approval.
                </td>
              </tr>
            ) : (
              trades.map((t, i) => (
                <tr
                  key={t.client_order_id || i}
                  style={{
                    borderBottom: '1px solid #181a1f',
                    backgroundColor: i % 2 === 0 ? 'transparent' : 'rgba(255, 255, 255, 0.01)',
                  }}
                >
                  <td style={{ padding: '12px 16px', fontFamily: 'monospace', color: '#f0b90b' }}>
                    {t.client_order_id}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span
                      style={{
                        padding: '2px 6px',
                        borderRadius: '3px',
                        fontSize: '11px',
                        backgroundColor: t.side === 'BUY' ? 'rgba(16, 185, 129, 0.15)' : 'rgba(239, 68, 68, 0.15)',
                        color: t.side === 'BUY' ? '#10b981' : '#ef4444',
                        fontWeight: 700,
                      }}
                    >
                      {t.side}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px', fontFamily: 'monospace', color: '#e2e4e8' }}>
                    {t.quantity} PAXG
                  </td>
                  <td style={{ padding: '12px 16px', fontFamily: 'monospace', color: '#f8fafc', fontWeight: 600 }}>
                    ${parseFloat(t.price).toFixed(2)}
                  </td>
                  <td style={{ padding: '12px 16px', fontFamily: 'monospace', color: '#9498a4' }}>
                    ${parseFloat(t.fee).toFixed(4)} USDT
                  </td>
                  <td style={{ padding: '12px 16px', color: '#676b78', fontFamily: 'monospace' }}>
                    {t.filled_at}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
};
