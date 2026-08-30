import React from 'react';
import { useBot } from '../../context/BotContext';

const stateLabel = (state: string | null | undefined): string => {
  switch (state) {
    case 'RUNNING_FLAT': return 'Watching the market — no position';
    case 'RUNNING_OPEN': return 'Holding a position';
    case 'PAPER_READY': return 'Ready to start paper trading';
    case 'COOLDOWN': return 'Cooling down after a trade';
    case 'RISK_HALTED': return 'Halted — daily risk limit reached';
    case 'DATA_HALTED': return 'Halted — market data unavailable';
    case 'EMERGENCY_STOPPED': return 'Emergency stopped';
    case 'BOOTING': return 'Starting up...';
    case 'DISARMED': return 'Stopped';
    case 'AUTONOMY_SUSPENDED': return 'Autonomy paused — waiting for review';
    case 'QUARANTINE': return 'Strategy quarantined after rollback';
    default: return state ? state.replace(/_/g, ' ').toLowerCase() : 'Unknown';
  }
};

const actionColor = (action: string): string => {
  const a = action.toUpperCase();
  if (a.includes('BUY') || a.includes('ENTRY')) return '#10b981';
  if (a.includes('SELL') || a.includes('EXIT') || a.includes('STOP')) return '#ef4444';
  return '#9498a4';
};

