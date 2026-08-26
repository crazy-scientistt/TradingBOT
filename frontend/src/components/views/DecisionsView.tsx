import React, { useState, useEffect } from 'react';
import { CheckCircle2, ShieldAlert, Clock, RefreshCw } from 'lucide-react';
import { api } from '../../api/client';

export const DecisionsView: React.FC = () => {
  const [decisions, setDecisions] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  const fetchDecisions = async () => {
    setLoading(true);
    try {
      const res = await api.getDecisions(50);
      setDecisions(res);
    } catch {
      // fallback
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchDecisions();
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
          <CheckCircle2 size={20} color="#f0b90b" />
          <div>
            <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
              Idempotent Decision Chain Audit Ledger
            </h2>
            <span style={{ fontSize: '12px', color: '#9498a4' }}>
              Every candidate evaluation recorded into SQLite with deterministic hash provenance
            </span>
          </div>
        </div>

        <button
          onClick={fetchDecisions}
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
          <RefreshCw size={13} className={loading ? 'spin' : ''} /> Refresh Ledger
        </button>
      </div>

      {/* Decision Table */}
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
              <th style={{ padding: '12px 16px' }}>Decision ID</th>
              <th style={{ padding: '12px 16px' }}>Symbol</th>
              <th style={{ padding: '12px 16px' }}>Timeframe</th>
              <th style={{ padding: '12px 16px' }}>Candle Close Time</th>
              <th style={{ padding: '12px 16px' }}>Mode</th>
              <th style={{ padding: '12px 16px' }}>Recorded At</th>
            </tr>
          </thead>
          <tbody>
            {decisions.length === 0 ? (
              <tr>
                <td colSpan={6} style={{ padding: '24px', textAlign: 'center', color: '#676b78' }}>
                  No decision chain records in ledger yet. Start the bot to begin recording 15m evaluations.
                </td>
              </tr>
            ) : (
              decisions.map((d, i) => (
                <tr
                  key={d.id || i}
                  style={{
                    borderBottom: '1px solid #181a1f',
                    backgroundColor: i % 2 === 0 ? 'transparent' : 'rgba(255, 255, 255, 0.01)',
                  }}
                >
                  <td style={{ padding: '12px 16px', fontFamily: 'monospace', color: '#f0b90b' }}>
                    {d.id?.substring(0, 16)}...
                  </td>
                  <td style={{ padding: '12px 16px', fontWeight: 600, color: '#f8fafc' }}>
                    {d.symbol || 'PAXGUSDT'}
                  </td>
                  <td style={{ padding: '12px 16px', color: '#9498a4' }}>
                    {d.timeframe || '15m'}
                  </td>
                  <td style={{ padding: '12px 16px', color: '#e2e4e8', fontFamily: 'monospace' }}>
                    {d.candle_close_time || '2026-08-26T20:00:00Z'}
                  </td>
                  <td style={{ padding: '12px 16px' }}>
                    <span
                      style={{
                        padding: '2px 6px',
                        borderRadius: '3px',
                        fontSize: '11px',
                        backgroundColor: 'rgba(240, 185, 11, 0.1)',
                        color: '#f0b90b',
                        fontWeight: 700,
                      }}
                    >
                      {d.mode || 'PAPER'}
                    </span>
                  </td>
                  <td style={{ padding: '12px 16px', color: '#676b78', fontFamily: 'monospace' }}>
                    {d.created_at || new Date().toISOString()}
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
