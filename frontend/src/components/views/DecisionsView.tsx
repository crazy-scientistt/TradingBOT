import React, { useState, useEffect, useCallback } from 'react';
import { CheckCircle2, RefreshCw } from 'lucide-react';
import { api } from '../../api/client';

interface DecisionRow {
  id?: string;
  mode?: string;
  account_scope?: string;
  symbol?: string;
  timeframe?: string;
  candle_close_time?: string;
  created_at?: string;
  ai_decision?: string | null;
  ai_confidence?: number | null;
  ai_reason_codes?: string[];
  ai_model?: string;
  risk_approved?: boolean | null;
  risk_reason_codes?: string[];
  plan?: unknown;
}

export const DecisionsView: React.FC = () => {
  const [decisions, setDecisions] = useState<DecisionRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchDecisions = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getDecisions(50);
      setDecisions(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load the decision ledger.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void fetchDecisions(); }, [fetchDecisions]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', color: '#e2e4e8' }}>
      <div style={{
        display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        backgroundColor: '#0d0e12', padding: '12px 16px', borderRadius: '8px', border: '1px solid #1e222b',
      }}>
        <div>
          <h2 style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#f8fafc' }}>
            Decision Ledger
          </h2>
          <span style={{ fontSize: '12px', color: '#9498a4' }}>
            Every closed-candle evaluation, with its reasoning and risk verdict.
          </span>
        </div>
        <button onClick={fetchDecisions} disabled={loading} style={{
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
        <table style={{ width: '100%', borderCollapse: 'collapse', textAlign: 'left', fontSize: '12.5px', minWidth: '760px' }}>
          <thead>
            <tr style={{ backgroundColor: '#121418', borderBottom: '1px solid #1e222b', color: '#9498a4' }}>
              <th style={{ padding: '10px 12px' }}>Time</th>
              <th style={{ padding: '10px 12px' }}>Symbol</th>
              <th style={{ padding: '10px 12px' }}>AI Decision</th>
              <th style={{ padding: '10px 12px' }}>Reasons</th>
              <th style={{ padding: '10px 12px' }}>Risk</th>
            </tr>
          </thead>
          <tbody>
            {loading && decisions.length === 0 ? (
              <tr><td colSpan={5} style={{ padding: '24px', textAlign: 'center', color: '#676b78' }}>Loading ledger...</td></tr>
            ) : decisions.length === 0 ? (
              <tr><td colSpan={5} style={{ padding: '24px', textAlign: 'center', color: '#676b78' }}>
                No closed candle has been evaluated yet. Press Start Paper Trading to begin.
              </td></tr>
            ) : decisions.map((d, i) => (
              <tr key={d.id || i} style={{ borderBottom: '1px solid #181a1f', backgroundColor: i % 2 === 0 ? 'transparent' : 'rgba(255,255,255,0.01)' }}>
                <td style={{ padding: '10px 12px', color: '#676b78', fontFamily: 'monospace', whiteSpace: 'nowrap' }}>
                  {d.candle_close_time ? new Date(d.candle_close_time).toLocaleTimeString() : '—'}
                </td>
                <td style={{ padding: '10px 12px', fontWeight: 600, color: '#f8fafc' }}>
                  {d.symbol || '—'}
                  <span style={{ color: '#676b78', fontWeight: 400, fontSize: '11px' }}> {d.timeframe || ''}</span>
                </td>
                <td style={{ padding: '10px 12px' }}>
                  <span style={{
                    padding: '2px 6px', borderRadius: '3px', fontSize: '11px', fontWeight: 700,
                    backgroundColor: d.ai_decision === 'BUY' ? 'rgba(16,185,129,0.12)' : d.ai_decision === 'SELL' ? 'rgba(239,68,68,0.12)' : 'rgba(148,152,164,0.12)',
                    color: d.ai_decision === 'BUY' ? '#10b981' : d.ai_decision === 'SELL' ? '#ef4444' : '#9498a4',
                  }}>
                    {d.ai_decision || '—'}
                  </span>
                  {d.ai_confidence != null && <span style={{ color: '#9498a4', fontSize: '11px', marginLeft: '6px' }}>{Math.round(d.ai_confidence * 100)}%</span>}
                </td>
                <td style={{ padding: '10px 12px' }}>
                  {(d.ai_reason_codes || []).map((c, j) => (
                    <span key={j} style={{
                      fontSize: '10px', padding: '1px 5px', margin: '0 2px 2px 0', borderRadius: '3px', display: 'inline-block',
                      backgroundColor: 'rgba(96,165,250,0.1)', color: '#60a5fa', border: '1px solid rgba(96,165,250,0.25)',
                    }}>{c}</span>
                  ))}
                  {(d.ai_reason_codes || []).length === 0 && <span style={{ color: '#676b78' }}>—</span>}
                </td>
                <td style={{ padding: '10px 12px' }}>
                  {d.risk_approved == null ? (
                    <span style={{ color: '#676b78', fontSize: '11px' }}>pending</span>
                  ) : (
                    <span style={{ color: d.risk_approved ? '#10b981' : '#ef4444', fontSize: '11px', fontWeight: 700 }}>
                      {d.risk_approved ? 'APPROVED' : 'DENIED'}
                    </span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};