export const AgentActivity: React.FC = () => {
  const {
    agentEvents, runtimeStatus, position, preflight, dataStatus,
    startPaperTrading, pauseTrading, emergencyStop,
  } = useBot();

  const preflightFails = preflight?.checks.filter(c => c.status === 'fail') ?? [];
  const canStart = preflight?.ready ?? false;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', color: '#e2e4e8' }}>
      {/* Status strip */}
      <div style={{
        backgroundColor: '#0d0e12', border: '1px solid #22242a', borderRadius: '8px',
        padding: '14px 16px', display: 'flex', flexDirection: 'column', gap: '10px',
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flexWrap: 'wrap' }}>
          <span style={{
            padding: '4px 10px', borderRadius: '4px', fontSize: '12px', fontWeight: 700,
            backgroundColor: runtimeStatus?.running ? 'rgba(16,185,129,0.12)' : 'rgba(148,152,164,0.12)',
            color: runtimeStatus?.running ? '#10b981' : '#9498a4',
            border: `1px solid ${runtimeStatus?.running ? 'rgba(16,185,129,0.4)' : 'rgba(148,152,164,0.3)'}`,
          }}>
            {stateLabel(runtimeStatus?.state)}
          </span>
          {position ? (
            <span style={{ fontSize: '12px', color: '#cbd5e1' }}>
              Entry {typeof position.entry === 'number' ? position.entry.toFixed(2) : '\u2014'} \u00b7
              Stop {typeof position.stop === 'number' ? position.stop.toFixed(2) : '\u2014'} \u00b7
              Target {typeof position.target === 'number' ? position.target.toFixed(2) : '\u2014'}
            </span>
          ) : (
            <span style={{ fontSize: '12px', color: '#676b78' }}>Flat \u2014 no open position</span>
          )}
        </div>

        {/* Controls */}
        <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
          <button onClick={startPaperTrading} disabled={!canStart} title={
            canStart ? 'Begin paper trading with verified market data'
              : preflightFails.map(c => `${c.label}: ${c.detail}`).join('; ') || 'Preflight checks not ready'
          } style={{
            padding: '8px 16px', borderRadius: '6px', fontWeight: 700, fontSize: '13px',
            border: 'none', cursor: canStart ? 'pointer' : 'not-allowed',
            backgroundColor: canStart ? '#10b981' : '#1e222b',
            color: canStart ? '#000' : '#676b78', opacity: canStart ? 1 : 0.7,
          }}>
            Start Paper Trading
          </button>
          <button onClick={pauseTrading} style={{
            padding: '8px 14px', borderRadius: '6px', fontWeight: 600, fontSize: '12px',
            border: '1px solid rgba(61, 126, 255,0.4)', cursor: 'pointer',
            backgroundColor: 'rgba(61, 126, 255,0.08)', color: 'var(--gold-primary)',
          }}>
            Pause new entries
          </button>
          <button onClick={emergencyStop} style={{
            padding: '8px 14px', borderRadius: '6px', fontWeight: 600, fontSize: '12px',
            border: '1px solid rgba(239,68,68,0.4)', cursor: 'pointer',
            backgroundColor: 'rgba(239,68,68,0.08)', color: '#ef4444',
          }}>
            Emergency stop
          </button>
        </div>

        {!canStart && preflightFails.length > 0 && (
          <div style={{ fontSize: '11px', color: '#fca5a5', lineHeight: 1.5 }}>
            {preflightFails.map(c => <div key={c.id}>\u26a0 {c.label}: {c.detail}</div>)}
          </div>
        )}
      </div>

      {/* Connection indicator */}
      {dataStatus.error && (
        <div style={{
          padding: '6px 12px', borderRadius: '6px', fontSize: '11px',
          border: '1px solid rgba(239,68,68,0.3)', backgroundColor: 'rgba(239,68,68,0.06)', color: '#fca5a5',
        }}>
          Reconnecting... {dataStatus.error}
        </div>
      )}

      {/* Activity feed */}
      <div style={{
        backgroundColor: '#0d0e12', border: '1px solid #22242a', borderRadius: '8px', padding: '12px 14px',
      }}>
        <div style={{ fontSize: '13px', fontWeight: 600, color: '#f8fafc', marginBottom: '10px' }}>
          Live Agent Activity
          <span style={{ fontSize: '11px', color: '#676b78', fontWeight: 400, marginLeft: '8px' }}>
            {agentEvents.length > 0 ? `${agentEvents.length} recent` : ''}
          </span>
        </div>

        {agentEvents.length === 0 ? (
          <div style={{
            padding: '24px', textAlign: 'center', color: '#9498a4', fontSize: '13px', lineHeight: 1.6,
          }}>
            <div>The agent has not evaluated a closed candle yet.</div>
            <div style={{ marginTop: '6px' }}>Set starting capital in Settings, press <strong style={{ color: '#10b981' }}>Start Paper Trading</strong>. Hermes researches, trades, and auto-promotes — no Promote click.</div>
            <div style={{ marginTop: '10px', fontSize: '11px', color: '#676b78' }}>
              Only the latest 30 events are shown to keep the page light. Full history is saved durably in the database (Decisions / Trades tabs).
            </div>
          </div>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '6px', maxHeight: '500px', overflowY: 'auto' }}>
            {agentEvents.map((evt) => (
              <div key={evt.event_id} style={{
                display: 'flex', gap: '8px', padding: '8px 10px', borderRadius: '6px',
                backgroundColor: '#121418', border: '1px solid #1c2028', alignItems: 'flex-start',
              }}>
                <span style={{ fontSize: '11px', color: '#676b78', fontFamily: 'monospace', whiteSpace: 'nowrap', minWidth: '60px' }}>
                  {new Date(evt.occurred_at).toLocaleTimeString()}
                </span>
                <span style={{
                  fontSize: '11px', fontWeight: 700, padding: '1px 6px', borderRadius: '3px',
                  backgroundColor: `${actionColor(evt.action)}18`, color: actionColor(evt.action),
                  textTransform: 'uppercase', whiteSpace: 'nowrap',
                }}>
                  {evt.action}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div style={{ fontSize: '12px', color: '#cbd5e1', lineHeight: 1.4 }}>{evt.reason}</div>
                  {evt.reason_codes.length > 0 && (
                    <div style={{ display: 'flex', gap: '4px', flexWrap: 'wrap', marginTop: '4px' }}>
                      {evt.reason_codes.map((code, i) => (
                        <span key={i} style={{
                          fontSize: '10px', padding: '1px 5px', borderRadius: '3px',
                          backgroundColor: 'rgba(96,165,250,0.1)', color: '#60a5fa',
                          border: '1px solid rgba(96,165,250,0.25)',
                        }}>{code}</span>
                      ))}
                    </div>
                  )}
                </div>
                {evt.audit_worthy && (
                  <span title="Audit-worthy event" style={{ fontSize: '10px', color: 'var(--gold-primary)' }}>\u2605</span>
                )}
              </div>
            ))}
          </div>
        )}

        {dataStatus.lastUpdatedAt && (
          <div style={{ fontSize: '10px', color: '#676b78', marginTop: '8px', textAlign: 'right' }}>
            Last snapshot: {new Date(dataStatus.lastUpdatedAt).toLocaleTimeString()}
          </div>
        )}
      </div>
    </div>
  );
};

